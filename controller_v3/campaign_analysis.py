"""Fixed-metric analysis for a Controller V3 paired campaign.

The analyzer never chooses a favorable metric or subset.  Callers provide the
registered quality column and non-degradation threshold before reading results.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterable


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _bootstrap_mean_delta(deltas: list[float], *, seed: int, samples: int) -> dict[str, float | None]:
    if not deltas:
        return {"lower": None, "upper": None}
    rng = random.Random(seed)
    means = [
        sum(rng.choice(deltas) for _ in deltas) / len(deltas)
        for _ in range(max(1, samples))
    ]
    return {"lower": _percentile(means, 0.025), "upper": _percentile(means, 0.975)}


def _paired_rows(
    original_rows: dict[str, dict[str, Any]],
    controller_rows: dict[str, dict[str, Any]],
    quality_field: str,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for task_id in sorted(set(original_rows) & set(controller_rows)):
        before = float(
            original_rows[task_id].get(
                quality_field,
                original_rows[task_id].get("score", original_rows[task_id].get("hard", 0.0)),
            )
            or 0.0
        )
        after = float(
            controller_rows[task_id].get(
                quality_field,
                controller_rows[task_id].get("score", controller_rows[task_id].get("hard", 0.0)),
            )
            or 0.0
        )
        pairs.append({"task_id": task_id, "original": before, "controller": after, "delta": after - before})
    return pairs


def _split_report(pairs: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    deltas = [pair["delta"] for pair in pairs]
    return {
        "tasks": len(pairs),
        "original_mean": _mean([pair["original"] for pair in pairs]),
        "controller_mean": _mean([pair["controller"] for pair in pairs]),
        "mean_delta": _mean(deltas),
        "wins": sum(delta > 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
        "pairs": pairs,
        "quality_non_degraded": bool(deltas) and _mean(deltas) >= threshold,
    }


def analyze_campaign(
    root: str | Path,
    *,
    methods: Iterable[str] = ("skillopt", "gepa", "evoskill", "trace2skill"),
    quality_field: str = "f1",
    threshold: float = -0.05,
    bootstrap_samples: int = 5000,
    seed: int = 0,
) -> dict[str, Any]:
    """Analyze paired task deltas using one pre-registered quality field."""
    root = Path(root)
    summary_path = root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "campaign": str(root),
        "quality_field": quality_field,
        "non_degradation_threshold": threshold,
        "bootstrap": {"samples": bootstrap_samples, "seed": seed},
        "methods": {},
    }
    for method in methods:
        original = summary.get("conditions", {}).get(f"{method}/original", {})
        controller = summary.get("conditions", {}).get(f"{method}/controller", {})
        original_rows = {
            str(row.get("id")): row
            for row in original.get("result", {}).get("rows", [])
            if row.get("id") is not None
        }
        controller_rows = {
            str(row.get("id")): row
            for row in controller.get("result", {}).get("rows", [])
            if row.get("id") is not None
        }
        ids = sorted(set(original_rows) & set(controller_rows))
        pairs = _paired_rows(original_rows, controller_rows, quality_field)
        deltas = [pair["delta"] for pair in pairs]
        original_tokens = original.get("tokens", {})
        controller_tokens = controller.get("tokens", {})
        original_cost_ok = bool(original.get("audit", {}).get("cost_usable"))
        controller_cost_ok = bool(controller.get("audit", {}).get("cost_usable"))
        original_total = int(original_tokens.get("total_tokens", 0) or 0)
        controller_total = int(controller_tokens.get("total_tokens", 0) or 0)
        savings = None
        if original_cost_ok and controller_cost_ok and original_total:
            savings = (original_total - controller_total) / original_total
        mean_delta = _mean(deltas)
        method_report = {
            "tasks": len(ids),
            "original_mean": _mean([pair["original"] for pair in pairs]),
            "controller_mean": _mean([pair["controller"] for pair in pairs]),
            "mean_delta": mean_delta,
            "delta_ci95": _bootstrap_mean_delta(deltas, seed=seed, samples=bootstrap_samples),
            "wins": sum(delta > 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "losses": sum(delta < 0 for delta in deltas),
            "pairs": pairs,
            "original_total_tokens": original_total,
            "controller_total_tokens": controller_total,
            "cost_comparison_usable": original_cost_ok and controller_cost_ok,
            "token_savings_fraction": savings,
            "quality_non_degraded": mean_delta is not None and mean_delta >= threshold,
            "controller_reduces_tokens": savings is not None and savings > 0,
            "supports_target_claim": bool(mean_delta is not None and mean_delta >= threshold and savings is not None and savings > 0),
        }
        heldout_original = {
            str(row.get("id")): row
            for row in original.get("result", {}).get("heldout_rows", [])
            if row.get("id") is not None
        }
        heldout_controller = {
            str(row.get("id")): row
            for row in controller.get("result", {}).get("heldout_rows", [])
            if row.get("id") is not None
        }
        heldout_pairs = _paired_rows(heldout_original, heldout_controller, quality_field)
        heldout_deltas = [pair["delta"] for pair in heldout_pairs]
        heldout_mean_delta = _mean(heldout_deltas)
        method_report["heldout"] = {
            "tasks": len(heldout_pairs),
            "original_mean": _mean([pair["original"] for pair in heldout_pairs]),
            "controller_mean": _mean([pair["controller"] for pair in heldout_pairs]),
            "mean_delta": heldout_mean_delta,
            "wins": sum(delta > 0 for delta in heldout_deltas),
            "ties": sum(delta == 0 for delta in heldout_deltas),
            "losses": sum(delta < 0 for delta in heldout_deltas),
            "pairs": heldout_pairs,
            "quality_non_degraded": heldout_mean_delta is not None and heldout_mean_delta >= threshold,
        }
        heldout_by_split: dict[str, dict[str, Any]] = {}
        split_names = sorted(
            {
                str(row.get("evaluation_split"))
                for row in list(heldout_original.values()) + list(heldout_controller.values())
                if row.get("evaluation_split")
            }
        )
        for split in split_names:
            split_original = {
                task_id: row
                for task_id, row in heldout_original.items()
                if str(row.get("evaluation_split")) == split
            }
            split_controller = {
                task_id: row
                for task_id, row in heldout_controller.items()
                if str(row.get("evaluation_split")) == split
            }
            heldout_by_split[split] = _split_report(
                _paired_rows(split_original, split_controller, quality_field),
                threshold,
            )
        method_report["heldout_by_split"] = heldout_by_split
        from .validity import invalid_row
        invalid = any(invalid_row(row) for row in list(original_rows.values()) + list(controller_rows.values()) + list(heldout_original.values()) + list(heldout_controller.values()))
        invalid = invalid or original.get("audit", {}).get("quality_usable") is False or controller.get("audit", {}).get("quality_usable") is False
        method_report["quality_comparison_usable"] = not invalid
        if invalid:
            method_report["supports_target_claim"] = False
            method_report["quality_non_degraded"] = None
            method_report["heldout"]["quality_non_degraded"] = None
            for split_report in heldout_by_split.values():
                split_report["quality_non_degraded"] = None
            method_report["warning"] = "execution errors contaminate scores; descriptive values only"
        report["methods"][method] = method_report
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--quality-field", default="f1")
    parser.add_argument("--threshold", type=float, default=-0.05)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = analyze_campaign(args.root, quality_field=args.quality_field, threshold=args.threshold)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
