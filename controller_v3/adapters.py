"""Named adapters for SkillOpt, GEPA, EvoSkill and Trace2Skill.

Each adapter is intentionally thin: the upstream method remains the owner of
its optimizer and evaluator.  These classes provide a stable Controller V3
entry point and a common SearchQA smoke-test contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .core import ControllerV3, EvidenceCard
from .runners import RunSummary, run_controller_loop


@dataclass
class MethodAdapter:
    name: str
    controller: ControllerV3
    batch_size: int = 4

    def run(
        self,
        tasks: Iterable[Mapping[str, Any]],
        *,
        skill: str,
        rollout: Callable[[Mapping[str, Any], str], Mapping[str, Any]],
        attempt: Callable[[str, list[EvidenceCard], str], tuple[str, str]],
        state_path: str | None = None,
    ) -> RunSummary:
        return run_controller_loop(
            method=self.name,
            tasks=tasks,
            skill=skill,
            rollout=rollout,
            attempt=attempt,
            controller=self.controller,
            batch_size=self.batch_size,
            state_path=state_path,
        )


class SkillOptV3Adapter(MethodAdapter):
    def __init__(self, controller: ControllerV3 | None = None, batch_size: int = 4):
        super().__init__("skillopt", controller or ControllerV3(), batch_size)


class GEPAV3Adapter(MethodAdapter):
    def __init__(self, controller: ControllerV3 | None = None, batch_size: int = 4):
        super().__init__("gepa", controller or ControllerV3(), batch_size)


class EvoSkillV3Adapter(MethodAdapter):
    def __init__(self, controller: ControllerV3 | None = None, batch_size: int = 4):
        super().__init__("evoskill", controller or ControllerV3(), batch_size)


class Trace2SkillV3Adapter(MethodAdapter):
    def __init__(self, controller: ControllerV3 | None = None, batch_size: int = 4):
        super().__init__("trace2skill", controller or ControllerV3(), batch_size)


ADAPTERS = {
    "skillopt": SkillOptV3Adapter,
    "gepa": GEPAV3Adapter,
    "evoskill": EvoSkillV3Adapter,
    "trace2skill": Trace2SkillV3Adapter,
}
