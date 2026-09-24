"""Run one resumable condition of the full Controller V3 campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .paired_experiment import _run_condition


def _load(path: Path, split: str) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"expected a JSON list in {path}")
    return [dict(row, evaluation_split=split) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", required=True)
    parser.add_argument("--condition", choices=("original", "controller"), required=True)
    parser.add_argument("--domain", choices=("searchqa", "alfworld"), required=True)
    parser.add_argument("--train-path", type=Path, required=True)
    parser.add_argument("--heldout-paths", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--api-workers", type=int, default=100)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--api-timeout", type=float, default=120.0)
    parser.add_argument("--alfworld-env-batch-size", type=int, default=1)
    parser.add_argument("--llm-name", default=None)
    parser.add_argument("--enable-thinking", choices=("true", "false"), default="false")
    args = parser.parse_args()

    train = _load(args.train_path, "train")
    heldout: list[dict] = []
    for path in args.heldout_paths:
        heldout.extend(_load(path, path.parent.name))
    if args.domain == "alfworld":
        os.environ["CONTROLLER_V3_ALF_MAX_STEPS"] = str(args.max_steps)
        os.environ["CONTROLLER_V3_ALF_MAX_TOKENS"] = str(args.max_tokens)
        os.environ["CONTROLLER_V3_ALF_API_WORKERS"] = str(args.api_workers)
        os.environ["CONTROLLER_V3_ALF_API_TIMEOUT"] = str(args.api_timeout)
        os.environ["CONTROLLER_V3_ALF_ENV_BATCH_SIZE"] = str(max(1, args.alfworld_env_batch_size))
        from .alfworld_bridges import ALFWORLD_BRIDGE_TYPES

        bridge_types = ALFWORLD_BRIDGE_TYPES
        skill = (
            "# ALFWorld skill\n"
            "Use the current observation to choose one valid <action> command. "
            "Complete the household task and avoid repeating failed actions.\n"
        )
        llm_name = args.llm_name or "alfworld-eval"
    else:
        from .native_bridges import BRIDGE_TYPES

        bridge_types = BRIDGE_TYPES
        skill = "Answer the question from context and use concise <answer> tags."
        llm_name = args.llm_name or "searchqa-eval"

    result = _run_condition(
        args.method,
        args.condition,
        train,
        args.out,
        args.max_tokens,
        batch_size=max(1, args.batch_size),
        heldout_items=heldout,
        skill=skill,
        domain=args.domain,
        bridge_type=bridge_types[args.method],
        llm_name=llm_name,
        api_workers=max(1, args.api_workers),
        enable_thinking=args.enable_thinking == "true",
    )
    (args.out / "condition_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"method": args.method, "condition": args.condition, "out": str(args.out), "resumed": result.get("resumed", False)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
