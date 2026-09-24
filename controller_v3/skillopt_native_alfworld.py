"""Run the SkillOpt trainer with official ALFWorld episodes and a V3 timing hook."""

import argparse
import fcntl
import inspect
import json
import os
from pathlib import Path
import sys
import types

from .config import runtime_paths

ROOT = Path(__file__).resolve().parents[1]

VENDOR = runtime_paths().skillopt_ete_root


def install_policy(trainer_module):
    from skillopt.evolution_controller import EvolutionDecision, EvolutionPolicy
    from controller_v3.core import ControllerV3, EvidenceBuffer

    class V3Policy(EvolutionPolicy):
        name = "controller_v3"

        def __init__(self):
            self.controller = ControllerV3(min_window_tasks=2, failure_rate_floor=0.4)

        def initial_state(self):
            return self.controller.initial_state()

        def reset_state(self, outcome="accepted", trigger_state=None):
            return self.controller.reset_state(
                trigger_state or self.initial_state(), accepted=outcome == "accepted"
            )

        def observe(
            self,
            skill,
            new_results,
            evidence_state,
            *,
            epoch_end=False,
            rollout_dir=None,
            context=None,
        ):
            context = context or {}
            buffer = EvidenceBuffer()
            for batch in context.get("buffered_batches", [new_results]):
                buffer.add(batch)
            decision = self.controller.observe(
                skill,
                new_results,
                evidence_state,
                buffer=buffer,
                attempts=context.get("attempt_history", []),
                context={**context, "epoch_end": epoch_end},
            )
            return EvolutionDecision(
                decision.action,
                decision.state,
                decision.reason,
                raw=decision.payload,
                meta={"controller_version": "v3"},
            )

    trainer_module.build_evolution_policy = lambda cfg: V3Policy()


