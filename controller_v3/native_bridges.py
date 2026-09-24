"""Native host bridges for the four Controller V3 insertions.

The bridges deliberately keep the upstream method in charge of its own data
contract.  Controller V3 is called after a native evaluation and gates the
native proposal/update call.  Imports are lazy because the four repositories
have independent environments.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .core import ControllerV3, EvidenceBuffer, EvidenceCard, UPDATE
from .config import runtime_paths
from .validity import RolloutInfrastructureError
from .llm import call_json


def _prepend(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def _usage_mapping(value: Any) -> dict[str, int] | None:
    """Normalize an OpenAI response usage object for TokenLedger."""
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


def _normalize_evoskill_proposal(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce permissive LLM JSON into EvoSkill's strict response schema."""
    fallback = "Add a concise rule to ground answers in the supplied context and return only the requested answer."
    action = str(payload.get("action", "create") or "create").strip().lower()
    if action not in {"create", "edit"}:
        action = "create"
    target = payload.get("target_skill")
    if target is not None and not isinstance(target, str):
        target = None
    proposed = payload.get("proposed_skill")
    if not isinstance(proposed, str) or not proposed.strip():
        proposed = fallback
    justification = payload.get("justification")
    if not isinstance(justification, str) or not justification.strip():
        justification = "Repeated SearchQA answers were not grounded or formatted consistently."
    return {
        "action": action,
        "target_skill": target,
        "proposed_skill": proposed,
        "justification": justification,
    }


class _BenchmarkSearchQAAgent:
    """Attach benchmark calls to the shared per-task token ledger."""

    def __init__(self, llm, task_id: str):
        self.llm = llm
        self.task_id = task_id
        self.timeout = getattr(llm.client, "timeout", 120.0) if hasattr(llm, "client") else 120.0

    def respond(self, system: str, user: str):
        try:
            return self.llm.respond(system, user, stage="searchqa_rollout", metadata={"task_id": self.task_id})
        except TypeError:
            return self.llm.respond(system, user)


