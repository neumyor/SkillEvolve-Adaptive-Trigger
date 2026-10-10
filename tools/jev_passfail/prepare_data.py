#!/usr/bin/env python3
"""Build a task-grouped Jev pass/fail dataset from the curated six-tuples."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path) -> list[Any]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_task_prompt(text: str) -> str:
    text = text.strip()
    marker = re.search(r"(?m)^## Task\s*$", text)
    if marker:
        text = text[marker.end() :].strip()
    return text


def question_for_group(dataset: str, text: str) -> str:
    if dataset == "alfworld":
        matches = re.findall(r"(?im)^Your task is to:\s*(.+?)\s*$", text)
        if matches:
            return matches[-1].strip()
        return text.strip()
    matches = re.findall(r"(?im)^## Question\s*\n(.+?)(?=\n## |\Z)", text)
    if matches:
        return matches[-1].strip()
    matches = re.findall(r"(?im)^Question:\s*(.+?)\s*$", text)
    if matches:
        return matches[-1].strip()
    return text.strip()


def norm_group_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def index_source_files(source_root: Path) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    route_root = source_root / "repos/pulled/ExpeToSkill/runs"
    for path in route_root.glob("**/routes/**/manifest.json"):
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        benchmark = ((data.get("config") or {}).get("benchmark") or {})
        dataset = str(benchmark.get("name") or data.get("dataset") or "").lower()
        tasks = data.get("tasks")
        if dataset not in {"searchqa", "alfworld"} or not isinstance(tasks, dict):
            continue
        rel_parts = path.relative_to(source_root).parts
        routes_index = rel_parts.index("routes")
        route_root_parts = list(rel_parts[:routes_index])
        if route_root_parts and route_root_parts[-1] == "run":
            route_root_parts.pop()
        routes.append({
            "path": path,
            "dataset": dataset,
            "split": str(data.get("split") or rel_parts[routes_index + 1]).lower(),
            "route_root": tuple(route_root_parts),
            "tasks": {str(k): str(v) for k, v in tasks.items()},
        })

    skillgen_by_dataset: dict[str, dict[str, dict[str, Any]]] = {"searchqa": {}, "alfworld": {}}
    skillgen_by_index: dict[str, dict[int, dict[str, Any]]] = {"searchqa": {}, "alfworld": {}}
    for dataset in ("searchqa", "alfworld"):
        unit_root = source_root / (
            f"repos/JudgeGateStudy/experiments/direct_v3_20260922_r3/full/"
            f"{dataset}_skillgen_judge/test_skill_units"
        )
        for path in unit_root.glob("*.json"):
            try:
                unit = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            instance_id = str(unit.get("instance_id", ""))
            if instance_id:
                if instance_id in skillgen_by_dataset[dataset]:
                    raise ValueError(f"duplicate SkillGEN instance_id: {dataset}/{instance_id}")
                skillgen_by_dataset[dataset][instance_id] = {"path": path, "unit": unit}
            prefix = path.name.split("_", 1)[0]
            if prefix.isdigit():
                index = int(prefix)
                if index in skillgen_by_index[dataset]:
                    raise ValueError(f"duplicate SkillGEN unit index: {dataset}/{index}")
                skillgen_by_index[dataset][index] = {"path": path, "unit": unit}

    return {
        "routes": routes,
        "skillgen": skillgen_by_dataset,
        "skillgen_by_index": skillgen_by_index,
    }


def get_unit_task(dataset: str, unit: dict[str, Any]) -> str:
    if dataset == "alfworld":
        metadata = unit.get("metadata") or {}
        initial = metadata.get("initial_observation")
        if initial:
            return str(initial).strip()
    for message in unit.get("messages", []):
        if message.get("role") == "user" and message.get("content"):
            return clean_task_prompt(str(message["content"]))
    raise ValueError("skillgen unit has no task text")


def row_task_text(
    dataset: str,
    method: str,
    task_id: str,
    artifact: dict[str, Any],
    source_root: Path,
    source_index: dict[str, Any],
) -> tuple[str, str, list[str]]:
    if method.startswith("ExpeToSkill"):
        values: set[str] = set()
        source_paths: set[str] = set()
        for score_rel in artifact.get("sources", []):
            score_parts = Path(score_rel).parts
            lowered_parts = {part.lower() for part in score_parts}
            if "admission" in lowered_parts:
                score_split = "admission"
            elif "preflight" in lowered_parts:
                score_split = "val"
            elif any(
                part == "final" or part == "final_comparison" or part.startswith("final-")
                for part in lowered_parts
            ):
                score_split = "final"
            else:
                score_split = None
            for route in source_index["routes"]:
                route_root = route["route_root"]
                if route["dataset"] != dataset or score_parts[: len(route_root)] != route_root:
                    continue
                if score_split and route["split"] != score_split:
                    continue
                route_key = task_id
                if route_key in route["tasks"]:
                    values.add(route["tasks"][route_key])
                    source_paths.add(route["path"].relative_to(source_root).as_posix())
        if len(values) == 1:
            return next(iter(values)), "expe_route_dataset_run", sorted(source_paths)
        raise ValueError(f"ExpeToSkill {dataset}/{task_id}: exact route lookup yielded {len(values)} values")

    if method == "GEPA":
        match = re.fullmatch(r"index:(\d+)", task_id)
        if not match:
            raise ValueError(f"GEPA task ID is not an index: {task_id}")
        index = int(match.group(1))
        entry = source_index["skillgen_by_index"][dataset].get(index)
        if entry is None:
            raise ValueError(f"GEPA index {index} has no paired SkillGEN input unit")
        return get_unit_task(dataset, entry["unit"]), "gepa_index_paired_skillgen_unit", [
            entry["path"].relative_to(source_root).as_posix()
        ]

    if method in {"SkillGEN", "RethinkSkill", "SkillOpt"}:
        entry = source_index["skillgen"][dataset].get(task_id)
        if entry is None and method == "SkillGEN" and task_id.isdigit():
            entry = source_index["skillgen_by_index"][dataset].get(int(task_id))
        if entry is None and dataset == "alfworld":
            match = re.fullmatch(r"(?:test|index):(\d+)", task_id)
            if match:
                entry = source_index["skillgen_by_index"][dataset].get(int(match.group(1)))
        if entry is None:
            raise ValueError(f"{method} task {dataset}/{task_id} has no paired SkillGEN input unit")
        source = {
            "SkillGEN": "skillgen_unit_user_message",
            "RethinkSkill": "rethink_case_id_paired_skillgen_unit",
            "SkillOpt": "skillopt_instance_id_paired_skillgen_unit",
        }[method]
        return get_unit_task(dataset, entry["unit"]), source, [
            entry["path"].relative_to(source_root).as_posix()
        ]

    raise ValueError(f"no source task text for {dataset}/{method}/{task_id}")


def assign_splits(rows: list[dict[str, Any]], seed: int) -> dict[str, list[dict[str, Any]]]:
    groups_by_dataset: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        groups_by_dataset[row["dataset"]].add(row["task_group"])
    assignment: dict[tuple[str, str], str] = {}
    for dataset, groups in groups_by_dataset.items():
        ordered = sorted(groups, key=lambda group: sha256(f"{seed}|{dataset}|{group}"))
        n = len(ordered)
        if n < 3:
            raise ValueError(f"{dataset} has only {n} task groups; at least 3 are required")
        n_test = max(1, round(n * 0.1))
        n_val = max(1, round(n * 0.1))
        for i, group in enumerate(ordered):
            split = "test" if i < n_test else "validation" if i < n_test + n_val else "train"
            assignment[(dataset, group)] = split
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for row in rows:
        splits[assignment[(row["dataset"], row["task_group"])]].append(row)
    return splits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tuples", type=Path, required=True)
    ap.add_argument("--skills", type=Path, required=True)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--service-dir", type=Path, required=True)
    ap.add_argument("--base-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--max-state", type=int)
    ap.add_argument(
        "--max-branch",
        type=int,
        help="Jev causal-row cap for state plus question branch",
    )
    ap.add_argument("--max-packed", type=int)
    ap.add_argument("--require-zero-overflow", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="resolve and encode one row per dataset/method; do not split")
    args = ap.parse_args()
    sys.path.insert(0, str(args.service_dir.resolve()))
    from model import (
        ContextOverflow,
        SERVE_MAX_BRANCH,
        SERVE_MAX_PACKED,
        SERVE_MAX_STATE,
        encode_record,
        load_tokenizer,
        tokenizer_decision_meta,
        user_tokens,
    )
    args.max_state = SERVE_MAX_STATE if args.max_state is None else args.max_state
    args.max_branch = SERVE_MAX_BRANCH if args.max_branch is None else args.max_branch
    args.max_packed = SERVE_MAX_PACKED if args.max_packed is None else args.max_packed
    if min(args.max_state, args.max_branch, args.max_packed) <= 0:
        ap.error("token limits must all be positive")

    rows = read_jsonl(args.tuples)
    if args.smoke:
        selected: list[Any] = []
        seen_sources: set[tuple[str, str]] = set()
        for row in rows:
            if isinstance(row, list) and len(row) == 6:
                source_key = (str(row[0]), str(row[2]))
                if source_key not in seen_sources:
                    selected.append(row)
                    seen_sources.add(source_key)
        rows = selected
    skill_manifest = read_json(args.skills / "manifest.json")
    artifacts = {item["file"]: item for item in skill_manifest["artifacts"]}
    skill_cache: dict[str, str] = {}
    source_index = index_source_files(args.source_root)
    aggregated: dict[str, dict[str, Any]] = {}
    row_resolution: list[dict[str, Any]] = []
    task_source_counts: Counter[str] = Counter()
    raw_counts: Counter[str] = Counter()
    raw_tuple_counts: Counter[str] = Counter()

    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError(f"line {line_number}: expected a six-element array")
        dataset, llm, method, skill_path, task_id, result = map(str, row)
        if dataset not in {"searchqa", "alfworld"} or result not in {"pass", "fail"}:
            raise ValueError(f"line {line_number}: invalid dataset/result")
        artifact = artifacts.get(skill_path)
        if artifact is None:
            raise ValueError(f"line {line_number}: missing skill manifest entry {skill_path}")
        if skill_path not in skill_cache:
            skill_cache[skill_path] = (args.skills.parent / skill_path).read_text(encoding="utf-8")
            if sha256(skill_cache[skill_path]) != artifact["sha256"]:
                raise ValueError(f"skill hash mismatch: {skill_path}")
            if len(skill_cache[skill_path].encode("utf-8")) != artifact["bytes"]:
                raise ValueError(f"skill byte count mismatch: {skill_path}")

        task_text, task_source, task_source_files = row_task_text(
            dataset, method, task_id, artifact, args.source_root, source_index
        )
        task_text = clean_task_prompt(task_text)
        if not task_text:
            raise ValueError(f"line {line_number}: empty task text")
        task_source_counts[task_source] += 1
        raw_counts[f"{dataset}/{result}"] += 1
        raw_tuple_counts[sha256(json.dumps(row, ensure_ascii=False, separators=(",", ":")))] += 1
        state = (
            f"Dataset: {dataset}\n"
            f"Target agent model: {llm}\n"
            f"\nSkill:\n{skill_cache[skill_path]}\n"
            f"\nTask:\n{task_text}"
        )
        task_question = question_for_group(dataset, task_text)
        task_group = f"{dataset}:{sha256(norm_group_text(task_question))}"
        state_hash = sha256(state)
        row_resolution.append({
            "source_line": line_number,
            "dataset": dataset,
            "llm": llm,
            "method": method,
            "task_id": task_id,
            "skill_file": skill_path,
            "skill_sha256": artifact["sha256"],
            "skill_source_files": artifact.get("sources", []),
            "task_resolver": task_source,
            "task_source_files": task_source_files,
            "task_group": task_group,
            "state_hash": state_hash,
            "result": result,
        })
        success = int(result == "pass")
        item = aggregated.get(state_hash)
        if item is None:
            item = {
                "state": state,
                "state_hash": state_hash,
                "dataset": dataset,
                "llm": llm,
                "task_group": task_group,
                "skill_file": skill_path,
                "skill_sha256": artifact["sha256"],
                "task_id_examples": [],
                "source_lines": [],
                "methods": [],
                "task_sources": [],
                "task_source_files": [],
                "skill_source_files": [],
                "n_pass": 0,
                "n_fail": 0,
            }
            aggregated[state_hash] = item
        elif item["task_group"] != task_group:
            raise ValueError(f"identical input maps to different task groups: {state_hash}")
        item["n_pass" if success else "n_fail"] += 1
        item["source_lines"].append(line_number)
        if task_id not in item["task_id_examples"]:
            item["task_id_examples"].append(task_id)
        if method not in item["methods"]:
            item["methods"].append(method)
        if task_source not in item["task_sources"]:
            item["task_sources"].append(task_source)
        for path in task_source_files:
            if path not in item["task_source_files"]:
                item["task_source_files"].append(path)
        for path in artifact.get("sources", []):
            if path not in item["skill_source_files"]:
                item["skill_source_files"].append(path)

    examples = list(aggregated.values())
    for item in examples:
        item["n_trials"] = item["n_pass"] + item["n_fail"]
        item["target_probs"] = [item["n_fail"] / item["n_trials"], item["n_pass"] / item["n_trials"]]

    tok = load_tokenizer(str(args.base_dir))
    tok_meta = tokenizer_decision_meta(tok)
    token_counts: list[int] = []
    state_token_counts: list[int] = []
    raw_state_token_counts: list[int] = []
    examples_by_dataset = Counter()
    retained_examples: list[dict[str, Any]] = []
    overflow_examples: list[dict[str, Any]] = []
    for item in examples:
        rec = {
            "state": item["state"],
            "questions": [{
                "type": "noul",
                "instr": "Will one run of the target agent complete this task successfully when using the provided skill?",
                "options": ["false", "true"],
                "label": 0,
                "target_probs": item["target_probs"],
            }],
        }
        raw_state_tokens = len(tok_meta["chat_head_ids"]) + len(user_tokens(tok, item["state"]))
        try:
            enc = encode_record(
                tok,
                rec,
                max_state=args.max_state,
                max_branch=args.max_branch,
                strict=True,
            )
            total_tokens = len(enc["causal_rows"][0])
            packed_tokens = len(enc["ids"])
            if packed_tokens > args.max_packed:
                raise ContextOverflow(
                    f"packed record exceeds {args.max_packed} tokens: {packed_tokens}"
                )
        except ContextOverflow as exc:
            preview = encode_record(
                tok,
                rec,
                max_state=args.max_state,
                max_branch=args.max_branch,
                strict=False,
            )
            preview_len = len(preview["causal_rows"][0])
            overflow_examples.append({
                "state_hash": item["state_hash"],
                "dataset": item["dataset"],
                "task_group": item["task_group"],
                "task_id_examples": item["task_id_examples"],
                "source_lines": item["source_lines"],
                "skill_file": item["skill_file"],
                "llm": item["llm"],
                "methods": item["methods"],
                "task_sources": item["task_sources"],
                "task_source_files": item["task_source_files"],
                "n_pass": item["n_pass"],
                "n_fail": item["n_fail"],
                "n_trials": item["n_trials"],
                "raw_state_tokens": raw_state_tokens,
                "preview_encoded_state_tokens": len(preview["state_ids"]),
                "preview_sequence_tokens": preview_len,
                "preview_packed_tokens": len(preview["ids"]),
                "reason": str(exc),
            })
            continue

        token_counts.append(total_tokens)
        state_token_counts.append(len(enc["state_ids"]))
        raw_state_token_counts.append(raw_state_tokens)
        examples_by_dataset[item["dataset"]] += 1
        item["token_count"] = total_tokens
        item["packed_token_count"] = packed_tokens
        item["raw_state_token_count"] = raw_state_tokens
        item["encoded_state_token_count"] = len(enc["state_ids"])
        item["state_truncated"] = False
        retained_examples.append(item)

    if not retained_examples:
        raise ValueError("no complete input fits the Jev serving limits")
    if sum(item["n_trials"] for item in examples) != len(rows):
        raise AssertionError("aggregation did not preserve every input row as one trial")

    if args.require_zero_overflow and overflow_examples:
        args.out.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.out / "examples.jsonl", retained_examples)
        write_jsonl(args.out / "row_resolution.jsonl", row_resolution)
        write_jsonl(args.out / "overflow.jsonl", overflow_examples)
        raise ValueError(
            f"zero-overflow gate failed: {len(overflow_examples)} unique inputs "
            f"carrying {sum(item['n_trials'] for item in overflow_examples)} trials exceed limits"
        )

    if args.smoke:
        args.out.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.out / "examples.jsonl", retained_examples)
        write_jsonl(args.out / "row_resolution.jsonl", row_resolution)
        write_jsonl(args.out / "overflow.jsonl", overflow_examples)
        report = {
            "mode": "smoke",
            "input_rows": len(rows),
            "encoded_examples": len(retained_examples),
            "overflow_examples": len(overflow_examples),
            "task_source_counts": dict(task_source_counts),
            "dataset_method_sources": sorted({
                (row["dataset"], row["method"]) for row in row_resolution
            }),
            "checks": {
                "conflicting_rows_preserved": sum(item["n_trials"] for item in retained_examples)
                    + sum(item["n_trials"] for item in overflow_examples) == len(rows),
                "retained_inputs_fit_strict_limits": all(not item["state_truncated"] for item in retained_examples),
            },
        }
        write_json(args.out / "audit.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    examples = retained_examples
    splits = assign_splits(examples, args.seed)
    split_group_sets = {name: {(r["dataset"], r["task_group"]) for r in values} for name, values in splits.items()}
    if split_group_sets["train"] & split_group_sets["validation"]:
        raise AssertionError("task leakage between train and validation")
    if split_group_sets["train"] & split_group_sets["test"]:
        raise AssertionError("task leakage between train and test")
    if split_group_sets["validation"] & split_group_sets["test"]:
        raise AssertionError("task leakage between validation and test")

    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "examples.jsonl", examples)
    write_jsonl(args.out / "row_resolution.jsonl", row_resolution)
    write_jsonl(args.out / "overflow.jsonl", overflow_examples)
    for name, values in splits.items():
        write_jsonl(args.out / f"{name}.jsonl", values)
    conflict_groups = [item for item in examples if item["n_pass"] and item["n_fail"]]
    dataset_splits: dict[str, Any] = {}
    for dataset in sorted({item["dataset"] for item in examples}):
        dataset_splits[dataset] = {
            split: {
                "examples": sum(x["dataset"] == dataset for x in vals),
                "task_groups": len({x["task_group"] for x in vals if x["dataset"] == dataset}),
                "trials": sum(x["n_trials"] for x in vals if x["dataset"] == dataset),
                "pass_trials": sum(x["n_pass"] for x in vals if x["dataset"] == dataset),
                "fail_trials": sum(x["n_fail"] for x in vals if x["dataset"] == dataset),
                "fractional_target_examples": sum(
                    x["dataset"] == dataset and x["n_pass"] > 0 and x["n_fail"] > 0
                    for x in vals
                ),
                "fractional_target_coverage": (
                    sum(x["dataset"] == dataset and x["n_pass"] > 0 and x["n_fail"] > 0 for x in vals)
                    / max(1, sum(x["dataset"] == dataset for x in vals))
                ),
                "repeated_trial_examples": sum(
                    x["dataset"] == dataset and x["n_trials"] > 1 for x in vals
                ),
            }
            for split, vals in splits.items()
        }
    overflow_by_dataset: dict[str, Any] = {}
    for dataset in sorted({item["dataset"] for item in examples} | {item["dataset"] for item in overflow_examples}):
        values = [item for item in overflow_examples if item["dataset"] == dataset]
        lengths = sorted(item["raw_state_tokens"] for item in values)
        overflow_by_dataset[dataset] = {
            "examples": len(values),
            "task_groups": len({item["task_group"] for item in values}),
            "trials": sum(item["n_trials"] for item in values),
            "reason_counts": dict(Counter(item["reason"].split(":")[0] for item in values)),
            "raw_state_tokens": (
                {
                    "min": lengths[0],
                    "p50": lengths[len(lengths) // 2],
                    "p95": lengths[math.ceil(len(lengths) * 0.95) - 1],
                    "max": lengths[-1],
                }
                if lengths else None
            ),
        }
    token_sorted = sorted(token_counts)
    split_checksums = {
        name: sha256((args.out / f"{name}.jsonl").read_text(encoding="utf-8"))
        for name in splits
    }
    split_assignment = [
        {"dataset": dataset, "task_group": group, "split": split}
        for split, values in splits.items()
        for dataset, group in sorted({(x["dataset"], x["task_group"]) for x in values})
    ]
    write_json(args.out / "split_manifest.json", {
        "seed": args.seed,
        "group_assignment": split_assignment,
        "split_sha256": split_checksums,
    })
    duplicate_tuple_groups = [
        {"tuple_hash": key, "count": count}
        for key, count in raw_tuple_counts.items()
        if count > 1
    ]
    report = {
        "seed": args.seed,
        "input_rows": len(rows),
        "training_examples": len(examples),
        "unique_examples_before_overflow": len(examples) + len(overflow_examples),
        "retained_trials": sum(item["n_trials"] for item in examples),
        "overflow_examples": len(overflow_examples),
        "overflow_trials": sum(item["n_trials"] for item in overflow_examples),
        "overflow_by_dataset": overflow_by_dataset,
        "exact_duplicate_tuple_rows_beyond_first": sum(count - 1 for count in raw_tuple_counts.values()),
        "exact_duplicate_tuple_groups": duplicate_tuple_groups,
        "conflicting_input_groups": len(conflict_groups),
        "conflicting_groups_examples": [
            {"state_hash": x["state_hash"], "n_pass": x["n_pass"], "n_fail": x["n_fail"]}
            for x in conflict_groups[:100]
        ],
        "raw_label_counts": dict(raw_counts),
        "task_source_counts": dict(task_source_counts),
        "dataset_splits": dataset_splits,
        "token_audit": {
            "serve_max_state": args.max_state,
            "serve_max_branch": args.max_branch,
            "serve_max_branch_semantics": "state_tokens_plus_question_branch_tokens",
            "serve_max_packed": args.max_packed,
            "examples_by_dataset": dict(examples_by_dataset),
            "strict_overflow_examples_by_dataset": dict(Counter(x["dataset"] for x in overflow_examples)),
            "state_truncated_total": 0,
            "total_examples": len(examples),
            "sequence_tokens": {
                "min": min(token_counts),
                "p50": token_sorted[len(token_sorted) // 2],
                "p95": token_sorted[math.ceil(len(token_sorted) * 0.95) - 1],
                "max": max(token_counts),
                "mean": statistics.mean(token_counts),
            },
            "encoded_state_tokens": {
                "min": min(state_token_counts),
                "max": max(state_token_counts),
                "mean": statistics.mean(state_token_counts),
            },
            "raw_state_tokens": {
                "min": min(raw_state_token_counts),
                "max": max(raw_state_token_counts),
                "mean": statistics.mean(raw_state_token_counts),
            },
            "longest_examples": [
                {
                    "state_hash": item["state_hash"],
                    "dataset": item["dataset"],
                    "task_group": item["task_group"],
                    "task_id_examples": item["task_id_examples"],
                    "sequence_tokens": item["token_count"],
                    "state_tokens": item["encoded_state_token_count"],
                    "packed_tokens": item["packed_token_count"],
                }
                for item in sorted(examples, key=lambda x: x["token_count"], reverse=True)[:20]
            ],
        },
        "checks": {
            "all_rows_have_skill": True,
            "all_rows_have_task": True,
            "all_task_groups_are_split_exclusive": True,
            "features_exclude_skillevolve_and_result": True,
            "conflicts_preserved_as_soft_targets": True,
            "all_retained_examples_strictly_fit_serving_limits": True,
            "all_input_rows_reconciled_to_retained_or_overflow": (
                sum(item["n_trials"] for item in examples)
                + sum(item["n_trials"] for item in overflow_examples)
                == len(rows)
            ),
        },
    }
    write_json(args.out / "audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
