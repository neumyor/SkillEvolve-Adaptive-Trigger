#!/usr/bin/env python3
"""Independently reconcile prepared Jev data, source rows, and task splits."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[Any]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def deterministic_assignment(
    groups_by_dataset: dict[str, set[str]], seed: int
) -> dict[tuple[str, str], str]:
    assignment: dict[tuple[str, str], str] = {}
    for dataset, groups in groups_by_dataset.items():
        ordered = sorted(
            groups,
            key=lambda group: hashlib.sha256(
                f"{seed}|{dataset}|{group}".encode("utf-8")
            ).hexdigest(),
        )
        if len(ordered) < 3:
            raise ValueError(f"{dataset} has fewer than three task groups")
        n_test = max(1, round(len(ordered) * 0.1))
        n_validation = max(1, round(len(ordered) * 0.1))
        for index, group in enumerate(ordered):
            split = (
                "test" if index < n_test
                else "validation" if index < n_test + n_validation
                else "train"
            )
            assignment[(dataset, group)] = split
    return assignment


def audit(raw_root: Path, data_dir: Path) -> dict[str, Any]:
    tuples = read_jsonl(raw_root / "skill_task_result_six_tuples.jsonl")
    resolution = read_jsonl(data_dir / "row_resolution.jsonl")
    examples = read_jsonl(data_dir / "examples.jsonl")
    overflows = read_jsonl(data_dir / "overflow.jsonl")
    generated_audit = read_json(data_dir / "audit.json")
    split_manifest = read_json(data_dir / "split_manifest.json")
    skill_manifest = read_json(raw_root / "skill_files/manifest.json")
    artifacts = {item["file"]: item for item in skill_manifest["artifacts"]}

    if len(tuples) != generated_audit["input_rows"]:
        raise ValueError("source tuple count disagrees with preparation audit")
    if len(resolution) != len(tuples):
        raise ValueError("row-resolution count does not match source tuple count")
    if [row["source_line"] for row in resolution] != list(range(1, len(tuples) + 1)):
        raise ValueError("source_line mapping is not a complete ordered partition")
    if not examples:
        raise ValueError("no prepared examples")

    raw_duplicates = Counter(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in tuples
    )
    raw_label_counts: Counter[str] = Counter()
    counts_by_state: dict[str, Counter[str]] = defaultdict(Counter)
    groups_by_state: dict[str, set[str]] = defaultdict(set)
    rows_by_state: dict[str, list[int]] = defaultdict(list)
    skill_hashes: dict[str, str] = {}

    for line_number, (source, resolved) in enumerate(zip(tuples, resolution), start=1):
        if not isinstance(source, list) or len(source) != 6:
            raise ValueError(f"source row {line_number} is not a six-tuple")
        dataset, llm, method, skill_file, task_id, result = map(str, source)
        for field, expected in (
            ("dataset", dataset),
            ("llm", llm),
            ("method", method),
            ("skill_file", skill_file),
            ("task_id", task_id),
            ("result", result),
        ):
            if resolved.get(field) != expected:
                raise ValueError(f"source row {line_number} mismatches resolution field {field}")
        if resolved.get("source_line") != line_number:
            raise ValueError(f"source row {line_number} has an incorrect source_line")
        state_hash = str(resolved.get("state_hash") or "")
        task_group = str(resolved.get("task_group") or "")
        if not state_hash or not task_group.startswith(f"{dataset}:"):
            raise ValueError(f"source row {line_number} lacks canonical input/task identity")
        if not resolved.get("task_source_files"):
            raise ValueError(f"source row {line_number} lacks a task source artifact")
        if skill_file not in artifacts:
            raise ValueError(f"source row {line_number} has no skill manifest entry")
        artifact = artifacts[skill_file]
        if resolved.get("skill_sha256") != artifact["sha256"]:
            raise ValueError(f"source row {line_number} has a skill hash mismatch")
        if skill_file not in skill_hashes:
            skill_path = raw_root / skill_file
            raw_skill = skill_path.read_bytes()
            actual = sha256_bytes(raw_skill)
            if actual != artifact["sha256"] or len(raw_skill) != artifact["bytes"]:
                raise ValueError(f"skill artifact changed or is incomplete: {skill_file}")
            skill_hashes[skill_file] = actual
        raw_label_counts[f"{dataset}/{result}"] += 1
        counts_by_state[state_hash][result] += 1
        groups_by_state[state_hash].add(task_group)
        rows_by_state[state_hash].append(line_number)

    example_by_hash: dict[str, dict[str, Any]] = {}
    groups_by_dataset: dict[str, set[str]] = defaultdict(set)
    for item in examples:
        state_hash = str(item.get("state_hash") or "")
        if not state_hash or state_hash in example_by_hash:
            raise ValueError("prepared input hashes are empty or duplicated")
        example_by_hash[state_hash] = item
        dataset = str(item["dataset"])
        task_group = str(item["task_group"])
        groups_by_dataset[dataset].add(task_group)
        if len(groups_by_state.get(state_hash, set())) != 1:
            raise ValueError(f"source rows do not resolve to one task group: {state_hash}")
        state = str(item["state"])
        if sha256_bytes(state.encode("utf-8")) != state_hash:
            raise ValueError(f"serialized input hash mismatch: {state_hash}")
        prefix = f"Dataset: {dataset}\nTarget agent model: {item['llm']}\n\nSkill:\n"
        task_marker = "\n\nTask:\n"
        if not state.startswith(prefix) or task_marker not in state:
            raise ValueError(f"serialized state violates the input contract: {state_hash}")
        skill_text, task_text = state[len(prefix):].split(task_marker, 1)
        skill_file = str(item["skill_file"])
        if skill_text != (raw_root / skill_file).read_text(encoding="utf-8"):
            raise ValueError(f"serialized state does not contain the complete skill: {state_hash}")
        if not task_text.strip():
            raise ValueError(f"serialized state has an empty task: {state_hash}")
        n_pass = counts_by_state[state_hash]["pass"]
        n_fail = counts_by_state[state_hash]["fail"]
        n_trials = n_pass + n_fail
        if (item["n_pass"], item["n_fail"], item["n_trials"]) != (n_pass, n_fail, n_trials):
            raise ValueError(f"soft-target counts do not reconcile: {state_hash}")
        expected_probs = [n_fail / n_trials, n_pass / n_trials]
        if any(abs(float(a) - b) > 1e-12 for a, b in zip(item["target_probs"], expected_probs)):
            raise ValueError(f"soft target does not match pass/fail mass: {state_hash}")
        if item.get("state_truncated") is not False:
            raise ValueError(f"retained input was truncated: {state_hash}")

    if set(counts_by_state) != set(example_by_hash):
        raise ValueError("source states and prepared examples are not a complete match")
    if overflows:
        raise ValueError(f"zero-overflow gate failed with {len(overflows)} inputs")
    if sum(item["n_trials"] for item in examples) != len(tuples):
        raise ValueError("retained trial total does not match source row count")
    if sum(item["n_trials"] for item in overflows) != generated_audit["overflow_trials"]:
        raise ValueError("overflow trial total does not match preparation audit")

    token_audit = generated_audit["token_audit"]
    max_state = int(token_audit["serve_max_state"])
    max_causal_row = int(token_audit["serve_max_branch"])
    max_packed = int(token_audit["serve_max_packed"])
    for item in examples:
        if item["raw_state_token_count"] > max_state:
            raise ValueError(f"state token limit exceeded: {item['state_hash']}")
        if item["token_count"] > max_causal_row or item["packed_token_count"] > max_packed:
            raise ValueError(f"causal-row or packed token limit exceeded: {item['state_hash']}")

    expected_splits = deterministic_assignment(groups_by_dataset, int(split_manifest["seed"]))
    listed_assignment = {
        (str(row["dataset"]), str(row["task_group"])): str(row["split"])
        for row in split_manifest["group_assignment"]
    }
    if listed_assignment != expected_splits:
        raise ValueError("split manifest does not match the registered deterministic rule")
    split_rows = {name: read_jsonl(data_dir / f"{name}.jsonl") for name in ("train", "validation", "test")}
    split_groups: dict[str, set[tuple[str, str]]] = {}
    assigned_states: Counter[str] = Counter()
    split_counts: dict[str, Any] = {}
    for split, values in split_rows.items():
        groups: set[tuple[str, str]] = set()
        stats: dict[str, Any] = {}
        for row in values:
            state_hash = str(row["state_hash"])
            if example_by_hash.get(state_hash) != row:
                raise ValueError(f"split row differs from canonical input: {state_hash}")
            if expected_splits[(str(row["dataset"]), str(row["task_group"]))] != split:
                raise ValueError(f"task group assigned to wrong split: {row['task_group']}")
            assigned_states[state_hash] += 1
            groups.add((str(row["dataset"]), str(row["task_group"])))
            dataset = str(row["dataset"])
            bucket = stats.setdefault(dataset, {
                "examples": 0,
                "task_groups": set(),
                "trials": 0,
                "pass_trials": 0,
                "fail_trials": 0,
                "fractional_target_examples": 0,
            })
            bucket["examples"] += 1
            bucket["task_groups"].add(str(row["task_group"]))
            bucket["trials"] += int(row["n_trials"])
            bucket["pass_trials"] += int(row["n_pass"])
            bucket["fail_trials"] += int(row["n_fail"])
            bucket["fractional_target_examples"] += int(row["n_pass"] > 0 and row["n_fail"] > 0)
        split_groups[split] = groups
        split_counts[split] = {
            dataset: {
                **values_for_dataset,
                "task_groups": len(values_for_dataset["task_groups"]),
                "fractional_target_coverage": (
                    values_for_dataset["fractional_target_examples"] / values_for_dataset["examples"]
                ),
            }
            for dataset, values_for_dataset in stats.items()
        }
        expected_checksum = split_manifest["split_sha256"][split]
        actual_checksum = sha256_bytes((data_dir / f"{split}.jsonl").read_bytes())
        if actual_checksum != expected_checksum:
            raise ValueError(f"{split} split checksum mismatch")
        for dataset, values_for_dataset in split_counts[split].items():
            if values_for_dataset["pass_trials"] == 0 or values_for_dataset["fail_trials"] == 0:
                raise ValueError(f"{dataset}/{split} lacks both labels for declared metrics")

    if set(assigned_states) != set(example_by_hash) or any(v != 1 for v in assigned_states.values()):
        raise ValueError("train/validation/test do not partition every prepared example once")
    if split_groups["train"] & split_groups["validation"]:
        raise ValueError("task group leakage between train and validation")
    if split_groups["train"] & split_groups["test"]:
        raise ValueError("task group leakage between train and test")
    if split_groups["validation"] & split_groups["test"]:
        raise ValueError("task group leakage between validation and test")

    mixed = sum(item["n_pass"] > 0 and item["n_fail"] > 0 for item in examples)
    return {
        "raw_tuple_rows": len(tuples),
        "exact_duplicate_tuple_rows_beyond_first": sum(count - 1 for count in raw_duplicates.values()),
        "skill_artifacts_verified": len(skill_hashes),
        "row_resolution_rows": len(resolution),
        "unique_inputs": len(examples),
        "retained_trials": sum(item["n_trials"] for item in examples),
        "overflow_inputs": len(overflows),
        "mixed_target_inputs": mixed,
        "raw_label_counts": dict(raw_label_counts),
        "token_limits": {
            "state": max_state,
            "causal_row": max_causal_row,
            "packed": max_packed,
            "branch_semantics": token_audit["serve_max_branch_semantics"],
        },
        "dataset_task_groups": {ds: len(groups) for ds, groups in groups_by_dataset.items()},
        "split_counts": split_counts,
        "checks": {
            "all_rows_resolved_once": True,
            "skill_hashes_and_bodies_match": True,
            "soft_targets_reconcile_to_source_rows": True,
            "zero_overflow_and_zero_truncation": True,
            "deterministic_split_assignment_matches_manifest": True,
            "split_files_match_checksums": True,
            "task_groups_are_split_exclusive": True,
            "all_examples_partitioned_once": True,
            "all_dataset_splits_support_binary_metrics": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(args.raw_root, args.data_dir)
    out = args.report or args.data_dir / "audit_independent.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
