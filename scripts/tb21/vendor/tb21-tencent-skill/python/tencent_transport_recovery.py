"""Plan, map, and report targeted retries for Tencent E2B transport failures."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


TRANSPORT_EXCEPTION_TYPES = frozenset(
    {"WriteError", "LocalProtocolError", "ProtocolError", "RemoteProtocolError"}
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reward(result: dict[str, Any]) -> float | int | None:
    verifier = result.get("verifier_result")
    if not isinstance(verifier, dict):
        return None
    rewards = verifier.get("rewards")
    if not isinstance(rewards, dict):
        return None
    value = rewards.get("reward")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _exception_type(result: dict[str, Any]) -> str | None:
    exception = result.get("exception_info")
    if not isinstance(exception, dict):
        return None
    value = exception.get("exception_type")
    return value if isinstance(value, str) else None


def build_transport_recovery_plan(source_job: Path) -> dict[str, Any]:
    """Select only final no-reward E2B transport failures, grouped per task."""
    source_job = source_job.resolve()
    candidates: list[dict[str, str]] = []
    valid_rewards = 0
    excluded: defaultdict[str, int] = defaultdict(int)
    for result_path in sorted(source_job.glob("*/result.json")):
        result = _read_json(result_path)
        task_name = result.get("task_name")
        if not isinstance(task_name, str):
            excluded["missing_task_name"] += 1
            continue
        if _reward(result) is not None:
            valid_rewards += 1
            continue
        exception_type = _exception_type(result)
        if exception_type not in TRANSPORT_EXCEPTION_TYPES:
            excluded[exception_type or "missing_reward_without_exception"] += 1
            continue
        candidates.append(
            {
                "task_name": task_name,
                "original_trial_dir": str(result_path.parent),
                "exception_type": exception_type,
            }
        )

    by_task: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for candidate in candidates:
        by_task[candidate["task_name"]].append(candidate)
    grouped: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for task_name, failures in by_task.items():
        failures.sort(key=lambda item: item["original_trial_dir"])
        grouped[len(failures)].append(
            {
                "task_name": task_name,
                "failures": failures,
                "replacement_trial_dirs": [],
            }
        )

    groups = []
    for failed_attempt_count in sorted(grouped):
        tasks = sorted(grouped[failed_attempt_count], key=lambda item: item["task_name"])
        groups.append(
            {
                "failed_attempt_count": failed_attempt_count,
                "task_names": [item["task_name"] for item in tasks],
                "tasks": tasks,
                "replacement_job": None,
            }
        )
    return {
        "version": 1,
        "source_job": str(source_job),
        "source_result_count": valid_rewards + len(candidates) + sum(excluded.values()),
        "source_valid_reward_count": valid_rewards,
        "eligible_transport_failure_count": len(candidates),
        "excluded_missing_reward_counts": dict(sorted(excluded.items())),
        "canary_task_names": sorted(by_task)[:20],
        "groups": groups,
    }


def write_plan_artifacts(plan: dict[str, Any], manifest: Path) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (manifest.parent / "recovery_batches.tsv").write_text(
        "".join(
            f"{index}\t{group['failed_attempt_count']}\t{' '.join(group['task_names'])}\n"
            for index, group in enumerate(plan["groups"])
        ),
        encoding="utf-8",
    )
    (manifest.parent / "canary_tasks.txt").write_text(
        "\n".join(plan["canary_task_names"]) + ("\n" if plan["canary_task_names"] else ""),
        encoding="utf-8",
    )


def record_replacements(manifest: Path, group_index: int, replacement_job: Path) -> dict[str, Any]:
    plan = _read_json(manifest)
    group = plan["groups"][group_index]
    replacement_by_task: defaultdict[str, list[Path]] = defaultdict(list)
    for result_path in sorted(replacement_job.glob("*/result.json")):
        result = _read_json(result_path)
        task_name = result.get("task_name")
        if isinstance(task_name, str):
            replacement_by_task[task_name].append(result_path.parent)
    for task in group["tasks"]:
        paths = sorted(replacement_by_task[task["task_name"]])
        expected = len(task["failures"])
        if len(paths) != expected:
            raise ValueError(
                f"replacement count for {task['task_name']} is {len(paths)}, expected {expected}"
            )
        task["replacement_trial_dirs"] = [str(path) for path in paths]
    group["replacement_job"] = str(replacement_job.resolve())
    manifest.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan


def validate_canary(job_dir: Path, expected_tasks: list[str]) -> list[str]:
    errors: list[str] = []
    results: defaultdict[str, list[Path]] = defaultdict(list)
    for result_path in sorted(job_dir.glob("*/result.json")):
        result = _read_json(result_path)
        task_name = result.get("task_name")
        if isinstance(task_name, str):
            results[task_name].append(result_path)
    for task_name in expected_tasks:
        task_results = results.get(task_name, [])
        if len(task_results) != 1:
            errors.append(f"{task_name}: expected one result, found {len(task_results)}")
            continue
        result_path = task_results[0]
        result = _read_json(result_path)
        if _reward(result) is None:
            errors.append(f"{task_name}: missing verifier reward ({_exception_type(result) or 'unknown'})")
        if _exception_type(result) in TRANSPORT_EXCEPTION_TYPES:
            errors.append(f"{task_name}: unhandled transport exception {_exception_type(result)}")
        trial_dir = result_path.parent
        for relative in (
            "agent/trajectory.json",
            "agent/raw_model_requests.jsonl",
            "agent/raw_model_responses.jsonl",
            "snapshot.json",
        ):
            if not (trial_dir / relative).is_file():
                errors.append(f"{task_name}: missing {relative}")
    return errors


def build_merged_report(manifest: Path) -> dict[str, Any]:
    plan = _read_json(manifest)
    attempts: list[dict[str, Any]] = []
    for result_path in sorted(Path(plan["source_job"]).glob("*/result.json")):
        result = _read_json(result_path)
        reward = _reward(result)
        if reward is not None:
            attempts.append(
                {
                    "task_name": result.get("task_name"),
                    "trial_dir": str(result_path.parent),
                    "reward": reward,
                    "source": "original",
                }
            )
    for group in plan["groups"]:
        for task in group["tasks"]:
            for failure, trial_dir in zip(
                task["failures"], task["replacement_trial_dirs"], strict=True
            ):
                result_path = Path(trial_dir) / "result.json"
                result = _read_json(result_path) if result_path.is_file() else {}
                attempts.append(
                    {
                        "task_name": task["task_name"],
                        "trial_dir": trial_dir,
                        "reward": _reward(result),
                        "source": "transport_recovery",
                        "original_trial_dir": failure["original_trial_dir"],
                    }
                )
    rewards = [attempt["reward"] for attempt in attempts if attempt["reward"] is not None]
    return {
        "source_job": plan["source_job"],
        "manifest": str(manifest.resolve()),
        "attempts": attempts,
        "rewarded_attempts": len(rewards),
        "reward_1_count": sum(reward == 1 for reward in rewards),
        "reward_0_count": sum(reward == 0 for reward in rewards),
        "missing_reward_count": sum(attempt["reward"] is None for attempt in attempts),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--source-job", required=True, type=Path)
    plan_parser.add_argument("--manifest", required=True, type=Path)
    record_parser = subparsers.add_parser("record-replacements")
    record_parser.add_argument("--manifest", required=True, type=Path)
    record_parser.add_argument("--group-index", required=True, type=int)
    record_parser.add_argument("--replacement-job", required=True, type=Path)
    canary_parser = subparsers.add_parser("validate-canary")
    canary_parser.add_argument("--job", required=True, type=Path)
    canary_parser.add_argument("--task-file", required=True, type=Path)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--manifest", required=True, type=Path)
    report_parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "plan":
        plan = build_transport_recovery_plan(args.source_job)
        write_plan_artifacts(plan, args.manifest)
        print(json.dumps({key: plan[key] for key in ("source_result_count", "eligible_transport_failure_count", "canary_task_names")}, sort_keys=True))
        return
    if args.command == "record-replacements":
        record_replacements(args.manifest, args.group_index, args.replacement_job)
        return
    if args.command == "validate-canary":
        expected_tasks = [line.strip() for line in args.task_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        errors = validate_canary(args.job, expected_tasks)
        if errors:
            raise SystemExit("canary failed:\n" + "\n".join(errors))
        print(f"canary passed for {len(expected_tasks)} tasks")
        return
    report = build_merged_report(args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("rewarded_attempts", "reward_1_count", "reward_0_count", "missing_reward_count")}, sort_keys=True))


if __name__ == "__main__":
    main()