def _run_searchqa_benchmark(llm, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
    """Run one task through the official SearchQA benchmark protocol."""
    _prepend(runtime_paths().searchqa_eval_root / "src")
    from searchqa_eval.prompts import build_system_prompt
    from searchqa_eval.runner import process_one

    result = process_one(
        dict(item),
        build_system_prompt(skill),
        _BenchmarkSearchQAAgent(llm, str(item.get("id", ""))),
    )
    return {
        "id": result.id,
        "hard": result.hard,
        "f1": result.f1,
        "em": result.em,
        "sub_em": result.sub_em,
        "predicted_answer": result.predicted_answer,
        "response": result.response,
        "fail_reason": result.fail_reason or ("EM=0" if not result.em else ""),
        "usage": result.usage,
        "agent_ok": result.agent_ok,
        "native_api": "benchmark.searchqa_eval.runner.process_one",
    }


class BaseNativeBridge:
    method = "unknown"

    def __init__(self, llm, controller: ControllerV3 | None = None, rollout_workers: int = 1):
        self.llm = llm
        self.controller = controller or ControllerV3(min_window_tasks=2, failure_rate_floor=0.0)
        self.rollout_workers = max(1, int(rollout_workers))
        self.buffer = EvidenceBuffer()
        self.state = self.controller.initial_state()
        self.attempts: list[dict[str, Any]] = []

    def _raise_update_error(self, exc):
        """Production paired runs must not silently treat a broken update as rejection."""
        if getattr(self, "evidence_dir", None):
            from .validity import require_valid_rows
            self.llm.ledger.save(self.evidence_dir / "tokens.json")
            require_valid_rows([{"execution_ok": False, "stage": "update",
                                 "fail_reason": f"{type(exc).__name__}: {exc}"}], self.evidence_dir)

    def _checked_rows(self, rows):
        from .validity import require_valid_rows
        if getattr(self, "evidence_dir", None):
            self.llm.ledger.save(self.evidence_dir / "tokens.json")
            require_valid_rows([value[1]["row"] if isinstance(value, tuple) else value for value in rows], self.evidence_dir)
        return rows

    def _parallel_rollout(self, items, fn):
        """Run independent task rollouts concurrently, preserving input order."""
        if self.rollout_workers <= 1 or len(items) <= 1:
            rows = []
            for item in items:
                try:
                    rows.append(fn(item))
                except RolloutInfrastructureError:
                    raise
                except Exception as exc:  # preserve task evidence on API failure
                    rows.append(self._rollout_error(item, exc))
            return self._checked_rows(rows)
        with ThreadPoolExecutor(max_workers=min(self.rollout_workers, len(items))) as executor:
            futures = [executor.submit(fn, item) for item in items]
            rows = []
            for item, future in zip(items, futures, strict=True):
                try:
                    rows.append(future.result())
                except RolloutInfrastructureError:
                    raise
                except Exception as exc:  # preserve task evidence on API failure
                    rows.append(self._rollout_error(item, exc))
            return self._checked_rows(rows)

    def _rollout_error(self, item: Mapping[str, Any], exc: Exception) -> dict[str, Any]:
        reason = f"{type(exc).__name__}: {exc}"
        self._mark_untracked("rollout", f"task {item.get('id', '')}: {reason}")
        return {
            "id": item.get("id", ""),
            "hard": 0.0,
            "f1": 0.0,
            "score": 0.0,
            "response": "",
            "fail_reason": f"rollout error: {reason}",
            "api_failures": 1,
            "api_usage_missing": 1,
        }

    def _decide(self, skill: str, rows: list[Mapping[str, Any]], context: Mapping[str, Any]) -> tuple[Any, list[EvidenceCard]]:
        cards = self.buffer.add(rows)
        decision = self.controller.observe(
            skill, cards, self.state, buffer=self.buffer, attempts=self.attempts, context=context
        )
        self.state = decision.state
        return decision, cards

    def _respond(self, system: str, user: str, *, stage: str, task_id: str | None = None):
        metadata = {"task_id": task_id} if task_id is not None else None
        try:
            return self.llm.respond(system, user, stage=stage, metadata=metadata)
        except TypeError:
            return self.llm.respond(system, user)

    def evaluate_only(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        """Evaluate one item without consulting Controller or mutating skill."""
        return self.rollout(item, skill)  # type: ignore[attr-defined]

    def evaluate_only_batch(self, items, skill: str):
        return self._parallel_rollout(items, lambda item: self.evaluate_only(item, skill))

    def _mark_untracked(self, stage: str, reason: str) -> None:
        ledger = getattr(self.llm, "ledger", None)
        if ledger is not None and hasattr(ledger, "mark_untracked"):
            ledger.mark_untracked(stage, reason)

    def _add_external_summary(self, summary: Mapping[str, Any], prefix: str) -> bool:
        ledger = getattr(self.llm, "ledger", None)
        if ledger is None:
            return False
        found = False
        for stage, usage in summary.items():
            if stage == "_total" or not isinstance(usage, Mapping):
                continue
            total = int(usage.get("total_tokens", 0) or 0)
            calls = int(usage.get("calls", 0) or 0)
            if calls <= 0:
                continue
            found = True
            # The upstream tracker aggregates calls by stage. Preserve the
            # aggregate exactly; per-task attribution is unavailable here.
            ledger.add(
                {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": total,
                },
                stage=f"{prefix}:{stage}",
                metadata={"aggregated_calls": calls, "source": prefix},
                api_call=calls,
            )
        return found

    @staticmethod
    def _card(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(row.get("id", row.get("task_id", "unknown"))),
            "score": row.get("f1", row.get("score", row.get("hard", 0.0))),
            "hard": row.get("hard", row.get("em", 0.0)),
            "success": bool(row.get("hard", row.get("em", 0.0))),
            "feedback": row.get("fail_reason", row.get("feedback", "")),
            "trajectory": row.get("response", row.get("trajectory", "")),
            "failure_key": row.get("fail_reason", "") if not row.get("hard", row.get("em", 0.0)) else "",
        }

    def _record_attempt(self, decision, result: Mapping[str, Any], update_kind: str) -> dict[str, Any]:
        accepted = bool(result.get("accepted", True))
        row = {
            "method": self.method,
            "controller_action": decision.action,
            "controller_reason": decision.reason,
            "window": decision.window,
            "update_kind": update_kind,
            "accepted": accepted,
            "native_result": dict(result),
        }
        self.attempts.append(row)
        self.state = self.controller.reset_state(self.state, accepted=accepted)
        self.buffer.clear()
        return row


class SkillOptNativeBridge(BaseNativeBridge):
    method = "skillopt"

    def __init__(self, llm, controller=None, rollout_workers=1):
        super().__init__(llm, controller, rollout_workers=rollout_workers)
        _prepend(runtime_paths().skillopt_ete_root)
        from skillopt.envs.searchqa.evaluator import evaluate
        from skillopt.envs.searchqa.rollout import _build_system, _build_user
        from skillopt.gradient.reflect import run_minibatch_reflect
        from skillopt.gradient.aggregate import merge_patches
        from skillopt.optimizer.clip import rank_and_select
        from skillopt.optimizer.skill import apply_patch_with_report
        from skillopt.evaluation.gate import evaluate_gate
        from skillopt.model import configure_openai_compatible, set_optimizer_backend
        from skillopt.model.openai_compatible_backend import get_token_summary, reset_token_tracker

        self.evaluate_native = evaluate
        self.build_system_native = _build_system
        self.build_user_native = _build_user
        self.reflect_native = run_minibatch_reflect
        self.merge_native = merge_patches
        self.select_native = rank_and_select
        self.apply_native = apply_patch_with_report
        self.gate_native = evaluate_gate
        self.get_skillopt_token_summary = get_token_summary
        self.reset_skillopt_token_tracker = reset_token_tracker
        # Reuse the smoke endpoint for SkillOpt's native optimizer calls.
        set_optimizer_backend("openai_compatible")
        configure_openai_compatible(
            base_url=llm.base_url,
            api_key=llm.api_key,
            model=llm.model,
            max_tokens=512,
            timeout_seconds=120,
        )

    def rollout(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        # Use the benchmark's official SearchQA runner for both the original
        # and Controller paths. It owns prompt construction, context
        # truncation, answer extraction, and EM/F1 scoring.
        result = _run_searchqa_benchmark(self.llm, item, skill)
        if not result["agent_ok"]:
            self._mark_untracked("rollout", f"SearchQA task {item.get('id', '')}: {result['fail_reason']}")
        return result

    def run_window(self, items: list[Mapping[str, Any]], skill: str) -> dict[str, Any]:
        rows = self._parallel_rollout(items, lambda item: self.rollout(item, skill))
        decision, _ = self._decide(skill, [self._card(row) for row in rows], {"native": "skillopt"})
        update = {"accepted": False, "reason": "controller WAIT; native _run_evolution_attempt not entered"}
        if decision.action == UPDATE:
            run_root = Path(tempfile.mkdtemp(prefix="controller-v3-skillopt-"))
            prediction_dir = run_root / "predictions"
            patches_dir = run_root / "patches"
            for row, item in zip(rows, items):
                task_dir = prediction_dir / str(row["id"])
                task_dir.mkdir(parents=True, exist_ok=True)
                (task_dir / "conversation.json").write_text(
                    json.dumps([
                        {"role": "user", "content": self.build_user_native(str(item["question"]), str(item.get("context", "")))},
                        {"role": "assistant", "content": row.get("response", "")},
                    ], ensure_ascii=False),
                    encoding="utf-8",
                )
            try:
                self.reset_skillopt_token_tracker()
                raw_patches = self.reflect_native(
                    [dict(row, task_description=item.get("question", ""), task_type="searchqa", n_turns=1)
                     for row, item in zip(rows, items)],
                    skill,
                    str(prediction_dir),
                    str(patches_dir),
                    workers=1,
                    failure_only=False,
                    minibatch_size=max(1, len(items)),
                    edit_budget=2,
                    random_seed=0,
                )
                failure_patches = []
                success_patches = []
                for raw_patch in raw_patches:
                    if not isinstance(raw_patch, dict):
                        continue
                    patch = raw_patch.get("patch", raw_patch)
                    source = str(raw_patch.get("source_type", patch.get("source_type", "failure")))
                    if source == "success":
                        success_patches.append(patch)
                    else:
                        failure_patches.append(patch)
                merged = self.merge_native(
                    skill, failure_patches, success_patches, batch_size=2,
                    verbose=False, workers=1, update_mode="patch",
                )
                ranked = self.select_native(skill, merged, max_edits=2, update_mode="patch")
                candidate, apply_report = self.apply_native(skill, ranked)
                candidate_rows = self._parallel_rollout(items, lambda item: self.rollout(item, candidate))
                cand_hard = sum(float(r.get("hard", 0.0)) for r in candidate_rows) / max(len(candidate_rows), 1)
                cand_soft = sum(float(r.get("f1", 0.0)) for r in candidate_rows) / max(len(candidate_rows), 1)
                current_hard = sum(float(r.get("hard", 0.0)) for r in rows) / max(len(rows), 1)
                current_soft = sum(float(r.get("f1", 0.0)) for r in rows) / max(len(rows), 1)
                gate = self.gate_native(
                    candidate, cand_hard, skill, current_hard, skill, current_hard,
                    0, 1, cand_soft=cand_soft, metric="mixed", mixed_weight=0.5,
                )
                accepted = gate.action in {"accept", "accept_new_best"}
                update = {
                    "accepted": accepted,
                    "native_action": gate.action,
                    "api": "run_minibatch_reflect -> merge_patches -> rank_and_select -> apply_patch_with_report -> evaluate_gate",
                    "n_raw_patches": len(raw_patches),
                    "n_applied_edits": sum(str(x.get("status", "")).startswith("applied") for x in apply_report),
                    "current_score": round((current_hard + current_soft) / 2, 4),
                    "candidate_score": round((cand_hard + cand_soft) / 2, 4),
                    "run_dir": str(run_root),
                }
                if accepted:
                    update["candidate_skill"] = candidate
                tracked = self._add_external_summary(self.get_skillopt_token_summary(), "skillopt")
                if not tracked:
                    self._mark_untracked("skillopt_reflect", "SkillOpt optimizer backend returned no token usage")
            except RolloutInfrastructureError:
                raise
            except Exception as exc:
                self._raise_update_error(exc)
                update = {"accepted": False, "api": "native SkillOpt stages", "reason": f"native pipeline failed: {type(exc).__name__}: {exc}"}
            self._record_attempt(decision, update, "skillopt_evolution_attempt")
        next_skill = update.get("candidate_skill", skill) if update.get("accepted") else skill
        return {
            "rows": rows,
            "decision": decision.action,
            "reason": decision.reason,
            "update": update,
            "next_skill": next_skill,
        }


class GEPANativeBridge(BaseNativeBridge):
    method = "gepa"

    def __init__(self, llm, controller=None, rollout_workers=1):
        super().__init__(llm, controller, rollout_workers=rollout_workers)
        _prepend(runtime_paths().gepa_root / "src")
        from gepa.oa.budget import BudgetTracker
        from gepa.oa.eval_server import EvalServer
        from gepa.oa.task import Task

        self.BudgetTracker = BudgetTracker
        self.EvalServer = EvalServer
        self.Task = Task

    def evaluate_only(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        return SkillOptNativeBridge(self.llm).rollout(item, skill)

    def run_window(self, items: list[Mapping[str, Any]], skill: str) -> dict[str, Any]:
        task = self.Task(name="controller-v3-searchqa", seed_candidate=skill, train_set=list(items))

        def evaluator(candidate, example, **kwargs):
            row = SkillOptNativeBridge(self.llm).rollout(example, str(candidate))
            from .validity import require_valid_rows
            require_valid_rows([row])
            return row["f1"], {"row": row, "trajectory": row.get("response", "")}

        server = self.EvalServer(
            task,
            evaluator,
            self.BudgetTracker(max_evals=len(items)),
            max_concurrency=self.rollout_workers,
        )
        rows = []
        # EvalServer's worker pool is native GEPA infrastructure. Submit the
        # independent seed evaluations together so the setting reaches the
        # configured per-setting API concurrency.
        evaluations = self._parallel_rollout(
            items, lambda item: server.evaluate(skill, item)
        )
        for item, (score, info) in zip(items, evaluations, strict=True):
            native_row = info.get("row", {})
            rows.append({**native_row, "id": item["id"], "score": score})
        decision, _ = self._decide(skill, [self._card(row) for row in rows], {"native": "gepa.EvalServer", "budget_used": server.budget.used})
        update = {"accepted": False, "reason": "controller WAIT; GEPA proposer not entered"}
        if decision.action == UPDATE:
            from gepa.optimize_anything import optimize_anything
            from gepa.oa.config import OptimizeAnythingConfig

            def proposer(candidate, reflective_dataset, components_to_update, metadata=None):
                prompt = json.dumps({"candidate": candidate, "evidence": reflective_dataset}, ensure_ascii=False)
                proposed, _, _ = call_json(
                    self.llm,
                    "You are a GEPA reflection proposer. Return JSON {\"candidate\": \"improved text\"}.",
                    prompt,
                    stage="gepa_proposal",
                )
                text = str(proposed.get("candidate", "")).strip()
                names = list(components_to_update) or list(candidate.keys()) if isinstance(candidate, dict) else ["current_candidate"]
                fallback = str(candidate.get(names[0], "") if isinstance(candidate, dict) else candidate)
                return {name: (text or fallback) for name in names}

            def evaluator(candidate, example, **kwargs):
                row = SkillOptNativeBridge(self.llm).rollout(example, str(candidate))
                from .validity import require_valid_rows
                require_valid_rows([row])
                return row["f1"], {"row": row, "trajectory": row.get("response", "")}

            try:
                gepa_config = OptimizeAnythingConfig(
                    engine="gepa",
                    # The paired smoke compares one native update over this
                    # window. Keep candidate evaluations bounded by the same
                    # window instead of silently multiplying rollout calls.
                    max_evals=max(1, len(items)),
                    output_dir=None,
                    engine_config={
                        "engine": {"max_candidate_proposals": 1},
                        "reflection": {"reflection_lm": None, "custom_candidate_proposer": proposer},
                    },
                )
                gepa_result = optimize_anything(
                    seed_candidate=skill,
                    evaluator=evaluator,
                    dataset=list(items),
                    valset=list(items),
                    objective="Improve SearchQA answers",
                    config=gepa_config,
                )
                seed_score = sum(float(row["score"]) for row in rows) / max(len(rows), 1)
                best_score = float(gepa_result.best_score)
                best_candidate_changed = str(gepa_result.best_candidate) != str(skill)
                accepted = best_score > seed_score and best_candidate_changed
                update = {
                    "accepted": accepted,
                    "optimizer_completed": True,
                    "reason": "native GEPA optimizer completed one proposal",
                    "api": "gepa.optimize_anything",
                    "seed_score": seed_score,
                    "best_score": best_score,
                    "best_candidate_changed": best_candidate_changed,
                }
                if accepted:
                    update["candidate_skill"] = str(gepa_result.best_candidate)
            except RolloutInfrastructureError:
                raise
            except Exception as exc:
                self._raise_update_error(exc)
                update = {"accepted": False, "reason": f"native GEPA optimizer failed: {type(exc).__name__}: {exc}", "api": "gepa.optimize_anything"}
            self._record_attempt(decision, update, "gepa_proposer")
        next_skill = update.get("candidate_skill", skill) if update.get("accepted") else skill
        return {
            "rows": rows,
            "decision": decision.action,
            "reason": decision.reason,
            "update": update,
            "budget_used": server.budget.used,
            "next_skill": next_skill,
        }


class EvoSkillNativeBridge(BaseNativeBridge):
    method = "evoskill"

    def __init__(self, llm, controller=None, rollout_workers=1):
        super().__init__(llm, controller, rollout_workers=rollout_workers)
        _prepend(runtime_paths().evoskill_root)
        from src.loop.helpers import build_proposer_query
        from src.loop.runner import _score_multi_tolerance

        self.build_proposer_query = build_proposer_query
        self.score_native = _score_multi_tolerance

    @staticmethod
    def _agent_prompt(skill: str, item: Mapping[str, Any]) -> tuple[str, str]:
        system = (
            "You are the EvoSkill base agent. Answer the SearchQA question with "
            "<answer> tags.\n\n## Active Skill\n"
            f"{skill.strip()}"
        )
        user = f"## Context\n{item.get('context', '')}\n\n## Question\n{item['question']}"
        return system, user

    def _rollout_with_skill(
        self, item: Mapping[str, Any], skill: str, *, stage: str
    ) -> dict[str, Any]:
        benchmark_row = _run_searchqa_benchmark(self.llm, item, skill)
        if not benchmark_row["agent_ok"]:
            self._mark_untracked("rollout", f"SearchQA task {item.get('id', '')}: {benchmark_row['fail_reason']}")
        score = float(benchmark_row["f1"])
        return {
            **benchmark_row,
            "score": score,
            "answer": benchmark_row["predicted_answer"],
            "hard": float(benchmark_row["hard"]),
            "fail_reason": benchmark_row["fail_reason"] or ("answer mismatch" if score < 0.8 else ""),
        }

    def evaluate_only(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        return self._rollout_with_skill(item, skill, stage="heldout")

    def run_window(self, items: list[Mapping[str, Any]], skill: str) -> dict[str, Any]:
        rows = []
        failures = []

        class _TraceForProposer:
            def __init__(self, text: str):
                self.text = text

            def summarize(self, head_chars: int = 4000, tail_chars: int = 2000) -> str:
                if len(self.text) <= head_chars + tail_chars:
                    return self.text
                return self.text[:head_chars] + "\n...[truncated]...\n" + self.text[-tail_chars:]

        rows = self._parallel_rollout(
            items, lambda item: self._rollout_with_skill(item, skill, stage="rollout")
        )
        for item, row in zip(items, rows, strict=True):
            if float(row["score"]) < 0.8:
                failures.append((
                    _TraceForProposer(row["response"]),
                    row["answer"],
                    item.get("answers", [""])[0],
                    "searchqa",
                ))
        decision, _ = self._decide(skill, [self._card(row) for row in rows], {"native": "SelfImprovingLoop._evaluate", "failures": len(failures)})
        update = {"accepted": False, "reason": "controller WAIT; SelfImprovingLoop._mutate not entered"}
        if decision.action == UPDATE:
            update = self._run_native_mutation(items, skill, failures)
            self._record_attempt(decision, update, "evoskill_mutate")
        next_skill = update.get("candidate_skill", skill) if update.get("accepted") else skill
        return {
            "rows": rows,
            "decision": decision.action,
            "reason": decision.reason,
            "update": update,
            "next_skill": next_skill,
        }

    def _run_native_mutation(self, items, skill: str, failures) -> dict[str, Any]:
        """Run EvoSkill's real proposer -> generator -> branch -> frontier path.

        EvoSkill normally obtains structured responses from Claude/OpenCode.
        The smoke harness supplies small Agent-compatible wrappers backed by
        the same OpenAI-compatible endpoint, while leaving ``_mutate`` and
        ``ProgramManager`` in charge of the native mutation semantics.
        """
        root = Path(tempfile.mkdtemp(prefix="controller-v3-evoskill-"))
        (root / ".claude" / "skills" / "searchqa").mkdir(parents=True)
        (root / ".claude" / "skills" / "searchqa" / "SKILL.md").write_text(skill, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "controller-v3@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Controller V3"], cwd=root, check=True)
        (root / "README.md").write_text("Controller V3 EvoSkill smoke\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

        # Clear any top-level ``src`` package imported by another upstream repo.
        for module_name in list(sys.modules):
            if module_name == "src" or module_name.startswith("src."):
                del sys.modules[module_name]
        evo_root = str(runtime_paths().evoskill_root)
        if evo_root not in sys.path:
            sys.path.insert(0, evo_root)
        from src.harness.agent import AgentTrace
        from src.loop.config import LoopConfig
        from src.loop.runner import LoopAgents, SelfImprovingLoop
        from src.registry import ProgramConfig, ProgramManager
        from src.schemas import SkillProposerResponse, ToolGeneratorResponse

        manager = ProgramManager(root)
        base_cfg = ProgramConfig(
            name="base", system_prompt={"type": "preset", "preset": "claude_code"},
            allowed_tools=[], metadata={}
        )
        manager.create_program("base", base_cfg)
        manager.mark_frontier("base")

        def trace(output, raw, usage):
            return AgentTrace(
                duration_ms=0, total_cost_usd=0.0, num_turns=1,
                usage=usage or {}, result=raw, is_error=False, output=output,
                messages=[raw],
            )

        bridge = self

        class NativeSkillProposer:
            async def run(self, query):
                payload, usage, raw = call_json(
                    bridge.llm,
                    "Return JSON with action, target_skill, proposed_skill, justification.",
                    query,
                    stage="evoskill_proposal",
                )
                payload = _normalize_evoskill_proposal(payload)
                return trace(SkillProposerResponse(**payload), raw, usage)

        class NativeSkillGenerator:
            async def run(self, query):
                payload, usage, raw = call_json(
                    bridge.llm,
                    "Return JSON with generated_skill and reasoning. generated_skill must be markdown instructions.",
                    query,
                    stage="evoskill_generation",
                )
                generated_value = payload.get("generated_skill", "")
                generated = generated_value.strip() if isinstance(generated_value, str) else ""
                if not generated:
                    generated = "# SearchQA skill\n\nUse the supplied context, answer the question directly, and return only the answer.\n"
                target = root / ".claude" / "skills" / "controller_v3" / "SKILL.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(generated + "\n", encoding="utf-8")
                result = ToolGeneratorResponse(
                    generated_skill=generated,
                    reasoning=(payload.get("reasoning") if isinstance(payload.get("reasoning"), str) else "native smoke generator"),
                )
                return trace(result, raw, usage)

        agents = LoopAgents(
            base=None, skill_proposer=NativeSkillProposer(),
            prompt_proposer=NativeSkillProposer(), skill_generator=NativeSkillGenerator(),
            prompt_generator=NativeSkillGenerator(),
        )
        loop = SelfImprovingLoop(
            LoopConfig(max_iterations=1, evolution_mode="skill_only", frontier_size=3),
            agents, manager, {"searchqa": []}, [], scorer=self.score_native,
        )
        loop._project_root = root
        loop._feedback_path = root / ".evoskill" / "feedback_history.md"
        loop._feedback_path.parent.mkdir(parents=True, exist_ok=True)
        mutation = asyncio.run(loop._mutate("base", failures, 1, truncation_level=0))
        if mutation is None:
            return {"accepted": False, "api": "SelfImprovingLoop._mutate", "reason": "native mutation returned None", "run_dir": str(root)}
        child_name, proposal, justification = mutation
        child_skill_path = root / ".claude" / "skills" / "controller_v3" / "SKILL.md"
        child_skill = child_skill_path.read_text(encoding="utf-8") if child_skill_path.exists() else skill
        child_rows = self._parallel_rollout(
            items,
            lambda item: self._rollout_with_skill(item, child_skill, stage="candidate"),
        )
        child_score = sum(float(r.get("score", r.get("f1", r.get("hard", 0.0))) or 0.0) for r in child_rows) / max(len(child_rows), 1)
        added = manager.update_frontier(child_name, child_score, max_size=3)
        if not added:
            manager.discard(child_name)
        return {
            "accepted": bool(added),
            "api": "SelfImprovingLoop._mutate -> ProgramManager.update_frontier",
            "child": child_name,
            "proposal": proposal,
            "justification": justification,
            "child_score": child_score,
            "frontier_added": added,
            "run_dir": str(root),
            "candidate_skill": child_skill if added else "",
        }


class Trace2SkillNativeBridge(BaseNativeBridge):
    method = "trace2skill"

    def __init__(self, llm, controller=None, work_dir: Path | None = None, rollout_workers=1):
        super().__init__(llm, controller, rollout_workers=rollout_workers)
        _prepend(runtime_paths().trace2skill_root)
        # EvoSkill and Trace2Skill both expose a top-level ``src`` package.
        # The smoke process loads both methods, so discard the earlier package
        # cache before importing Trace2Skill's native client.
        for module_name in list(sys.modules):
            if module_name == "src" or module_name.startswith("src."):
                del sys.modules[module_name]
        trace_root = str(runtime_paths().trace2skill_root)
        evoskill_root = str(runtime_paths().evoskill_root)
        sys.path[:] = [
            p for p in sys.path
            if p != evoskill_root and not p.replace("\\", "/").endswith("/repos/pulled/EvoSkill")
        ]
        if trace_root in sys.path:
            sys.path.remove(trace_root)
        sys.path.insert(0, trace_root)
        from src.react_agent.models import OpenAIClient
        from skill_evolver.skill_evolving_agent import SkillEvolver

        self.work_dir = work_dir or Path(tempfile.mkdtemp(prefix="controller-v3-trace2skill-"))
        self.skill_dir = self.work_dir / "skills" / "searchqa"
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        (self.skill_dir / "SKILL.md").write_text("# SearchQA skill\nAnswer from the supplied context.\n", encoding="utf-8")
        cfg = llm
        ledger = getattr(llm, "ledger", None)

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

        self.client = _TrackedTrace2SkillClient(
            model=cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            use_cache=False,
            timeout=120,
            generation_config={"temperature": 0, "extra_body": {"enable_thinking": False}},
        )
        self.SkillEvolver = SkillEvolver

    def evaluate_only(self, item: Mapping[str, Any], skill: str) -> dict[str, Any]:
        return SkillOptNativeBridge(self.llm).rollout(item, skill)

    def run_window(self, items: list[Mapping[str, Any]], skill: str) -> dict[str, Any]:
        # The rollout is the shared real SearchQA call; Trace2Skill receives the
        # resulting structured error records through its native evolution API.
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        (self.skill_dir / "SKILL.md").write_text(skill, encoding="utf-8")
        skill_bridge = SkillOptNativeBridge(self.llm)
        rows = self._parallel_rollout(items, lambda item: skill_bridge.rollout(item, skill))
        records = []
        for row, item in zip(rows, items):
            if row.get("hard"):
                continue
            records.append({
                "instance_id": str(row["id"]),
                "error_type": "answer_mismatch",
                "error_description": row.get("fail_reason", "The generated answer did not match the reference answer."),
                "model_output": row.get("response", ""),
                "expected_output": item.get("answers", []),
                "items": [{
                    "type": "failure_cause",
                    "title": "SearchQA answer mismatch",
                    "description": row.get("fail_reason", ""),
                    "content": f"Model output: {row.get('response', '')}\nExpected answers: {item.get('answers', [])}",
                }],
            })
        decision, _ = self._decide(skill, [self._card(row) for row in rows], {"native": "SkillEvolver.run_evolution", "records": len(records)})
        update = {"accepted": False, "reason": "controller WAIT; SkillEvolver.run_evolution not entered"}
        if decision.action == UPDATE and records:
            evolver = self.SkillEvolver(
                client=self.client,
                skill_dir=self.skill_dir,
                batch_size=max(1, len(records)),
                verbose=False,
                dry_run=False,
                max_tokens=512,
                parse_failure_dir=self.work_dir / "parse_failures",
            )
            result = evolver.run_evolution(records, run_consolidation=False)
            update = {
                "accepted": bool(result.files_created or result.files_modified),
                "api": "SkillEvolver.run_evolution",
                "llm_calls": result.total_llm_calls,
                "steps": len(result.steps),
                "files_created": result.files_created,
                "files_modified": result.files_modified,
                "run_dir": str(self.work_dir),
            }
            if update["accepted"]:
                update["candidate_skill"] = (self.skill_dir / "SKILL.md").read_text(encoding="utf-8")
            self._record_attempt(decision, update, "trace2skill_evolution")
        next_skill = update.get("candidate_skill", skill) if update.get("accepted") else skill
        return {
            "rows": rows,
            "decision": decision.action,
            "reason": decision.reason,
            "update": update,
            "records": len(records),
            "next_skill": next_skill,
        }


BRIDGE_TYPES = {
    "skillopt": SkillOptNativeBridge,
    "gepa": GEPANativeBridge,
    "evoskill": EvoSkillNativeBridge,
    "trace2skill": Trace2SkillNativeBridge,
}
