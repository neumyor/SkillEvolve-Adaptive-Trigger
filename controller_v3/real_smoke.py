"""Real-LLM SearchQA smoke test for all four Controller V3 bridges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .llm import build_llm
from .config import runtime_paths
from .native_bridges import BRIDGE_TYPES


def run(data_path: Path, out_dir: Path, limit: int = 2, start: int = 0) -> dict:
    items = json.loads(data_path.read_text(encoding="utf-8"))[start : start + limit]
    if len(items) < 2:
        raise ValueError("real smoke requires at least two SearchQA items")
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for method, bridge_type in BRIDGE_TYPES.items():
        llm = build_llm(max_tokens=512)
        bridge = bridge_type(llm)
        result = bridge.run_window(items, "Answer the question from context and use concise <answer> tags.")
        payload = {"method": method, "items": len(items), "llm_model": llm.model, "api_calls": llm.usage.api_calls, "usage": llm.usage.to_dict(), "result": result}
        (out_dir / f"{method}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report[method] = {"items": len(items), "controller_action": result["decision"], "api_calls": llm.usage.api_calls, "update": result["update"]}
    (out_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/controller_v3_real_smoke"))
    parser.add_argument("--data-path", type=Path, default=runtime_paths().searchqa_eval_root / "data/searchqa_split/train/items.json")
    args = parser.parse_args()
    print(json.dumps(run(args.data_path, args.out_dir, args.limit, args.start), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
