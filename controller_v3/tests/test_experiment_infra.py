from __future__ import annotations

import json
import os
import sys
import time
import types
from dataclasses import replace
from pathlib import Path

import pytest

from controller_v3.audit import audit_run
from controller_v3.core import ControllerV3, EvidenceBuffer, FixedImmediateSchedule, UPDATE, WAIT
from controller_v3.usage import LedgerLLM, TokenLedger


def test_token_ledger_sums_by_stage() -> None:
    ledger = TokenLedger(condition="controller", method="fake")
    with ledger.stage("rollout"):
        ledger.add({"prompt_tokens": 3, "completion_tokens": 2})
    with ledger.stage("proposal"):
        ledger.add({"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12})
    summary = ledger.summary()
    assert summary["total_tokens"] == 17
    assert summary["by_stage"]["rollout"]["api_calls"] == 1
    assert summary["by_stage"]["proposal"]["total_tokens"] == 12


def test_audit_is_non_blocking_for_warnings(tmp_path: Path) -> None:
    (tmp_path / "progress.jsonl").write_text(
        json.dumps({"task_id": "a"}) + "\n" + json.dumps({"task_id": "a"}) + "\n",
        encoding="utf-8",
    )
    result = audit_run(tmp_path)
    assert result["audit_status"] == "warning"
    assert result["quality_usable"] is True
    assert "duplicate task ids" in result["warnings"]


def test_controller_wait_and_update() -> None:
    controller = ControllerV3(min_window_tasks=2, failure_rate_floor=0.0)
    state = controller.initial_state()
    buffer = EvidenceBuffer()
    first_cards = buffer.add([{"id": "1", "hard": 0, "fail_reason": "x"}])
    first = controller.observe("s", first_cards, state, buffer=buffer)
    assert first.action == WAIT
    second_cards = buffer.add([{"id": "2", "hard": 0, "fail_reason": "x"}])
    second = controller.observe("s", second_cards, first.state, buffer=buffer)
    assert second.action == UPDATE


def test_original_schedule_always_updates_without_v3_judgement() -> None:
    policy = FixedImmediateSchedule()
    buffer = EvidenceBuffer()
    cards = buffer.add([{"id": "a", "hard": 1}])
    decision = policy.observe("skill", cards, policy.initial_state(), buffer=buffer)
    assert decision.action == UPDATE
    assert decision.reason == "original fixed immediate schedule"


def test_parallel_rollout_keeps_task_evidence_when_one_call_fails() -> None:
    from controller_v3.native_bridges import BaseNativeBridge

    bridge = BaseNativeBridge.__new__(BaseNativeBridge)
    bridge.rollout_workers = 2
    bridge.llm = types.SimpleNamespace(ledger=None)

    def rollout(item):
        if item["id"] == "bad":
            raise TimeoutError("upstream timeout")
        return {"id": item["id"], "hard": 1.0, "f1": 1.0}

    rows = bridge._parallel_rollout([{"id": "ok"}, {"id": "bad"}], rollout)
    assert [row["id"] for row in rows] == ["ok", "bad"]
    assert rows[1]["hard"] == 0.0
    assert "upstream timeout" in rows[1]["fail_reason"]


def test_ledger_stage_and_untracked_cost_flag() -> None:
    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            return "ok", {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}

    ledger = TokenLedger(condition="controller", method="fake")
    client = LedgerLLM(Client(), ledger)
    client.respond("system", "user", stage="rollout", metadata={"task_id": "a"})
    ledger.mark_untracked("native_update", "fake backend")
    assert ledger.summary()["by_stage"]["rollout"]["total_tokens"] == 7
    assert ledger.summary()["cost_usable"] is False
    assert ledger.records[0].metadata["task_id"] == "a"


def test_audit_marks_untracked_tokens_cost_unusable(tmp_path: Path) -> None:
    (tmp_path / "progress.jsonl").write_text(json.dumps({"task_id": "a", "row": {}}) + "\n", encoding="utf-8")
    ledger = TokenLedger(condition="controller", method="fake")
    ledger.add({"prompt_tokens": 1, "completion_tokens": 1})
    ledger.mark_untracked("native", "not exposed")
    (tmp_path / "tokens.json").write_text(json.dumps(ledger.to_dict()), encoding="utf-8")
    result = audit_run(tmp_path)
    assert result["quality_usable"] is True
    assert result["cost_usable"] is False
    assert any("untracked" in warning for warning in result["warnings"])


def test_paired_runner_resumes_task_evidence_without_duplicate_calls(tmp_path: Path, monkeypatch) -> None:
    import controller_v3.paired_experiment as paired

    calls = []

    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            calls.append(user)
            return "answer", {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}

    class Bridge:
        def __init__(self, llm, controller=None):
            self.llm = llm

        def run_window(self, items, skill):
            rows = []
            for item in items:
                self.llm.respond("s", str(item["id"]), stage="rollout", metadata={"task_id": str(item["id"])})
                rows.append({"id": item["id"], "hard": 1.0, "f1": 1.0, "response": "answer"})
            return {"rows": rows, "decision": "WAIT", "reason": "test", "update": {"accepted": False}}

    data = [{"id": str(index), "question": f"q{index}", "answers": ["a"]} for index in range(3)]
    data_path = tmp_path / "items.json"
    data_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(paired, "build_llm", lambda max_tokens: Client())
    monkeypatch.setattr(paired, "BRIDGE_TYPES", {"fake": Bridge})

    first = paired.run(data_path, tmp_path / "out", limit=2, methods=["fake"], batch_size=1)
    assert first["fake/original"]["new_tasks"] == 2
    first_call_count = len(calls)
    second = paired.run(data_path, tmp_path / "out", limit=3, methods=["fake"], batch_size=1)
    # The manifest changed with the requested item window, so this is a new
    # run in the same directory; the first two task ids still remain evidence.
    assert second["fake/original"]["new_tasks"] == 1
    assert len(calls) == first_call_count + 2  # one missing task per condition
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["paired"]["fake"]["paired"]


def test_paired_runner_rejects_changed_task_payload_on_resume(tmp_path: Path, monkeypatch) -> None:
    import controller_v3.paired_experiment as paired

    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            return "answer", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    class Bridge:
        def __init__(self, llm, controller=None):
            self.llm = llm

        def run_window(self, items, skill):
            return {"rows": [{"id": x["id"], "hard": 1.0, "f1": 1.0} for x in items], "decision": "WAIT", "update": {}}

    monkeypatch.setattr(paired, "build_llm", lambda max_tokens: Client())
    data_path = tmp_path / "items.json"
    data_path.write_text(json.dumps([{"id": "a", "question": "first"}, {"id": "b", "question": "second"}]), encoding="utf-8")
    paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2)
    data_path.write_text(json.dumps([{"id": "a", "question": "CHANGED"}, {"id": "b", "question": "second"}]), encoding="utf-8")
    try:
        paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2)
    except ValueError as exc:
        assert "task payload changed" in str(exc)
    else:
        raise AssertionError("changed task payload was accepted during resume")


