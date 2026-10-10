#!/usr/bin/env python3
"""Validation-selected threshold analysis for saved Jev pass/fail predictions."""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from metrics import resample_task_groups


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _mass(row: dict[str, Any], key: str) -> float:
    multiplier = float(row.get("_bootstrap_multiplier", 1.0))
    return float(row[key]) * multiplier


def confusion(rows: Iterable[dict[str, Any]], threshold: float) -> dict[str, float]:
    tp = fp = fn = tn = 0.0
    for row in rows:
        if float(row["p_pass"]) >= threshold:
            tp += _mass(row, "n_pass")
            fp += _mass(row, "n_fail")
        else:
            fn += _mass(row, "n_pass")
            tn += _mass(row, "n_fail")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def threshold_metrics(rows: Iterable[dict[str, Any]], threshold: float) -> dict[str, float | None]:
    values = list(rows)
    c = confusion(values, threshold)
    tp, fp, fn, tn = (c[name] for name in ("tp", "fp", "fn", "tn"))
    total = tp + fp + fn + tn
    pass_recall = tp / (tp + fn) if tp + fn else None
    fail_recall = tn / (tn + fp) if tn + fp else None
    pass_precision = tp / (tp + fp) if tp + fp else None
    fail_precision = tn / (tn + fn) if tn + fn else None
    pass_f1 = (
        2 * tp / (2 * tp + fp + fn)
        if 2 * tp + fp + fn
        else None
    )
    fail_f1 = (
        2 * tn / (2 * tn + fp + fn)
        if 2 * tn + fp + fn
        else None
    )
    macro_f1 = (
        (pass_f1 + fail_f1) / 2
        if pass_f1 is not None and fail_f1 is not None
        else None
    )
    balanced_accuracy = (
        (pass_recall + fail_recall) / 2
        if pass_recall is not None and fail_recall is not None
        else None
    )
    return {
        "threshold": threshold,
        "accuracy": (tp + tn) / total if total else None,
        "balanced_accuracy": balanced_accuracy,
        "macro_f1": macro_f1,
        "pass_f1": pass_f1,
        "fail_f1": fail_f1,
        "pass_precision": pass_precision,
        "fail_precision": fail_precision,
        "pass_recall": pass_recall,
        "fail_recall": fail_recall,
        "recall_gap": abs(pass_recall - fail_recall)
        if pass_recall is not None and fail_recall is not None
        else None,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "trial_weight": total,
    }


