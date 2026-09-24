"""Controller V3: evidence-triggered timing for skill evolution.

This module is dependency-free so it can be embedded in optimizers with very
different runtime stacks.  It does not generate edits and it never selects
which examples a host optimizer consumes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping


WAIT = "WAIT"
UPDATE = "UPDATE"


@dataclass
class EvidenceCard:
    """One execution converted to the controller's common evidence format."""

    task_id: str
    success: bool
    score: float = 0.0
    feedback: str = ""
    trajectory: str = ""
    failure_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Mapping[str, Any], index: int = 0) -> "EvidenceCard":
        task_id = str(result.get("task_id", result.get("id", index)))
        score_value = result.get("score", result.get("hard", result.get("em", 0.0)))
        try:
            score = float(score_value or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        success = bool(result.get("success", result.get("agent_ok", score >= 1.0)))
        if "hard" in result or "em" in result:
            success = score >= 1.0
        failure_key = str(
            result.get("failure_key")
            or result.get("fail_reason")
            or result.get("error_type")
            or result.get("feedback", "")
        ).strip()
        return cls(
            task_id=task_id,
            success=success,
            score=score,
            feedback=str(result.get("feedback", result.get("fail_reason", "")) or ""),
            trajectory=str(result.get("trajectory", result.get("response", "")) or ""),
            failure_key=failure_key[:240],
            metadata=dict(result.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AttemptRecord:
    """A host optimizer attempt, kept separate from evidence hypotheses."""

    attempt: int
    tasks_consumed: int
    validation: str
    score_before: float | None = None
    score_after: float | None = None
    candidate_score: float | None = None
    edits: list[str] = field(default_factory=list)
    targeted_defect: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControllerDecision:
    action: str
    state: dict[str, Any]
    reason: str
    window: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_update(self) -> bool:
        return self.action == UPDATE


class EvidenceBuffer:
    """Crash-friendly in-memory window with explicit snapshot/clear operations."""

    def __init__(self) -> None:
        self._cards: list[EvidenceCard] = []

    def add(self, results: Iterable[Mapping[str, Any] | EvidenceCard]) -> list[EvidenceCard]:
        added = [
            item if isinstance(item, EvidenceCard) else EvidenceCard.from_result(item, i)
            for i, item in enumerate(results)
        ]
        self._cards.extend(added)
        return added

    def extend(self, cards: Iterable[EvidenceCard]) -> None:
        self._cards.extend(cards)

    def snapshot(self) -> list[EvidenceCard]:
        return list(self._cards)

    def clear(self) -> None:
        self._cards.clear()

    def __len__(self) -> int:
        return len(self._cards)

    def summary(self) -> dict[str, Any]:
        failures = [c for c in self._cards if not c.success]
        over = sum("over" in c.failure_key.lower() for c in failures)
        under = sum("under" in c.failure_key.lower() for c in failures)
        return {
            "tasks": len(self._cards),
            "failures": len(failures),
            "failure_rate": round(len(failures) / len(self._cards), 4) if self._cards else 0.0,
            "failure_keys": dict(Counter(c.failure_key for c in failures if c.failure_key)),
            "over": over,
            "under": under,
        }


class ControllerV3:
    """Semantic evidence judge with deterministic safety gates.

    ``judge`` is optional.  Production integrations pass an LLM-backed judge
    accepting one JSON-serializable payload and returning ``WAIT``/``UPDATE``
    plus optional hypotheses.  The built-in judge is intentionally simple and
    exists for deterministic smoke tests and offline development.
    """

    version = "v3"

    def __init__(
        self,
        *,
        min_window_tasks: int = 4,
        failure_rate_floor: float = 0.4,
        max_attempt_history: int = 5,
        judge: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.min_window_tasks = max(0, int(min_window_tasks))
        self.failure_rate_floor = float(failure_rate_floor)
        self.max_attempt_history = max(0, int(max_attempt_history))
        self.judge = judge

    def initial_state(self) -> dict[str, Any]:
        return {
            "hypotheses": [],
            "tasks_since_last_attempt": 0,
            "failures_since_last_attempt": 0,
            "consecutive_rejects": 0,
            "unresolved": "",
        }

    @staticmethod
    def _window(cards: list[EvidenceCard]) -> dict[str, Any]:
        failures = [c for c in cards if not c.success]
        keys = Counter(c.failure_key for c in failures if c.failure_key)
        return {
            "tasks": len(cards),
            "failures": len(failures),
            "failure_rate": round(len(failures) / len(cards), 4) if cards else 0.0,
            "failure_keys": dict(keys),
            "over": sum("over" in c.failure_key.lower() for c in failures),
            "under": sum("under" in c.failure_key.lower() for c in failures),
        }

    def _advance(self, state: Mapping[str, Any] | None, cards: list[EvidenceCard]) -> dict[str, Any]:
        out = dict(state or self.initial_state())
        out["hypotheses"] = list(out.get("hypotheses") or [])[:8]
        out["tasks_since_last_attempt"] = int(out.get("tasks_since_last_attempt", 0) or 0) + len(cards)
        out["failures_since_last_attempt"] = int(out.get("failures_since_last_attempt", 0) or 0) + sum(
            not c.success for c in cards
        )
        return out

    def _builtin_judge(self, payload: dict[str, Any]) -> dict[str, Any]:
        window = payload["window"]
        failures = [c for c in payload["cards"] if not c["success"]]
        repeated = [key for key, count in window["failure_keys"].items() if count >= 2]
        enough = window["tasks"] >= self.min_window_tasks
        actionable = bool(repeated) or (enough and window["failure_rate"] >= 0.75)
        if not failures:
            return {"decision": WAIT, "reason": "the evidence window has no failures"}
        if not enough and window["failure_rate"] < self.failure_rate_floor:
            return {"decision": WAIT, "reason": "the evidence window is below the V3 floor"}
        if actionable:
            defect = repeated[0] if repeated else "recurring failures in the current skill"
            return {
                "decision": UPDATE,
                "reason": f"recurring actionable evidence: {defect}",
                "evidence_state": {
                    "hypotheses": [{
                        "defect": defect,
                        "support_count": max(2, window["failures"]),
                        "contradiction_count": 0,
                        "supporting_cases": [c["task_id"] for c in failures[:6]],
                        "contradicting_cases": [],
                        "status": "active",
                        "assessment": "same failure signature recurs across the window",
                    }],
                },
            }
        return {"decision": WAIT, "reason": "failures are isolated or task-specific"}

    def observe(
        self,
        skill: str,
        new_results: Iterable[Mapping[str, Any] | EvidenceCard],
        evidence_state: Mapping[str, Any] | None = None,
        *,
        buffer: EvidenceBuffer | None = None,
        attempts: Iterable[AttemptRecord | Mapping[str, Any]] = (),
        context: Mapping[str, Any] | None = None,
    ) -> ControllerDecision:
        cards = [
            item if isinstance(item, EvidenceCard) else EvidenceCard.from_result(item, i)
            for i, item in enumerate(new_results)
        ]
        # Hosts normally add the new cards to ``buffer`` before consulting us.
        # Treat that buffer as authoritative; appending ``cards`` again would
        # silently double the evidence and change the trigger timing.
        all_cards = buffer.snapshot() if buffer is not None else list(cards)
        state = self._advance(evidence_state, cards)
        window = self._window(all_cards)
        history = [a.to_dict() if isinstance(a, AttemptRecord) else dict(a) for a in attempts]
        payload = {
            "version": self.version,
            "skill": skill,
            "cards": [c.to_dict() for c in all_cards],
            "window": window,
            "evidence_state": state,
            "attempts": history[-self.max_attempt_history:] if self.max_attempt_history else [],
            "context": dict(context or {}),
        }
        raw = dict(self.judge(payload) if self.judge is not None else self._builtin_judge(payload))
        action = str(raw.get("decision", raw.get("action", WAIT))).upper()
        if action not in (WAIT, UPDATE):
            action = WAIT
        returned_state = raw.get("evidence_state")
        if isinstance(returned_state, Mapping):
            state.update({k: v for k, v in returned_state.items() if k != "tasks_since_last_attempt"})
            state["tasks_since_last_attempt"] = int(state["tasks_since_last_attempt"])
            state["failures_since_last_attempt"] = int(state["failures_since_last_attempt"])
        reason = str(raw.get("reason", ""))[:800] or "controller decision"
        return ControllerDecision(action, state, reason, window, payload)

    def reset_state(self, state: Mapping[str, Any], *, accepted: bool) -> dict[str, Any]:
        if accepted:
            return self.initial_state()
        carried = []
        for hypothesis in state.get("hypotheses", []) if isinstance(state, Mapping) else []:
            if not isinstance(hypothesis, Mapping) or not hypothesis.get("defect"):
                continue
            carried.append({
                "defect": str(hypothesis["defect"])[:400],
                "support_count": 0,
                "contradiction_count": 0,
                "supporting_cases": [],
                "contradicting_cases": [],
                "status": "weakened",
                "assessment": str(hypothesis.get("assessment", ""))[:400],
                "prior_support": int(hypothesis.get("support_count", 0) or 0),
                "prior_window_tasks": int(state.get("tasks_since_last_attempt", 0) or 0),
            })
        return {
            "hypotheses": carried,
            "tasks_since_last_attempt": 0,
            "failures_since_last_attempt": 0,
            "consecutive_rejects": int(state.get("consecutive_rejects", 0) or 0) + 1,
            "unresolved": str(state.get("unresolved", ""))[:600],
        }


class FixedImmediateSchedule:
    """Minimal original-method schedule used as the paired baseline.

    It deliberately has the same host-facing protocol as ``ControllerV3`` but
    performs no evidence judgement: every completed window enters the host's
    native update path immediately.  This makes the baseline definition
    explicit and avoids attributing Controller V3 logic to the original run.
    """

    version = "original-fixed-immediate"

    def initial_state(self) -> dict[str, Any]:
        return {"schedule": "immediate"}

    def observe(self, skill, new_results, evidence_state=None, *, buffer=None, attempts=(), context=None):
        cards = buffer.snapshot() if buffer is not None else list(new_results)
        window = {
            "tasks": len(cards),
            "failures": sum(not getattr(card, "success", False) for card in cards),
        }
        return ControllerDecision(
            action=UPDATE,
            state=dict(evidence_state or self.initial_state()),
            reason="original fixed immediate schedule",
            window=window,
        )

    def reset_state(self, state, *, accepted: bool):
        return self.initial_state()