def test_paired_runner_rejects_changed_runtime_configuration_on_resume(tmp_path: Path, monkeypatch) -> None:
    import controller_v3.paired_experiment as paired

    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            return "answer", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    class Bridge:
        def __init__(self, llm, controller=None):
            self.llm = llm

        def run_window(self, items, skill):
            return {"rows": [{"id": item["id"], "hard": 1.0, "f1": 1.0} for item in items], "decision": "WAIT", "update": {}}

    monkeypatch.setattr(paired, "build_llm", lambda *args, **kwargs: Client())
    data_path = tmp_path / "items.json"
    data_path.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf-8")
    paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2, max_tokens=32)
    with pytest.raises(ValueError, match="runtime configuration changed: max_tokens"):
        paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2, max_tokens=64)


def test_paired_runner_resumes_heldout_evidence_without_re_evaluating(tmp_path: Path, monkeypatch) -> None:
    import controller_v3.paired_experiment as paired

    calls = []

    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            calls.append((system, user))
            return "answer", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    class Bridge:
        def __init__(self, llm, controller=None):
            self.llm = llm

        def run_window(self, items, skill):
            return {"rows": [{"id": x["id"], "hard": 1.0, "f1": 1.0} for x in items], "decision": "WAIT", "update": {}}

        def evaluate_only(self, item, skill):
            self.llm.respond("heldout", item["id"])
            return {"id": item["id"], "score": 1.0, "hard": 1.0, "f1": 1.0}

    monkeypatch.setattr(paired, "build_llm", lambda max_tokens: Client())
    data_path = tmp_path / "items.json"
    heldout_path = tmp_path / "heldout.json"
    data_path.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf-8")
    heldout_path.write_text(json.dumps([{"id": "h"}]), encoding="utf-8")
    first = paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2, heldout_path=heldout_path, heldout_limit=1)
    first_calls = len(calls)
    second = paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2, heldout_path=heldout_path, heldout_limit=1)
    assert len(calls) == first_calls
    assert second["fake/original"]["resumed"] is True
    assert second["fake/original"]["result"]["heldout_rows"][0]["id"] == "h"
    assert first["fake/controller"]["result"]["heldout_rows"]