def roc_auc(rows: Iterable[dict[str, Any]]) -> float | None:
    groups: dict[float, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        score = float(row["p_pass"])
        groups[score][0] += _mass(row, "n_pass")
        groups[score][1] += _mass(row, "n_fail")
    positive_mass = sum(value[0] for value in groups.values())
    negative_mass = sum(value[1] for value in groups.values())
    if not positive_mass or not negative_mass:
        return None
    concordant = 0.0
    negatives_below = 0.0
    for score in sorted(groups):
        positive, negative = groups[score]
        concordant += positive * (negatives_below + 0.5 * negative)
        negatives_below += negative
    return concordant / (positive_mass * negative_mass)


def pr_auc(rows: Iterable[dict[str, Any]]) -> float | None:
    groups: dict[float, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        score = float(row["p_pass"])
        groups[score][0] += _mass(row, "n_pass")
        groups[score][1] += _mass(row, "n_fail")
    positive_mass = sum(value[0] for value in groups.values())
    if not positive_mass:
        return None
    true_positive = 0.0
    seen = 0.0
    previous_recall = 0.0
    average_precision = 0.0
    for score in sorted(groups, reverse=True):
        positive, negative = groups[score]
        true_positive += positive
        seen += positive + negative
        recall = true_positive / positive_mass
        precision = true_positive / seen if seen else 0.0
        average_precision += (recall - previous_recall) * precision
        previous_recall = recall
    return average_precision


def threshold_candidates(rows: Iterable[dict[str, Any]]) -> list[float]:
    return sorted({0.0, 1.0, *[float(row["p_pass"]) for row in rows]})


def select_threshold(metrics: list[dict[str, Any]], objective: str) -> dict[str, Any]:
    if objective == "recall_gap":
        return min(metrics, key=lambda item: (item[objective], -float(item["macro_f1"]), abs(item["threshold"] - 0.5), item["threshold"]))
    return min(metrics, key=lambda item: (-float(item[objective]), abs(item["threshold"] - 0.5), item["threshold"]))


def bootstrap_selected(
    rows: list[dict[str, Any]], threshold: float, replicates: int, seed: int
) -> dict[str, dict[str, float]]:
    rng = random.Random(seed)
    names = ("balanced_accuracy", "macro_f1", "pass_f1", "fail_f1", "pass_recall", "fail_recall", "recall_gap", "roc_auc", "pr_auc")
    samples: dict[str, list[float]] = {name: [] for name in names}
    for _ in range(replicates):
        sampled = resample_task_groups(rows, rng)
        metric = threshold_metrics(sampled, threshold)
        values = {**metric, "roc_auc": roc_auc(sampled), "pr_auc": pr_auc(sampled)}
        for name in names:
            value = values[name]
            if value is not None:
                samples[name].append(float(value))
    def percentile(values: list[float], probability: float) -> float:
        position = (len(values) - 1) * probability
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[lower]
        fraction = position - lower
        return values[lower] * (1.0 - fraction) + values[upper] * fraction

    result: dict[str, dict[str, float]] = {}
    for name, values in samples.items():
        values.sort()
        if not values:
            continue
        result[name] = {
            "low": percentile(values, 0.025),
            "high": percentile(values, 0.975),
            "valid_replicates": len(values),
        }
    return result


def analyze_model(
    validation: list[dict[str, Any]], test: list[dict[str, Any]], replicates: int, seed: int
) -> dict[str, Any]:
    validation_metrics = [threshold_metrics(validation, threshold) for threshold in threshold_candidates(validation)]
    selections: dict[str, Any] = {}
    for objective in ("macro_f1", "balanced_accuracy", "recall_gap"):
        selected = select_threshold(validation_metrics, objective)
        threshold = float(selected["threshold"])
        test_metrics = threshold_metrics(test, threshold)
        test_metrics["roc_auc"] = roc_auc(test)
        test_metrics["pr_auc"] = pr_auc(test)
        selections[objective] = {
            "validation": selected,
            "test": test_metrics,
            "test_bootstrap_95": bootstrap_selected(test, threshold, replicates, seed),
        }
    return {
        "validation_roc_auc": roc_auc(validation),
        "validation_pr_auc": pr_auc(validation),
        "test_roc_auc": roc_auc(test),
        "test_pr_auc": pr_auc(test),
        "selections": selections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260929)
    args = parser.parse_args()
    run_root = args.root / "runs/full_train_20260929_v1"
    test_root = args.root / "evaluations/final_test_20260929_v1"
    models = {
        "original_jev": (
            read_jsonl(run_root / "validation/baseline_jev.jsonl"),
            read_jsonl(test_root / "predictions/original_jev.jsonl"),
        ),
        "fine_tuned_best": (
            read_jsonl(run_root / "validation/epoch_01.jsonl"),
            read_jsonl(test_root / "predictions/fine_tuned_best.jsonl"),
        ),
    }
    result = {
        "status": "complete",
        "threshold_semantics": "predict pass when p_pass >= threshold",
        "threshold_selection": "validation-only; macro_f1 and balanced_accuracy are maximized, recall_gap is minimized; ties choose threshold closest to 0.5 then lower threshold",
        "auc_definition": "trial-weighted soft-label ROC-AUC with half credit for tied scores; PR-AUC is weighted average precision",
        "bootstrap": {"replicates": args.replicates, "seed": args.seed, "resampling": "task groups within dataset with observed dataset trial mix"},
        "models": {name: analyze_model(validation, test, args.replicates, args.seed) for name, (validation, test) in models.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": "complete"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
