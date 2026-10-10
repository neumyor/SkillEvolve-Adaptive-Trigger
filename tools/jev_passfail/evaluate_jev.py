#!/usr/bin/env python3
"""One-time frozen-checkpoint test evaluation for Jev pass/fail probabilities."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from metrics import bootstrap_confidence_intervals, metrics_by_dataset
from train_jev import (
    atomic_json,
    dataset_checksums,
    file_sha256,
    load_encoded,
    model_source_checksums,
    read_json,
    read_jsonl,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_frozen_run(run_root: Path) -> tuple[dict[str, Any], Path]:
    complete_path = run_root / "training_complete.json"
    best_path = run_root / "best.json"
    manifest_path = run_root / "run_manifest.json"
    if not complete_path.is_file() or not best_path.is_file() or not manifest_path.is_file():
        raise RuntimeError("test evaluation requires a completed run with a frozen best checkpoint")
    complete = read_json(complete_path)
    best = read_json(best_path)
    manifest = read_json(manifest_path)
    if complete["best_checkpoint"] != best["checkpoint"] or int(complete["best_epoch"]) != int(best["epoch"]):
        raise ValueError("training completion marker and best-checkpoint pointer disagree")
    checkpoint = run_root / "checkpoints" / best["checkpoint"]
    state_path = checkpoint / "training_state.pt"
    if not state_path.is_file() or not (checkpoint / "head.pt").is_file() or not (checkpoint / "adapter_model.safetensors").is_file():
        raise ValueError("selected best checkpoint is incomplete")
    if not manifest.get("config_sha256"):
        raise ValueError("training run manifest has no frozen config checksum")
    return {"complete": complete, "best": best, "manifest": manifest}, checkpoint


def validate_predictions(
    predictions: list[dict[str, Any]], entries: list[dict[str, Any]]
) -> None:
    expected = sorted(entry["row"]["state_hash"] for entry in entries)
    actual = sorted(row["state_hash"] for row in predictions)
    if actual != expected or len(actual) != len(set(actual)):
        raise ValueError("test predictions do not match the frozen unique-input test split")
    for row in predictions:
        for name in ("p_fail", "p_pass"):
            value = float(row[name])
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"invalid {name} for {row['state_hash']}")
        if abs(float(row["p_fail"]) + float(row["p_pass"]) - 1.0) > 1e-6:
            raise ValueError(f"unnormalized test probabilities for {row['state_hash']}")


def evaluate_model(
    checkpoint: Path,
    label: str,
    runtime: dict[str, Any],
    entries: list[dict[str, Any]],
    out_root: Path,
) -> None:
    torch = runtime["torch"]
    dist = runtime["dist"]
    rank = runtime["rank"]
    world_size = runtime["world_size"]
    local_rank = runtime["local_rank"]
    model, _ = runtime["service_model"].load_checkpoint(
        checkpoint,
        device=f"cuda:{local_rank}",
        dtype=torch.bfloat16,
    )
    model.eval()
    output_path = out_root / "predictions" / f"{label}.jsonl"
    metrics = runtime["evaluate_split"](
        SimpleNamespace(module=model),
        entries,
        rank,
        world_size,
        dist,
        torch,
        output_path,
    )
    del model
    torch.cuda.empty_cache()
    report_error = [None]
    if rank == 0:
        try:
            predictions = read_jsonl(output_path)
            validate_predictions(predictions, entries)
            report = {
                "created_at_utc": utc_now(),
                "checkpoint_label": label,
                "checkpoint_path": str(checkpoint),
                "checkpoint_sha256": {
                    "head.pt": file_sha256(checkpoint / "head.pt"),
                    "adapter_model.safetensors": file_sha256(checkpoint / "adapter_model.safetensors"),
                },
                "examples": len(predictions),
                "trials": sum(int(row["n_trials"]) for row in predictions),
                "metrics": metrics_by_dataset(predictions),
                "bootstrap": bootstrap_confidence_intervals(
                    predictions,
                    replicates=2000,
                    seed=20260929,
                ),
            }
            atomic_json(out_root / "reports" / f"{label}.json", report)
        except Exception as exc:
            report_error[0] = f"{type(exc).__name__}: {exc}"
    dist.broadcast_object_list(report_error, src=0)
    if report_error[0]:
        raise RuntimeError(f"could not finalize {label} test report: {report_error[0]}")
    dist.barrier()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-dir", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--split-dir", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frozen, best_checkpoint = verify_frozen_run(args.run_root)
    os.environ["MINICPM_S1_BASE_MODEL_PATH"] = str(args.base_dir.resolve())
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(args.service_dir.resolve()))
    import torch
    import torch.distributed as dist
    from model import MiniCPMSystemOne, encode_record, load_tokenizer
    from train_jev import evaluate_split

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if world_size != 8 or torch.cuda.device_count() < 8:
        raise SystemExit(f"registered test evaluation requires 8 GPUs; got world_size={world_size}, devices={torch.cuda.device_count()}")
    torch.cuda.set_device(local_rank)
    torch.set_num_threads(4)
    torch.manual_seed(20260929 + rank)
    torch.cuda.manual_seed_all(20260929 + rank)
    random.seed(20260929 + rank)
    dist.init_process_group(backend="nccl", device_id=torch.device(f"cuda:{local_rank}"))

    best_state = torch.load(
        best_checkpoint / "training_state.pt", map_location="cpu", weights_only=False
    )
    best = frozen["best"]
    if (
        int(best_state["epoch"]) != int(best["epoch"])
        or int(best_state["best_epoch"]) != int(best["epoch"])
        or abs(float(best_state["best_val_nll"]) - float(best["validation_trial_weighted_nll"])) > 1e-10
        or best_state["config_sha256"] != frozen["manifest"]["config_sha256"]
    ):
        raise ValueError("selected checkpoint state does not match the frozen best-checkpoint record")
    if best_state["data_checksums"] != dataset_checksums(args.data_dir, args.split_dir):
        raise ValueError("frozen training or validation inputs changed before test evaluation")
    source_checksums = model_source_checksums(args.checkpoint_dir, args.base_dir)
    if source_checksums != frozen["manifest"]["base_checkpoint_sha256"]:
        raise ValueError("original Jev checkpoint or base model changed after training")

    lock = None
    setup_error = [None]
    if rank == 0:
        try:
            args.out_root.mkdir(parents=True, exist_ok=True)
            lock = (args.out_root / "evaluation.lock").open("a+")
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if any(path.name != "evaluation.lock" for path in args.out_root.iterdir()):
                raise FileExistsError("test evaluation output already exists; do not rerun against the same frozen test")
            (args.out_root / "predictions").mkdir()
            (args.out_root / "reports").mkdir()
            split_manifest = read_json(args.split_dir / "split_manifest.json")
            test_path = args.split_dir / "test.jsonl"
            for split_name in ("train", "validation"):
                if split_manifest["split_sha256"][split_name] != frozen["manifest"]["split_sha256"][split_name]:
                    raise ValueError(f"frozen {split_name} split changed after training")
            if split_manifest["split_sha256"]["test"] != file_sha256(test_path):
                raise ValueError("frozen test split checksum mismatch")
            atomic_json(args.out_root / "evaluation_manifest.json", {
                "started_at_utc": utc_now(),
                "protocol": frozen["manifest"]["protocol"],
                "training_config_sha256": frozen["manifest"]["config_sha256"],
                "evaluation_code_sha256": file_sha256(Path(__file__)),
                "best_checkpoint": frozen["best"],
                "test_split_sha256": split_manifest["split_sha256"]["test"],
                "metrics": ["trial-weighted soft NLL", "Brier", "10-bin ECE", "balanced accuracy", "fail recall", "expected macro-F1"],
                "bootstrap_replicates": 2000,
                "bootstrap_seed": 20260929,
                "test_access_started": True,
            })
        except Exception as exc:
            setup_error[0] = f"{type(exc).__name__}: {exc}"
            if lock is not None:
                lock.close()
                lock = None
    dist.broadcast_object_list(setup_error, src=0)
    if setup_error[0]:
        if lock is not None:
            lock.close()
        dist.destroy_process_group()
        raise RuntimeError(f"test evaluation preflight failed: {setup_error[0]}")
    dist.barrier()

    tokenizer = load_tokenizer(str(args.base_dir))
    entries = load_encoded(args.split_dir / "test.jsonl", tokenizer, encode_record)
    test_rows = [entry["row"] for entry in entries]
    expected_test_hashes = sorted(row["state_hash"] for row in test_rows)
    if len(expected_test_hashes) != len(set(expected_test_hashes)):
        raise ValueError("frozen test split contains duplicate states")
    dist.barrier()

    runtime = {
        "torch": torch,
        "dist": dist,
        "rank": rank,
        "world_size": world_size,
        "local_rank": local_rank,
        "service_model": MiniCPMSystemOne,
        "evaluate_split": evaluate_split,
    }
    try:
        evaluate_model(args.checkpoint_dir, "original_jev", runtime, entries, args.out_root)
        evaluate_model(best_checkpoint, "fine_tuned_best", runtime, entries, args.out_root)
        if rank == 0:
            baseline_path = args.out_root / "predictions" / "original_jev.jsonl"
            best_path = args.out_root / "predictions" / "fine_tuned_best.jsonl"
            baseline = read_jsonl(baseline_path)
            best = read_jsonl(best_path)
            validate_predictions(baseline, entries)
            validate_predictions(best, entries)
            if [row["state_hash"] for row in baseline] != [row["state_hash"] for row in best]:
                raise ValueError("baseline and fine-tuned test predictions are not row-aligned")
            manifest = read_json(args.out_root / "evaluation_manifest.json")
            manifest.update({
                "finished_at_utc": utc_now(),
                "test_examples": len(entries),
                "test_trials": sum(int(row["n_trials"]) for row in test_rows),
                "status": "complete",
            })
            atomic_json(args.out_root / "evaluation_manifest.json", manifest)
    finally:
        if lock is not None:
            lock.close()
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