def test_paired_runner_restores_skill_checkpoint_on_resume(tmp_path: Path, monkeypatch) -> None:
    import controller_v3.paired_experiment as paired

    seen_skills = []

    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            return "answer", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    class Bridge:
        def __init__(self, llm, controller=None):
            self.state = {"tasks_since_last_attempt": 0}
            self.attempts = []

        def run_window(self, items, skill):
            seen_skills.append((tuple(item["id"] for item in items), skill))
            self.state = {"tasks_since_last_attempt": self.state["tasks_since_last_attempt"] + len(items)}
            return {
                "rows": [{"id": item["id"], "hard": 1.0, "f1": 1.0} for item in items],
                "decision": "UPDATE",
                "update": {"accepted": True},
                "next_skill": skill + " -> evolved",
            }

    monkeypatch.setattr(paired, "build_llm", lambda max_tokens: Client())
    monkeypatch.setattr(paired, "BRIDGE_TYPES", {"fake": Bridge})
    data_path = tmp_path / "items.json"
    data_path.write_text(json.dumps([{"id": "a"}, {"id": "b"}, {"id": "c"}]), encoding="utf-8")
    out = tmp_path / "out"
    paired.run(data_path, out, methods=["fake"], bridge_types={"fake": Bridge}, limit=2, batch_size=1)
    paired.run(data_path, out, methods=["fake"], bridge_types={"fake": Bridge}, limit=3, batch_size=1)
    resumed_calls = [skill for ids, skill in seen_skills if ids == ("c",)]
    assert resumed_calls == [
        "Answer the question from context and use concise <answer> tags. -> evolved -> evolved",
        "Answer the question from context and use concise <answer> tags. -> evolved -> evolved",
    ]
    assert json.loads((out / "fake" / "original" / "state.json").read_text())["completed_task_ids"] == ["a", "b", "c"]


def test_evoskill_prompt_contains_active_skill() -> None:
    from controller_v3.native_bridges import EvoSkillNativeBridge

    system, user = EvoSkillNativeBridge._agent_prompt("Use the context before answering.", {"question": "q", "context": "c"})
    assert "Use the context before answering." in system
    assert "## Active Skill" in system
    assert "## Question\nq" in user