def official_rollout(self, env_manager, skill_content, out_dir, **kwargs):
    from controller_v3.alfworld_bridges import ALFWorldBaseBridge
    from controller_v3.llm import build_llm
    from controller_v3.usage import LedgerLLM, TokenLedger
    from controller_v3.validity import require_valid_rows

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    client = build_llm(
        "alfworld-eval", max_tokens=self.max_completion_tokens, enable_thinking=False
    )
    client.timeout = 300
    client.retries = 4
    client.retry_backoff = 2
    ledger_path = out / "tokens.json"
    ledger = (
        TokenLedger.from_dict(json.loads(ledger_path.read_text()))
        if ledger_path.exists()
        else TokenLedger(condition=self.run_condition, method="skillopt")
    )
    bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
    bridge.llm = LedgerLLM(client, ledger)
    bridge.benchmark_env = True
    bridge.env_batch_size = self.workers
    bridge.max_api_workers = 128
    bridge.max_steps = self.max_steps
    bridge.evidence_dir = out
    items = [
        dict(
            item,
            gamefile=str(
                (Path(os.environ["ALFWORLD_DATA"]) / item["gamefile"]).resolve()
            )
            if not Path(item["gamefile"]).is_absolute()
            else item["gamefile"],
        )
        for item in env_manager.items
    ]
    rows = bridge._rollout(items, skill_content)
    require_valid_rows(rows, out)
    for row, item in zip(rows, items, strict=True):
        row.update(
            task_description=item.get("task_description", item.get("task_type", "")),
            task_type=item.get("task_type", ""),
            soft=float(row["hard"]),
        )
        task = out / "predictions" / str(row["id"])
        task.mkdir(parents=True, exist_ok=True)
        (task / "conversation.json").write_text(row["trajectory"])
    (out / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (out / "execution_failure.json").unlink(missing_ok=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--condition", choices=["original", "controller"], required=True
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-workers", type=int, choices=range(1,129), default=1)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(VENDOR))
    from skillopt.config import load_config, flatten_config
    from skillopt.envs.alfworld.adapter import ALFWorldAdapter
    from skillopt.model.openai_compatible_backend import configure_openai_compatible
    from controller_v3.llm import load_llm_config
    import skillopt.engine.trainer as trainer

    paths = runtime_paths()
    cfg = flatten_config(
        load_config(str(paths.skillopt_root / "configs/alfworld/default.yaml"))
    )
    cfg.update(
        out_root=str(args.out.resolve()),
        split_dir=str(paths.skillopt_root / "data/alfworld_path_split"),
        skill_init=str(
            paths.skillopt_root / "skillopt/envs/alfworld/skills/initial.md"
        ),
        evolution_mode="fixed" if args.condition == "original" else "controller",
        observation_batch_size=4,
        gate_mode="rollout",
        model_backend="openai_compatible",
        optimizer_backend="openai_compatible",
        target_backend="openai_compatible",
        workers=args.env_workers,
        max_api_workers=128,
    )
    llm_cfg = load_llm_config("alfworld-eval")
    cfg.update(optimizer_model=llm_cfg["model"], target_model=llm_cfg["model"])
    if args.smoke:
        split_root = args.out.resolve() / "smoke_split"
        for split in ["train", "val", "test"]:
            rows = json.loads(
                (Path(cfg["split_dir"]) / split / "items.json").read_text()
            )[:2]
            target = split_root / split / "items.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(rows))
        cfg.update(
            split_dir=str(split_root),
            num_epochs=1,
            batch_size=2,
            observation_batch_size=2,
            slow_update_samples=2,
        )
    args.out.mkdir(parents=True, exist_ok=True)
    lock = (args.out / "run.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (args.out / "effective_config.json").write_text(json.dumps(cfg, indent=2))
    if args.config_only:
        return
    # Persist optimizer usage after every returned call, independently of
    # the trainer's in-memory counters. Preserve earlier process totals.
    import threading
    import skillopt.model.openai_compatible_backend as backend
    from controller_v3.usage import TokenLedger

    optimizer_path = args.out / "optimizer_tokens.json"
    optimizer_ledger = (
        TokenLedger.from_dict(json.loads(optimizer_path.read_text()))
        if optimizer_path.exists()
        else TokenLedger(condition=args.condition, method="skillopt")
    )
    native_chat = backend._chat_messages_impl
    native_client = backend._get_client
    usage_lock = threading.RLock()

    def tracked_chat(*call_args, **call_kwargs):
        try:
            result, usage = native_chat(*call_args, **call_kwargs)
        except Exception:
            with usage_lock:
                optimizer_ledger.mark_untracked(
                    "native_optimizer", "failed native request; usage unknown"
                )
                optimizer_ledger.save(optimizer_path)
            raise
        with usage_lock:
            optimizer_ledger.add(
                usage,
                stage=str(
                    call_kwargs.get(
                        "stage",
                        call_args[3] if len(call_args) > 3 else "native_optimizer",
                    )
                ),
            )
            optimizer_ledger.save(optimizer_path)
        return result, usage

    def tracked_client(role):
        client = native_client(role)

        def create(**kwargs):
            try:
                return client.chat.completions.create(**kwargs)
            except Exception:
                with usage_lock:
                    optimizer_ledger.mark_untracked(
                        "native_optimizer", "native API attempt failed; usage unknown"
                    )
                    optimizer_ledger.save(optimizer_path)
                raise

        return types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
        )

    backend._get_client = tracked_client
    backend._chat_messages_impl = tracked_chat
    configure_openai_compatible(
        **llm_cfg,
        max_tokens=cfg["max_completion_tokens"],
        timeout_seconds=300,
        enable_thinking=False,
    )
    accepted = inspect.signature(ALFWorldAdapter.__init__).parameters
    adapter = ALFWorldAdapter(**{k: v for k, v in cfg.items() if k in accepted})
    native_load_trajectory = adapter._load_traj_data

    def load_reference(item):
        gamefile = Path(item["gamefile"])
        if not gamefile.is_absolute():
            gamefile = Path(os.environ["ALFWORLD_DATA"]) / gamefile
        return native_load_trajectory(dict(item, gamefile=str(gamefile)))

    adapter._load_traj_data = load_reference
    adapter.run_condition = args.condition
    adapter.rollout = types.MethodType(official_rollout, adapter)
    if args.condition == "controller":
        install_policy(trainer)
    result = trainer.ReflACTTrainer(cfg, adapter).train()
    combined = TokenLedger(condition=args.condition, method="skillopt")
    combined.merge(optimizer_ledger)
    for ledger_file in args.out.rglob("tokens.json"):
        combined.merge(json.loads(ledger_file.read_text()))
    combined.save(args.out / "combined_tokens.json")
    result["full_cost_ledger"] = combined.summary()
    result["primary_test_metric"] = (
        "test_hard (best skill chosen by validation, not best test result)"
    )
    (args.out / "native_summary.json").write_text(
        json.dumps(result, indent=2, default=str)
    )


if __name__ == "__main__":
    main()
