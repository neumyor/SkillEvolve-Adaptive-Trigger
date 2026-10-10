#!/usr/bin/env python3
"""Generate Terminal-Bench task skills concurrently without running evaluations."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import generate_tencent_skill_pack as author


def discover_tasks(dataset_path: Path) -> list[str]:
    return sorted(
        instruction.parent.name
        for instruction in dataset_path.glob("*/instruction.md")
        if instruction.parent.is_dir()
    )


def skill_name_for_task(task_name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", task_name).strip("-")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def attempt_record(attempt_root: Path, task_name: str, attempt: int) -> dict[str, Any]:
    generation_dir = attempt_root / "generation"
    manifest_path = generation_dir / "generation.json"
    if not manifest_path.is_file():
        manifest_path = generation_dir / "generation_error.json"
    record: dict[str, Any] = {
        "attempt": attempt,
        "artifact_root": str(attempt_root),
        "manifest_path": str(manifest_path) if manifest_path.is_file() else None,
    }
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record.update(
            {
                "status": manifest.get("status", "success"),
                "sandbox_id": manifest.get("sandbox_id"),
                "sandbox_state": manifest.get("sandbox_state"),
                "error": manifest.get("error"),
            }
        )
    else:
        record.update({"status": "failed", "error": "missing generation manifest"})
    return record


def build_author_command(
    args: argparse.Namespace, task_name: str, skill_name: str, output_root: Path
) -> list[str]:
    return [
        sys.executable,
        str(Path(author.__file__).resolve()),
        "--instruction-file",
        str(args.dataset_path / task_name / "instruction.md"),
        "--skill-creator-dir",
        str(args.skill_creator_dir),
        "--output-root",
        str(output_root),
        "--skill-name",
        skill_name,
        "--model",
        args.model,
        "--api-base",
        args.api_base,
        "--timeout-sec",
        str(args.timeout_sec),
        "--sandbox-create-timeout",
        str(args.sandbox_create_timeout),
        "--sandbox-retention",
        "none",
        "--proxy-port",
        str(args.proxy_port),
    ]


async def generate_one(
    args: argparse.Namespace,
    run_root: Path,
    task_name: str,
    progress_path: Path,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    task_root = run_root / "tasks" / task_name
    skill_name = skill_name_for_task(task_name)
    attempts: list[dict[str, Any]] = []
    async with semaphore:
        for attempt in range(1, args.max_attempts + 1):
            attempt_root = task_root / f"attempt-{attempt:02d}"
            try:
                attempt_root.mkdir(parents=True)
                process = await asyncio.create_subprocess_exec(
                    *build_author_command(args, task_name, skill_name, attempt_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=args.timeout_sec + args.sandbox_create_timeout + 300,
                    )
                except TimeoutError:
                    process.kill()
                    stdout, stderr = await process.communicate()
                    raise RuntimeError("author process timed out")
                (attempt_root / "author.stdout.log").write_bytes(stdout)
                (attempt_root / "author.stderr.log").write_bytes(stderr)
                if process.returncode != 0:
                    raise RuntimeError(f"author process exited with {process.returncode}")
                package = attempt_root / "skills" / skill_name
                if not package.is_dir():
                    raise RuntimeError("author completed without a generated skill package")
                destination = run_root / "skills" / skill_name
                await asyncio.to_thread(shutil.copytree, package, destination)
                record = attempt_record(attempt_root, task_name, attempt)
                record["status"] = "success"
                attempts.append(record)
                outcome = {"task": task_name, "skill_name": skill_name, "status": "success", "attempts": attempts, "skill_dir": str(destination)}
                append_jsonl(progress_path, outcome)
                return outcome
            except Exception as exc:
                record = attempt_record(attempt_root, task_name, attempt)
                record["status"] = "failed"
                record["error"] = record.get("error") or str(exc)
                attempts.append(record)
                append_jsonl(progress_path, {"task": task_name, "status": "retrying" if attempt < args.max_attempts else "failed", "attempt": record})

    outcome = {"task": task_name, "skill_name": skill_name, "status": "failed", "attempts": attempts, "skill_dir": None}
    append_jsonl(progress_path, outcome)
    return outcome


async def async_main(args: argparse.Namespace) -> int:
    tasks = discover_tasks(args.dataset_path)
    if len(tasks) != args.expected_task_count:
        raise SystemExit(f"expected {args.expected_task_count} tasks, discovered {len(tasks)}")
    if args.dry_run:
        print(json.dumps({
            "mode": "e2b_openclaw_skill_authoring_batch",
            "task_count": len(tasks),
            "n_concurrent": args.n_concurrent,
            "max_attempts": args.max_attempts,
            "sandbox_retention": "none",
            "uses_harbor": False,
            "runs_verifier": False,
            "task_filter": None,
        }, ensure_ascii=False))
        return 0

    if not args.skill_creator_dir.joinpath("SKILL.md").is_file():
        raise SystemExit(f"official Anthropic skill-creator is missing: {args.skill_creator_dir}")
    if not args.dataset_path.is_dir():
        raise SystemExit(f"dataset path is missing: {args.dataset_path}")
    if args.run_root.exists():
        raise SystemExit(f"run root already exists: {args.run_root}")

    args.run_root.mkdir(parents=True)
    progress_path = args.run_root / "progress.jsonl"
    run_manifest = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "e2b_openclaw_skill_authoring_batch",
        "task_count": len(tasks),
        "n_concurrent": args.n_concurrent,
        "max_attempts": args.max_attempts,
        "sandbox_retention": "none",
        "model": args.model,
        "api_base": args.api_base,
        "uses_harbor": False,
        "runs_verifier": False,
        "tasks": tasks,
    }
    write_json(args.run_root / "run.json", run_manifest)
    semaphore = asyncio.Semaphore(args.n_concurrent)
    outcomes = await asyncio.gather(
        *(generate_one(args, args.run_root, task, progress_path, semaphore) for task in tasks)
    )
    summary = {
        **run_manifest,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "success_count": sum(outcome["status"] == "success" for outcome in outcomes),
        "failure_count": sum(outcome["status"] != "success" for outcome in outcomes),
        "outcomes": outcomes,
    }
    write_json(args.run_root / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in ("success_count", "failure_count")}, ensure_ascii=False))
    return 0 if summary["failure_count"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-path", required=True, type=Path)
    parser.add_argument("--skill-creator-dir", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--model", default=author.DEFAULT_MODEL)
    parser.add_argument("--api-base", default=author.DEFAULT_API_BASE)
    parser.add_argument("--n-concurrent", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--expected-task-count", type=int, default=89)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--sandbox-create-timeout", type=int, default=180)
    parser.add_argument("--proxy-port", type=int, default=18080)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.n_concurrent != 100:
        raise SystemExit("full skill generation requires --n-concurrent=100")
    if args.max_attempts != 2:
        raise SystemExit("full skill generation requires --max-attempts=2")
    if args.sandbox_create_timeout < 30:
        raise SystemExit("sandbox create timeout must be at least 30 seconds")
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
