#!/usr/bin/env python3
"""Audit a completed training run without reading the test split."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from metrics import metrics_by_dataset
from train_jev import (
    atomic_json,
    dataset_checksums,
    file_sha256,
    model_source_checksums,
    read_json,
    read_jsonl,
)


def assert_close(actual: Any, expected: Any, path: str = "metrics") -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError(f"{path} fields differ")
        for key in expected:
            assert_close(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"{path} list lengths differ")
        for index, (got, want) in enumerate(zip(actual, expected)):
            assert_close(got, want, f"{path}[{index}]")
        return
    if isinstance(expected, bool):
        if actual is not expected:
            raise ValueError(f"{path} differs")
        return
    if isinstance(expected, (int, float)):
        if not isinstance(actual, (int, float)) or not math.isclose(
            float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-10
        ):
            raise ValueError(f"{path} differs: {actual!r} != {expected!r}")
        return
    if actual != expected:
        raise ValueError(f"{path} differs")


def check_prediction_rows(
    predictions: list[dict[str, Any]], validation_rows: list[dict[str, Any]], label: str
) -> dict[str, Any]:
    expected = {row["state_hash"]: row for row in validation_rows}
    actual_hashes = [row["state_hash"] for row in predictions]
    if len(actual_hashes) != len(set(actual_hashes)) or set(actual_hashes) != set(expected):
        raise ValueError(f"{label} prediction states do not match the frozen validation split")
    for prediction in predictions:
        source = expected[prediction["state_hash"]]
        for key in ("dataset", "task_group", "n_pass", "n_fail", "n_trials"):
            if prediction[key] != source[key]:
                raise ValueError(f"{label} prediction provenance mismatch for {prediction['state_hash']}")
        p_fail, p_pass = float(prediction["p_fail"]), float(prediction["p_pass"])
        if not math.isfinite(p_fail) or not math.isfinite(p_pass):
            raise ValueError(f"{label} has nonfinite probability for {prediction['state_hash']}")
        if not 0.0 <= p_fail <= 1.0 or not 0.0 <= p_pass <= 1.0:
            raise ValueError(f"{label} probability out of range for {prediction['state_hash']}")
        if abs(p_fail + p_pass - 1.0) > 1e-6:
            raise ValueError(f"{label} probability is not normalized for {prediction['state_hash']}")
    return metrics_by_dataset(predictions)


def audit_run(args: argparse.Namespace, torch: Any) -> dict[str, Any]:
    run_root = args.run_root
    complete = read_json(run_root / "training_complete.json")
    best = read_json(run_root / "best.json")
    latest = read_json(run_root / "latest.json")
    manifest = read_json(run_root / "run_manifest.json")
    events = read_jsonl(run_root / "metrics.jsonl")
    if not events:
        raise ValueError("completed training run has no epoch records")
    epochs = [int(event["epoch"]) for event in events]
    if epochs != list(range(1, len(epochs) + 1)):
        raise ValueError(f"epoch records are missing, repeated, or unordered: {epochs}")
    last_epoch = int(complete["last_epoch"])
    if epochs[-1] != last_epoch or int(latest["epoch"]) != last_epoch:
        raise ValueError("completion, latest pointer, and epoch log disagree")
    if latest["checkpoint"] != f"epoch_{last_epoch:02d}":
        raise ValueError("latest checkpoint name does not match its epoch")
    if last_epoch > int(manifest["training"]["epochs"]):
        raise ValueError("training exceeded the registered epoch limit")
    if bool(complete["early_stopped"]) != (int(events[-1]["stale_epochs"]) >= int(manifest["training"]["patience"])):
        raise ValueError("early-stop marker disagrees with the final epoch state")

    current_data_checksums = dataset_checksums(args.data_dir, args.split_dir)
    if current_data_checksums != manifest["data_checksums"]:
        raise ValueError("prepared training/validation data changed during the run")
    current_source_checksums = model_source_checksums(args.checkpoint_dir, args.base_dir)
    if current_source_checksums != manifest["base_checkpoint_sha256"]:
        raise ValueError("original Jev model or base files changed during training")
    split_manifest = read_json(args.split_dir / "split_manifest.json")
    validation_path = args.split_dir / "validation.jsonl"
    if split_manifest["split_sha256"]["validation"] != file_sha256(validation_path):
        raise ValueError("frozen validation split checksum mismatch")
    validation_rows = read_jsonl(validation_path)
    checkpoint_root = run_root / "checkpoints"
    expected_checkpoints = {f"epoch_{epoch:02d}" for epoch in epochs}
    actual_checkpoints = {
        path.name for path in checkpoint_root.glob("epoch_[0-9][0-9]") if path.is_dir()
    }
    if actual_checkpoints != expected_checkpoints:
        raise ValueError("checkpoint directories do not match the completed epoch log")
    if list(checkpoint_root.glob(".epoch_*.tmp.*")):
        raise ValueError("temporary checkpoint directory remains after training")

    code_dir = Path(__file__).parent
    for name, expected_hash in manifest["code_sha256"].items():
        path = code_dir / name
        if not path.is_file() or file_sha256(path) != expected_hash:
            raise ValueError(f"training code changed after the run started: {name}")

    selection_nll = math.inf
    selected_epoch = None
    stale_epochs = 0
    global_steps = 0
    for event in events:
        epoch = int(event["epoch"])
        if int(event["global_step"]) <= global_steps:
            raise ValueError("global optimizer step did not increase monotonically")
        global_steps = int(event["global_step"])
        expected_prediction = f"epoch_{epoch:02d}.jsonl"
        checkpoint = run_root / "checkpoints" / expected_prediction.removesuffix(".jsonl")
        state_path = checkpoint / "training_state.pt"
        if not state_path.is_file() or not (checkpoint / "head.pt").is_file() or not (checkpoint / "adapter_model.safetensors").is_file():
            raise ValueError(f"epoch {epoch} checkpoint is incomplete")
        state = torch.load(state_path, map_location="cpu", weights_only=False)
        if (
            int(state["epoch"]) != epoch
            or state["config_sha256"] != manifest["config_sha256"]
            or state["data_checksums"] != manifest["data_checksums"]
            or state["epoch_record"] != event
            or state["global_step"] != event["global_step"]
        ):
            raise ValueError(f"epoch {epoch} checkpoint metadata disagrees with the event log")
        pred_path = run_root / "validation" / state["validation_prediction"]
        if file_sha256(pred_path) != state["validation_prediction_sha256"]:
            raise ValueError(f"epoch {epoch} validation prediction checksum mismatch")
        predictions = read_jsonl(pred_path)
        recomputed = check_prediction_rows(predictions, validation_rows, f"epoch {epoch}")
        assert_close(event["validation"], recomputed, f"epoch_{epoch}.validation")
        val_nll = float(recomputed["overall"]["nll"])
        improved = selected_epoch is None or val_nll < selection_nll - float(manifest["training"]["min_delta"])
        if bool(event["selected"]) != improved:
            raise ValueError(f"epoch {epoch} selection flag disagrees with validation NLL")
        if improved:
            selected_epoch = epoch
            selection_nll = val_nll
            stale_epochs = 0
        else:
            stale_epochs += 1
        if (
            int(event["best_epoch"]) != selected_epoch
            or abs(float(event["best_validation_trial_weighted_nll"]) - selection_nll) > 1e-10
            or int(event["stale_epochs"]) != stale_epochs
        ):
            raise ValueError(f"epoch {epoch} best-state fields are inconsistent")

    if (
        int(best["epoch"]) != selected_epoch
        or best["checkpoint"] != f"epoch_{selected_epoch:02d}"
        or abs(float(best["validation_trial_weighted_nll"]) - selection_nll) > 1e-10
        or int(complete["best_epoch"]) != selected_epoch
        or complete["best_checkpoint"] != best["checkpoint"]
        or abs(float(complete["best_validation_trial_weighted_nll"]) - selection_nll) > 1e-10
    ):
        raise ValueError("final best-checkpoint selection is inconsistent")
    best_state = torch.load(
        run_root / "checkpoints" / best["checkpoint"] / "training_state.pt",
        map_location="cpu",
        weights_only=False,
    )
    if len(best_state["rng_by_rank"]) != 8 or not best_state["optimizer_state"]["state"]:
        raise ValueError("best checkpoint is missing distributed RNG or optimizer state")

    baseline_path = run_root / "validation" / "baseline_jev.jsonl"
    baseline_metrics = read_json(run_root / "validation" / "baseline_jev_metrics.json")
    baseline_predictions = read_jsonl(baseline_path)
    recomputed_baseline = check_prediction_rows(baseline_predictions, validation_rows, "baseline")
    assert_close(baseline_metrics, recomputed_baseline, "baseline_validation")
    return {
        "status": "passed",
        "last_epoch": last_epoch,
        "best_epoch": selected_epoch,
        "best_validation_trial_weighted_nll": selection_nll,
        "epochs_audited": len(events),
        "validation_examples_per_epoch": len(validation_rows),
        "data_checksums": current_data_checksums,
        "code_sha256": manifest["code_sha256"],
        "audit_code_sha256": file_sha256(Path(__file__)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--split-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (args.run_root / "training_complete.json").is_file():
        raise SystemExit("training run is not complete")
    import os
    os.environ["MINICPM_S1_BASE_MODEL_PATH"] = str(args.base_dir.resolve())
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str((args.run_root.parent.parent / "code").resolve()))
    import torch

    result = audit_run(args, torch)
    report_path = args.run_root / "reports" / "training_integrity_audit.json"
    atomic_json(report_path, result)
    print(json.dumps({"audit": str(report_path), **result}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
