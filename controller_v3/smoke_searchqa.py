"""Offline SearchQA smoke test for all Controller V3 host adapters.

The test exercises the real SearchQA split format and the complete lifecycle
for each adapter.  It uses a deterministic mock rollout and a no-op candidate
attempt, so it validates integration and persistence without model/network
cost.  A real host replaces only the two callbacks with its native rollout and
optimizer invocation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .adapters import ADAPTERS
from .config import runtime_paths


def _load_items(path: Path, limit: int) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        rows = json.load(stream)
    if not isinstance(rows, list):
        raise ValueError(f"expected a JSON list in {path}")
    selected = rows[:limit]
    for index, row in enumerate(selected):
        # Keep the deterministic mock independent of released hash-shaped IDs.
        row.setdefault("_smoke_index", index)
    return selected


def _rollout(item: Mapping[str, Any], skill: str) -> dict[str, Any]:
    # Two repeated failures force one UPDATE in a four-task smoke window.
    idx = int(item.get("_smoke_index", 0))
    failed = idx % 4 in (0, 1)
    return {
        "id": item.get("id", idx),
        "hard": 0 if failed else 1,
        "score": 0.0 if failed else 1.0,
        "success": not failed,
        "feedback": "under-specified answer" if failed else "",
        "trajectory": f"mock rollout with skill chars={len(skill)}",
        "failure_key": "under-specified" if failed else "",
    }


def _attempt(skill: str, cards: list[Any], reason: str) -> tuple[str, str]:
    # Preserve the current artifact while proving that the host callback was
    # invoked with the whole evidence window.
    if len(cards) < 2:
        raise AssertionError("an UPDATE must receive the complete evidence window")
    return skill, "accepted"


def run_smoke(data_path: str | Path, *, limit: int = 8, out_dir: str | Path | None = None) -> dict[str, Any]:
    items = _load_items(Path(data_path), limit)
    if len(items) < 4:
        raise ValueError("SearchQA smoke requires at least four items")
    results: dict[str, Any] = {}
    for name, adapter_cls in ADAPTERS.items():
        state_path = None
        if out_dir is not None:
            state_path = str(Path(out_dir) / f"{name}.jsonl")
        adapter = adapter_cls(batch_size=4)
        summary = adapter.run(
            items,
            skill="# SearchQA smoke skill\nAnswer concisely.",
            rollout=_rollout,
            attempt=_attempt,
            state_path=state_path,
        )
        if summary.observations != (len(items) + 3) // 4:
            raise AssertionError(f"{name}: observation count mismatch: {summary}")
        if summary.updates < 1:
            raise AssertionError(f"{name}: controller never triggered UPDATE: {summary}")
        results[name] = summary.to_dict()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-path",
        type=Path,
        default=runtime_paths().searchqa_eval_root / "data/searchqa_split/train/items.json",
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    report = run_smoke(args.data_path, limit=args.limit, out_dir=args.out_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
