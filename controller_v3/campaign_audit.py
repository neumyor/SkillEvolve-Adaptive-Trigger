"""Campaign-level integrity checks for paired Controller V3 runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_campaign(
    root: str | Path,
    *,
    methods: Iterable[str] = ("skillopt", "gepa", "evoskill", "trace2skill"),
    require_cost: bool = True,
) -> dict[str, Any]:
    """Check that a completed paired campaign is internally comparable.

    This is intentionally independent of quality values.  It verifies that
    both conditions contain the same task population and that every reported
    cost comparison has complete usage evidence.
    """
    root = Path(root)
    errors: list[str] = []
    warnings: list[str] = []
    method_report: dict[str, Any] = {}
    summary_path = root / "summary.json"
    summary: dict[str, Any] = {}
    if not summary_path.exists():
        errors.append("missing summary.json")
    else:
        try:
            summary = _load(summary_path)
        except (OSError, json.JSONDecodeError, TypeError):
            errors.append("summary.json is unreadable")

    for method in methods:
        conditions: dict[str, Any] = {}
        condition_ids: dict[str, set[str]] = {}
        manifests: dict[str, dict[str, Any]] = {}
        for condition in ("original", "controller"):
            path = root / method / condition
            missing = [name for name in ("manifest.json", "progress.jsonl", "result.json", "tokens.json", "audit.json") if not (path / name).exists()]
            if missing:
                errors.append(f"{method}/{condition}: missing {', '.join(missing)}")
                continue
            try:
                manifest = _load(path / "manifest.json")
                result = _load(path / "result.json")
                tokens = _load(path / "tokens.json")
                audit = _load(path / "audit.json")
                progress = [json.loads(line) for line in (path / "progress.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                errors.append(f"{method}/{condition}: unreadable artifact ({type(exc).__name__})")
                continue
            ids = [str(row.get("task_id", "")) for row in progress]
            condition_ids[condition] = set(ids)
            manifests[condition] = manifest
            heldout_ids: list[str] | None = None
            if len(ids) != len(set(ids)) or any(not task_id for task_id in ids):
                errors.append(f"{method}/{condition}: duplicate or empty task IDs")
            result_ids = {str(row.get("id", "")) for row in result.get("rows", [])}
            if result_ids != condition_ids[condition]:
                errors.append(f"{method}/{condition}: result rows do not match progress evidence")
            heldout_path = path / "heldout.json"
            if heldout_path.exists():
                try:
                    heldout = _load(heldout_path)
                    heldout_ids = [str(task_id) for task_id in heldout.get("task_ids", [])]
                    heldout_row_ids = [str(row.get("id", "")) for row in heldout.get("rows", [])]
                except (OSError, json.JSONDecodeError, TypeError) as exc:
                    errors.append(f"{method}/{condition}: unreadable held-out evidence ({type(exc).__name__})")
                else:
                    if not heldout_ids or len(heldout_ids) != len(set(heldout_ids)):
                        errors.append(f"{method}/{condition}: empty or duplicate held-out task IDs")
                    if heldout_row_ids != heldout_ids:
                        errors.append(f"{method}/{condition}: held-out result rows do not match held-out task IDs")
            manifest_ids = [str(item) for item in manifest.get("items", [])]
            if manifest_ids and ids != manifest_ids:
                errors.append(f"{method}/{condition}: progress order/population does not match manifest")
            if not audit.get("quality_usable", False):
                errors.append(f"{method}/{condition}: quality audit is unusable")
            if require_cost and not audit.get("cost_usable", False):
                errors.append(f"{method}/{condition}: cost audit is unusable")
            if tokens.get("summary", {}).get("untracked_calls", 0):
                message = f"{method}/{condition}: token ledger has untracked calls"
                if require_cost:
                    errors.append(message)
                else:
                    warnings.append(message)
            conditions[condition] = {
                "tasks": len(ids),
                "audit_status": audit.get("audit_status"),
                "quality_usable": bool(audit.get("quality_usable")),
                "cost_usable": bool(audit.get("cost_usable")),
                "total_tokens": tokens.get("summary", {}).get("total_tokens", 0),
            }
            if heldout_ids is not None:
                conditions[condition]["heldout_ids"] = heldout_ids
        if set(condition_ids) == {"original", "controller"}:
            if condition_ids["original"] != condition_ids["controller"]:
                errors.append(f"{method}: original/controller task populations differ")
            if manifests["original"].get("items_hash") != manifests["controller"].get("items_hash"):
                errors.append(f"{method}: original/controller items_hash differ")
            if manifests["original"].get("skill_hash") != manifests["controller"].get("skill_hash"):
                errors.append(f"{method}: original/controller skill_hash differ")
            for field in ("evaluation_harness", "llm_name", "max_tokens", "alfworld_thinking", "alfworld_env_batch_size"):
                if field not in manifests["original"] or field not in manifests["controller"]:
                    # Historical campaigns predate these manifest fields.  Do
                    # not discard their task- and usage-level evidence merely
                    # because provenance was added later; state the limit so
                    # it cannot be mistaken for a fully reproducible record.
                    warnings.append(f"{method}: missing runtime provenance field {field}")
                elif manifests["original"].get(field) != manifests["controller"].get(field):
                    errors.append(f"{method}: original/controller {field} differ")
            original_item_hashes = manifests["original"].get("item_hashes")
            controller_item_hashes = manifests["controller"].get("item_hashes")
            if isinstance(original_item_hashes, dict) and isinstance(controller_item_hashes, dict) and original_item_hashes != controller_item_hashes:
                errors.append(f"{method}: original/controller per-item hashes differ")
            paired = summary.get("paired", {}).get(method, {}).get("paired", [])
            paired_ids = {str(row.get("task_id", "")) for row in paired}
            if paired_ids != condition_ids["original"]:
                errors.append(f"{method}: summary paired IDs do not match evidence")
            original_heldout = conditions.get("original", {}).get("heldout_ids")
            controller_heldout = conditions.get("controller", {}).get("heldout_ids")
            if (original_heldout is None) != (controller_heldout is None):
                errors.append(f"{method}: held-out evidence exists for only one condition")
            elif original_heldout is not None and original_heldout != controller_heldout:
                errors.append(f"{method}: original/controller held-out task populations differ")
        method_report[method] = conditions

    return {
        "campaign": str(root),
        "status": "error" if errors else ("warning" if warnings else "ok"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "methods": method_report,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--allow-untracked-cost", action="store_true")
    args = parser.parse_args()
    report = audit_campaign(args.root, require_cost=not args.allow_untracked_cost)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)
