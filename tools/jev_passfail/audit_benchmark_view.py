#!/usr/bin/env python3
"""Independent audit of a single-benchmark filtered view."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def assignment(groups: set[str], dataset: str, seed: int) -> dict[str, str]:
    ordered = sorted(groups, key=lambda group: hashlib.sha256(f"{seed}|{dataset}|{group}".encode()).hexdigest())
    n_test = max(1, round(len(ordered) * 0.1))
    n_validation = max(1, round(len(ordered) * 0.1))
    return {group: "test" if i < n_test else "validation" if i < n_test + n_validation else "train" for i, group in enumerate(ordered)}


def audit(source_root: Path, view_root: Path, dataset: str) -> dict[str, Any]:
    source_data = source_root / "data"
    source_splits = source_root / "splits"
    view_data = view_root / "data"
    view_splits = view_root / "splits"
    source_examples = [row for row in read_jsonl(source_data / "examples.jsonl") if row["dataset"] == dataset]
    view_examples = read_jsonl(view_data / "examples.jsonl")
    source_resolution = [row for row in read_jsonl(source_data / "row_resolution.jsonl") if row["dataset"] == dataset]
    view_resolution = read_jsonl(view_data / "row_resolution.jsonl")
    if view_examples != source_examples:
        raise ValueError(f"{dataset}: filtered examples differ from source subset")
    if view_resolution != source_resolution:
        raise ValueError(f"{dataset}: filtered row resolution differs from source subset")
    if any(row["dataset"] != dataset for row in view_examples + view_resolution):
        raise ValueError(f"{dataset}: cross-benchmark row found")
    counts = Counter((row["state_hash"], row["result"]) for row in view_resolution)
    for row in view_examples:
        actual = (counts[(row["state_hash"], "pass")], counts[(row["state_hash"], "fail")])
        expected = (row["n_pass"], row["n_fail"])
        if actual != expected or row["n_trials"] != sum(actual):
            raise ValueError(f"{dataset}: target count mismatch for {row['state_hash']}")
        if row.get("state_truncated") is not False or row["raw_state_token_count"] > 6144 or row["token_count"] > 6144 or row["packed_token_count"] > 6400:
            raise ValueError(f"{dataset}: length/truncation gate failed for {row['state_hash']}")
    if len({row["state_hash"] for row in view_examples}) != len(view_examples):
        raise ValueError(f"{dataset}: duplicate prepared state")
    source_manifest = read_json(source_splits / "split_manifest.json")
    view_manifest = read_json(view_splits / "split_manifest.json")
    groups = {row["task_group"] for row in view_examples}
    expected_assignment = assignment(groups, dataset, int(source_manifest["seed"]))
    listed = {(row["dataset"], row["task_group"]): row["split"] for row in view_manifest["group_assignment"]}
    if listed != {(dataset, group): split for group, split in expected_assignment.items()}:
        raise ValueError(f"{dataset}: split assignment mismatch")
    if int(view_manifest["seed"]) != int(source_manifest["seed"]):
        raise ValueError(f"{dataset}: split seed mismatch")
    split_rows: dict[str, list[dict[str, Any]]] = {}
    split_hashes: dict[str, str] = {}
    all_hashes: list[str] = []
    split_counts: dict[str, Any] = {}
    split_groups: dict[str, set[str]] = {}
    for split in ("train", "validation", "test"):
        path = view_splits / f"{split}.jsonl"
        rows = read_jsonl(path)
        split_rows[split] = rows
        split_hashes[split] = sha256_file(path)
        if split_hashes[split] != view_manifest["split_sha256"][split]:
            raise ValueError(f"{dataset}: {split} checksum mismatch")
        if any(expected_assignment[row["task_group"]] != split for row in rows):
            raise ValueError(f"{dataset}: {split} contains a group assigned elsewhere")
        split_groups[split] = {row["task_group"] for row in rows}
        if not rows or not sum(row["n_pass"] for row in rows) or not sum(row["n_fail"] for row in rows):
            raise ValueError(f"{dataset}: {split} lacks both labels")
        split_counts[split] = {
            "examples": len(rows),
            "task_groups": len(split_groups[split]),
            "trials": sum(row["n_trials"] for row in rows),
            "pass_trials": sum(row["n_pass"] for row in rows),
            "fail_trials": sum(row["n_fail"] for row in rows),
            "fractional_target_examples": sum(row["n_pass"] > 0 and row["n_fail"] > 0 for row in rows),
            "repeated_trial_examples": sum(row["n_trials"] > 1 for row in rows),
        }
        split_counts[split]["fractional_target_coverage"] = split_counts[split]["fractional_target_examples"] / len(rows)
        all_hashes.extend(row["state_hash"] for row in rows)
    if len(all_hashes) != len(set(all_hashes)) or set(all_hashes) != {row["state_hash"] for row in view_examples}:
        raise ValueError(f"{dataset}: split files do not partition examples exactly once")
    if split_groups["train"] & split_groups["validation"] or split_groups["train"] & split_groups["test"] or split_groups["validation"] & split_groups["test"]:
        raise ValueError(f"{dataset}: task group leakage")
    report = {
        "status": "passed",
        "dataset": dataset,
        "source_examples_sha256": sha256_file(source_data / "examples.jsonl"),
        "source_row_resolution_sha256": sha256_file(source_data / "row_resolution.jsonl"),
        "source_split_manifest_sha256": sha256_file(source_splits / "split_manifest.json"),
        "row_resolution_rows": len(view_resolution),
        "unique_inputs": len(view_examples),
        "retained_trials": sum(row["n_trials"] for row in view_examples),
        "mixed_target_inputs": sum(row["n_pass"] > 0 and row["n_fail"] > 0 for row in view_examples),
        "task_groups": len(groups),
        "split_counts": split_counts,
        "split_sha256": split_hashes,
        "checks": {
            "filtered_examples_exact_source_subset": True,
            "filtered_resolution_exact_source_subset": True,
            "zero_overflow_and_zero_truncation": True,
            "soft_targets_reconcile": True,
            "deterministic_split_assignment": True,
            "split_files_match_checksums": True,
            "task_groups_are_split_exclusive": True,
            "all_examples_partitioned_once": True,
            "all_splits_support_binary_metrics": True,
        },
    }
    output = view_data / "audit_independent.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--view-root", type=Path, required=True)
    parser.add_argument("--dataset", required=True, choices=("searchqa", "alfworld"))
    args = parser.parse_args()
    print(json.dumps(audit(args.source_root, args.view_root, args.dataset), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
