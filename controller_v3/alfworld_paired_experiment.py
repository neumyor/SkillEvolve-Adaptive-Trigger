"""Paired Controller V3 smoke/experiment runner for ALFWorld."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from .alfworld_bridges import ALFWORLD_BRIDGE_TYPES
from .paired_experiment import _paired_summary, run


DEFAULT_TRAIN = Path("repos/pulled/SkillOpt/data/alfworld_path_split/train/items.json")
DEFAULT_VAL = Path("repos/pulled/SkillOpt/data/alfworld_path_split/val/items.json")
DEFAULT_TEST = Path("repos/pulled/SkillOpt/data/alfworld_path_split/test/items.json")
DEFAULT_SKILL = """# ALFWorld skill
Use the current observation to choose one valid <action> command. Complete the
household task and avoid repeating failed actions.
"""


def _task_type(item: dict) -> str:
    value = str(item.get("task_type", "")).strip()
    if value:
        return value
    gamefile = str(item.get("gamefile", ""))
    known = (
        "pick_and_place_simple",
        "pick_two_obj_and_place",
        "look_at_obj_in_light",
        "pick_heat_then_place_in_recep",
        "pick_cool_then_place_in_recep",
        "pick_clean_then_place_in_recep",
    )
    return next((name for name in known if name in gamefile), "other")


def _stratified_items(path: Path, per_type: int, offset: int = 0) -> list[dict]:
    all_items = json.loads(path.read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for item in all_items:
        groups[_task_type(item)].append(item)
    return [
        item
        for task_type in sorted(groups)
        for item in groups[task_type][offset : offset + per_type]
    ]


def _items_by_id(path: Path, item_ids: list[str]) -> list[dict]:
    """Select an explicit, reproducible task population in source order."""
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("explicit ALFWorld task IDs must be unique")
    items = json.loads(path.read_text(encoding="utf-8"))
    by_id = {str(item.get("id", "")): item for item in items}
    missing = [item_id for item_id in item_ids if item_id not in by_id]
    if missing:
        raise ValueError(f"unknown ALFWorld task IDs: {missing}")
    selected = [by_id[item_id] for item_id in item_ids]
    if len(selected) < 2:
        raise ValueError("explicit ALFWorld selection requires at least two tasks")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=Path, default=DEFAULT_TRAIN)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/controller_v3_alfworld_paired"))
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--heldout-path", type=Path, default=DEFAULT_VAL)
    parser.add_argument("--heldout-limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--api-timeout", type=float, default=None,
                        help="per-model-call wall timeout in seconds; omit to use the bridge default")
    parser.add_argument("--stratified-per-type", type=int, default=0,
                        help="select this many tasks per ALFWorld task type in source order")
    parser.add_argument("--stratified-offset", type=int, default=0,
                        help="skip this many source tasks within each type before selection")
    parser.add_argument("--item-ids", nargs="*", default=None,
                        help="explicit train task IDs, e.g. train:0001 train:0006")
    parser.add_argument("--heldout-item-ids", nargs="*", default=None,
                        help="explicit held-out task IDs, e.g. val:0001 val:0004")
    parser.add_argument("--methods", nargs="*", choices=sorted(ALFWORLD_BRIDGE_TYPES))
    args = parser.parse_args()
    if args.max_steps is not None:
        os.environ["CONTROLLER_V3_ALF_MAX_STEPS"] = str(args.max_steps)
    os.environ["CONTROLLER_V3_ALF_MAX_TOKENS"] = str(args.max_tokens)
    if args.api_timeout is not None:
        os.environ["CONTROLLER_V3_ALF_API_TIMEOUT"] = str(args.api_timeout)
    selected_items = None
    selected_heldout_items = None
    if args.item_ids is not None and args.stratified_per_type > 0:
        raise ValueError("choose either --item-ids or --stratified-per-type, not both")
    if args.heldout_item_ids is not None and args.heldout_limit > 0:
        raise ValueError("choose either --heldout-item-ids or --heldout-limit, not both")
    if args.item_ids is not None:
        selected_items = _items_by_id(args.data_path, args.item_ids)
    elif args.stratified_per_type > 0:
        if args.stratified_offset < 0:
            raise ValueError("stratified offset must be non-negative")
        selected_items = _stratified_items(args.data_path, args.stratified_per_type, args.stratified_offset)
        if len(selected_items) < 2:
            raise ValueError("stratified ALFWorld selection requires at least two tasks")
    if args.heldout_item_ids is not None:
        selected_heldout_items = _items_by_id(args.heldout_path, args.heldout_item_ids)
    elif args.heldout_limit > 0 and args.stratified_per_type > 0:
        selected_heldout_items = _stratified_items(args.heldout_path, args.stratified_per_type, args.stratified_offset)
        selected_heldout_items = selected_heldout_items[:args.heldout_limit]
    report = run(
        args.data_path,
        args.out_dir,
        start=args.start,
        limit=args.limit,
        methods=args.methods,
        max_tokens=args.max_tokens,
        batch_size=args.batch_size,
        heldout_path=args.heldout_path,
        heldout_limit=args.heldout_limit,
        bridge_types=ALFWORLD_BRIDGE_TYPES,
        skill=DEFAULT_SKILL,
        domain="alfworld",
        llm_name="alfworld-eval",
        items_override=selected_items,
        heldout_items_override=selected_heldout_items,
    )
    print(json.dumps({"conditions": report, "paired": _paired_summary(report)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
