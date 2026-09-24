from pathlib import Path

from controller_v3.core import ControllerV3, EvidenceBuffer
from controller_v3.smoke_searchqa import run_smoke


def test_controller_v3_does_not_double_count_buffered_cards():
    policy = ControllerV3(min_window_tasks=4)
    buffer = EvidenceBuffer()
    cards = buffer.add([
        {"id": "a", "hard": 0, "failure_key": "same"},
        {"id": "b", "hard": 0, "failure_key": "same"},
    ])
    decision = policy.observe("skill", cards, policy.initial_state(), buffer=buffer)
    assert decision.window["tasks"] == 2
    assert decision.window["failures"] == 2


def test_searchqa_smoke_all_adapters(tmp_path):
    data = Path(__file__).parents[1] / "benchmark/searchqa-eval/data/searchqa_split/train/items.json"
    report = run_smoke(data, limit=8, out_dir=tmp_path)
    assert set(report) == {"skillopt", "gepa", "evoskill", "trace2skill"}
    assert all(row["updates"] >= 1 for row in report.values())
    assert all((tmp_path / f"{name}.jsonl").exists() for name in report)


def test_controller_v3_preserves_rejected_hypothesis_as_weakened():
    policy = ControllerV3()
    state = {
        "hypotheses": [{"defect": "missing recovery", "support_count": 3, "assessment": "x"}],
        "tasks_since_last_attempt": 6,
        "failures_since_last_attempt": 3,
        "consecutive_rejects": 0,
    }
    next_state = policy.reset_state(state, accepted=False)
    assert next_state["hypotheses"][0]["status"] == "weakened"
    assert next_state["hypotheses"][0]["prior_support"] == 3
    assert next_state["tasks_since_last_attempt"] == 0
