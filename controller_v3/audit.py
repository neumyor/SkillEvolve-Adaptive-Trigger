"""Non-blocking audit for paired experiment artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def audit_run(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    warnings: list[str] = []
    errors: list[str] = []
    progress = root / "progress.jsonl"
    rows: list[dict[str, Any]] = []
    if not progress.exists():
        errors.append("missing progress.jsonl")
    else:
        for line_no, line in enumerate(progress.read_text(encoding="utf-8").splitlines(), 1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                errors.append(f"invalid progress JSON at line {line_no}")
    task_ids = [str(r.get("task_id", "")) for r in rows]
    if not task_ids:
        errors.append("no task records")
    if len(task_ids) != len(set(task_ids)):
        warnings.append("duplicate task ids")
    if any(not task_id for task_id in task_ids):
        warnings.append("some task ids are empty")
    manifest_path = root / "manifest.json"
    expected_ids: list[str] | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_items = manifest.get("items")
            if isinstance(raw_items, list):
                expected_ids = [str(item) for item in raw_items]
                if task_ids != expected_ids:
                    errors.append("progress task IDs do not match manifest items")
        except (OSError, json.JSONDecodeError, TypeError):
            warnings.append("manifest is unreadable")
    from .validity import invalid_row
    evidence_rows = [entry.get("row", {}) for entry in rows]
    for filename, field in (("heldout.json", "rows"), ("result.json", "heldout_rows")):
        if (root / filename).exists():
            try:
                evidence_rows.extend(json.loads((root / filename).read_text()).get(field, []))
            except (ValueError, OSError):
                errors.append(f"unreadable {filename}")
    failures = {str(row.get("id", "")) for row in evidence_rows if invalid_row(row)}
    if failures:
        errors.append(f"execution failures in {len(failures)} task(s); not valid task scores")
    if (root / "execution_failure.json").exists():
        errors.append("unresolved execution failure checkpoint")
    ledger = root / "tokens.json"
    cost_usable = ledger.exists()
    if not cost_usable:
        warnings.append("token ledger is missing")
    else:
        try:
            token_payload = json.loads(ledger.read_text(encoding="utf-8"))
            token_summary = token_payload.get("summary", {})
            if token_summary.get("untracked_calls", 0) or token_summary.get("cost_usable") is False:
                cost_usable = False
                warnings.append("some native calls have untracked token usage")
            if not token_payload.get("records"):
                cost_usable = False
                warnings.append("token ledger has no API records")
            records = token_payload.get("records", [])
            if isinstance(records, list):
                record_total = sum(int(record.get("total_tokens", 0) or 0) for record in records if isinstance(record, dict))
                record_calls = sum(int(record.get("api_call", 1) or 1) for record in records if isinstance(record, dict))
                if record_total != int(token_summary.get("total_tokens", 0) or 0):
                    cost_usable = False
                    warnings.append("token ledger total does not match records")
                if record_calls != int(token_summary.get("api_calls", 0) or 0):
                    cost_usable = False
                    warnings.append("token ledger call count does not match records")
        except (OSError, json.JSONDecodeError, TypeError):
            cost_usable = False
            warnings.append("token ledger is unreadable")
    status = "error" if errors else ("warning" if warnings else "ok")
    return {
        "audit_status": status,
        "quality_usable": bool(rows) and not errors,
        "cost_usable": cost_usable and not errors,
        "warnings": warnings,
        "errors": errors,
        "tasks": len(rows),
    }