def test_trace2skill_import_isolated_from_evoskill_src_package(monkeypatch) -> None:
    """The two pulled repositories both expose ``src`` at top level."""
    from controller_v3.alfworld_bridges import _prepare_trace2skill_imports

    original_path = list(sys.path)
    original_modules = {
        name: module for name, module in sys.modules.items()
        if name == "src" or name.startswith("src.")
    }
    monkeypatch.setattr(sys, "path", original_path + ["/tmp/repos/pulled/EvoSkill"])
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src.loop"] = types.ModuleType("src.loop")
    try:
        _prepare_trace2skill_imports()
        assert str(Path(__file__).parents[2] / "repos/pulled/Trace2Skill") == sys.path[0]
        assert "src" not in sys.modules
        assert "src.loop" not in sys.modules
        assert all("repos/pulled/EvoSkill" not in path for path in sys.path)
    finally:
        for name in list(sys.modules):
            if name == "src" or name.startswith("src."):
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_runner_passes_explicit_llm_config_to_condition(tmp_path: Path, monkeypatch) -> None:
    import controller_v3.paired_experiment as paired

    names = []

    class Client:
        model = "fake"
        base_url = "http://fake"
        api_key = "unused"

        def respond(self, system, user):
            return "answer", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    def fake_build(name="searchqa-eval", *, max_tokens=512):
        names.append(name)
        return Client()

    class Bridge:
        def __init__(self, llm, controller=None):
            self.llm = llm

        def run_window(self, items, skill):
            return {"rows": [{"id": item["id"], "hard": 1.0, "f1": 1.0} for item in items], "decision": "WAIT", "update": {}}

    data_path = tmp_path / "items.json"
    data_path.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf-8")
    monkeypatch.setattr(paired, "build_llm", fake_build)
    paired.run(data_path, tmp_path / "out", methods=["fake"], bridge_types={"fake": Bridge}, limit=2, batch_size=2, llm_name="alfworld-eval")
    assert names == ["alfworld-eval", "alfworld-eval"]


