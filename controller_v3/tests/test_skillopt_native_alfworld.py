import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_original_skillopt_config_and_timing_only_difference(tmp_path):
    configs = []
    for condition in ["original", "controller"]:
        out = tmp_path / condition
        subprocess.run(
            [
                sys.executable,
                "-m",
                "controller_v3.skillopt_native_alfworld",
                "--condition",
                condition,
                "--out",
                str(out),
                "--config-only",
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            check=True,
        )
        configs.append(json.loads((out / "effective_config.json").read_text()))
    a, b = configs
    for key, expected in {
        "num_epochs": 4,
        "batch_size": 40,
        "accumulation": 1,
        "minibatch_size": 8,
        "merge_batch_size": 8,
        "edit_budget": 4,
        "min_edit_budget": 2,
        "lr_scheduler": "cosine",
        "use_gate": True,
        "use_slow_update": True,
        "use_meta_skill": True,
        "slow_update_samples": 20,
        "max_steps": 50,
        "max_completion_tokens": 16384,
        "gate_mode": "rollout",
    }.items():
        assert a[key] == b[key] == expected
    assert {k for k in a if a[k] != b[k]} == {"out_root", "evolution_mode"}
    assert a["evolution_mode"] == "fixed" and b["evolution_mode"] == "controller"
    assert Path(a["skill_init"]).read_text()


def test_v3_hook_uses_buffer_without_changing_skill():
    sys.path.insert(0, str(ROOT / "repos/SkillOptETE"))
    from types import SimpleNamespace
    from controller_v3.skillopt_native_alfworld import install_policy

    trainer = SimpleNamespace()
    install_policy(trainer)
    policy = trainer.build_evolution_policy({})
    rows = [{"id": str(i), "hard": 0, "fail_reason": "same failure"} for i in range(4)]
    decision = policy.observe(
        "unchanged skill",
        rows,
        policy.initial_state(),
        context={"buffered_batches": [rows]},
    )
    assert decision.action == "UPDATE"
    assert decision.raw["skill"] == "unchanged skill"
    assert len(decision.raw["cards"]) == 4
