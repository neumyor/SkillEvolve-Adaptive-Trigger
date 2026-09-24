from __future__ import annotations

import json
from pathlib import Path

from controller_v3.config import runtime_paths


def test_runtime_paths_load_local_config(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "controller.json"
    config.write_text(json.dumps({"paths": {"gepa_root": "external/gepa", "llm_config": "secrets/llm.json"}}))
    monkeypatch.setenv("CONTROLLER_V3_CONFIG", str(config))
    paths = runtime_paths()
    assert paths.gepa_root == (tmp_path / "external/gepa").resolve()
    assert paths.llm_config == (tmp_path / "secrets/llm.json").resolve()


def test_runtime_paths_allow_environment_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONTROLLER_V3_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setenv("CONTROLLER_V3_ALFWORLD_EVAL_ROOT", str(tmp_path / "alfworld"))
    assert runtime_paths().alfworld_eval_root == (tmp_path / "alfworld").resolve()