def test_trace2skill_usage_object_is_normalized() -> None:
    from controller_v3.alfworld_bridges import _usage_mapping

    class Usage:
        prompt_tokens = 11
        completion_tokens = 7
        total_tokens = 18

    assert _usage_mapping(Usage()) == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert _usage_mapping({"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})["total_tokens"] == 5
    assert _usage_mapping(object()) is None


def test_evoskill_proposal_payload_is_coerced_for_native_schema() -> None:
    from controller_v3.native_bridges import _normalize_evoskill_proposal

    value = _normalize_evoskill_proposal({"action": "none", "proposed_skill": None, "justification": None})
    assert value["action"] == "create"
    assert isinstance(value["proposed_skill"], str) and value["proposed_skill"]
    assert isinstance(value["justification"], str) and value["justification"]
    assert value["target_skill"] is None


def test_campaign_audit_checks_paired_population(tmp_path: Path) -> None:
    from controller_v3.campaign_audit import audit_campaign

    root = tmp_path / "campaign"
    summary = {"paired": {"fake": {"paired": [{"task_id": "a"}]}}}
    for condition in ("original", "controller"):
        path = root / "fake" / condition
        path.mkdir(parents=True)
        manifest = {
            "items_hash": "items",
            "skill_hash": "skill",
            "llm_name": "fake",
            "max_tokens": 32,
            "alfworld_thinking": None,
        }
        audit = {"audit_status": "ok", "quality_usable": True, "cost_usable": True}
        tokens = {"summary": {"total_tokens": 2, "untracked_calls": 0}}
        result = {"rows": [{"id": "a"}]}
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (path / "progress.jsonl").write_text(json.dumps({"task_id": "a"}) + "\n", encoding="utf-8")
        (path / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (path / "tokens.json").write_text(json.dumps(tokens), encoding="utf-8")
        (path / "audit.json").write_text(json.dumps(audit), encoding="utf-8")
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    report = audit_campaign(root, methods=("fake",))
    assert report["ok"] is True


def test_campaign_audit_can_keep_quality_evidence_when_cost_is_unusable(tmp_path: Path) -> None:
    from controller_v3.campaign_audit import audit_campaign

    root = tmp_path / "campaign"
    summary = {"paired": {"fake": {"paired": [{"task_id": "a"}]}}}
    for condition in ("original", "controller"):
        path = root / "fake" / condition
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(json.dumps({"items_hash": "items", "skill_hash": "skill", "llm_name": "fake", "max_tokens": 32, "alfworld_thinking": None}), encoding="utf-8")
        (path / "progress.jsonl").write_text(json.dumps({"task_id": "a", "row": {"id": "a"}}) + "\n", encoding="utf-8")
        (path / "result.json").write_text(json.dumps({"rows": [{"id": "a"}]}), encoding="utf-8")
        (path / "tokens.json").write_text(json.dumps({"summary": {"total_tokens": 2, "untracked_calls": 1}}), encoding="utf-8")
        (path / "audit.json").write_text(json.dumps({"audit_status": "warning", "quality_usable": True, "cost_usable": False}), encoding="utf-8")
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    report = audit_campaign(root, methods=("fake",), require_cost=False)
    assert report["ok"] is True
    assert report["warnings"]


def test_campaign_audit_rejects_mismatched_heldout_population(tmp_path: Path) -> None:
    from controller_v3.campaign_audit import audit_campaign

    root = tmp_path / "campaign"
    summary = {"paired": {"fake": {"paired": [{"task_id": "a"}]}}}
    for condition, heldout_id in (("original", "h1"), ("controller", "h2")):
        path = root / "fake" / condition
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(json.dumps({"items_hash": "items", "skill_hash": "skill", "llm_name": "fake", "max_tokens": 32, "alfworld_thinking": None}), encoding="utf-8")
        (path / "progress.jsonl").write_text(json.dumps({"task_id": "a"}) + "\n", encoding="utf-8")
        (path / "result.json").write_text(json.dumps({"rows": [{"id": "a"}]}), encoding="utf-8")
        (path / "tokens.json").write_text(json.dumps({"summary": {"total_tokens": 2, "untracked_calls": 0}}), encoding="utf-8")
        (path / "audit.json").write_text(json.dumps({"audit_status": "ok", "quality_usable": True, "cost_usable": True}), encoding="utf-8")
        (path / "heldout.json").write_text(json.dumps({"task_ids": [heldout_id], "rows": [{"id": heldout_id}]}), encoding="utf-8")
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    report = audit_campaign(root, methods=("fake",))
    assert report["ok"] is False
    assert any("held-out task populations differ" in error for error in report["errors"])


def test_campaign_audit_warns_for_missing_runtime_provenance(tmp_path: Path) -> None:
    from controller_v3.campaign_audit import audit_campaign

    root = tmp_path / "campaign"
    for condition in ("original", "controller"):
        path = root / "fake" / condition
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(json.dumps({"items_hash": "items", "skill_hash": "skill"}), encoding="utf-8")
        (path / "progress.jsonl").write_text(json.dumps({"task_id": "a"}) + "\n", encoding="utf-8")
        (path / "result.json").write_text(json.dumps({"rows": [{"id": "a"}]}), encoding="utf-8")
        (path / "tokens.json").write_text(json.dumps({"summary": {"total_tokens": 2, "untracked_calls": 0}}), encoding="utf-8")
        (path / "audit.json").write_text(json.dumps({"audit_status": "ok", "quality_usable": True, "cost_usable": True}), encoding="utf-8")
    (root / "summary.json").write_text(json.dumps({"paired": {"fake": {"paired": [{"task_id": "a"}]}}}), encoding="utf-8")
    report = audit_campaign(root, methods=("fake",))
    assert report["ok"] is True
    assert any("missing runtime provenance field" in warning for warning in report["warnings"])


def test_audit_rejects_missing_manifest_task_evidence_and_inconsistent_tokens(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"items": ["a", "b"]}), encoding="utf-8")
    (tmp_path / "progress.jsonl").write_text(json.dumps({"task_id": "a", "row": {}}) + "\n", encoding="utf-8")
    (tmp_path / "tokens.json").write_text(json.dumps({
        "records": [{"total_tokens": 3, "api_call": 1}],
        "summary": {"total_tokens": 9, "api_calls": 1, "untracked_calls": 0},
    }), encoding="utf-8")
    result = audit_run(tmp_path)
    assert result["quality_usable"] is False
    assert result["cost_usable"] is False
    assert any("manifest items" in error for error in result["errors"])
    assert any("does not match records" in warning for warning in result["warnings"])


def test_campaign_analysis_uses_all_paired_tasks_and_fixed_metric(tmp_path: Path) -> None:
    from controller_v3.campaign_analysis import analyze_campaign

    root = tmp_path / "analysis"
    root.mkdir()
    conditions = {}
    for condition, values, tokens in (
        ("original", [0.5, 1.0, 0.0], 100),
        ("controller", [0.6, 1.0, 0.0], 75),
    ):
        conditions[f"fake/{condition}"] = {
            "result": {
                "rows": [{"id": str(i), "f1": value} for i, value in enumerate(values)],
                "heldout_rows": [
                    {"id": "val-0", "f1": values[0], "evaluation_split": "val"},
                    {"id": "test-0", "f1": values[1], "evaluation_split": "test"},
                ],
            },
            "tokens": {"total_tokens": tokens},
            "audit": {"cost_usable": True},
        }
    (root / "summary.json").write_text(json.dumps({"conditions": conditions}), encoding="utf-8")
    report = analyze_campaign(root, methods=("fake",), quality_field="f1", bootstrap_samples=100)
    result = report["methods"]["fake"]
    assert result["tasks"] == 3
    assert abs(result["mean_delta"] - 0.1 / 3) < 1e-12
    assert result["wins"] == 1 and result["ties"] == 2
    assert result["controller_reduces_tokens"] is True
    assert result["supports_target_claim"] is True
    assert result["heldout"]["tasks"] == 2
    assert abs(result["heldout"]["mean_delta"] - 0.05) < 1e-12
    assert result["heldout_by_split"]["val"]["tasks"] == 1
    assert result["heldout_by_split"]["test"]["tasks"] == 1
    assert result["heldout_by_split"]["val"]["wins"] == 1


def test_full_campaign_merge_writes_real_paired_summary(tmp_path: Path, monkeypatch) -> None:
    from controller_v3 import full_campaign

    root = tmp_path / "campaign"
    for method in full_campaign.METHODS:
        for condition in ("original", "controller"):
            path = root / "searchqa" / method / condition
            path.mkdir(parents=True)
            payload = {
                "method": method,
                "condition": condition,
                "result": {"rows": [{"id": "task-1", "f1": 0.5}]},
                "tokens": {"total_tokens": 10},
                "audit": {"quality_usable": True, "cost_usable": True},
            }
            (path / "condition_result.json").write_text(json.dumps(payload), encoding="utf-8")
            (path / "manifest.json").write_text(json.dumps({"items": ["task-1"]}), encoding="utf-8")
            (path / "progress.jsonl").write_text(json.dumps({"task_id": "task-1", "row": {"id": "task-1"}}) + "\n", encoding="utf-8")
            (path / "result.json").write_text(json.dumps(payload["result"]), encoding="utf-8")
            (path / "tokens.json").write_text(json.dumps({"summary": {"total_tokens": 10}}), encoding="utf-8")
            (path / "audit.json").write_text(json.dumps({"quality_usable": True, "cost_usable": True}), encoding="utf-8")
    monkeypatch.setattr(full_campaign, "audit_campaign", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(full_campaign, "analyze_campaign", lambda *_args, **_kwargs: {})
    full_campaign._merge_domain(root, "searchqa", quality_field="f1")
    summary = json.loads((root / "searchqa" / "summary.json").read_text())
    assert all(summary["paired"][method]["paired"] for method in full_campaign.METHODS)


def _load_alfworld_rollout_module():
    """Load SkillOpt's ALFWorld runner without requiring an installed package."""
    root = Path(__file__).parents[2] / "repos" / "SkillOptETE"
    value = str(root)
    if value not in sys.path:
        sys.path.insert(0, value)
    import skillopt.envs.alfworld.rollout as rollout

    return rollout


class _FakeALFEnv:
    def reset(self, _payload):
        return (
            {"text": ["observation"], "anchor": ["Your task is to: put the apple in the box"]},
            [{"extra.gamefile": "pick_and_place/test_game.json"}],
        )

    def step(self, actions):
        assert len(actions) == 1
        return (
            {"anchor": ["The episode ended"]},
            [0.0],
            [True],
            [{"won": False}],
        )


def test_alfworld_batch_recovers_from_api_error(monkeypatch, tmp_path: Path) -> None:
    rollout = _load_alfworld_rollout_module()

    def fail(**_kwargs):
        raise RuntimeError("endpoint unavailable")

    monkeypatch.setattr(rollout, "chat_target", fail)
    rows = rollout.run_alfworld_batch(
        _FakeALFEnv(),
        "skill",
        max_steps=1,
        out_root=str(tmp_path),
        max_api_workers=1,
        result_ids=["task-a"],
        api_timeout=0.1,
    )
    assert rows[0]["id"] == "task-a"
    assert rows[0]["api_failures"] == 1
    conversation = json.loads(
        (tmp_path / "predictions" / "task-a" / "conversation.json").read_text()
    )
    assert "endpoint unavailable" in conversation[0]["api_error"]


def test_alfworld_rollout_normalizes_a_concise_bare_action() -> None:
    rollout = _load_alfworld_rollout_module()
    normalized, valid = rollout._normalize_action_response("go to desk 1")
    assert valid is True
    assert normalized == "<action>go to desk 1</action>"
    _, valid = rollout._normalize_action_response("I should go to desk 1 because it is nearby.")
    assert valid is False


def test_alfworld_batch_enforces_api_deadline(monkeypatch, tmp_path: Path) -> None:
    rollout = _load_alfworld_rollout_module()
    request_options = []

    def hang(**kwargs):
        request_options.append(kwargs)
        time.sleep(0.08)
        return "<action>look</action>", {}

    monkeypatch.setattr(rollout, "chat_target", hang)
    started = time.monotonic()
    rows = rollout.run_alfworld_batch(
        _FakeALFEnv(),
        "skill",
        max_steps=1,
        out_root=str(tmp_path),
        max_api_workers=1,
        result_ids=["task-timeout"],
        api_timeout=0.005,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 0.06
    assert rows[0]["api_failures"] == 1
    conversation = json.loads(
        (tmp_path / "predictions" / "task-timeout" / "conversation.json").read_text()
    )
    assert conversation[0]["api_error"] == "timeout after 0.005s"
    assert request_options and request_options[0]["retries"] == 1


def test_alfworld_bridge_turns_native_batch_failure_into_task_evidence(monkeypatch) -> None:
    from controller_v3.alfworld_bridges import ALFWorldBaseBridge

    bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
    bridge.max_steps = 1
    bridge.max_completion_tokens = 8
    bridge.max_api_workers = 1
    bridge.api_timeout = 0.1
    bridge.reset_token_tracker = lambda: None
    bridge._harvest_tracker = lambda _stage: None
    bridge.build_env = lambda **_kwargs: _FakeALFEnv()

    def fail_batch(*_args, **_kwargs):
        raise RuntimeError("environment worker crashed")

    bridge.run_batch = fail_batch
    rows = bridge._rollout([{"id": "task-crash", "gamefile": "train/game.json"}], "skill")
    assert rows[0]["id"] == "task-crash"
    assert rows[0]["hard"] == 0
    assert "environment worker crashed" in rows[0]["fail_reason"]
    assert rows[0]["metadata"]["rollout_error"]


def test_alfworld_bridge_propagates_accepted_candidate_skill() -> None:
    from controller_v3.alfworld_bridges import ALFWorldBaseBridge

    bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
    bridge.equivalence_scope = "test"
    bridge._rollout = lambda items, skill: [{"id": item["id"], "hard": 0, "score": 0.0} for item in items]
    bridge._decide = lambda *args, **kwargs: (types.SimpleNamespace(action=UPDATE, reason="test"), [])
    bridge._run_update = lambda rows, items, skill: {"accepted": True, "candidate_skill": "new skill"}
    bridge._record_attempt = lambda *args, **kwargs: None
    result = bridge.run_window([{"id": "a"}], "old skill")
    assert result["next_skill"] == "new skill"


def test_alfworld_cli_forwards_max_tokens_to_native_bridge(monkeypatch) -> None:
    import controller_v3.alfworld_paired_experiment as runner

    monkeypatch.setattr(sys, "argv", ["alfworld_paired_experiment", "--max-tokens", "37"])
    monkeypatch.setattr(runner, "run", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "_paired_summary", lambda report: {})
    runner.main()
    assert os.environ["CONTROLLER_V3_ALF_MAX_TOKENS"] == "37"


def test_alfworld_explicit_item_selection_preserves_requested_order(tmp_path: Path) -> None:
    from controller_v3.alfworld_paired_experiment import _items_by_id

    path = tmp_path / "items.json"
    path.write_text(json.dumps([
        {"id": "train:0001", "gamefile": "one"},
        {"id": "train:0002", "gamefile": "two"},
        {"id": "train:0003", "gamefile": "three"},
    ]), encoding="utf-8")
    selected = _items_by_id(path, ["train:0003", "train:0001"])
    assert [item["id"] for item in selected] == ["train:0003", "train:0001"]


def test_alfworld_explicit_item_selection_rejects_duplicates_and_unknown_ids(tmp_path: Path) -> None:
    from controller_v3.alfworld_paired_experiment import _items_by_id

    path = tmp_path / "items.json"
    path.write_text(json.dumps([{"id": "train:0001"}, {"id": "train:0002"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        _items_by_id(path, ["train:0001", "train:0001"])
    with pytest.raises(ValueError, match="unknown"):
        _items_by_id(path, ["train:0001", "train:9999"])


def test_alfworld_cli_forwards_explicit_item_overrides(monkeypatch, tmp_path: Path) -> None:
    import controller_v3.alfworld_paired_experiment as runner

    data = tmp_path / "train.json"
    heldout = tmp_path / "val.json"
    data.write_text(json.dumps([{"id": "train:0001"}, {"id": "train:0002"}]), encoding="utf-8")
    heldout.write_text(json.dumps([{"id": "val:0001"}, {"id": "val:0002"}]), encoding="utf-8")
    captured = {}
    monkeypatch.setattr(sys, "argv", [
        "alfworld_paired_experiment", "--data-path", str(data), "--heldout-path", str(heldout),
        "--item-ids", "train:0002", "train:0001", "--heldout-item-ids", "val:0002", "val:0001",
    ])
    monkeypatch.setattr(runner, "run", lambda *args, **kwargs: captured.update(kwargs) or {})
    monkeypatch.setattr(runner, "_paired_summary", lambda report: {})
    runner.main()
    assert [item["id"] for item in captured["items_override"]] == ["train:0002", "train:0001"]
    assert [item["id"] for item in captured["heldout_items_override"]] == ["val:0002", "val:0001"]


def test_alfworld_api_failure_keeps_quality_but_invalidates_cost_ledger() -> None:
    from controller_v3.alfworld_bridges import ALFWorldBaseBridge

    bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
    bridge.max_steps = 1
    bridge.max_completion_tokens = 8
    bridge.max_api_workers = 1
    bridge.api_timeout = 0.1
    bridge.reset_token_tracker = lambda: None
    bridge.build_env = lambda **_kwargs: _FakeALFEnv()
    bridge.get_token_summary = lambda: {
        "rollout": {"calls": 1, "prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
    }
    bridge.run_batch = lambda *_args, **_kwargs: [{
        "id": "task-api-failure",
        "hard": 0,
        "soft": 0.0,
        "api_failures": 1,
        "api_usage_missing": 1,
        "fail_reason": "timeout",
    }]
    ledger = TokenLedger(condition="controller", method="alfworld")
    bridge.llm = types.SimpleNamespace(ledger=ledger)

    rows = bridge._rollout([{"id": "task-api-failure", "gamefile": "train/game.json"}], "skill")
    assert rows[0]["hard"] == 0
    assert ledger.summary()["total_tokens"] == 3
    assert ledger.summary()["cost_usable"] is False


def test_openai_compatible_backend_forwards_thinking_policy(monkeypatch) -> None:
    root = Path(__file__).parents[2] / "repos" / "SkillOptETE"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import skillopt.model.openai_compatible_backend as backend

    calls = []

    class Message:
        content = "<action>look</action>"

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]
        usage = types.SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return Response()

    class Client:
        chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setattr(backend, "TARGET_CONFIG", replace(backend.TARGET_CONFIG, enable_thinking=False))
    monkeypatch.setattr(backend, "_get_client", lambda _role: Client())
    text, usage = backend._chat_messages_impl(
        [{"role": "user", "content": "act"}], 16, 1, "test", role="target"
    )
    assert text == "<action>look</action>"
    assert usage["total_tokens"] == 5
    assert calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
