"""Supervisor for the full paired SearchQA and/or ALFWorld campaign.

The supervisor launches independent condition processes: four methods x two
conditions for each selected domain. Each condition has its own checkpoint and
token ledger, while the process-local API worker pool is capped explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .campaign_analysis import analyze_campaign
from .campaign_audit import audit_campaign
from .paired_experiment import _paired_summary
from .config import runtime_paths


ROOT = Path(__file__).parents[1]
METHODS = ("skillopt", "gepa", "evoskill", "trace2skill")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _dataset_spec(domain: str, alfworld_split_root: Path | None = None) -> dict:
    paths = runtime_paths()
    if domain == "searchqa":
        base = paths.searchqa_eval_root / "data/searchqa_split"
    else:
        base = alfworld_split_root or paths.skillopt_root / "data/alfworld_path_split"
    paths = {split: base / f"{split}/items.json" for split in ("train", "val", "test")}
    return {"paths": paths, "counts": {split: len(json.loads(path.read_text())) for split, path in paths.items()}}


def _command(domain: str, method: str, condition: str, out: Path, spec: dict, args) -> list[str]:
    return [
        args.python,
        "-m",
        "controller_v3.condition_runner",
        "--method",
        method,
        "--condition",
        condition,
        "--domain",
        domain,
        "--train-path",
        str(spec["paths"]["train"]),
        "--heldout-paths",
        str(spec["paths"]["val"]),
        str(spec["paths"]["test"]),
        "--out",
        str(out),
        "--batch-size",
        str(args.batch_size),
        "--api-workers",
        str(args.api_workers),
        "--max-tokens",
        str(args.max_tokens),
        "--max-steps",
        str(args.max_steps),
        "--api-timeout",
        str(args.api_timeout),
        "--alfworld-env-batch-size",
        str(args.alfworld_env_batch_size),
        "--llm-name",
        args.llm_name[domain],
        "--enable-thinking",
        "true" if args.enable_thinking else "false",
    ]


def _merge_domain(root: Path, domain: str, *, quality_field: str, methods=METHODS) -> dict:
    domain_root = root / domain
    conditions = {}
    for method in methods:
        for condition in ("original", "controller"):
            payload = json.loads((domain_root / method / condition / "condition_result.json").read_text())
            conditions[f"{method}/{condition}"] = payload
    summary = {
        "conditions": conditions,
        "paired": _paired_summary(conditions),
    }
    _write(domain_root / "summary.json", summary)
    audit = audit_campaign(domain_root, methods=methods)
    _write(domain_root / "campaign_audit.json", audit)
    analysis = analyze_campaign(domain_root, methods=methods, quality_field=quality_field, threshold=0.0)
    _write(domain_root / ("analysis_f1_full.json" if domain == "searchqa" else "analysis_hard_full.json"), analysis)
    return {"audit": audit, "analysis": analysis}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=Path("tmp/controller_v3_full_campaign"))
    parser.add_argument(
        "--domains",
        nargs="+",
        choices=("searchqa", "alfworld"),
        default=["searchqa", "alfworld"],
        help="Domains to run. Select only alfworld for the ALFWorld campaign.",
    )
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--alfworld-split-root", type=Path)
    parser.add_argument("--api-workers", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--alfworld-env-batch-size", type=int, default=1)
    parser.add_argument("--api-timeout", type=float, default=120.0)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--llm-name-searchqa", default="searchqa-eval")
    parser.add_argument("--llm-name-alfworld", default="alfworld-eval")
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument(
        "--max-active-settings",
        type=int,
        default=2,
        help="Maximum number of condition processes active at once.",
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable for condition workers")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-report", type=Path, help="Matching controller_v3.preflight report required for a full run")
    args = parser.parse_args()
    args.api_workers = max(1, min(128, args.api_workers))
    args.batch_size = max(1, args.batch_size)
    args.max_active_settings = max(1, args.max_active_settings)
    # Preserve caller order while avoiding duplicate condition trees and
    # making the manifest deterministic for resume/audit.
    args.domains = list(dict.fromkeys(args.domains))
    args.methods = list(dict.fromkeys(args.methods))
    args.llm_name = {"searchqa": args.llm_name_searchqa, "alfworld": args.llm_name_alfworld}

    out_root = args.out_root
    out_root.mkdir(parents=True, exist_ok=True)
    specs = {domain: _dataset_spec(domain, args.alfworld_split_root) for domain in args.domains}
    total_settings = len(args.domains) * len(args.methods) * 2
    manifest = {
        "runner": "controller_v3.full_campaign",
        "runner_version": "full-v2",
        "domains": args.domains,
        "methods": args.methods,
        "conditions_per_domain": len(args.methods) * 2,
        "total_settings": total_settings,
        "api_workers_per_setting": args.api_workers,
        "maximum_total_api_workers": min(total_settings, args.max_active_settings) * args.api_workers,
        "max_active_settings": args.max_active_settings,
        "batch_size": args.batch_size,
        "max_tokens": args.max_tokens,
        "max_steps": args.max_steps,
        "api_timeout": args.api_timeout,
        "alfworld_env_batch_size": max(1, args.alfworld_env_batch_size),
        "enable_thinking": args.enable_thinking,
        "metric_registration": {"searchqa": "f1", "alfworld": "hard"},
        "split_protocol": "train=adaptive evolution; val+test=evaluation-only",
        "datasets": {
            domain: {
                "counts": specs[domain]["counts"],
                "hashes": {split: _hash_file(path) for split, path in specs[domain]["paths"].items()},
            }
            for domain in specs
        },
    }
    _write(out_root / "campaign_manifest.json", manifest)
    if args.dry_run:
        for domain in specs:
            for method in args.methods:
                for condition in ("original", "controller"):
                    print(" ".join(map(str, _command(domain, method, condition, out_root / domain / method / condition, specs[domain], args))))
        return 0

    if not args.preflight_report:
        parser.error("Full runs require --preflight-report; run controller_v3.preflight first")
    from .preflight import validate_report
    validate_report(args.preflight_report, args.domains, args.max_tokens, llm_names=args.llm_name, enable_thinking=args.enable_thinking, max_steps=args.max_steps)

    import fcntl
    campaign_lock = (out_root / "campaign.lock").open("a+")
    fcntl.flock(campaign_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    pending = [
        (domain, method, condition)
        for domain in args.domains
        for method in args.methods
        for condition in ("original", "controller")
    ]
    children = []
    status = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "settings": {}}
    def launch_one(domain: str, method: str, condition: str) -> None:
        out = out_root / domain / method / condition
        out.mkdir(parents=True, exist_ok=True)
        log = out / "driver.log"
        handle = log.open("a", encoding="utf-8")
        command = _command(domain, method, condition, out, specs[domain], args)
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            start_new_session=True,
        )
        key = f"{domain}/{method}/{condition}"
        children.append((key, proc, handle))
        status["settings"][key] = {"pid": proc.pid, "status": "running", "out": str(out)}

    while pending or children:
        while pending and len(children) < args.max_active_settings:
            launch_one(*pending.pop(0))
        _write(out_root / "status.json", status)
        if not children:
            continue
        remaining = []
        for key, proc, handle in children:
            code = proc.poll()
            if code is None:
                remaining.append((key, proc, handle))
                continue
            handle.close()
            if code != 0:
                for domain, method, condition in pending:
                    status["settings"][f"{domain}/{method}/{condition}"] = {"status": "not_started_after_failure"}
                pending.clear()
            status["settings"][key].update({"status": "ok" if code == 0 else "failed", "exit_code": code})
        children = remaining
        if children:
            time.sleep(max(1.0, args.poll_seconds))
    status["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write(out_root / "status.json", status)
    failed = [key for key, value in status["settings"].items() if value["status"] != "ok"]
    if failed:
        print(json.dumps({"status": "failed", "settings": failed}, ensure_ascii=False), flush=True)
        return 1
    reports = {
        domain: _merge_domain(out_root, domain, quality_field="f1" if domain == "searchqa" else "hard", methods=args.methods)
        for domain in args.domains
    }
    _write(out_root / "final_report.json", reports)
    print(json.dumps({"status": "ok", "out_root": str(out_root), "audits": {domain: report["audit"]["status"] for domain, report in reports.items()}}, ensure_ascii=False), flush=True)
    return 0 if all(report["audit"]["ok"] for report in reports.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
