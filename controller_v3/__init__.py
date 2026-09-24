"""Reusable Controller V3 timing policy and method adapters.

The package deliberately owns only the *when* decision.  A host method keeps
ownership of rollout, reflection/proposal, candidate application, and its
validation gate.
"""

from .core import (
    AttemptRecord,
    ControllerDecision,
    ControllerV3,
    EvidenceBuffer,
    EvidenceCard,
)

__all__ = [
    "AttemptRecord",
    "ControllerDecision",
    "ControllerV3",
    "EvidenceBuffer",
    "EvidenceCard",
]
