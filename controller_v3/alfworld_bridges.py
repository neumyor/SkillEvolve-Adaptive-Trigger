"""ALFWorld host bridges used by the paired Controller V3 runner.

ALFWorld is an interactive environment rather than a static QA table.  The
rollout therefore stays in SkillOpt's environment adapter, which is the shared
ALFWorld implementation already used by the repository.  The other three
hosts reuse their native proposal APIs where those APIs accept arbitrary
evaluation records; their metadata records the resulting equivalence scope.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
from typing import Any, Mapping

from .core import ControllerV3, UPDATE
from .validity import RolloutInfrastructureError
from .llm import call_json
from .native_bridges import BaseNativeBridge, _prepend


class _EpisodeUsage:
    """Small cumulative usage view expected by the benchmark episode runner."""

    def __init__(self) -> None:
        self.values = {"prompt_tokens": 0, "completion_tokens": 0, "api_calls": 0, "api_errors": 0}

    def add(self, usage: Mapping[str, Any] | None) -> None:
        usage = usage or {}
        self.values["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        self.values["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        self.values["api_calls"] += 1

    def to_dict(self) -> dict[str, int]:
        return dict(self.values)

    def delta_since(self, previous: Mapping[str, Any]) -> dict[str, int]:
        current = self.to_dict()
        return {key: current[key] - int(previous.get(key, 0) or 0) for key in current}


class _BenchmarkALFAgent:
    def __init__(self, llm, task_id: str) -> None:
        self.llm = llm
        self.task_id = task_id
        self.usage = _EpisodeUsage()
        self.last_finish_reason = None

    def respond(self, user_prompt: str) -> tuple[str, dict[str, Any]]:
        raw, usage = self.llm.respond(
            "You are an expert agent operating in the ALFRED Embodied Environment.",
            user_prompt,
            stage="alfworld_rollout",
            metadata={"task_id": self.task_id},
        )
        self.usage.add(usage)
        return raw, usage


class _StaticBenchmarkSkillProvider:
    def __init__(self, skill: str, skill_view_type) -> None:
        self.skill = skill
        self.skill_view_type = skill_view_type

    def view_for(self, _gamefile: str, _observation: str):
        return self.skill_view_type(prefix=self.skill.strip())


def _prepare_trace2skill_imports() -> None:
    """Make Trace2Skill's ``src`` package win over another host's package.

    EvoSkill and Trace2Skill both ship a top-level ``src`` package.  The
    paired runner imports multiple bridges in one process, so Python may have
    cached EvoSkill's package before the Trace2Skill bridge is constructed.
    Remove that cache and put Trace2Skill first on ``sys.path`` before using
    its native evolution API.
    """
    trace_root = Path(__file__).parents[1] / "repos/pulled/Trace2Skill"
    for module_name in list(sys.modules):
        if module_name == "src" or module_name.startswith("src."):
            del sys.modules[module_name]
    sys.path[:] = [p for p in sys.path if "repos/pulled/EvoSkill" not in p]
    trace_value = str(trace_root)
    if trace_value in sys.path:
        sys.path.remove(trace_value)
    sys.path.insert(0, trace_value)


def _usage_mapping(value: Any) -> dict[str, int] | None:
    """Normalize OpenAI's usage object for the shared token ledger."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if not isinstance(value, Mapping):
        value = {
            key: getattr(value, key, None)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
    if not any(value.get(key) is not None for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
        return None
    return {key: int(value.get(key, 0) or 0) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


class ALFWorldBaseBridge(BaseNativeBridge):
    domain = "alfworld"
    equivalence_scope = "shared SkillOpt ALFWorld rollout; host-specific update adapter"

    def __init__(self, llm, controller=None):
        if controller is None:
            controller = ControllerV3(
                min_window_tasks=int(os.environ.get("CONTROLLER_V3_ALF_MIN_WINDOW_TASKS", "2")),
                failure_rate_floor=float(os.environ.get("CONTROLLER_V3_ALF_FAILURE_RATE_FLOOR", "0.4")),
            )
        super().__init__(llm, controller)
        _prepend(Path(__file__).parents[1] / "repos/SkillOptETE")
        from skillopt.envs.alfworld.rollout import build_alfworld_env, run_alfworld_batch
        from skillopt.gradient.aggregate import merge_patches
        from skillopt.gradient.reflect import run_minibatch_reflect
        from skillopt.model import configure_openai_compatible, set_optimizer_backend, set_target_backend
        from skillopt.model.openai_compatible_backend import get_token_summary, reset_token_tracker
        from skillopt.optimizer.clip import rank_and_select
        from skillopt.optimizer.skill import apply_patch_with_report
        from skillopt.evaluation.gate import evaluate_gate

        self.build_env = build_alfworld_env
        self.run_batch = run_alfworld_batch
        self.reflect_native = run_minibatch_reflect
        self.merge_native = merge_patches
        self.select_native = rank_and_select
        self.apply_native = apply_patch_with_report
        self.gate_native = evaluate_gate
        self.get_token_summary = get_token_summary
        self.reset_token_tracker = reset_token_tracker
        self.max_steps = int(os.environ.get("CONTROLLER_V3_ALF_MAX_STEPS", "50"))
        self.max_completion_tokens = int(os.environ.get("CONTROLLER_V3_ALF_MAX_TOKENS", "512"))
        self.max_api_workers = int(os.environ.get("CONTROLLER_V3_ALF_API_WORKERS", "1"))
        # The vendor environment starts one OS process per env instance. Keep
        # this separate from API concurrency so a large evaluation batch does
        # not create hundreds of resident ALFWorld workers.
        self.env_batch_size = max(1, int(os.environ.get("CONTROLLER_V3_ALF_ENV_BATCH_SIZE", "1")))
        _prepend(Path(__file__).parents[1] / "benchmark/alfworld-eval/src")
        self.benchmark_env = True
        timeout_value = os.environ.get("CONTROLLER_V3_ALF_API_TIMEOUT", "120").strip()
        self.api_timeout = float(timeout_value) if timeout_value else None
        # A transient upstream 5xx can invalidate an otherwise healthy
        # environment batch.  Retry failed spawned episodes at the batch
        # boundary so infrastructure failures are not scored as model
        # failures.  The worker itself already retries individual requests.
        self.rollout_retries = max(
            0, int(os.environ.get("CONTROLLER_V3_ALF_ROLLOUT_RETRIES", "3"))
        )
        set_optimizer_backend("openai_compatible")
        set_target_backend("openai_compatible")
        configure_openai_compatible(
            base_url=llm.base_url,
            api_key=llm.api_key,
            model=llm.model,
            max_tokens=self.max_completion_tokens,
            timeout_seconds=120,
            enable_thinking=False,
        )

    @staticmethod
    def _eval_dataset(item: Mapping[str, Any]) -> tuple[str, bool]:
        gamefile = str(item.get("gamefile", ""))
        if "/valid_seen/" in gamefile:
            return "eval_in_distribution", False
        if "/valid_unseen/" in gamefile:
            return "eval_out_of_distribution", False
        return "train", True

    def _harvest_tracker(self, stage: str) -> bool:
        tracked = self._add_external_summary(self.get_token_summary(), f"alfworld:{stage}")
        if not tracked:
            self._mark_untracked(stage, "SkillOpt ALFWorld backend returned no token usage")
        return tracked

    def rollout(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        return self._rollout([item], skill)[0]

    def _rollout(self, items: list[Mapping[str, Any]], skill: str) -> list[dict[str, Any]]:
        env_batch_size = max(1, int(getattr(self, "env_batch_size", len(items))))
        if getattr(self, "benchmark_env", False):
            from .alfworld_worker import run_episode_job
            from .validity import require_valid_rows
            from dataclasses import asdict

            client = getattr(self.llm, "client", self.llm)
            config = {key: value for key, value in asdict(client).items() if key != "usage"}
            ledger = self.llm.ledger
            jobs = [(dict(item), skill, config, ledger.condition, ledger.method, getattr(self, "max_steps", 50)) for item in items]
            if not jobs:
                return []
            workers = min(env_batch_size, self.max_api_workers, len(items))
            # spawn gives every worker fresh parser/planner globals. Never fork
            # a threaded parent or pass an environment/client/ledger to workers.
            import hashlib
            rows = [None] * len(jobs)
            pending = []
            evidence_dir = getattr(self, "evidence_dir", None)
            call_index = getattr(self, "rollout_call_index", 0)
            self.rollout_call_index = call_index + 1
            def consume(index, key, payload):
                row, usage = payload
                # Cache records and tokens are committed together. On resume,
                # don't charge cached calls twice if tokens.json already has them.
                seen = any((r.metadata.get("episode_key") == key or r.metadata.get("cache_key") == key) for r in ledger.records)
                if not seen:
                    for record in usage["records"]:
                        record.setdefault("metadata", {})["episode_key"] = key
                    ledger.merge(usage)
                rows[index] = row
                if evidence_dir:
                    ledger.save(evidence_dir / "tokens.json")
            for index, job in enumerate(jobs):
                # Never write the API key into evidence or fingerprints.
                public_config = {k: v for k, v in config.items() if k not in {"api_key", "retry_backoff"}}
                # Compatibility with the original episode keys: transport policy
                # does not change task/model/skill identity.
                public_config["timeout"] = 120.0
                public_config["retries"] = 2
                key = hashlib.sha256(json.dumps([job[0], skill, public_config, call_index, job[-1], "spawn-v2"], sort_keys=True).encode()).hexdigest()
                cache = evidence_dir / "episodes" / (key + ".json") if evidence_dir else None
                if cache and cache.exists():
                    payload = json.loads(cache.read_text())
                    if payload[0].get("execution_ok"):
                        consume(index, key, payload)
                        continue
                pending.append((index, key, cache, job))
            # Retry only infrastructure failures.  A fresh spawned process is
            # used for each retry, which also refreshes the ALFWorld parser and
            # avoids retaining a broken worker or transient 5xx connection.
            attempt_jobs = pending
            for attempt in range(getattr(self, "rollout_retries", 3) + 1):
                if not attempt_jobs:
                    break
                failed_jobs = []
                with ProcessPoolExecutor(
                    max_workers=min(workers, len(attempt_jobs)),
                    mp_context=multiprocessing.get_context("spawn"),
                ) as pool:
                    futures = {
                        pool.submit(run_episode_job, job): (index, key, cache, job)
                        for index, key, cache, job in attempt_jobs
                    }
                    for future in as_completed(futures):
                        index, key, cache, job = futures[future]
                        payload = future.result()
                        if cache:
                            cache.parent.mkdir(exist_ok=True)
                            if cache.exists():
                                import uuid
                                archive = cache.parent.parent / "episode_failures"
                                archive.mkdir(exist_ok=True)
                                cache.replace(archive / (key + "-" + uuid.uuid4().hex + ".json"))
                            temporary = cache.with_suffix(".tmp")
                            temporary.write_text(json.dumps(payload, ensure_ascii=False))
                            temporary.replace(cache)
                        import uuid
                        consume(index, key + ":attempt:" + uuid.uuid4().hex, payload)
                        # Mark a stable cache identity only after a successful
                        # execution.  A failed attempt must not suppress token
                        # accounting for the successful retry that follows.
                        if payload[0].get("execution_ok"):
                            for record in ledger.records:
                                if record.metadata.get("episode_key", "").startswith(key + ":attempt:"):
                                    record.metadata["cache_key"] = key
                        if evidence_dir:
                            ledger.save(evidence_dir / "tokens.json")
                        if not payload[0].get("execution_ok"):
                            failed_jobs.append((index, key, cache, job))
                            if evidence_dir:
                                failure_dir = evidence_dir / "episode_failures"
                                failure_dir.mkdir(exist_ok=True)
                                (failure_dir / (key + "-" + uuid.uuid4().hex + ".json")).write_text(
                                    json.dumps(payload, ensure_ascii=False)
                                )
                attempt_jobs = failed_jobs
            if getattr(self, "defer_execution_errors", False):
                return rows
            require_valid_rows(rows, getattr(self, "evidence_dir", None))
            return rows
        if len(items) > env_batch_size:
            rows: list[dict[str, Any]] = []
            for offset in range(0, len(items), env_batch_size):
                rows.extend(self._rollout_chunk(items[offset : offset + env_batch_size], skill))
            return rows
        return self._rollout_chunk(items, skill)

    def _rollout_chunk(self, items: list[Mapping[str, Any]], skill: str) -> list[dict[str, Any]]:
        if not getattr(self, "benchmark_env", False):
            return self._rollout_native_chunk(items, skill)
        if not items:
            return []
        from alfworld_eval.env import AlfworldTextEnv, split_for_gamefile
        from alfworld_eval.unified.runner import run_unified_episode
        from alfworld_eval.unified.prompts import SkillView

        gamefiles = [str(item["gamefile"]) for item in items]
        split = split_for_gamefile(gamefiles[0])
        env = None
        rows: list[dict[str, Any]] = []
        try:
            env = AlfworldTextEnv(
                config_path=Path(__file__).parents[1] / "benchmark/alfworld-eval/configs/textworld.yaml",
                split=split,
                seed=42,
                gamefiles=gamefiles,
            )
            provider = _StaticBenchmarkSkillProvider(skill, SkillView)
            for item in items:
                agent = _BenchmarkALFAgent(self.llm, str(item.get("id", "")))
                episode = run_unified_episode(
                    env,
                    agent,
                    provider,
                    max_steps=getattr(self, "max_steps", 50),
                    record_trajectory=True,
                )
                rows.append({
                    "id": item.get("id", ""),
                    "hard": int(episode.success),
                    "soft": float(episode.success),
                    "score": float(episode.success),
                    "n_turns": episode.steps,
                    "fail_reason": "" if episode.success else episode.termination_reason,
                    "gamefile": episode.gamefile or item.get("gamefile", ""),
                    "task_type": episode.task_type,
                    "response": json.dumps(episode.trajectory, ensure_ascii=False),
                    "trajectory": json.dumps(episode.trajectory, ensure_ascii=False),
                    "success": bool(episode.success),
                    "execution_ok": True,
                    "api_failures": int(episode.usage.get("api_errors", 0) or 0),
                    "metadata": {"domain": "alfworld", "native_api": "benchmark.alfworld_eval.runner.run_unified_episode"},
                })
        except RolloutInfrastructureError:
            raise
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            import traceback
            trace = traceback.format_exc()
            rows = [{
                "id": item.get("id", ""), "hard": 0, "soft": 0.0, "score": 0.0,
                "n_turns": 0, "fail_reason": f"rollout error: {reason}",
                "gamefile": item.get("gamefile", ""), "task_type": item.get("task_type", "other"),
                "response": "", "trajectory": "", "success": False, "api_failures": 0,
                "execution_ok": False, "error_traceback": trace,
                "metadata": {"domain": "alfworld", "native_api": "benchmark.alfworld_eval.runner.run_unified_episode"},
            } for item in items]
        finally:
            if env is not None:
                env.close()
        return rows

    def _rollout_native_chunk(self, items: list[Mapping[str, Any]], skill: str) -> list[dict[str, Any]]:
        if not items:
            return []
        run_root = Path(tempfile.mkdtemp(prefix="controller-v3-alfworld-rollout-"))
        dataset, is_train = self._eval_dataset(items[0])
        gamefiles = [str(item["gamefile"]) for item in items]
        result_ids = [str(item.get("id", index)) for index, item in enumerate(items)]
        self.reset_token_tracker()
        env = None
        run_error = ""
        try:
            env = self.build_env(
                env_num=len(items),
                eval_dataset=dataset,
                seed=42,
                is_train=is_train,
                specific_gamefiles=gamefiles,
            )
            native_rows = self.run_batch(
                env,
                skill_content=skill,
                max_steps=self.max_steps,
                out_root=str(run_root),
                max_api_workers=min(self.max_api_workers, len(items)),
                max_completion_tokens=self.max_completion_tokens,
                result_ids=result_ids,
                api_timeout=self.api_timeout,
            )
        except RolloutInfrastructureError:
            raise
        except Exception as exc:  # preserve task-level evidence when the host fails
            native_rows = []
            run_error = f"{type(exc).__name__}: {exc}"
        finally:
            if env is not None:
                close = getattr(env, "close", None)
                if callable(close):
                    close()
        self._harvest_tracker("rollout")
        if run_error:
            native_rows = [
                {
                    "id": task_id,
                    "hard": 0,
                    "soft": 0.0,
                    "n_turns": 0,
                    "fail_reason": f"rollout error: {run_error}",
                    "agent_ok": False,
                    "api_failures": 1,
                    "gamefile": item.get("gamefile", ""),
                    "task_type": item.get("task_type", "other"),
                    "task_description": item.get("task_description", ""),
                }
                for task_id, item in zip(result_ids, items)
            ]
        missing_usage = sum(int(row.get("api_usage_missing", 0) or 0) for row in native_rows)
        if missing_usage:
            # A failed response can have incurred server-side tokens without
            # exposing usage to the client. Keep its quality evidence, but do
            # not claim that the cost ledger is complete.
            self._mark_untracked(
                "alfworld:rollout",
                f"{missing_usage} ALFWorld action request(s) lacked response usage",
            )
        rows: list[dict[str, Any]] = []
        for native in native_rows:
            task_id = str(native.get("id", ""))
            conversation = run_root / "predictions" / task_id / "conversation.json"
            trajectory = ""
            if conversation.exists():
                try:
                    trajectory = conversation.read_text(encoding="utf-8")
                except OSError:
                    trajectory = ""
            rows.append({
                **native,
                "score": float(native.get("soft", native.get("hard", 0.0)) or 0.0),
                "response": trajectory,
                "trajectory": trajectory,
                "success": bool(native.get("hard", 0)),
                "metadata": {
                    "domain": self.domain,
                    "rollout_dir": str(run_root),
                    "api_failures": int(native.get("api_failures", 0) or 0),
                    "rollout_error": run_error,
                },
            })
        return rows

    def evaluate_only(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        return self.rollout(item, skill)

    def evaluate_only_batch(self, items, skill: str):
        # The benchmark environment advances the supplied gamefile list one
        # episode at a time; _rollout keeps the environment process bounded.
        return self._rollout(list(items), skill)

    def _skillopt_update(self, rows: list[dict[str, Any]], items: list[Mapping[str, Any]], skill: str) -> dict[str, Any]:
        root = Path(tempfile.mkdtemp(prefix="controller-v3-alfworld-update-"))
        prediction_dir = root / "predictions"
        patches_dir = root / "patches"
        for row in rows:
            task_dir = prediction_dir / str(row["id"])
            task_dir.mkdir(parents=True, exist_ok=True)
            trajectory = row.get("trajectory", "")
            (task_dir / "conversation.json").write_text(str(trajectory), encoding="utf-8")
        self.reset_token_tracker()
        raw_patches = self.reflect_native(
            [dict(row, task_description=item.get("task_description", item.get("task_type", "alfworld")), task_type=item.get("task_type", "alfworld")) for row, item in zip(rows, items)],
            skill,
            str(prediction_dir),
            str(patches_dir),
            workers=1,
            failure_only=False,
            minibatch_size=max(1, len(rows)),
            edit_budget=2,
            random_seed=0,
        )
        self._harvest_tracker("reflect")
        failures, successes = [], []
        for raw in raw_patches:
            if not isinstance(raw, dict):
                continue
            patch = raw.get("patch", raw)
            if str(raw.get("source_type", patch.get("source_type", "failure"))) == "success":
                successes.append(patch)
            else:
                failures.append(patch)
        merged = self.merge_native(skill, failures, successes, batch_size=2, verbose=False, workers=1, update_mode="patch")
        ranked = self.select_native(skill, merged, max_edits=2, update_mode="patch")
        candidate, apply_report = self.apply_native(skill, ranked)
        candidate_rows = self._rollout(items, candidate)
        current = sum(float(row.get("score", 0.0)) for row in rows) / max(len(rows), 1)
        proposed = sum(float(row.get("score", 0.0)) for row in candidate_rows) / max(len(candidate_rows), 1)
        gate = self.gate_native(candidate, proposed, skill, current, skill, current, 0, 1, metric="hard")
        accepted = gate.action in {"accept", "accept_new_best"}
        result = {
            "accepted": accepted,
            "native_action": gate.action,
            "api": "SkillOpt ALFWorld reflect -> aggregate -> select -> patch -> gate",
            "n_raw_patches": len(raw_patches),
            "n_applied_edits": sum(str(x.get("status", "")).startswith("applied") for x in apply_report),
            "current_score": current,
            "candidate_score": proposed,
            "run_dir": str(root),
        }
        if accepted:
            result["candidate_skill"] = candidate
        return result

    def run_window(self, items: list[Mapping[str, Any]], skill: str) -> dict[str, Any]:
        rows = self._rollout(items, skill)
        decision, _ = self._decide(skill, [self._card(row) for row in rows], {"native": "SkillOpt ALFWorld rollout", "equivalence_scope": self.equivalence_scope})
        update: dict[str, Any] = {"accepted": False, "reason": "Controller WAIT; native update not entered"}
        if decision.action == UPDATE:
            try:
                update = self._run_update(rows, items, skill)
            except RolloutInfrastructureError:
                raise
            except Exception as exc:  # keep task evidence even when update fails
                self._raise_update_error(exc)
                update = {"accepted": False, "api": self.method, "reason": f"native update failed: {type(exc).__name__}: {exc}"}
            self._record_attempt(decision, update, f"{self.method}_alfworld_update")
        next_skill = update.get("candidate_skill", skill) if update.get("accepted") else skill
        return {
            "rows": rows,
            "decision": decision.action,
            "reason": decision.reason,
            "update": update,
            "equivalence_scope": self.equivalence_scope,
            "next_skill": next_skill,
        }

    def _run_update(self, rows, items, skill):
        return self._skillopt_update(rows, items, skill)


class ALFWorldSkillOptBridge(ALFWorldBaseBridge):
    method = "skillopt"
    equivalence_scope = "native SkillOpt ALFWorld reflect/update path"


class ALFWorldGEPABridge(ALFWorldBaseBridge):
    method = "gepa"
    equivalence_scope = "GEPA proposal API over native ALFWorld evaluator"

    def _run_update(self, rows, items, skill):
        _prepend(Path(__file__).parents[1] / "repos/pulled/GEPA/src")
        from gepa.optimize_anything import optimize_anything
        from gepa.oa.config import OptimizeAnythingConfig

        def evaluator(candidate, example, **kwargs):
            row = self.rollout(example, str(candidate))
            return float(row.get("score", 0.0)), {"row": row, "trajectory": row.get("trajectory", "")}

        def proposer(candidate, reflective_dataset, components_to_update, metadata=None):
            proposed, _, _ = call_json(self.llm, "Return JSON {\"candidate\": \"improved ALFWorld skill\"}.", json.dumps({"candidate": candidate, "evidence": reflective_dataset}, ensure_ascii=False), stage="gepa_proposal")
            text = str(proposed.get("candidate", "")).strip()
            if not text:
                raise ValueError("GEPA returned no structured candidate")
            names = list(components_to_update) if components_to_update else ["current_candidate"]
            return {name: text for name in names}

        config = OptimizeAnythingConfig(
            engine="gepa",
            # Reserve seed validation, reflection minibatch, candidate minibatch
            # and candidate validation; a seed-only budget never proposes.
            max_evals=2 * len(items) + 6,
            max_concurrency=1,
            output_dir=None,
            engine_config={"engine": {"max_candidate_proposals": 1, "parallel": False, "max_workers": 1}, "reflection": {"reflection_lm": None, "custom_candidate_proposer": proposer}},
        )
        result = optimize_anything(seed_candidate=skill, evaluator=evaluator, dataset=list(items), valset=list(items), objective="Improve ALFWorld success", config=config)
        before = sum(float(row.get("score", 0.0)) for row in rows) / max(len(rows), 1)
        after = float(result.best_score)
        accepted = after > before and str(result.best_candidate) != skill
        output = {"accepted": accepted, "api": "gepa.optimize_anything", "seed_score": before, "best_score": after, "equivalence_scope": self.equivalence_scope}
        if accepted:
            output["candidate_skill"] = str(result.best_candidate)
        return output


class ALFWorldEvoSkillBridge(ALFWorldBaseBridge):
    method = "evoskill"
    equivalence_scope = "EvoSkill proposal/generation semantics over native ALFWorld evaluator"

    def _run_update(self, rows, items, skill):
        proposal, _, _ = call_json(self.llm, "Return JSON {\"skill\": \"improved ALFWorld instructions\"}.", json.dumps({"skill": skill, "failures": [row.get("fail_reason", "") for row in rows if not row.get("hard")]}), stage="evoskill_proposal")
        candidate = str(proposal.get("skill", "")).strip()
        if not candidate:
            raise ValueError("EvoSkill returned no structured skill candidate")
        candidate_rows = self._rollout(items, candidate)
        before = sum(float(row.get("score", 0.0)) for row in rows) / max(len(rows), 1)
        after = sum(float(row.get("score", 0.0)) for row in candidate_rows) / max(len(candidate_rows), 1)
        accepted = after > before
        output = {"accepted": accepted, "api": "EvoSkill proposal -> native ALFWorld validation", "seed_score": before, "candidate_score": after, "equivalence_scope": self.equivalence_scope}
        if accepted:
            output["candidate_skill"] = candidate
        return output


class ALFWorldTrace2SkillBridge(ALFWorldBaseBridge):
    method = "trace2skill"
    equivalence_scope = "Trace2Skill evolution records over native ALFWorld trajectories"

    def _run_update(self, rows, items, skill):
        # Trace2Skill's evolution API consumes structured error records.  Keep
        # the real trajectories and task IDs; no SearchQA-specific fields are
        # fabricated here.
        _prepare_trace2skill_imports()
        from src.react_agent.models import OpenAIClient
        from skill_evolver.skill_evolving_agent import SkillEvolver

        work = Path(tempfile.mkdtemp(prefix="controller-v3-alfworld-trace2skill-"))
        skill_dir = work / "skills" / "alfworld"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill, encoding="utf-8")
        records = [{
            "instance_id": str(row["id"]),
            "error_type": "alfworld_failure",
            "error_description": row.get("fail_reason", "episode did not succeed"),
            "model_output": row.get("trajectory", ""),
            "expected_output": "successful episode",
            "items": [{"type": "failure_cause", "title": "ALFWorld episode failure", "description": row.get("fail_reason", "")}],
        } for row in rows if not row.get("hard")]
        if not records:
            return {"accepted": False, "api": "SkillEvolver.run_evolution", "reason": "no failure records", "equivalence_scope": self.equivalence_scope}
        trace_max_tokens = int(os.environ.get("CONTROLLER_V3_ALF_TRACE_MAX_TOKENS", str(max(256, self.max_completion_tokens))))
        # The ALFWorld model's reasoning output can consume a tiny smoke
        # budget before it emits Trace2Skill's JSON patch.  Keep the native
        # parser/evolver, but disable optional thinking and reserve enough
        # output for one structured patch response.
        ledger = getattr(self.llm, "ledger", None)

        class _TrackedTrace2SkillClient(OpenAIClient):
            def _send_request_with_retry(self, messages, config):
                response = super()._send_request_with_retry(messages, config)
                usage = _usage_mapping(getattr(response, "usage", None))
                if ledger is not None:
                    if usage is None:
                        ledger.mark_untracked("trace2skill_evolution", "Trace2Skill response did not expose usage")
                    else:
                        ledger.add(usage, stage="trace2skill_evolution")
                return response

        client = _TrackedTrace2SkillClient(
            model=self.llm.model,
            api_key=self.llm.api_key,
            base_url=self.llm.base_url,
            use_cache=False,
            timeout=120,
            generation_config={"temperature": 0, "extra_body": {"enable_thinking": False}},
        )
        result = SkillEvolver(
            client=client,
            skill_dir=skill_dir,
            batch_size=len(records),
            verbose=False,
            dry_run=False,
            max_tokens=trace_max_tokens,
            parse_failure_dir=work / "parse_failures",
        ).run_evolution(records, run_consolidation=False)
        output = {
            "accepted": bool(result.files_created or result.files_modified),
            "api": "SkillEvolver.run_evolution",
            "llm_calls": result.total_llm_calls,
            "trace_max_tokens": trace_max_tokens,
            "equivalence_scope": self.equivalence_scope,
        }
        if output["accepted"]:
            output["candidate_skill"] = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        return output


ALFWORLD_BRIDGE_TYPES = {
    "skillopt": ALFWorldSkillOptBridge,
    "gepa": ALFWorldGEPABridge,
    "evoskill": ALFWorldEvoSkillBridge,
    "trace2skill": ALFWorldTrace2SkillBridge,
}
