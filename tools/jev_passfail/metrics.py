"""Trial-weighted probability metrics and task-cluster bootstrap intervals."""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Any, Iterable


METRIC_NAMES = (
    "nll",
    "brier",
    "ece",
    "balanced_accuracy",
    "fail_recall",
    "expected_macro_f1",
)


def _values(row: dict[str, Any]) -> tuple[float, float, float, float]:
    n_pass = int(row["n_pass"])
    n_fail = int(row["n_fail"])
    n_trials = int(row.get("n_trials", n_pass + n_fail))
    if n_trials != n_pass + n_fail or n_trials <= 0:
        raise ValueError("trial counts must be positive and reconcile")
    p_pass = float(row["p_pass"])
    if not math.isfinite(p_pass) or not 0.0 <= p_pass <= 1.0:
        raise ValueError(f"invalid pass probability: {p_pass}")
    multiplier = float(row.get("_bootstrap_multiplier", 1.0))
    if not math.isfinite(multiplier) or multiplier < 0:
        raise ValueError(f"invalid bootstrap multiplier: {multiplier}")
    return p_pass, n_pass / n_trials, float(n_trials), multiplier


def compute_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    bins = [{"weight": 0.0, "prediction": 0.0, "target": 0.0} for _ in range(10)]
    total_weight = 0.0
    total_nll = 0.0
    total_brier = 0.0
    tp = fp = fn = tn = 0.0

    for row in data:
        p_pass, q_pass, n_trials, multiplier = _values(row)
        weight = n_trials * multiplier
        if weight == 0:
            continue
        q_fail = 1.0 - q_pass
        p_safe = min(1.0 - 1e-15, max(1e-15, p_pass))
        total_nll += weight * (
            -q_pass * math.log(p_safe) - q_fail * math.log1p(-p_safe)
        )
        total_brier += weight * (p_pass - q_pass) ** 2
        total_weight += weight

        bin_index = min(9, int(p_pass * 10))
        bins[bin_index]["weight"] += weight
        bins[bin_index]["prediction"] += weight * p_pass
        bins[bin_index]["target"] += weight * q_pass

        if p_pass >= 0.5:
            tp += weight * q_pass
            fp += weight * q_fail
        else:
            fn += weight * q_pass
            tn += weight * q_fail

    if total_weight == 0:
        return {
            "unique_inputs": len(data),
            "trial_weight": 0.0,
            **{name: None for name in METRIC_NAMES},
            "fractional_confusion": None,
        }

    ece = 0.0
    for bucket in bins:
        if bucket["weight"]:
            pred_mean = bucket["prediction"] / bucket["weight"]
            target_mean = bucket["target"] / bucket["weight"]
            ece += bucket["weight"] / total_weight * abs(pred_mean - target_mean)

    pass_mass = tp + fn
    fail_mass = tn + fp
    pass_recall = tp / pass_mass if pass_mass else None
    fail_recall = tn / fail_mass if fail_mass else None
    f1_pass_den = 2 * tp + fp + fn
    f1_fail_den = 2 * tn + fp + fn
    f1_pass = 2 * tp / f1_pass_den if f1_pass_den else None
    f1_fail = 2 * tn / f1_fail_den if f1_fail_den else None
    macro_f1 = (
        (f1_pass + f1_fail) / 2
        if f1_pass is not None and f1_fail is not None
        else None
    )
    balanced_accuracy = (
        (pass_recall + fail_recall) / 2
        if pass_recall is not None and fail_recall is not None
        else None
    )
    return {
        "unique_inputs": len(data),
        "trial_weight": total_weight,
        "nll": total_nll / total_weight,
        "brier": total_brier / total_weight,
        "ece": ece,
        "balanced_accuracy": balanced_accuracy,
        "fail_recall": fail_recall,
        "expected_macro_f1": macro_f1,
        "fractional_confusion": {
            "true_pass_pred_pass": tp,
            "true_fail_pred_pass": fp,
            "true_pass_pred_fail": fn,
            "true_fail_pred_fail": tn,
        },
    }


def metrics_by_dataset(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    datasets = sorted({str(row["dataset"]) for row in data})
    return {
        "overall": compute_metrics(data),
        "by_dataset": {
            dataset: compute_metrics(row for row in data if str(row["dataset"]) == dataset)
            for dataset in datasets
        },
    }


def resample_task_groups(
    rows: Iterable[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    data = list(rows)
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    target_trials: Counter[str] = Counter()
    for row in data:
        dataset = str(row["dataset"])
        group = str(row["task_group"])
        groups[dataset][group].append(row)
        target_trials[dataset] += int(row.get("n_trials", int(row["n_pass"]) + int(row["n_fail"])))

    sampled: list[dict[str, Any]] = []
    for dataset in sorted(groups):
        dataset_groups = groups[dataset]
        group_names = sorted(dataset_groups)
        draws = Counter(rng.choices(group_names, k=len(group_names)))
        sampled_trials = sum(
            draws[group]
            * sum(int(row.get("n_trials", int(row["n_pass"]) + int(row["n_fail"]))) for row in dataset_groups[group])
            for group in group_names
        )
        if sampled_trials <= 0:
            raise ValueError(f"bootstrap sampled no trial mass for {dataset}")
        dataset_scale = target_trials[dataset] / sampled_trials
        for group in group_names:
            multiplier = draws[group] * dataset_scale
            if not multiplier:
                continue
            for row in dataset_groups[group]:
                clone = dict(row)
                clone["_bootstrap_multiplier"] = multiplier
                sampled.append(clone)
    return sampled


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot compute percentile of no values")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_confidence_intervals(
    rows: Iterable[dict[str, Any]],
    replicates: int = 2000,
    seed: int = 20260929,
) -> dict[str, Any]:
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    data = list(rows)
    samples: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    rng = random.Random(seed)
    for _ in range(replicates):
        report = metrics_by_dataset(resample_task_groups(data, rng))
        for population, metrics in [("overall", report["overall"]), *report["by_dataset"].items()]:
            for metric in METRIC_NAMES:
                value = metrics[metric]
                if value is not None:
                    samples[population][metric].append(float(value))

    intervals: dict[str, Any] = {}
    for population, metrics in samples.items():
        intervals[population] = {
            metric: {
                "low": _percentile(values, 0.025),
                "high": _percentile(values, 0.975),
                "valid_replicates": len(values),
            }
            for metric, values in metrics.items()
        }
    return {"replicates": replicates, "seed": seed, "intervals_95_percentile": intervals}
