"""Small host-agnostic runners used by the four method adapters."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .core import AttemptRecord, ControllerV3, EvidenceBuffer, EvidenceCard, UPDATE


@dataclass
class RunSummary:
    method: str
    decisions: int
    updates: int
    attempts: int
    accepted: int
    rejected: int
    observations: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_controller_loop(
    *,
    method: str,
    tasks: Iterable[Mapping[str, Any]],
    skill: str,
    rollout: Callable[[Mapping[str, Any], str], Mapping[str, Any]],
    attempt: Callable[[str, list[EvidenceCard], str], tuple[str, str]],
    controller: ControllerV3 | None = None,
    batch_size: int = 4,
    state_path: str | Path | None = None,
) -> RunSummary:
    """Run a resumable controller loop around a host method.

    ``rollout`` and ``attempt`` are the only method-specific hooks.  The
    latter returns ``(new_skill, validation)`` where validation is accepted or
    rejected.  Every decision is optionally appended to a JSONL state file.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    policy = controller or ControllerV3()
    buffer = EvidenceBuffer()
    state = policy.initial_state()
    history: list[AttemptRecord] = []
    decisions = updates = accepted = rejected = observations = 0
    task_list = list(tasks)
    for start in range(0, len(task_list), batch_size):
        batch = task_list[start : start + batch_size]
        cards = buffer.add(rollout(task, skill) for task in batch)
        observations += 1
        decision = policy.observe(skill, cards, state, buffer=buffer, attempts=history)
        state = decision.state
        decisions += 1
        if state_path is not None:
            path = Path(state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "method": method,
                    "observation": observations,
                    "action": decision.action,
                    "reason": decision.reason,
                    "window": decision.window,
                    "state": state,
                }, ensure_ascii=False) + "\n")
        if decision.action != UPDATE:
            continue
        updates += 1
        new_skill, validation = attempt(skill, buffer.snapshot(), decision.reason)
        normalized = str(validation).lower()
        is_accepted = normalized.startswith("accept")
        accepted += int(is_accepted)
        rejected += int(not is_accepted)
        history.append(AttemptRecord(
            attempt=len(history) + 1,
            tasks_consumed=len(buffer),
            validation="accepted" if is_accepted else "rejected",
            targeted_defect=decision.reason,
        ))
        skill = new_skill if is_accepted else skill
        state = policy.reset_state(state, accepted=is_accepted)
        buffer.clear()
    return RunSummary(method, decisions, updates, len(history), accepted, rejected, observations)
