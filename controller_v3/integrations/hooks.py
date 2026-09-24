"""Callback contract used to embed Controller V3 into existing methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..core import EvidenceCard


@dataclass(frozen=True)
class HostHooks:
    """The four method families need the same two lifecycle callbacks."""

    rollout: Callable[[Mapping[str, Any], str], Mapping[str, Any]]
    update: Callable[[str, list[EvidenceCard], str], tuple[str, str]]


def make_hooks(
    *,
    rollout: Callable[[Mapping[str, Any], str], Mapping[str, Any]],
    update: Callable[[str, list[EvidenceCard], str], tuple[str, str]],
) -> HostHooks:
    """Validate and package host callbacks for a ``MethodAdapter``."""
    if not callable(rollout) or not callable(update):
        raise TypeError("rollout and update must be callable")
    return HostHooks(rollout=rollout, update=update)
