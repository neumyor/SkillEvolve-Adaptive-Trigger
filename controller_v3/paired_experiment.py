"""Small paired original-vs-Controller runner with resume and raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .audit import audit_run
from .core import FixedImmediateSchedule
from .llm import build_llm
from .native_bridges import BRIDGE_TYPES
from .usage import LedgerLLM, TokenLedger
from .config import runtime_paths


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _item_hashes(items: list[dict[str, Any]]) -> dict[str, str]:
    """Keep per-id fingerprints so resume cannot mix changed task payloads."""
    return {str(item["id"]): _hash(item) for item in items}


def _read_progress(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = str(item.get("task_id", ""))
        if task_id:
            rows.setdefault(task_id, item)
    return rows


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _combine_results(parts: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = [part.get("decision", "WAIT") for part in parts]
    updates = [part.get("update", {}) for part in parts]
    return {
        "rows": rows,
        "decision": decisions[-1] if decisions else "WAIT",
        "decisions": decisions,
        "reason": parts[-1].get("reason", "") if parts else "resumed from task evidence",
        "update": updates[-1] if updates else {"accepted": False, "reason": "no new window"},
        "updates": updates,
        "windows": len(parts),
    }


def _run_condition_unlocked(
    method: str,
    condition: str,
    items: list[dict[str, Any]],
    out: Path,
    max_tokens: int,
    *,
    batch_size: int = 4,
    heldout_items: list[dict[str, Any]] | None = None,
    skill: str = "Answer the question from context and use concise <answer> tags.",
    domain: str = "searchqa",
    bridge_type: Any | None = None,
    llm_name: str | None = None,
    api_workers: int = 1,
    enable_thinking: bool | None = False,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    item_ids = [str(x["id"]) for x in items]
    manifest = {
        "method": method,
        "condition": condition,
        "domain": domain,
        "evaluation_harness": (
            "benchmark/alfworld-eval" if domain == "alfworld" else "benchmark/searchqa-eval"
        ),
        "llm_name": llm_name or "searchqa-eval",
        "max_tokens": max_tokens,
        "api_workers": max(1, int(api_workers)),
        "enable_thinking": enable_thinking,
        "alfworld_thinking": False if domain == "alfworld" else None,
        "alfworld_env_batch_size": (
            int(os.environ.get("CONTROLLER_V3_ALF_ENV_BATCH_SIZE", "1"))
            if domain == "alfworld" else None
        ),
        "items": item_ids,
        "item_hashes": _item_hashes(items),
        "items_hash": _hash(items),
        "skill_hash": _hash(skill),
    }
    manifest.update({
        "runner_version": "paired-v3-isolated",
        "baseline_definition": (
            "fixed immediate UPDATE schedule through the native bridge"
            if condition == "original" else "Controller V3 adaptive WAIT/UPDATE schedule"
        ),
        "checkpoint_granularity": "task evidence, flushed after each window",
        "comparison_scope": "native bridge smoke schedule; not a complete upstream training harness",
    })
    old_manifest = None
    if (out / "manifest.json").exists():
        try:
            old_manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old_manifest = None
    if old_manifest and (
        old_manifest.get("domain", "searchqa") != domain
        or old_manifest.get("method") != method
        or old_manifest.get("condition") != condition
        or old_manifest.get("skill_hash") != manifest["skill_hash"]
    ):
        raise ValueError(f"existing run manifest does not match {domain}/{method}/{condition}")
    if old_manifest:
        # These parameters determine both the model behavior and the unit of
        # the cost comparison.  A resume must never append calls made with a
        # different endpoint/model budget to the existing token ledger.
        for field in ("runner_version", "evaluation_harness", "llm_name", "max_tokens", "api_workers", "enable_thinking", "alfworld_thinking", "alfworld_env_batch_size"):
            if old_manifest.get(field) != manifest.get(field):
                raise ValueError(
                    f"existing run manifest runtime configuration changed: {field}"
                )
        old_ids = [str(value) for value in old_manifest.get("items", [])]
        # A resumed run may append a suffix of new tasks, but it must preserve
        # the prior stream prefix because Controller state depends on order.
        if old_ids and item_ids[: len(old_ids)] != old_ids:
            raise ValueError("existing run manifest task order does not match the requested prefix")
        old_item_hashes = old_manifest.get("item_hashes", {})
        if isinstance(old_item_hashes, dict):
            changed = [
                task_id for task_id in old_ids
                if task_id in manifest["item_hashes"]
                and old_item_hashes.get(task_id) != manifest["item_hashes"].get(task_id)
            ]
            if changed:
                raise ValueError(f"existing run manifest task payload changed: {changed[:3]}")
        elif len(item_ids) == len(old_ids) and old_manifest.get("items_hash") != manifest["items_hash"]:
            # Manifests produced before per-item hashes still reject a
            # same-size replacement instead of silently mixing evidence.
            raise ValueError("existing run manifest task payload changed")
    _write_json(out / "manifest.json", manifest)
    progress = _read_progress(out / "progress.jsonl")
    existing = set(progress)
    expected = set(item_ids)
    complete = expected.issubset(existing) and all(
        (out / name).exists() for name in ("result.json", "tokens.json", "audit.json")
    )
    if complete:
        resumed_result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        heldout_payload = None
        if heldout_items and (out / "heldout.json").exists():
            try:
                candidate = json.loads((out / "heldout.json").read_text(encoding="utf-8"))
                if [str(x) for x in candidate.get("task_ids", [])] == [str(x["id"]) for x in heldout_items]:
                    heldout_payload = candidate
            except (OSError, json.JSONDecodeError, TypeError):
                heldout_payload = None
        if not heldout_items or heldout_payload is not None:
            if heldout_payload is not None:
                resumed_result["heldout_rows"] = heldout_payload.get("rows", [])
            return {
                "method": method,
                "condition": condition,
                "result": resumed_result,
                "tokens": json.loads((out / "tokens.json").read_text(encoding="utf-8"))["summary"],
                "audit": json.loads((out / "audit.json").read_text(encoding="utf-8")),
                "resumed": True,
            }
    ledger = TokenLedger(condition=condition, method=method)
    if (out / "tokens.json").exists():
        try:
            ledger.merge(json.loads((out / "tokens.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    try:
        if llm_name is None:
            client = build_llm(max_tokens=max_tokens, enable_thinking=enable_thinking)
        else:
            client = build_llm(llm_name, max_tokens=max_tokens, enable_thinking=enable_thinking)
    except TypeError as exc:
        # Preserve compatibility with test doubles and older callers that
        # expose only the original max_tokens argument.
        if "enable_thinking" not in str(exc):
            raise
        if llm_name is None:
            client = build_llm(max_tokens=max_tokens)
        else:
            client = build_llm(llm_name, max_tokens=max_tokens)
    if domain == "alfworld":
        client.timeout = float(os.environ.get("CONTROLLER_V3_ALF_API_TIMEOUT", "120"))
        client.retries = int(os.environ.get("CONTROLLER_V3_ALF_API_ATTEMPTS", "2"))
        client.retry_backoff = float(os.environ.get("CONTROLLER_V3_ALF_RETRY_BACKOFF", "0"))
    llm = LedgerLLM(client, ledger)
    controller = FixedImmediateSchedule() if condition == "original" else None
    bridge_cls = bridge_type or BRIDGE_TYPES[method]
    try:
        bridge = bridge_cls(llm, controller=controller, rollout_workers=max(1, int(api_workers)))
    except TypeError as exc:
        # Keep tiny test doubles and legacy third-party bridge constructors
        # compatible while native bridges opt into the worker setting.
        if "rollout_workers" not in str(exc):
            raise
        bridge = bridge_cls(llm, controller=controller)
    if domain == "alfworld":
        setattr(bridge, "max_api_workers", max(1, int(api_workers)))
    bridge.evidence_dir = out
    evaluate_batch = getattr(bridge, "evaluate_only_batch", None)
    state_path = out / "state.json"
    if state_path.exists():
        try:
            checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
            bridge.rollout_call_index = checkpoint.get("rollout_call_index", 0)
            saved_skill = checkpoint.get("skill")
            if isinstance(saved_skill, str):
                skill = saved_skill
            saved_state = checkpoint.get("controller_state")
            if isinstance(saved_state, dict) and hasattr(bridge, "state"):
                bridge.state = saved_state
            saved_attempts = checkpoint.get("attempts")
            if isinstance(saved_attempts, list) and hasattr(bridge, "attempts"):
                bridge.attempts = saved_attempts
        except (OSError, json.JSONDecodeError, TypeError):
            # A truncated checkpoint must not make the evidence unreadable;
            # the next window starts from the initial controller state.
            pass
    missing = [item for item in items if str(item["id"]) not in existing]
    prior_result: dict[str, Any] = {}
    if (out / "result.json").exists():
        try:
            prior_result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            prior_result = {}
    prior_decisions = prior_result.get("decisions", []) or ([prior_result["decision"]] if prior_result.get("decision") else [])
    prior_updates = prior_result.get("updates", []) or ([prior_result["update"]] if prior_result.get("update") else [])
    parts: list[dict[str, Any]] = [
        {"decision": decision, "update": update}
        for decision, update in zip(prior_decisions, prior_updates)
    ]
    all_rows = [entry.get("row", {}) for entry in progress.values() if isinstance(entry.get("row"), dict)]
    for start in range(0, len(missing), max(1, batch_size)):
        window_items = missing[start : start + max(1, batch_size)]
        part = bridge.run_window(window_items, skill)
        from .validity import require_valid_rows
        require_valid_rows(part.get("rows", []), out)
        parts.append(part)
        next_skill = part.get("next_skill", part.get("skill"))
        if isinstance(next_skill, str) and next_skill.strip():
            skill = next_skill
        for row in part.get("rows", []):
            task_id = str(row.get("id", ""))
            if not task_id or task_id in progress:
                continue
            entry = {
                "task_id": task_id,
                "method": method,
                "condition": condition,
                "window_index": len(parts),
                "row": row,
                "decision": part.get("decision", "WAIT"),
                "update": part.get("update", {}),
            }
            progress[task_id] = entry
            all_rows.append(row)
            with (out / "progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        result = _combine_results(parts, all_rows)
        _write_json(out / "result.json", result)
        llm.ledger.save(out / "tokens.json")
        _write_json(state_path, {
            "skill": skill,
            "controller_state": getattr(bridge, "state", None),
            "attempts": getattr(bridge, "attempts", []),
            "completed_task_ids": sorted(progress),
            "rollout_call_index": getattr(bridge, "rollout_call_index", 0),
        })
        _write_json(out / "audit.json", audit_run(out))

    result = _combine_results(parts, all_rows)
    if heldout_items:
        evaluate_only = getattr(bridge, "evaluate_only", None)
        if evaluate_only is None:
            heldout_rows = []
            result["heldout_warning"] = "bridge does not expose evaluation-only scoring"
        else:
            if callable(evaluate_batch):
                bridge.defer_execution_errors = True
                heldout_rows = []
                chunk_size = max(1, int(api_workers))
                for offset in range(0, len(heldout_items), chunk_size):
                    heldout_rows.extend(evaluate_batch(heldout_items[offset : offset + chunk_size], skill))
            elif api_workers <= 1:
                heldout_rows = [evaluate_only(item, skill) for item in heldout_items]
            else:
                with ThreadPoolExecutor(max_workers=min(api_workers, len(heldout_items))) as executor:
                    futures = [executor.submit(evaluate_only, item, skill) for item in heldout_items]
                    heldout_rows = [future.result() for future in futures]
        from .validity import require_valid_rows
        require_valid_rows(heldout_rows, out)
        # Bridges intentionally return native rows, so preserve the split
        # provenance from the evaluation input for val/test reporting.
        split_by_id = {
            str(item["id"]): item.get("evaluation_split")
            for item in heldout_items
            if item.get("evaluation_split") is not None
        }
        if split_by_id:
            heldout_rows = [
                dict(row, evaluation_split=split_by_id[str(row.get("id"))])
                if str(row.get("id")) in split_by_id else row
                for row in heldout_rows
            ]
        result["heldout_rows"] = heldout_rows
        _write_json(out / "heldout.json", {"rows": heldout_rows, "task_ids": [str(x["id"]) for x in heldout_items]})
    _write_json(out / "result.json", result)
    llm.ledger.save(out / "tokens.json")
    (out / "execution_failure.json").unlink(missing_ok=True)
    audit = audit_run(out)
    _write_json(out / "audit.json", audit)
    return {"method": method, "condition": condition, "result": result, "tokens": llm.ledger.summary(), "audit": audit, "resumed_tasks": sorted(existing), "new_tasks": len(missing)}


def _run_condition(*args, **kwargs):
    """One writer per condition; interrupted runs retain the same lock path."""
    import fcntl
    import inspect
    bound = inspect.signature(_run_condition_unlocked).bind(*args, **kwargs)
    out = Path(bound.arguments["out"])
    out.mkdir(parents=True, exist_ok=True)
    with (out / "condition.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"condition already running: {out}") from exc
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        return _run_condition_unlocked(*args, **kwargs)


def _paired_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for method in sorted({key.split("/", 1)[0] for key in report}):
        original = report.get(f"{method}/original", {})
        controller = report.get(f"{method}/controller", {})
        def metrics(entry: dict[str, Any]) -> dict[str, Any]:
            rows = entry.get("result", {}).get("rows", [])
            hard = [float(row.get("hard", row.get("em", 0.0)) or 0.0) for row in rows]
            soft = [float(row.get("f1", row.get("score", 0.0)) or 0.0) for row in rows]
            return {
                "tasks": len(rows),
                "mean_hard": sum(hard) / len(hard) if hard else None,
                "mean_soft": sum(soft) / len(soft) if soft else None,
                "updates": sum(action == "UPDATE" for action in entry.get("result", {}).get("decisions", [])),
                "accepted": sum(bool(update.get("accepted")) for update in entry.get("result", {}).get("updates", []) if isinstance(update, dict)),
            }
        om, cm = metrics(original), metrics(controller)
        orows = {str(row.get("id")): row for row in original.get("result", {}).get("rows", [])}
        crows = {str(row.get("id")): row for row in controller.get("result", {}).get("rows", [])}
        paired = []
        for task_id in sorted(set(orows) & set(crows)):
            def score(row): return float(row.get("f1", row.get("score", row.get("hard", 0.0))) or 0.0)
            paired.append({"task_id": task_id, "original": score(orows[task_id]), "controller": score(crows[task_id]), "delta": score(crows[task_id]) - score(orows[task_id])})
        ot, ct = original.get("tokens", {}), controller.get("tokens", {})
        summary[method] = {
            "original": om,
            "controller": cm,
            "quality_delta_mean_soft": (cm["mean_soft"] - om["mean_soft"]) if cm["mean_soft"] is not None and om["mean_soft"] is not None else None,
            "paired": paired,
            "token_delta": ct.get("total_tokens", 0) - ot.get("total_tokens", 0),
            "token_savings_fraction": (ot.get("total_tokens", 0) - ct.get("total_tokens", 0)) / ot["total_tokens"] if ot.get("total_tokens") else None,
            "quality_comparison_usable": bool(original.get("audit", {}).get("quality_usable")) and bool(controller.get("audit", {}).get("quality_usable")),
            "cost_comparison_usable": bool(original.get("audit", {}).get("cost_usable")) and bool(controller.get("audit", {}).get("cost_usable")),
            "audit_warnings": {
                "original": original.get("audit", {}).get("warnings", []),
                "controller": controller.get("audit", {}).get("warnings", []),
            },
        }
        for label, entry in (("original", original), ("controller", controller)):
            heldout = entry.get("result", {}).get("heldout_rows", [])
            if heldout:
                values = [float(row.get("f1", row.get("score", 0.0)) or 0.0) for row in heldout]
                summary[method].setdefault("heldout", {})[label] = {
                    "tasks": len(values),
                    "mean_soft": sum(values) / len(values),
                }
    return summary


def run(
    data_path: Path,
    out_dir: Path,
    *,
    start: int = 0,
    limit: int = 4,
    methods: list[str] | None = None,
    max_tokens: int = 512,
    batch_size: int = 4,
    heldout_path: Path | None = None,
    heldout_limit: int = 0,
    bridge_types: dict[str, Any] | None = None,
    skill: str = "Answer the question from context and use concise <answer> tags.",
    domain: str = "searchqa",
    llm_name: str | None = None,
    api_workers: int = 1,
    enable_thinking: bool | None = False,
    items_override: list[dict[str, Any]] | None = None,
    heldout_items_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = (
        list(items_override)
        if items_override is not None
        else json.loads(data_path.read_text(encoding="utf-8"))[start : start + limit]
    )
    if len(items) < 2:
        raise ValueError("paired smoke requires at least two items")
    if bridge_types is None and domain == "alfworld":
        from .alfworld_bridges import ALFWORLD_BRIDGE_TYPES

        selected_types = ALFWORLD_BRIDGE_TYPES
    else:
        selected_types = bridge_types or BRIDGE_TYPES
    selected = methods or list(selected_types)
    heldout_items = list(heldout_items_override or [])
    if not heldout_items and heldout_path and heldout_limit:
        heldout_items = json.loads(heldout_path.read_text(encoding="utf-8"))[:heldout_limit]
    report: dict[str, Any] = {}
    for method in selected:
        for condition in ("original", "controller"):
            report[f"{method}/{condition}"] = _run_condition(
                method,
                condition,
                items,
                out_dir / method / condition,
                max_tokens,
                batch_size=batch_size,
                heldout_items=heldout_items,
                skill=skill,
                domain=domain,
                bridge_type=selected_types[method],
                llm_name=llm_name,
                api_workers=api_workers,
                enable_thinking=enable_thinking,
            )
    report_summary = _paired_summary(report)
    _write_json(out_dir / "summary.json", {"conditions": report, "paired": report_summary})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", type=Path, default=runtime_paths().searchqa_eval_root / "data/searchqa_split/train/items.json")
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/controller_v3_paired_smoke"))
    parser.add_argument("--start", type=int, default=100)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--methods", nargs="*", choices=sorted(BRIDGE_TYPES))
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--heldout-path", type=Path, default=None)
    parser.add_argument("--heldout-limit", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.data_path, args.out_dir, start=args.start, limit=args.limit, methods=args.methods, batch_size=args.batch_size, heldout_path=args.heldout_path, heldout_limit=args.heldout_limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
