#!/usr/bin/env python3
"""DDP LoRA fine-tuning for Jev pass/fail probabilities."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics import metrics_by_dataset
from training_utils import epoch_batches


QUESTION = {
    "type": "noul",
    "instr": "Will one run of the target agent complete this task successfully when using the provided skill?",
    "options": ["false", "true"],
    "label": 0,
}
LIMITS = {"max_state": 6144, "max_branch": 6144, "max_packed": 6400}
TRAINING = {
    "seed": 20260929,
    "epochs": 10,
    "patience": 2,
    "min_delta": 1e-6,
    "global_effective_batch": 32,
    "micro_batch_per_gpu": 1,
    "gradient_accumulation_per_gpu": 4,
    "learning_rate": 1e-5,
    "weight_decay": 0.01,
    "gradient_clip": 1.0,
    "dtype": "bfloat16",
    "scheduler": "constant",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def training_data_gate(data_dir: Path) -> tuple[dict[str, Any], dict[str, int | str], int]:
    """Normalize the mixed-view and benchmark-filtered audit schemas.

    The original preparation audit stores token limits and nested dataset split
    counts, while a filtered view's independent audit stores direct split
    counts and the generated audit stores the token audit.  Training must apply
    the same gate to either immutable view without weakening any check.
    """
    independent = read_json(data_dir / "audit_independent.json")
    generated = read_json(data_dir / "audit.json")
    overflow = independent.get("overflow_inputs")
    if overflow is None:
        overflow = independent.get("overflow_examples")
    if overflow is None:
        overflow = generated.get("overflow_inputs", generated.get("overflow_examples", 0))
    independent = dict(independent)
    independent["_normalized_overflow_inputs"] = int(overflow)

    token_limits = independent.get("token_limits")
    if token_limits is None:
        token_audit = generated.get("token_audit", {})
        token_limits = {
            "state": token_audit.get("serve_max_state"),
            "causal_row": token_audit.get("serve_max_branch"),
            "packed": token_audit.get("serve_max_packed"),
            "branch_semantics": token_audit.get("serve_max_branch_semantics"),
        }

    split_counts = independent.get("split_counts")
    if split_counts is None:
        split_counts = generated.get("dataset_splits", {})
    train_counts = split_counts.get("train", {})
    if "examples" in train_counts:
        expected_train_examples = int(train_counts["examples"])
    else:
        expected_train_examples = sum(
            int(dataset_counts.get("train", {}).get("examples", 0))
            for dataset_counts in split_counts.values()
        )
    return independent, token_limits, expected_train_examples


def acquire_run_lock(run_root: Path, rank: int):
    if rank != 0:
        return None
    run_root.mkdir(parents=True, exist_ok=True)
    lock = (run_root / "trainer.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.seek(0)
        owner = lock.read().strip() or "unknown"
        lock.close()
        raise RuntimeError(f"run is already locked by {owner}") from exc
    lock.seek(0)
    lock.truncate()
    lock.write(json.dumps({"pid": os.getpid(), "started_at_utc": utc_now()}) + "\n")
    lock.flush()
    os.fsync(lock.fileno())
    return lock


def dataset_checksums(data_dir: Path, split_dir: Path) -> dict[str, str]:
    names = {
        "examples": data_dir / "examples.jsonl",
        "row_resolution": data_dir / "row_resolution.jsonl",
        "audit_independent": data_dir / "audit_independent.json",
        "split_manifest": split_dir / "split_manifest.json",
        "train": split_dir / "train.jsonl",
        "validation": split_dir / "validation.jsonl",
    }
    return {key: file_sha256(path) for key, path in names.items()}


def model_source_checksums(checkpoint_dir: Path, base_dir: Path) -> dict[str, str]:
    paths = {
        "adapter_config": checkpoint_dir / "adapter_config.json",
        "adapter_weights": checkpoint_dir / "adapter_model.safetensors",
        "head": checkpoint_dir / "head.pt",
        "base_config": base_dir / "config.json",
        "tokenizer": base_dir / "tokenizer.json",
    }
    return {key: file_sha256(path) for key, path in paths.items()}


def load_encoded(
    path: Path,
    tokenizer: Any,
    encode_record: Any,
    *,
    limit: int | None = None,
    distinct_datasets: bool = False,
) -> list[dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    seen_datasets: set[str] = set()
    with path.open(encoding="utf-8") as f:
        rows = (json.loads(line) for line in f if line.strip())
        for row in rows:
            dataset = str(row["dataset"])
            if distinct_datasets and dataset in seen_datasets:
                continue
            if limit is not None and len(encoded) >= limit:
                break
            n_pass = int(row["n_pass"])
            n_fail = int(row["n_fail"])
            n_trials = int(row["n_trials"])
            if n_trials != n_pass + n_fail:
                raise ValueError(f"trial counts do not reconcile for {row['state_hash']}")
            if abs(sum(float(x) for x in row["target_probs"]) - 1.0) > 1e-7:
                raise ValueError(f"invalid target distribution for {row['state_hash']}")
            record = {"state": row["state"], "questions": [{**QUESTION, "target_probs": row["target_probs"]}]}
            enc = encode_record(
                tokenizer,
                record,
                max_state=LIMITS["max_state"],
                max_branch=LIMITS["max_branch"],
                strict=True,
            )
            if len(enc["ids"]) > LIMITS["max_packed"]:
                raise ValueError(f"packed input exceeds limit for {row['state_hash']}")
            if enc.get("state_truncated"):
                raise ValueError(f"training input was silently trimmed: {row['state_hash']}")
            encoded.append({"row": row, "enc": enc})
            seen_datasets.add(dataset)
    if not encoded:
        raise ValueError(f"empty split: {path}")
    if limit is not None and len(encoded) != limit:
        raise ValueError(f"requested {limit} smoke rows but found {len(encoded)}")
    return encoded


def calibration_values(model: Any) -> tuple[Any, float, dict[str, Any]]:
    head = model.head
    bias = head.noul_bias.detach().float()
    typed_temperature = float(head.type_temps[1].detach().cpu().item())
    temperature = typed_temperature if typed_temperature != 1.0 else float(head.temperature)
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError(f"invalid Jev noul temperature: {temperature}")
    if bias.numel() != 2 or not bool(torch_isfinite(bias).all()):
        raise ValueError("invalid Jev noul calibration bias")
    return bias, temperature, {"noul_bias": bias.detach().cpu().tolist(), "noul_temperature": temperature}


def torch_isfinite(tensor: Any):
    import torch

    return torch.isfinite(tensor)


def make_optimizer(model: Any, torch: Any):
    params = [parameter for parameter in model.parameters() if parameter.requires_grad]
    if not params:
        raise ValueError("no trainable LoRA parameters")
    optimizer = torch.optim.AdamW(
        params,
        lr=TRAINING["learning_rate"],
        weight_decay=TRAINING["weight_decay"],
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    return optimizer, scheduler, params


def enable_lora_training(model: Any) -> tuple[list[Any], list[str]]:
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    trainable_names = []
    trainable_params = []
    for name, parameter in model.named_parameters():
        if "lora_" in name:
            parameter.requires_grad_(True)
            trainable_names.append(name)
            trainable_params.append(parameter)
    if not trainable_params:
        raise RuntimeError("loaded Jev adapter contains no LoRA parameters")
    if any("lora_" not in name for name, p in model.named_parameters() if p.requires_grad):
        raise RuntimeError("a non-LoRA parameter became trainable")

    base = model.lm.get_base_model()
    if not hasattr(base, "gradient_checkpointing_enable"):
        raise RuntimeError("base model does not support gradient checkpointing")
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    if hasattr(base, "enable_input_require_grads"):
        base.enable_input_require_grads()
    elif hasattr(base, "get_input_embeddings"):
        embedding = base.get_input_embeddings()
        embedding.register_forward_hook(
            lambda _module, _inputs, output: output.requires_grad_(True)
        )
    if getattr(base, "config", None) is not None and hasattr(base.config, "use_cache"):
        base.config.use_cache = False
    return trainable_params, trainable_names


def fixed_calibrated_loss(raw_logits: Any, target_probs: list[float], bias: Any, temperature: float):
    import torch
    import torch.nn.functional as F

    target = torch.tensor(target_probs, dtype=torch.float32, device=raw_logits.device)
    calibrated = (raw_logits.float() - bias.to(raw_logits.device)) / temperature
    return -(target * F.log_softmax(calibrated, dim=-1)).sum()


def evaluate_split(
    ddp_model: Any,
    entries: list[dict[str, Any]],
    rank: int,
    world_size: int,
    dist: Any,
    torch: Any,
    output_path: Path | None,
) -> dict[str, Any] | None:
    model = ddp_model.module
    model.eval()
    local: list[dict[str, Any]] = []
    with torch.no_grad():
        for index in range(rank, len(entries), world_size):
            entry = entries[index]
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model.forward_batch([entry["enc"]])[0][0]
            probs = torch.softmax(logits.float(), dim=-1)
            if not bool(torch.isfinite(probs).all()) or abs(float(probs.sum().cpu()) - 1.0) > 1e-6:
                raise RuntimeError(f"invalid evaluation probabilities for {entry['row']['state_hash']}")
            p_fail, p_pass = (float(x) for x in probs.detach().cpu().tolist())
            row = entry["row"]
            local.append({
                "dataset": row["dataset"],
                "state_hash": row["state_hash"],
                "task_group": row["task_group"],
                "n_pass": row["n_pass"],
                "n_fail": row["n_fail"],
                "n_trials": row["n_trials"],
                "p_fail": p_fail,
                "p_pass": p_pass,
            })
    gathered: list[Any] = [None] * world_size
    dist.all_gather_object(gathered, local)
    metrics = None
    if rank == 0:
        predictions = sorted(
            [item for shard in gathered for item in shard],
            key=lambda item: item["state_hash"],
        )
        if len(predictions) != len(entries):
            raise RuntimeError("distributed evaluation prediction count mismatch")
        if len({row["state_hash"] for row in predictions}) != len(predictions):
            raise RuntimeError("distributed evaluation duplicated a state")
        metrics = metrics_by_dataset(predictions)
        if output_path is not None:
            atomic_jsonl(output_path, predictions)
    dist.barrier()
    return metrics


def gather_rng_state(torch: Any, dist: Any, world_size: int, device: int) -> list[dict[str, Any]]:
    local = {
        "python": random.getstate(),
        "torch_cpu": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state(device),
    }
    gathered: list[Any] = [None] * world_size
    dist.all_gather_object(gathered, local)
    return gathered


def restore_rng_state(torch: Any, state: dict[str, Any], device: int) -> None:
    random.setstate(state["python"])
    torch.set_rng_state(state["torch_cpu"])
    torch.cuda.set_rng_state(state["torch_cuda"], device)


def atomic_checkpoint(
    model: Any,
    optimizer: Any,
    scheduler: Any,
    epoch: int,
    global_step: int,
    best_epoch: int,
    best_val_nll: float,
    stale_epochs: int,
    epoch_record: dict[str, Any],
    validation_path: Path,
    run_root: Path,
    rank: int,
    world_size: int,
    device: int,
    dist: Any,
    torch: Any,
    config_sha256: str,
    data_checksums: dict[str, str],
) -> None:
    rng_states = gather_rng_state(torch, dist, world_size, device)
    dist.barrier()
    if rank == 0:
        checkpoints = run_root / "checkpoints"
        checkpoints.mkdir(parents=True, exist_ok=True)
        final = checkpoints / f"epoch_{epoch:02d}"
        tmp = checkpoints / f".epoch_{epoch:02d}.tmp.{os.getpid()}"
        if final.exists() or tmp.exists():
            raise FileExistsError(f"refusing to overwrite checkpoint {final}")
        tmp.mkdir(parents=True)
        prediction_hash = file_sha256(validation_path)
        model.save_checkpoint(tmp, extra_meta={"epoch": epoch, "selected_by": "validation_trial_weighted_soft_nll"})
        training_state = {
            "epoch": epoch,
            "global_step": global_step,
            "best_epoch": best_epoch,
            "best_val_nll": best_val_nll,
            "stale_epochs": stale_epochs,
            "epoch_record": epoch_record,
            "validation_prediction": validation_path.name,
            "validation_prediction_sha256": prediction_hash,
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "rng_by_rank": rng_states,
            "config_sha256": config_sha256,
            "data_checksums": data_checksums,
        }
        torch.save(training_state, tmp / "training_state.pt")
        for path in tmp.iterdir():
            if path.is_file():
                with path.open("rb") as f:
                    os.fsync(f.fileno())
        fd = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, final)
        atomic_json(run_root / "latest.json", {"checkpoint": final.name, "epoch": epoch})
        if epoch_record["selected"]:
            atomic_json(run_root / "best.json", {
                "checkpoint": final.name,
                "epoch": epoch,
                "validation_trial_weighted_nll": best_val_nll,
            })
        append_jsonl(run_root / "metrics.jsonl", epoch_record)
    dist.barrier()


def reconcile_resume(
    run_root: Path, torch: Any, *, repair: bool = True
) -> tuple[Path | None, dict[str, Any] | None, list[dict[str, Any]]]:
    latest_path = run_root / "latest.json"
    events_path = run_root / "metrics.jsonl"
    events = read_jsonl(events_path) if events_path.exists() else []
    if not latest_path.exists():
        checkpoints = run_root / "checkpoints"
        committed = list(checkpoints.glob("epoch_[0-9][0-9]")) if checkpoints.exists() else []
        if committed or events:
            raise ValueError("checkpoint artifacts exist but latest pointer is missing")
        return None, None, events

    latest = read_json(latest_path)
    checkpoint = run_root / "checkpoints" / latest["checkpoint"]
    state = torch.load(checkpoint / "training_state.pt", map_location="cpu", weights_only=False)
    if int(state["epoch"]) != int(latest["epoch"]):
        raise ValueError("latest pointer and resumable checkpoint epoch disagree")
    event_epochs = [int(event["epoch"]) for event in events]
    if len(event_epochs) != len(set(event_epochs)) or any(epoch > state["epoch"] for epoch in event_epochs):
        raise ValueError("epoch log and latest checkpoint are inconsistent")
    if state["epoch"] not in event_epochs:
        if repair:
            append_jsonl(events_path, state["epoch_record"])
        events.append(state["epoch_record"])
    predictions = run_root / "validation" / state["validation_prediction"]
    if not predictions.exists() or file_sha256(predictions) != state["validation_prediction_sha256"]:
        raise ValueError("latest checkpoint validation predictions are missing or changed")

    # The checkpoint directory is committed before latest.json. Recover that single
    # valid next epoch if the process died between the directory rename and pointer update.
    orphan_epoch = int(state["epoch"]) + 1
    orphan = run_root / "checkpoints" / f"epoch_{orphan_epoch:02d}"
    if orphan.exists():
        if orphan_epoch in event_epochs:
            raise ValueError("orphan checkpoint already appears in the epoch log")
        candidate = torch.load(orphan / "training_state.pt", map_location="cpu", weights_only=False)
        if int(candidate["epoch"]) != orphan_epoch:
            raise ValueError("orphan checkpoint directory and state epoch disagree")
        if candidate["config_sha256"] != state["config_sha256"] or candidate["data_checksums"] != state["data_checksums"]:
            raise ValueError("orphan checkpoint config or data checksums differ")
        candidate_predictions = run_root / "validation" / candidate["validation_prediction"]
        if (
            not candidate_predictions.exists()
            or file_sha256(candidate_predictions) != candidate["validation_prediction_sha256"]
            or not (orphan / "head.pt").is_file()
            or not (orphan / "adapter_model.safetensors").is_file()
        ):
            raise ValueError("orphan checkpoint is incomplete or its validation predictions changed")
        if not repair:
            raise ValueError("orphan checkpoint was not promoted by rank zero before resume")
        atomic_json(latest_path, {"checkpoint": orphan.name, "epoch": orphan_epoch})
        append_jsonl(events_path, candidate["epoch_record"])
        events.append(candidate["epoch_record"])
        checkpoint, state = orphan, candidate
    best_checkpoint = run_root / "checkpoints" / f"epoch_{int(state['best_epoch']):02d}"
    if not best_checkpoint.is_dir():
        raise ValueError("best checkpoint referenced by resumable state is missing")
    expected_best = {
        "checkpoint": best_checkpoint.name,
        "epoch": int(state["best_epoch"]),
        "validation_trial_weighted_nll": float(state["best_val_nll"]),
    }
    best_path = run_root / "best.json"
    if repair:
        atomic_json(best_path, expected_best)
    elif not best_path.exists() or read_json(best_path) != expected_best:
        raise ValueError("best checkpoint pointer disagrees with resumable state")
    return checkpoint, state, events


def create_run_manifest(
    run_root: Path,
    checkpoint_dir: Path,
    base_dir: Path,
    data_dir: Path,
    split_dir: Path,
    calibration: dict[str, Any],
    data_checksums: dict[str, str],
) -> tuple[dict[str, Any], str]:
    source = model_source_checksums(checkpoint_dir, base_dir)
    split_manifest = read_json(split_dir / "split_manifest.json")
    if split_manifest["split_sha256"]["train"] != file_sha256(split_dir / "train.jsonl"):
        raise ValueError("frozen train split hash mismatch")
    if split_manifest["split_sha256"]["validation"] != file_sha256(split_dir / "validation.jsonl"):
        raise ValueError("frozen validation split hash mismatch")
    audit, token_limits, _ = training_data_gate(data_dir)
    if not all(audit["checks"].values()) or audit["_normalized_overflow_inputs"] != 0:
        raise ValueError("independent data audit did not pass")
    if token_limits != {
        "state": LIMITS["max_state"],
        "causal_row": LIMITS["max_branch"],
        "packed": LIMITS["max_packed"],
        "branch_semantics": "state_tokens_plus_question_branch_tokens",
    }:
        raise ValueError("independent data audit token limits differ from training configuration")
    config = {
        "protocol": "jev_passfail_probability_v1_caps6144x6144",
        "training": TRAINING,
        "token_limits": LIMITS,
        "question": QUESTION,
        "calibration": calibration,
        "base_checkpoint_dir": str(checkpoint_dir),
        "base_dir": str(base_dir),
        "base_checkpoint_sha256": source,
        "data_checksums": data_checksums,
        "split_sha256": split_manifest["split_sha256"],
        "code_sha256": {
            path.name: file_sha256(path)
            for path in Path(__file__).parent.glob("*.py")
            if path.name in {
                "train_jev.py", "metrics.py", "training_utils.py", "audit_prepared.py", "prepare_data.py"
            }
        },
    }
    config_hash = canonical_sha256(config)
    config["config_sha256"] = config_hash
    path = run_root / "run_manifest.json"
    if path.exists():
        previous = read_json(path)
        if previous.get("config_sha256") != config_hash:
            raise ValueError("run manifest changed; start a new run directory")
        return previous, config_hash
    atomic_json(path, {"created_at_utc": utc_now(), **config})
    return config, config_hash


def smoke(args: argparse.Namespace, runtime: dict[str, Any]) -> None:
    torch = runtime["torch"]
    dist = runtime["dist"]
    rank = runtime["rank"]
    world_size = runtime["world_size"]
    local_rank = runtime["local_rank"]
    service_model = runtime["service_model"]
    dist.barrier()

    model, tokenizer = service_model.load_checkpoint(
        args.checkpoint_dir,
        device=f"cuda:{local_rank}",
        dtype=torch.bfloat16,
    )
    smoke_entries = load_encoded(
        args.smoke_jsonl,
        tokenizer,
        runtime["encode_record"],
        limit=args.smoke_rows,
        distinct_datasets=(args.smoke_rows == 2),
    )
    entry = smoke_entries[rank % len(smoke_entries)]
    trainable, trainable_names = enable_lora_training(model)
    optimizer, scheduler, _ = make_optimizer(model, torch)
    ddp_model = torch.nn.parallel.DistributedDataParallel(
        model,
        device_ids=[local_rank],
        output_device=local_rank,
        find_unused_parameters=False,
        broadcast_buffers=False,
    )
    bias, temperature, calibration = calibration_values(model)
    if not bool(model.head.use_prior):
        raise RuntimeError("Jev inference calibration is disabled in the loaded checkpoint")

    model.eval()
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        rows = model._extract_causal_rows(entry["enc"])
        hidden = model._forward_causal_rows(rows)
        n_opts = int(entry["enc"]["n_opts"][0])
        raw_reference = model.head.forward_raw(hidden[0], n_opts)
        inferred_logits = model.head(hidden[0], n_opts, q_type=QUESTION["type"])
        expected_inferred = (raw_reference.float() - bias) / temperature
        if not torch.allclose(inferred_logits.float(), expected_inferred, atol=1e-5, rtol=1e-5):
            raise RuntimeError("Jev inference calibration differs from the fixed training calibration")

    model.train()
    optimizer.zero_grad(set_to_none=True)
    input_ids = torch.tensor([int(entry["row"]["n_trials"])], dtype=torch.float64, device=local_rank)
    dist.all_reduce(input_ids, op=dist.ReduceOp.SUM)
    global_trials = float(input_ids.item())
    with torch.autocast("cuda", dtype=torch.bfloat16):
        logits = ddp_model(entry["enc"])[0]
        loss = fixed_calibrated_loss(
            logits,
            entry["row"]["target_probs"],
            bias,
            temperature,
        )
    manual_target = torch.tensor(
        entry["row"]["target_probs"], dtype=torch.float32, device=logits.device
    )
    manual_calibrated = (logits.detach().float() - bias.to(logits.device)) / temperature
    manual = -(manual_target * torch.log_softmax(manual_calibrated, dim=-1)).sum()
    if not torch.isfinite(loss) or abs(float(loss.detach().cpu()) - float(manual.cpu())) > 1e-6:
        raise RuntimeError("smoke soft-target loss is nonfinite or disagrees with direct calculation")
    scaled_loss = loss * (world_size * int(entry["row"]["n_trials"]) / global_trials)
    scaled_loss.backward()
    for name, parameter in model.named_parameters():
        if "lora_" in name and parameter.grad is None:
            raise RuntimeError(f"LoRA parameter received no gradient: {name}")
        if "lora_" not in name and parameter.grad is not None:
            raise RuntimeError(f"non-LoRA parameter received a gradient: {name}")
    changed_candidates = [
        (name, parameter)
        for name, parameter in model.named_parameters()
        if "lora_" in name and parameter.grad is not None and torch.count_nonzero(parameter.grad).item() > 0
    ]
    if not changed_candidates:
        raise RuntimeError("smoke produced no nonzero LoRA gradient")
    changed_name, changed_parameter = changed_candidates[0]
    before = changed_parameter.detach().clone()
    torch.nn.utils.clip_grad_norm_(trainable, TRAINING["gradient_clip"])
    optimizer.step()
    scheduler.step()
    if torch.equal(before, changed_parameter.detach()):
        raise RuntimeError("optimizer step did not change a LoRA parameter")

    model.eval()
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        eval_logits = model.forward_batch([entry["enc"]])[0][0]
        probabilities = torch.softmax(eval_logits.float(), dim=-1)
    if not bool(torch.isfinite(probabilities).all()) or abs(float(probabilities.sum().cpu()) - 1.0) > 1e-6:
        raise RuntimeError("smoke probabilities are not finite and normalized")
    before_reload = probabilities.detach().cpu()

    run_root = args.out_root
    if rank == 0:
        if run_root.exists() and any(run_root.iterdir()):
            raise FileExistsError(f"smoke output already exists: {run_root}")
        run_root.mkdir(parents=True, exist_ok=True)
    dist.barrier()
    rng_states = gather_rng_state(torch, dist, world_size, local_rank)
    checkpoint_path = run_root / "checkpoint"
    if rank == 0:
        tmp = run_root / f".checkpoint.tmp.{os.getpid()}"
        tmp.mkdir(parents=True)
        model.save_checkpoint(tmp, extra_meta={"smoke": True, "input_state_hash": entry["row"]["state_hash"]})
        torch.save({
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "rng_by_rank": rng_states,
            "epoch": 0,
            "global_step": 1,
            "calibration": calibration,
        }, tmp / "training_state.pt")
        os.replace(tmp, checkpoint_path)
    dist.barrier()

    del ddp_model, optimizer, scheduler, trainable, model
    torch.cuda.synchronize(local_rank)
    torch.cuda.empty_cache()
    reloaded, _ = service_model.load_checkpoint(
        checkpoint_path,
        device=f"cuda:{local_rank}",
        dtype=torch.bfloat16,
    )
    reloaded_params, _ = enable_lora_training(reloaded)
    restored_optimizer, restored_scheduler, _ = make_optimizer(reloaded, torch)
    checkpoint_state = torch.load(
        checkpoint_path / "training_state.pt", map_location="cpu", weights_only=False
    )
    restored_optimizer.load_state_dict(checkpoint_state["optimizer_state"])
    restored_scheduler.load_state_dict(checkpoint_state["scheduler_state"])
    if not restored_optimizer.state:
        raise RuntimeError("smoke optimizer state did not survive checkpoint reload")
    reloaded.eval()
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        logits_after = reloaded.forward_batch([entry["enc"]])[0][0]
        probabilities_after = torch.softmax(logits_after.float(), dim=-1).cpu()
    delta = float(torch.max(torch.abs(before_reload - probabilities_after)))
    if delta > 1e-6:
        raise RuntimeError(f"save/reload probability mismatch: max_abs_diff={delta}")
    local_report = {
        "rank": rank,
        "state_hash": entry["row"]["state_hash"],
        "dataset": entry["row"]["dataset"],
        "task_group": entry["row"]["task_group"],
        "sequence_tokens": len(entry["enc"]["causal_rows"][0]),
        "n_trials": entry["row"]["n_trials"],
        "loss": float(manual.cpu()),
        "probabilities": before_reload.tolist(),
        "reload_max_abs_probability_difference": delta,
    }
    gathered_reports: list[Any] = [None] * world_size
    dist.all_gather_object(gathered_reports, local_report)
    reports_by_state: dict[str, dict[str, Any]] = {}
    for report in gathered_reports:
        previous = reports_by_state.get(report["state_hash"])
        if previous is not None:
            repeated_delta = max(
                abs(a - b) for a, b in zip(previous["probabilities"], report["probabilities"])
            )
            if repeated_delta > 1e-6:
                raise RuntimeError("DDP ranks produced different probabilities for the same smoke input")
        else:
            reports_by_state[report["state_hash"]] = report
    smoke_coverage = sorted(reports_by_state.values(), key=lambda item: item["dataset"])
    expected_datasets = {entry["row"]["dataset"] for entry in smoke_entries}
    observed_datasets = {report["dataset"] for report in smoke_coverage}
    if len(smoke_coverage) != args.smoke_rows or observed_datasets != expected_datasets:
        raise RuntimeError("8-GPU smoke did not cover each selected training input exactly")
    if args.smoke_rows == 2 and observed_datasets != {"searchqa", "alfworld"}:
        raise RuntimeError("two-row smoke must cover SearchQA and ALFWorld")
    del reloaded, restored_optimizer, restored_scheduler, reloaded_params
    torch.cuda.empty_cache()
    if rank == 0:
        atomic_json(run_root / "smoke_result.json", {
            "state_hash": entry["row"]["state_hash"],
            "task_group": entry["row"]["task_group"],
            "sequence_tokens": len(entry["enc"]["causal_rows"][0]),
            "world_size": world_size,
            "global_trial_weight": global_trials,
            "loss": float(manual.cpu()),
            "probabilities": before_reload.tolist(),
            "reload_max_abs_probability_difference": delta,
            "changed_lora_parameter": changed_name,
            "trainable_parameter_count": len(trainable_names),
            "input_coverage": smoke_coverage,
            "checks": {
                "finite_soft_loss": True,
                "inference_and_training_calibration_match": True,
                "all_gradients_are_lora_only": True,
                "optimizer_updated_lora": True,
                "probabilities_normalized": True,
                "adapter_optimizer_scheduler_reload": True,
                "prediction_reload_equal": True,
                "all_selected_datasets_covered": True,
                "ddp_duplicate_input_predictions_equal": True,
            },
        })
    dist.barrier()


def train(args: argparse.Namespace, runtime: dict[str, Any]) -> None:
    torch = runtime["torch"]
    dist = runtime["dist"]
    rank = runtime["rank"]
    world_size = runtime["world_size"]
    local_rank = runtime["local_rank"]
    service_model = runtime["service_model"]

    data_audit, token_limits, expected_train_examples = training_data_gate(args.data_dir)
    if not all(data_audit["checks"].values()) or data_audit["_normalized_overflow_inputs"]:
        raise RuntimeError("training blocked because the independent data audit failed")
    if token_limits != {
        "state": LIMITS["max_state"],
        "causal_row": LIMITS["max_branch"],
        "packed": LIMITS["max_packed"],
        "branch_semantics": "state_tokens_plus_question_branch_tokens",
    }:
        raise ValueError("frozen data token limits differ from the training configuration")

    lock = acquire_run_lock(args.out_root, rank)
    if rank == 0 and not args.resume:
        if any(path.name != "trainer.lock" for path in args.out_root.iterdir()):
            raise FileExistsError(f"training output already has files: {args.out_root}")
        (args.out_root / "checkpoints").mkdir(parents=True, exist_ok=True)
        (args.out_root / "validation").mkdir(parents=True, exist_ok=True)
    dist.barrier()

    checksums = dataset_checksums(args.data_dir, args.split_dir) if rank == 0 else None
    source_checksums = model_source_checksums(args.checkpoint_dir, args.base_dir) if rank == 0 else None
    obj = [checksums, source_checksums]
    dist.broadcast_object_list(obj, src=0)
    checksums, source_checksums = obj
    split_manifest = read_json(args.split_dir / "split_manifest.json")
    if split_manifest["split_sha256"]["train"] != file_sha256(args.split_dir / "train.jsonl"):
        raise ValueError("train split changed after freeze")
    if split_manifest["split_sha256"]["validation"] != file_sha256(args.split_dir / "validation.jsonl"):
        raise ValueError("validation split changed after freeze")

    if args.resume:
        if rank == 0:
            reconcile_resume(args.out_root, torch, repair=True)
        dist.barrier()
        resume_checkpoint, saved_state, _events = reconcile_resume(
            args.out_root, torch, repair=False
        )
        if saved_state is not None:
            if saved_state["data_checksums"] != checksums:
                raise ValueError("frozen data changed since the previous checkpoint")
            if saved_state["config_sha256"] != read_json(args.out_root / "run_manifest.json")["config_sha256"]:
                raise ValueError("resume config checksum mismatch")
            completed_path = args.out_root / "training_complete.json"
            if completed_path.exists():
                completed = read_json(completed_path)
                if (
                    int(completed["last_epoch"]) != int(saved_state["epoch"])
                    or int(completed["best_epoch"]) != int(saved_state["best_epoch"])
                    or completed["best_checkpoint"] != f"epoch_{int(saved_state['best_epoch']):02d}"
                ):
                    raise ValueError("training completion marker disagrees with the latest checkpoint")
                if rank == 0:
                    print(json.dumps({"event": "resume_noop", "last_epoch": completed["last_epoch"]}), flush=True)
                dist.barrier()
                if lock is not None:
                    lock.close()
                return
        checkpoint_to_load = resume_checkpoint or args.checkpoint_dir
    else:
        saved_state = None
        checkpoint_to_load = args.checkpoint_dir

    model, tokenizer = service_model.load_checkpoint(
        checkpoint_to_load,
        device=f"cuda:{local_rank}",
        dtype=torch.bfloat16,
    )
    trainable_params, trainable_names = enable_lora_training(model)
    bias, temperature, calibration = calibration_values(model)
    if not bool(model.head.use_prior):
        raise RuntimeError("Jev inference calibration is disabled in the loaded checkpoint")
    if rank == 0:
        current_config, config_hash = create_run_manifest(
            args.out_root,
            args.checkpoint_dir,
            args.base_dir,
            args.data_dir,
            args.split_dir,
            calibration,
            checksums,
        )
        if current_config.get("base_checkpoint_sha256") != source_checksums:
            raise ValueError("base checkpoint changed while creating the run manifest")
        config_obj = [config_hash]
    else:
        config_obj = [None]
    dist.broadcast_object_list(config_obj, src=0)
    config_hash = config_obj[0]
    dist.barrier()

    train_entries = load_encoded(args.split_dir / "train.jsonl", tokenizer, runtime["encode_record"])
    validation_entries = load_encoded(
        args.split_dir / "validation.jsonl", tokenizer, runtime["encode_record"]
    )
    if len(train_entries) != expected_train_examples:
        raise ValueError("encoded train count differs from the independent audit")

    optimizer, scheduler, trainable_params = make_optimizer(model, torch)
    ddp_model = torch.nn.parallel.DistributedDataParallel(
        model,
        device_ids=[local_rank],
        output_device=local_rank,
        find_unused_parameters=False,
        broadcast_buffers=False,
    )
    if saved_state is None:
        start_epoch = 1
        global_step = 0
        best_epoch = None
        best_val_nll = math.inf
        stale_epochs = 0
        baseline_path = args.out_root / "validation" / "baseline_jev.jsonl"
        baseline_metrics_path = args.out_root / "validation" / "baseline_jev_metrics.json"
        existing_baseline = baseline_path.exists() or baseline_metrics_path.exists()
        if existing_baseline and not args.resume:
            raise FileExistsError("baseline validation outputs exist without a resumable checkpoint")
        if existing_baseline and baseline_path.exists():
            baseline_rows = read_jsonl(baseline_path)
            expected_hashes = sorted(entry["row"]["state_hash"] for entry in validation_entries)
            actual_hashes = sorted(row["state_hash"] for row in baseline_rows)
            if actual_hashes != expected_hashes:
                raise ValueError("partial-run baseline predictions do not match the frozen validation split")
            baseline = metrics_by_dataset(baseline_rows)
            if baseline_metrics_path.exists() and canonical_sha256(read_json(baseline_metrics_path)) != canonical_sha256(baseline):
                raise ValueError("partial-run baseline metrics do not match its saved predictions")
        else:
            baseline = evaluate_split(
                ddp_model,
                validation_entries,
                rank,
                world_size,
                dist,
                torch,
                baseline_path,
            )
        if rank == 0:
            atomic_json(baseline_metrics_path, baseline)
            print(json.dumps({"event": "baseline_validation", "metrics": baseline}, ensure_ascii=False), flush=True)
        dist.barrier()
    else:
        optimizer.load_state_dict(saved_state["optimizer_state"])
        scheduler.load_state_dict(saved_state["scheduler_state"])
        if len(saved_state["rng_by_rank"]) != world_size:
            raise ValueError("checkpoint RNG state does not match world size")
        restore_rng_state(torch, saved_state["rng_by_rank"][rank], local_rank)
        start_epoch = int(saved_state["epoch"]) + 1
        global_step = int(saved_state["global_step"])
        best_epoch = saved_state["best_epoch"]
        best_val_nll = float(saved_state["best_val_nll"])
        stale_epochs = int(saved_state["stale_epochs"])

    remaining_epochs = range(start_epoch, TRAINING["epochs"] + 1)
    if stale_epochs >= TRAINING["patience"]:
        remaining_epochs = range(start_epoch, start_epoch)
    for epoch in remaining_epochs:
        model.train()
        started = time.monotonic()
        for global_indices, per_rank in epoch_batches(
            len(train_entries),
            world_size,
            TRAINING["global_effective_batch"],
            TRAINING["seed"],
            epoch,
        ):
            global_weight = sum(
                int(train_entries[index]["row"]["n_trials"])
                for index in global_indices
            )
            if global_weight <= 0:
                raise RuntimeError("global batch has no observed trials")
            local_indices = per_rank[rank]
            optimizer.zero_grad(set_to_none=True)
            for micro_index, index in enumerate(local_indices):
                sync_context = (
                    contextlib.nullcontext()
                    if micro_index == len(local_indices) - 1
                    else ddp_model.no_sync()
                )
                entry = train_entries[index] if index >= 0 else train_entries[0]
                with sync_context:
                    with torch.autocast("cuda", dtype=torch.bfloat16):
                        logits = ddp_model(entry["enc"])[0]
                        if index >= 0:
                            row = entry["row"]
                            per_input_loss = fixed_calibrated_loss(
                                logits, row["target_probs"], bias, temperature
                            )
                            numerator = per_input_loss * int(row["n_trials"])
                        else:
                            numerator = logits.sum() * 0.0
                        loss = numerator * (world_size / global_weight)
                    loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable_params, TRAINING["gradient_clip"])
            optimizer.step()
            scheduler.step()
            global_step += 1

        prediction_path = args.out_root / "validation" / f"epoch_{epoch:02d}.jsonl"
        validation = evaluate_split(
            ddp_model,
            validation_entries,
            rank,
            world_size,
            dist,
            torch,
            prediction_path,
        )
        selection_nll = float(validation["overall"]["nll"]) if rank == 0 else None
        broadcast = [selection_nll]
        dist.broadcast_object_list(broadcast, src=0)
        selection_nll = float(broadcast[0])
        improved = best_epoch is None or selection_nll < best_val_nll - TRAINING["min_delta"]
        if improved:
            best_val_nll = selection_nll
            best_epoch = epoch
            stale_epochs = 0
        else:
            stale_epochs += 1
        epoch_record = {
            "epoch": epoch,
            "global_step": global_step,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "validation": validation,
            "selected": improved,
            "best_epoch": best_epoch,
            "best_validation_trial_weighted_nll": best_val_nll,
            "stale_epochs": stale_epochs,
        }
        atomic_checkpoint(
            model,
            optimizer,
            scheduler,
            epoch,
            global_step,
            best_epoch,
            best_val_nll,
            stale_epochs,
            epoch_record,
            prediction_path,
            args.out_root,
            rank,
            world_size,
            local_rank,
            dist,
            torch,
            config_hash,
            checksums,
        )
        if rank == 0:
            print(json.dumps({"event": "epoch_complete", **epoch_record}, ensure_ascii=False), flush=True)
        if stale_epochs >= TRAINING["patience"]:
            break

    if rank == 0:
        best = read_json(args.out_root / "best.json")
        atomic_json(args.out_root / "training_complete.json", {
            "finished_at_utc": utc_now(),
            "best_checkpoint": best["checkpoint"],
            "best_epoch": best["epoch"],
            "best_validation_trial_weighted_nll": best["validation_trial_weighted_nll"],
            "last_epoch": int(read_json(args.out_root / "latest.json")["epoch"]),
            "early_stopped": stale_epochs >= TRAINING["patience"],
        })
    dist.barrier()
    if lock is not None:
        lock.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-dir", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--split-dir", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--smoke-jsonl", type=Path)
    parser.add_argument("--smoke-rows", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.smoke and args.resume:
        raise SystemExit("--smoke and --resume cannot be combined")
    if args.smoke and args.smoke_jsonl is None:
        raise SystemExit("--smoke requires --smoke-jsonl")
    if args.smoke and args.smoke_rows not in (1, 2):
        raise SystemExit("--smoke-rows must be 1 or 2")
    os.environ["MINICPM_S1_BASE_MODEL_PATH"] = str(args.base_dir.resolve())
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(args.service_dir.resolve()))
    import torch
    import torch.distributed as dist
    from model import MiniCPMSystemOne, encode_record

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if world_size != 8:
        raise SystemExit(f"the registered experiment requires exactly 8 ranks; got {world_size}")
    if torch.cuda.device_count() < world_size:
        raise SystemExit(f"requested {world_size} ranks but only {torch.cuda.device_count()} CUDA devices are visible")
    torch.cuda.set_device(local_rank)
    torch.set_num_threads(4)
    torch.manual_seed(TRAINING["seed"] + rank)
    torch.cuda.manual_seed_all(TRAINING["seed"] + rank)
    random.seed(TRAINING["seed"] + rank)
    dist.init_process_group(backend="nccl")

    runtime = {
        "torch": torch,
        "dist": dist,
        "rank": rank,
        "world_size": world_size,
        "local_rank": local_rank,
        "service_model": MiniCPMSystemOne,
        "encode_record": encode_record,
    }
    try:
        if args.smoke:
            smoke(args, runtime)
        else:
            train(args, runtime)
    finally:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
