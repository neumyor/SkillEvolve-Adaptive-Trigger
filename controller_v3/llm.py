"""Small real-LLM client used by the Controller V3 SearchQA smoke run."""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from .config import runtime_paths

_SEARCHQA_SRC = runtime_paths().searchqa_eval_root / "src"
if str(_SEARCHQA_SRC) not in sys.path:
    sys.path.insert(0, str(_SEARCHQA_SRC))
from searchqa_eval.agent import OpenAIChatAgent  # noqa: E402


def load_llm_config(name: str = "searchqa-eval") -> dict[str, str]:
    path = runtime_paths().llm_config
    data = json.loads(path.read_text(encoding="utf-8"))
    cfg = data.get(name) or data.get("default")
    if not isinstance(cfg, Mapping):
        raise ValueError(f"missing LLM configuration: {name}")
    required = ("base_url", "model", "api_key")
    if any(not cfg.get(key) for key in required):
        raise ValueError(f"incomplete LLM configuration: {name}")
    return {key: str(cfg[key]) for key in required}


def build_llm(
    name: str = "searchqa-eval",
    *,
    max_tokens: int = 512,
    enable_thinking: bool | None = False,
) -> OpenAIChatAgent:
    cfg = load_llm_config(name)
    return OpenAIChatAgent(
        base_url=cfg["base_url"],
        model=cfg["model"],
        api_key=cfg["api_key"],
        temperature=0.0,
        max_tokens=max_tokens,
        timeout=120.0,
        retries=2,
        enable_thinking=enable_thinking,
    )


def call_json(
    llm: OpenAIChatAgent,
    system: str,
    user: str,
    *,
    stage: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    # LedgerLLM accepts the optional accounting fields; native clients keep
    # their original two-argument interface.
    try:
        raw, usage = llm.respond(system, user, stage=stage, metadata=metadata)
    except TypeError:
        raw, usage = llm.respond(system, user)
    # The benchmark agent restores separate reasoning as a think block.
    # Only the final answer is structured output; reasoning may quote JSON.
    text = raw.rsplit("</think>", 1)[-1].strip()
    if "<think>" in text:
        text = ""
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                value = {}
        else:
            value = {}
    return (value if isinstance(value, dict) else {}), usage, raw
