"""Local runtime configuration for external benchmark and method checkouts.

The repository contains only the example configuration.  A user can copy it
to ``config/controller_v3.json`` or set the documented environment variables;
neither file is tracked by Git.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "controller_v3.json"


@dataclass(frozen=True)
class RuntimePaths:
    benchmark_root: Path
    alfworld_eval_root: Path
    searchqa_eval_root: Path
    skillopt_root: Path
    skillopt_ete_root: Path
    gepa_root: Path
    evoskill_root: Path
    trace2skill_root: Path
    llm_config: Path


def _path(value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _load_file(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Controller V3 config: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"Controller V3 config must be a JSON object: {path}")
    return value


def runtime_paths(config_path: str | os.PathLike[str] | None = None) -> RuntimePaths:
    """Resolve external paths from local config, environment, then defaults."""
    selected = Path(config_path or os.environ.get("CONTROLLER_V3_CONFIG", DEFAULT_CONFIG))
    if not selected.is_absolute():
        selected = (ROOT / selected).resolve()
    raw = _load_file(selected)
    values = dict(raw.get("paths", {})) if isinstance(raw.get("paths", {}), Mapping) else {}

    def choose(name: str, env_name: str, default: str) -> Path:
        if os.environ.get(env_name):
            return _path(os.environ[env_name], ROOT)
        if name in values:
            return _path(values[name], selected.parent)
        return _path(default, ROOT)

    benchmark = choose("benchmark_root", "CONTROLLER_V3_BENCHMARK_ROOT", "benchmark")
    alfworld = choose("alfworld_eval_root", "CONTROLLER_V3_ALFWORLD_EVAL_ROOT", str(benchmark / "alfworld-eval"))
    searchqa = choose("searchqa_eval_root", "CONTROLLER_V3_SEARCHQA_EVAL_ROOT", str(benchmark / "searchqa-eval"))
    return RuntimePaths(
        benchmark_root=benchmark,
        alfworld_eval_root=alfworld,
        searchqa_eval_root=searchqa,
        skillopt_root=choose("skillopt_root", "CONTROLLER_V3_SKILLOPT_ROOT", "repos/pulled/SkillOpt"),
        skillopt_ete_root=choose("skillopt_ete_root", "CONTROLLER_V3_SKILLOPT_ETE_ROOT", "repos/SkillOptETE"),
        gepa_root=choose("gepa_root", "CONTROLLER_V3_GEPA_ROOT", "repos/pulled/GEPA"),
        evoskill_root=choose("evoskill_root", "CONTROLLER_V3_EVOSKILL_ROOT", "repos/pulled/EvoSkill"),
        trace2skill_root=choose("trace2skill_root", "CONTROLLER_V3_TRACE2SKILL_ROOT", "repos/pulled/Trace2Skill"),
        llm_config=choose("llm_config", "CONTROLLER_V3_LLM_CONFIG", "benchmark/llm_config.json"),
    )
