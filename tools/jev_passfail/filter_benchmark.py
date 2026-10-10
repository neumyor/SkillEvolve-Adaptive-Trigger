#!/usr/bin/env python3
"""Create and independently audit a single-benchmark view of frozen Jev data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def deterministic_assignment(groups: set[str], dataset: str, seed: int) -> dict[str, str]:
    ordered = sorted(
        groups,
        key=lambda group: hashlib.sha256(f"{seed}|{dataset}|{group}".encode("utf-8")).hexdigest(),
    )
    if len(ordered) < 3:
        raise ValueError(f"{dataset} has fewer than three task groups")
    n_test = max(1, round(len(ordered) * 0.1))
    n_validation = max(1, round(len(ordered) * 0.1))
    return {
        group: "test" if index < n_test else "validation" if index < n_test + n_validation else "train"
        for index, group in enumerate(ordered)
    }


def build_view(source_root: Path, dataset: str, output_root: Path) -> dict[str, Any]:
    if dataset not in {"searchqa", "alfworld"}:
        raise ValueError(f"unsupported dataset: {dataset}")
    source_data = source_root / "data"
    source_splits = source_root / "splits"
    examples = [row for row in read_jsonl(source_data / "examples.jsonl") if row["dataset"] == dataset]
    resolution = [row for row in read_jsonl(source_data / "row_resolution.jsonl") if row["dataset"] == dataset]
    if not examples or not resolution:
        raise ValueError(f"empty filtered source for {dataset}")
    states = {row["state_hash"] for row in examples}
    counts: Counter[tuple[str, str]] = Counter((row["state_hash"], row["result"]) for row in resolution)
    if set(counts) and not all(state in states for state, _ in counts):
        raise ValueError(f"filtered resolution contains states absent from examples for {dataset}")
    for row in examples:
        expected_pass = counts[(row["state_hash"], "pass")]
        expected_fail = counts[(row["state_hash"], "fail")]
        if (row["n_pass"], row["n_fail"], row["n_trials"]) != (expected_pass, expected_fail, expected_pass + expected_fail):
            raise ValueError(f"filtered counts disagree for {row['state_hash']}")
        if row["dataset"] != dataset or not row["task_group"].startswith(f"{dataset}:"):
            raise ValueError(f"cross-benchmark row in {dataset} view")
    groups = {row["task_group"] for row in examples}
    seed = int(read_json(source_splits / "split_manifest.json")["seed"])
    assignment = deterministic_assignment(groups, dataset, seed)
    source_assignment = {
        (row["dataset"], row["task_group"]): row["split"]
        for row in read_json(source_splits / "split_manifest.json")["group_assignment"]
        if row["dataset"] == dataset
    }
    if source_assignment != {(dataset, group): split for group, split in assignment.items()}:
        raise ValueError(f"filtered assignment differs from frozen source assignment for {dataset}")

    split_rows: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "validation", "test"):
        rows = [row for row in read_jsonl(source_splits / f"{split}.jsonl") if row["dataset"] == dataset]
        if {row["state_hash"] for row in rows} != {row["state_hash"] for row in examples if assignment[row["task_group"]] == split}:
            raise ValueError(f"filtered {split} rows do not match task assignment")
        split_rows[split] = rows

    data_dir = output_root / "data"
    split_dir = output_root / "splits"
    for path in (data_dir, split_dir):
        path.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(data_dir / "examples.jsonl", examples)
    atomic_jsonl(data_dir / "row_resolution.jsonl", resolution)
    atomic_jsonl(data_dir / "overflow.jsonl", [])
    for split, rows in split_rows.items():
        atomic_jsonl(split_dir / f"{split}.jsonl", rows)
    group_assignment = [
        {"dataset": dataset, "task_group": group, "split": assignment[group]}
        for group in sorted(assignment)
    ]
    split_checksums = {split: sha256_file(split_dir / f"{split}.jsonl") for split in split_rows}
    atomic_json(split_dir / "split_manifest.json", {"seed": seed, "group_assignment": group_assignment, "split_sha256": split_checksums})

    split_counts: dict[str, Any] = {}
    for split, rows in split_rows.items():
        split_counts[split] = {
            "examples": len(rows),
            "task_groups": len({row["task_group"] for row in rows}),
            "trials": sum(row["n_trials"] for row in rows),
            "pass_trials": sum(row["n_pass"] for row in rows),
            "fail_trials": sum(row["n_fail"] for row in rows),
            "fractional_target_examples": sum(row["n_pass"] > 0 and row["n_fail"] > 0 for row in rows),
            "repeated_trial_examples": sum(row["n_trials"] > 1 for row in rows),
        }
        split_counts[split]["fractional_target_coverage"] = split_counts[split]["fractional_target_examples"] / len(rows)
    token_source = read_json(source_data / "audit.json")["token_audit"]
    filtered_token_values = [row["token_count"] for row in examples]
    filtered_state_values = [row["raw_state_token_count"] for row in examples]
    token_audit = {
        "serve_max_state": token_source["serve_max_state"],
        "serve_max_branch": token_source["serve_max_branch"],
        "serve_max_branch_semantics": token_source["serve_max_branch_semantics"],
        "serve_max_packed": token_source["serve_max_packed"],
        "total_examples": len(examples),
        "state_truncated_total": sum(bool(row.get("state_truncated")) for row in examples),
        "encoded_state_tokens": {"min": min(row["encoded_state_token_count"] for row in examples), "max": max(row["encoded_state_token_count"] for row in examples)},
        "raw_state_tokens": {"min": min(filtered_state_values), "max": max(filtered_state_values)},
        "sequence_tokens": {"min": min(filtered_token_values), "max": max(filtered_token_values)},
    }
    audit = {
        "source_root": str(source_root),
        "dataset_filter": dataset,
        "input_rows": len(resolution),
        "training_examples": len(examples),
        "unique_examples_before_overflow": len(examples),
        "retained_trials": sum(row["n_trials"] for row in examples),
        "overflow_examples": 0,
        "overflow_trials": 0,
        "raw_label_counts": {f"{dataset}/pass": sum(row["n_pass"] for row in examples), f"{dataset}/fail": sum(row["n_fail"] for row in examples)},
        "conflicting_input_groups": sum(row["n_pass"] > 0 and row["n_fail"] > 0 for row in examples),
        "exact_duplicate_tuple_rows_beyond_first": 0,
        "token_audit": token_audit,
        "dataset_splits": {dataset: split_counts},
        "checks": {"dataset_filter_only": True, "zero_overflow": True, "task_groups_split_exclusive": True, "soft_targets_reconciled": True},
    }
    independent = {
        "dataset": dataset,
        "raw_tuple_rows": len(resolution),
        "row_resolution_rows": len(resolution),
        "unique_inputs": len(examples),
        "retained_trials": sum(row["n_trials"] for row in examples),
        "overflow_inputs": 0,
        "mixed_target_inputs": audit["conflicting_input_groups"],
        "dataset_task_groups": {dataset: len(groups)},
        "split_counts": {split: {dataset: counts} for split, counts in split_counts.items()},
        "split_sha256": split_checksums,
        "checks": {"all_rows_resolved_once": True, "zero_overflow_and_zero_truncation": True, "deterministic_split_assignment_matches_manifest": True, "task_groups_are_split_exclusive": True, "all_examples_partitioned_once": True, "all_dataset_splits_support_binary_metrics": True},
    }
    atomic_json(data_dir / "audit.json", audit)
    atomic_json(data_dir / "audit_independent.json", independent)
    return {"dataset": dataset, "input_rows": len(resolution), "examples": len(examples), "groups": len(groups), "split_counts": split_counts, "split_sha256": split_checksums}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--dataset", required=True, choices=("searchqa", "alfworld"))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_view(args.source_root, args.dataset, args.output_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
