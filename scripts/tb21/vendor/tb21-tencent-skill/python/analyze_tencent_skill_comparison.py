"""Build the reproducible Tencent TB2.1 bare-vs-skill analysis artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import textwrap
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


TRANSPORT_EXCEPTIONS = {
    "WriteError",
    "LocalProtocolError",
    "ProtocolError",
    "RemoteProtocolError",
}
IMPROVEMENT_CASES = [
    "extract-elf",
    "polyglot-c-py",
    "db-wal-recovery",
    "reshard-c4-data",
    "break-filter-js-from-html",
]
DEFAULT_BARE_JOB = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_smoke/"
    "tb21_tencent_full3_qwen_co_c25_20260812_222647"
)
DEFAULT_SKILL_JOB = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_skill_eval/"
    "tb21_tencent_full_20260817_165607"
)
DEFAULT_RECOVERY_ROOT = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_transport_recovery/"
    "tb21_tencent_full_20260817_165607"
)
DEFAULT_BARE_RETRIES = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_retry_archives/"
    "tb21_tencent_full3_qwen_co_c25_20260812_222647"
)
DEFAULT_BARE_ADJUDICATION = Path(
    "/data2/liyishan/tbench2-openclaw-min/exports/"
    "tb21_tencent_full3_qwen_co_c25_20260812_222647_formal3/"
    "reward_adjudication_missing_as_zero.json"
)
DEFAULT_BARE_RECHECK_ROOT = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_recheck"
)
DEFAULT_BARE_RECHECK_RETRIES = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_retry_archives"
)
DEFAULT_SKILL_RETRIES = Path(
    "/data2/liyishan/tbench2-openclaw-min/jobs/tb21_tencent_skill_retry_archives/"
    "tb21_tencent_full_20260817_165607"
)
DEFAULT_OUTPUT = Path(
    "/data2/liyishan/tbench2-openclaw-min/artifacts/"
    "tb21_tencent_skill_comparison_20260818"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reward_from_result(result: dict[str, Any]) -> float | None:
    try:
        value = result["verifier_result"]["rewards"]["reward"]
    except (KeyError, TypeError):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def exception_info(result: dict[str, Any]) -> tuple[str, str]:
    value = result.get("exception_info") or {}
    return str(value.get("exception_type") or ""), str(value.get("exception_message") or "")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_seconds(result: dict[str, Any]) -> float | None:
    started = parse_time(result.get("started_at"))
    finished = parse_time(result.get("finished_at"))
    if started is None or finished is None:
        return None
    return max(0.0, (finished - started).total_seconds())


def compact(value: str, limit: int = 360) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def verifier_excerpt(trial_dir: Path, limit: int = 1400) -> str:
    path = trial_dir / "verifier" / "test-stdout.txt"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return compact("\n".join(lines[-20:]), limit)


def snapshot_status(trial_dir: Path) -> str:
    path = trial_dir / "snapshot.json"
    if not path.is_file():
        return ""
    try:
        return str(read_json(path).get("status") or "")
    except (OSError, ValueError):
        return "invalid"


def trajectory_evidence(trial_dir: Path, task_name: str) -> dict[str, Any]:
    path = trial_dir / "agent" / "trajectory.json"
    evidence: dict[str, Any] = {
        "has_trajectory": path.is_file(),
        "trajectory_path": str(path) if path.is_file() else "",
        "trajectory_steps": 0,
        "skill_read": False,
        "skill_read_command": "",
        "initial_reasoning": "",
        "final_message": "",
        "commands": [],
    }
    if not path.is_file():
        return evidence
    try:
        trajectory = read_json(path)
    except (OSError, ValueError):
        return evidence
    steps = trajectory.get("steps") or []
    evidence["trajectory_steps"] = len(steps)
    skill_path = f"/opt/openclaw-skills/{task_name}/SKILL.md"
    messages: list[str] = []
    reasoning: list[str] = []
    commands: list[str] = []
    for step in steps:
        if step.get("source") != "agent":
            continue
        if step.get("message"):
            messages.append(str(step["message"]))
        if step.get("reasoning_content"):
            reasoning.append(str(step["reasoning_content"]))
        for call in step.get("tool_calls") or []:
            arguments = call.get("arguments") or {}
            command = arguments.get("keystrokes")
            if isinstance(command, str) and command.strip():
                command = command.strip()
                commands.append(command)
                if skill_path in command and not evidence["skill_read"]:
                    evidence["skill_read"] = True
                    evidence["skill_read_command"] = compact(command, 240)
    evidence["commands"] = [compact(command, 240) for command in commands[:12]]
    evidence["initial_reasoning"] = compact(reasoning[0] if reasoning else "", 900)
    evidence["final_message"] = compact(messages[-1] if messages else "", 900)
    return evidence


def classify_exception(exception_type: str, message: str) -> str:
    text = f"{exception_type}\n{message}".lower()
    if "http 401" in text or "unauthorized" in text or "authentication" in text:
        return "Authentication"
    if exception_type in TRANSPORT_EXCEPTIONS or "connectionstate.closed" in text:
        return "E2B transport"
    if "agenttimeout" in text or "agent execution timed out" in text:
        return "Agent timeout"
    if "verifiertimeout" in text or "verifier execution timed out" in text:
        return "Verifier timeout"
    if "paused sandbox instance quota" in text or "pausedinstance" in text:
        return "Snapshot quota"
    if "model request failed after retries" in text:
        return "Model retries exhausted"
    if "not enough disk space" in text or "notenoughspace" in text:
        return "Disk space"
    if "tmux" in text or "send-keys" in text:
        return "Tmux/session"
    return "Other" if exception_type or message else "None"


def build_attempt(
    run: str,
    task_name: str,
    trial_dir: Path,
    source: str,
    original_trial_dir: Path | None = None,
    reward_override: float | None = None,
    override_reward: bool = False,
) -> dict[str, Any]:
    result_path = trial_dir / "result.json"
    result = read_json(result_path) if result_path.is_file() else {}
    raw_reward = reward_from_result(result)
    reward = reward_override if override_reward else raw_reward
    exc_type, exc_message = exception_info(result)
    agent_result = result.get("agent_result") or {}
    metadata = agent_result.get("metadata") or {}
    evidence = trajectory_evidence(trial_dir, task_name)
    verifier_path = trial_dir / "verifier" / "test-stdout.txt"
    return {
        "run": run,
        "task_name": task_name,
        "attempt_index": 0,
        "trial_name": trial_dir.name,
        "trial_dir": str(trial_dir),
        "original_trial_dir": str(original_trial_dir or trial_dir),
        "result_path": str(result_path) if result_path.is_file() else "",
        "verifier_path": str(verifier_path) if verifier_path.is_file() else "",
        "source": source,
        "raw_reward": raw_reward,
        "reward_resolution": source,
        "reward": reward,
        "conservative_reward": 1 if reward == 1 else 0,
        "status": "reward_1" if reward == 1 else "reward_0" if reward == 0 else "missing_reward",
        "exception_type": exc_type,
        "exception_message": compact(exc_message, 500),
        "exception_category": classify_exception(exc_type, exc_message),
        "exception_blocks_reward": bool((exc_type or exc_message) and reward is None),
        "started_at": result.get("started_at") or "",
        "finished_at": result.get("finished_at") or "",
        "duration_sec": duration_seconds(result),
        "input_tokens": agent_result.get("n_input_tokens"),
        "output_tokens": agent_result.get("n_output_tokens"),
        "cache_tokens": agent_result.get("n_cache_tokens"),
        "episodes": metadata.get("n_episodes"),
        "snapshot_status": snapshot_status(trial_dir),
        "verifier_excerpt": verifier_excerpt(trial_dir),
        **evidence,
    }


def assign_attempt_indices(attempts: list[dict[str, Any]]) -> None:
    by_run_task: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        by_run_task[(attempt["run"], attempt["task_name"])].append(attempt)
    for rows in by_run_task.values():
        rows.sort(key=lambda row: (row["original_trial_dir"], row["trial_dir"]))
        for index, row in enumerate(rows, 1):
            row["attempt_index"] = index


def load_bare_attempts(
    job_dir: Path, adjudication_path: Path, recheck_root: Path
) -> list[dict[str, Any]]:
    adjudication = read_json(adjudication_path)
    attempts: list[dict[str, Any]] = []
    for item in adjudication["trials"]:
        task_name = str(item["task"])
        original_trial = job_dir / str(item["trial_id"])
        source = str(item["source"])
        expected_reward = float(item["reward"])
        if source == "original":
            trial_dir = original_trial
            source_label = "bare_original"
            override_reward = False
        elif source == "recheck":
            trial_dir = (
                recheck_root
                / str(item["source_run_id"])
                / str(item["source_trial_id"])
            )
            source_label = "bare_recheck"
            override_reward = False
        elif source == "imputed_zero":
            trial_dir = original_trial
            source_label = "bare_adjudicated_zero"
            override_reward = True
        else:
            raise ValueError(f"unsupported bare adjudication source: {source}")

        attempt = build_attempt(
            "bare",
            task_name,
            trial_dir,
            source_label,
            original_trial,
            expected_reward,
            override_reward,
        )
        if attempt["reward"] != expected_reward:
            raise ValueError(
                f"bare adjudication mismatch for {original_trial.name}: "
                f"expected {expected_reward}, found {attempt['reward']} in {trial_dir}"
            )
        attempts.append(attempt)
    assign_attempt_indices(attempts)
    return attempts


def load_skill_attempts(skill_job: Path, recovery_root: Path) -> list[dict[str, Any]]:
    merged = read_json(recovery_root / "merged_report.json")
    manifest = read_json(recovery_root / "transport_recovery_manifest.json")
    attempts: list[dict[str, Any]] = []
    represented_originals: set[str] = set()
    for item in merged["attempts"]:
        trial_dir = Path(item["trial_dir"])
        original = Path(item.get("original_trial_dir") or item["trial_dir"])
        represented_originals.add(str(original))
        attempts.append(
            build_attempt(
                "skill",
                str(item["task_name"]),
                trial_dir,
                str(item.get("source") or "skill_final"),
                original,
            )
        )

    eligible_originals = {
        failure["original_trial_dir"]
        for group in manifest["groups"]
        for task in group["tasks"]
        for failure in task["failures"]
    }
    for result_path in sorted(skill_job.glob("*/result.json")):
        if str(result_path.parent) in represented_originals or str(result_path.parent) in eligible_originals:
            continue
        result = read_json(result_path)
        if reward_from_result(result) is not None:
            raise ValueError(f"unrepresented valid skill result: {result_path}")
        attempts.append(
            build_attempt(
                "skill",
                str(result["task_name"]),
                result_path.parent,
                "excluded_original",
            )
        )
    assign_attempt_indices(attempts)
    return attempts


def percentile(values: Iterable[float], fraction: float) -> float | None:
    data = sorted(float(value) for value in values if value is not None)
    if not data:
        return None
    position = (len(data) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    return data[lower] * (upper - position) + data[upper] * (position - lower)


def distribution_stats(values: Iterable[Any]) -> dict[str, Any]:
    data = [float(value) for value in values if isinstance(value, (int, float))]
    return {
        "count": len(data),
        "median": percentile(data, 0.5),
        "p25": percentile(data, 0.25),
        "p75": percentile(data, 0.75),
        "p95": percentile(data, 0.95),
    }


def bootstrap_ci(values: list[float], seed: int, samples: int = 10_000) -> list[float]:
    generator = random.Random(seed)
    estimates = []
    for _ in range(samples):
        estimates.append(statistics.fmean(generator.choice(values) for _ in values))
    return [float(percentile(estimates, 0.025)), float(percentile(estimates, 0.975))]


def paired_bootstrap_ci(
    bare_values: list[float], skill_values: list[float], seed: int, samples: int = 10_000
) -> list[float]:
    generator = random.Random(seed)
    indices = list(range(len(bare_values)))
    estimates = []
    for _ in range(samples):
        selected = [generator.choice(indices) for _ in indices]
        estimates.append(
            statistics.fmean(skill_values[index] - bare_values[index] for index in selected)
        )
    return [float(percentile(estimates, 0.025)), float(percentile(estimates, 0.975))]


def exact_mcnemar_p(improved: int, regressed: int) -> float:
    discordant = improved + regressed
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, value) for value in range(min(improved, regressed) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def group_attempts(attempts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        grouped[attempt["task_name"]].append(attempt)
    return dict(grouped)


def run_metrics(attempts: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    grouped = group_attempts(attempts)
    task_success_rates = [
        sum(row["conservative_reward"] for row in rows) / 3 for rows in grouped.values()
    ]
    task_pass = [float(any(row["reward"] == 1 for row in rows)) for rows in grouped.values()]
    successes = sum(row["reward"] == 1 for row in attempts)
    zeros = sum(row["reward"] == 0 for row in attempts)
    missing = sum(row["reward"] is None for row in attempts)
    evaluated = successes + zeros
    complete_tasks = [
        rows for rows in grouped.values() if len(rows) == 3 and all(row["reward"] is not None for row in rows)
    ]
    patterns = Counter(
        f"{sum(row['reward'] == 1 for row in rows)}/"
        f"{sum(row['reward'] == 0 for row in rows)}/"
        f"{sum(row['reward'] is None for row in rows)}"
        for rows in grouped.values()
    )
    efficiency = {}
    for status in ("all", "reward_1", "reward_0", "missing_reward"):
        rows = attempts if status == "all" else [row for row in attempts if row["status"] == status]
        efficiency[status] = {
            "duration_sec": distribution_stats(row["duration_sec"] for row in rows),
            "input_tokens": distribution_stats(row["input_tokens"] for row in rows),
            "output_tokens": distribution_stats(row["output_tokens"] for row in rows),
            "episodes": distribution_stats(row["episodes"] for row in rows),
        }
    return {
        "planned_attempts": len(attempts),
        "tasks": len(grouped),
        "reward_1": successes,
        "reward_0": zeros,
        "missing_reward": missing,
        "conservative_accuracy": successes / len(attempts),
        "evaluated_accuracy": successes / evaluated if evaluated else None,
        "pass_at_3_tasks": int(sum(task_pass)),
        "pass_at_3": statistics.fmean(task_pass),
        "attempt_bernoulli_variance": (successes / len(attempts))
        * (1.0 - successes / len(attempts)),
        "task_success_rate_variance": statistics.pvariance(task_success_rates),
        "complete_three_attempt_tasks": len(complete_tasks),
        "mean_within_task_variance": statistics.fmean(
            statistics.pvariance([row["conservative_reward"] for row in rows])
            for rows in complete_tasks
        ),
        "success_zero_missing_patterns": dict(sorted(patterns.items())),
        "conservative_accuracy_ci95": bootstrap_ci(task_success_rates, seed),
        "pass_at_3_ci95": bootstrap_ci(task_pass, seed + 1),
        "efficiency": efficiency,
    }


def build_task_rows(
    bare: list[dict[str, Any]], skill: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    bare_grouped = group_attempts(bare)
    skill_grouped = group_attempts(skill)
    tasks = sorted(set(bare_grouped) | set(skill_grouped))
    task_rows = []
    matrix = Counter()
    for task in tasks:
        b = bare_grouped[task]
        s = skill_grouped[task]
        b_success = sum(row["reward"] == 1 for row in b)
        s_success = sum(row["reward"] == 1 for row in s)
        b_pass = b_success > 0
        s_pass = s_success > 0
        if b_pass and s_pass:
            transition = "both_pass"
        elif not b_pass and s_pass:
            transition = "improved"
        elif b_pass and not s_pass:
            transition = "regressed"
        else:
            transition = "neither_pass"
        matrix[transition] += 1
        task_rows.append(
            {
                "task_name": task,
                "bare_successes": b_success,
                "bare_zeros": sum(row["reward"] == 0 for row in b),
                "bare_missing": sum(row["reward"] is None for row in b),
                "bare_pass_at_3": int(b_pass),
                "bare_success_rate": b_success / 3,
                "bare_within_variance": statistics.pvariance(
                    [row["conservative_reward"] for row in b]
                ),
                "skill_successes": s_success,
                "skill_zeros": sum(row["reward"] == 0 for row in s),
                "skill_missing": sum(row["reward"] is None for row in s),
                "skill_pass_at_3": int(s_pass),
                "skill_success_rate": s_success / 3,
                "skill_within_variance": statistics.pvariance(
                    [row["conservative_reward"] for row in s]
                ),
                "success_delta": (s_success - b_success) / 3,
                "transition": transition,
                "skill_trajectory_count": sum(row["has_trajectory"] for row in s),
                "skill_read_count": sum(row["skill_read"] for row in s),
            }
        )
    return task_rows, dict(matrix)


def execution_row(stage: str, kind: str, trial_dir: Path) -> dict[str, Any]:
    result_path = trial_dir / "result.json"
    result = read_json(result_path) if result_path.is_file() else {}
    reward = reward_from_result(result)
    exc_type, exc_message = exception_info(result)
    task_name = str(result.get("task_name") or trial_dir.name.split("__", 1)[0])
    return {
        "stage": stage,
        "record_kind": kind,
        "task_name": task_name,
        "trial_dir": str(trial_dir),
        "reward": reward,
        "status": "reward_1" if reward == 1 else "reward_0" if reward == 0 else "missing_reward",
        "exception_type": exc_type,
        "exception_category": classify_exception(exc_type, exc_message),
        "exception_message": compact(exc_message, 500),
        "exception_blocks_reward": bool((exc_type or exc_message) and reward is None),
        "snapshot_status": snapshot_status(trial_dir),
        "has_trajectory": (trial_dir / "agent" / "trajectory.json").is_file(),
    }


def load_executions(
    bare_job: Path,
    skill_job: Path,
    recovery_root: Path,
    bare_retries: Path,
    bare_recheck_root: Path,
    bare_recheck_retries: Path,
    skill_retries: Path,
) -> list[dict[str, Any]]:
    rows = []
    for stage, job in (("bare_final", bare_job), ("skill_source_final", skill_job)):
        for path in sorted(job.glob("*/result.json")):
            rows.append(execution_row(stage, "formal_final", path.parent))
    for job in sorted((recovery_root / "jobs").glob("tb21_tencent_transport_recovery_g*")):
        for path in sorted(job.glob("*/result.json")):
            rows.append(execution_row("skill_recovery_final", "formal_replacement", path.parent))
    if bare_recheck_root.is_dir():
        for job in sorted(bare_recheck_root.glob("tb21_tencent_*")):
            for path in sorted(job.glob("*/result.json")):
                rows.append(execution_row("bare_recheck_final", "formal_replacement", path.parent))
    archives = [
        ("bare_retry", bare_retries),
        ("skill_source_retry", skill_retries),
        ("skill_recovery_retry", recovery_root / "retry_archives"),
    ]
    for stage, archive_root in archives:
        if not archive_root.is_dir():
            continue
        for execution_dir in sorted(archive_root.rglob("execution-*")):
            if execution_dir.is_dir():
                rows.append(execution_row(stage, "retry_archive", execution_dir))
    if bare_recheck_retries.is_dir():
        patterns = ("tb21_tencent_no_reward_recheck*", "tb21_tencent_protocol_repair*")
        for pattern in patterns:
            for job in sorted(bare_recheck_retries.glob(pattern)):
                for execution_dir in sorted(job.rglob("execution-*")):
                    if execution_dir.is_dir():
                        rows.append(
                            execution_row(
                                "bare_recheck_retry", "retry_archive", execution_dir
                            )
                        )
    return rows


def summarize_environment(executions: list[dict[str, Any]]) -> dict[str, Any]:
    summary: defaultdict[str, Counter[tuple[str, bool]]] = defaultdict(Counter)
    for row in executions:
        if row["exception_category"] == "None":
            continue
        summary[row["stage"]][
            (row["exception_category"], bool(row["exception_blocks_reward"]))
        ] += 1
    return {
        stage: [
            {"category": category, "blocking": blocking, "count": count}
            for (category, blocking), count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
            )
        ]
        for stage, counts in sorted(summary.items())
    }


def choose_representative(
    attempts: list[dict[str, Any]], reward: float
) -> dict[str, Any] | None:
    candidates = [
        row for row in attempts if row["reward"] == reward and row["has_trajectory"]
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            row["duration_sec"] if row["duration_sec"] is not None else float("inf"),
            row["trial_dir"],
        )
    )
    return candidates[len(candidates) // 2]


def root_cause_label(skill_attempt: dict[str, Any] | None, expected_reward: float) -> str:
    if skill_attempt is None:
        return "缺少可分析轨迹"
    commands = "\n".join(skill_attempt.get("commands") or []).lower()
    if skill_attempt["exception_category"] == "Agent timeout":
        return "执行超时"
    if not skill_attempt.get("skill_read"):
        return "技能未实际读取"
    if expected_reward == 1:
        return "技能提供了可执行路径并通过 verifier"
    validation_terms = ("pytest", "make test", "ctest", "curl", "diff", "verify", "test")
    if not any(term in commands for term in validation_terms):
        return "读取技能后缺少充分本地验证"
    return "技能策略或实现未满足 verifier"


def attempt_evidence_markdown(label: str, row: dict[str, Any] | None) -> str:
    if row is None:
        return f"### {label}\n\n无带轨迹的代表 attempt。\n"
    commands = row.get("commands") or []
    command_text = "\n".join(f"- `{compact(command, 180)}`" for command in commands[:8])
    return f"""### {label}

- Reward：`{row['reward']}`
- Trial：`{row['trial_dir']}`
- Result：`{row['result_path'] or '不存在'}`
- Trajectory：`{row['trajectory_path']}`
- Verifier：`{row['verifier_path'] or '不存在'}`
- Skill 读取：`{row['skill_read']}`{f"，命令 `{row['skill_read_command']}`" if row['skill_read_command'] else ""}
- 初始推理：{row['initial_reasoning'] or '无'}
- 最终陈述：{row['final_message'] or '无'}
- Verifier 摘要：{row['verifier_excerpt'] or '无 test-stdout'}

关键命令：

{command_text or '- 无可提取命令'}
"""


def write_case_studies(
    output: Path,
    bare: list[dict[str, Any]],
    skill: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    case_dir = output / "case_studies"
    case_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("regression_*.md", "improvement_*.md"):
        for stale in case_dir.glob(pattern):
            stale.unlink()
    bare_grouped = group_attempts(bare)
    skill_grouped = group_attempts(skill)
    index = []
    regression_tasks = [
        row["task_name"] for row in task_rows if row["transition"] == "regressed"
    ]
    improvement_tasks = [
        task
        for task in IMPROVEMENT_CASES
        if any(
            row["task_name"] == task and row["transition"] == "improved"
            for row in task_rows
        )
    ]
    for case_type, tasks in (
        ("regression", regression_tasks),
        ("improvement", improvement_tasks),
    ):
        for task in tasks:
            if case_type == "regression":
                bare_rep = choose_representative(bare_grouped[task], 1.0)
                skill_rep = choose_representative(skill_grouped[task], 0.0)
                label = root_cause_label(skill_rep, 0.0)
            else:
                bare_rep = choose_representative(bare_grouped[task], 0.0)
                skill_rep = choose_representative(skill_grouped[task], 1.0)
                label = root_cause_label(skill_rep, 1.0)
            path = case_dir / f"{case_type}_{task}.md"
            bare_rewards = [row["reward"] for row in bare_grouped[task]]
            skill_rewards = [row["reward"] for row in skill_grouped[task]]
            path.write_text(
                f"# {task}: {'退化' if case_type == 'regression' else '提升'}案例\n\n"
                f"- 裸跑结果：`{bare_rewards}`\n"
                f"- Skill 结果：`{skill_rewards}`\n"
                f"- 证据分类：{label}\n"
                "- 说明：代表 attempt 按运行时长中位位置选择，避免挑选极端轨迹。\n\n"
                + attempt_evidence_markdown("裸跑代表 attempt", bare_rep)
                + "\n"
                + attempt_evidence_markdown("Skill 代表 attempt", skill_rep),
                encoding="utf-8",
            )
            index.append(
                {
                    "task_name": task,
                    "case_type": case_type,
                    "bare_rewards": bare_rewards,
                    "skill_rewards": skill_rewards,
                    "root_cause_label": label,
                    "path": str(path),
                }
            )
    return index


def write_environment_cases(output: Path, executions: list[dict[str, Any]]) -> Path:
    path = output / "case_studies" / "environment_cases.md"
    specifications = [
        ("bare_final", "Snapshot quota", False),
        ("bare_final", "E2B transport", True),
        ("bare_final", "Tmux/session", True),
        ("bare_final", "Model retries exhausted", True),
        ("bare_final", "Verifier timeout", True),
        ("bare_recheck_final", "Authentication", True),
        ("bare_recheck_final", "E2B transport", True),
        ("bare_recheck_final", "Agent timeout", False),
        ("bare_recheck_final", "Verifier timeout", True),
        ("skill_source_final", "E2B transport", True),
        ("skill_source_final", "Disk space", True),
        ("skill_recovery_final", "Agent timeout", False),
        ("skill_recovery_final", "Tmux/session", True),
        ("skill_recovery_final", "Other", True),
    ]
    lines = [
        "# 环境与执行失败案例",
        "",
        "下列计数基于 `executions.csv`，包括 formal final 与 retry archives。",
        "阻断标记表示该 execution 没有 reward；非阻断异常可能与有效 reward 同时存在。",
        "",
    ]
    for stage, category, blocking in specifications:
        matches = [
            row
            for row in executions
            if row["stage"] == stage
            and row["exception_category"] == category
            and bool(row["exception_blocks_reward"]) == blocking
        ]
        if not matches:
            continue
        sample = matches[0]
        lines.extend(
            [
                f"## {stage}: {category}",
                "",
                f"- 执行数：{len(matches)}",
                f"- 阻断 reward：{'是' if blocking else '否'}",
                f"- 样本任务：`{sample['task_name']}`",
                f"- 样本目录：`{sample['trial_dir']}`",
                f"- 异常类型：`{sample['exception_type'] or 'N/A'}`",
                f"- 异常信息：{sample['exception_message'] or 'N/A'}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{100 * value:.2f}%"


def fmt_num(value: float | None, digits: int = 2) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def report_markdown(
    summary: dict[str, Any], task_rows: list[dict[str, Any]], cases: list[dict[str, Any]]
) -> str:
    bare = summary["runs"]["bare"]
    skill = summary["runs"]["skill"]
    cross = summary["cross"]
    improvements = [row for row in task_rows if row["transition"] == "improved"]
    regressions = [row for row in task_rows if row["transition"] == "regressed"]
    env_lines = []
    for stage, entries in summary["environment"].items():
        for entry in entries:
            env_lines.append(
                f"| {stage} | {entry['category']} | {'是' if entry['blocking'] else '否'} | {entry['count']} |"
            )
    case_lines = [
        f"| {case['case_type']} | `{case['task_name']}` | {case['bare_rewards']} | {case['skill_rewards']} | {case['root_cause_label']} | [详情]({Path(case['path']).relative_to(Path(case['path']).parents[1])}) |"
        for case in cases
    ]
    skill_read = summary["skill_read"]
    return f"""# Tencent TB2.1 裸跑与 Skill 对照分析

## 执行摘要

裸跑按正式裁决合并后，Skill 的正确率从 **{fmt_pct(bare['conservative_accuracy'])}**（{bare['reward_1']}/267）变为 **{fmt_pct(skill['conservative_accuracy'])}**（{skill['reward_1']}/267），绝对变化 **{fmt_pct(cross['accuracy_delta'])}**。pass@3 从 **{bare['pass_at_3_tasks']}/89（{fmt_pct(bare['pass_at_3'])}）**变为 **{skill['pass_at_3_tasks']}/89（{fmt_pct(skill['pass_at_3'])}）**。

任务级转移为：共同通过 {cross['transition_matrix']['both_pass']}，共同未通过 {cross['transition_matrix']['neither_pass']}，提升 {cross['transition_matrix']['improved']}，退化 {cross['transition_matrix']['regressed']}。McNemar exact p={cross['mcnemar_exact_p']:.4f}；pass@3 的净提升在 89 题规模下没有显示强统计证据，而 attempt 正确率和成功次数分布存在明显正向变化。

![总体指标](figures/overview.png)

## 数据与口径

- 裸跑正式数据：89 题 × 3 attempts = 267；其中 251 个原始有效结果、11 个有效重跑替换、5 个未解决结果按正式裁决记为 0。
- Skill 正式数据：83 个原始有效 attempt、183 个 transport replacement、1 个未替换磁盘不足 attempt，共 267。
- 20 题 transport canary 不进入正式指标。
- 主正确率和 pass@3 将缺失 reward 计为失败；有效评测正确率仅用于环境诊断。
- 两个 job 的随机 trial ID 不可配对，交叉统计以任务为配对单位。
- Retry archives 仅进入执行与环境诊断，不重复计入正式正确率。

## 单次运行指标

| 指标 | 裸跑 | Skill |
|---|---:|---:|
| Reward 1 | {bare['reward_1']} | {skill['reward_1']} |
| Reward 0 | {bare['reward_0']} | {skill['reward_0']} |
| 无 reward | {bare['missing_reward']} | {skill['missing_reward']} |
| 保守正确率 | {fmt_pct(bare['conservative_accuracy'])} | {fmt_pct(skill['conservative_accuracy'])} |
| 有效评测正确率 | {fmt_pct(bare['evaluated_accuracy'])} | {fmt_pct(skill['evaluated_accuracy'])} |
| pass@3 | {bare['pass_at_3_tasks']}/89 | {skill['pass_at_3_tasks']}/89 |
| Attempt Bernoulli 方差 | {bare['attempt_bernoulli_variance']:.4f} | {skill['attempt_bernoulli_variance']:.4f} |
| 任务成功率方差 | {bare['task_success_rate_variance']:.4f} | {skill['task_success_rate_variance']:.4f} |
| 完整三次任务数 | {bare['complete_three_attempt_tasks']} | {skill['complete_three_attempt_tasks']} |
| 平均组内方差 | {bare['mean_within_task_variance']:.4f} | {skill['mean_within_task_variance']:.4f} |

![成功次数分布](figures/success_distribution.png)

保守正确率任务级 bootstrap 95% CI：裸跑 {fmt_pct(bare['conservative_accuracy_ci95'][0])}–{fmt_pct(bare['conservative_accuracy_ci95'][1])}，Skill {fmt_pct(skill['conservative_accuracy_ci95'][0])}–{fmt_pct(skill['conservative_accuracy_ci95'][1])}。配对正确率增量 95% CI 为 {fmt_pct(cross['accuracy_delta_ci95'][0])}–{fmt_pct(cross['accuracy_delta_ci95'][1])}。

## 交叉分析

![任务转移矩阵](figures/transition_matrix.png)

![逐题成功次数变化](figures/task_delta.png)

严格退化任务共 {len(regressions)} 个：{', '.join(f'`{row["task_name"]}`' for row in regressions)}。

严格提升任务共 {len(improvements)} 个：{', '.join(f'`{row["task_name"]}`' for row in improvements)}。

Skill 正式 attempt 中，有轨迹 {skill_read['trajectory_attempts']} 个，实际执行技能读取命令 {skill_read['read_attempts']} 个；读取率按有轨迹 attempt 计为 {fmt_pct(skill_read['read_rate_on_trajectories'])}。未产生轨迹的基础设施失败不计为“未读技能”。

## 效率

| 指标（全部正式 attempts） | 裸跑中位数 | Skill 中位数 | 裸跑 P95 | Skill P95 |
|---|---:|---:|---:|---:|
| 运行时间（秒） | {fmt_num(bare['efficiency']['all']['duration_sec']['median'])} | {fmt_num(skill['efficiency']['all']['duration_sec']['median'])} | {fmt_num(bare['efficiency']['all']['duration_sec']['p95'])} | {fmt_num(skill['efficiency']['all']['duration_sec']['p95'])} |
| 输入 tokens | {fmt_num(bare['efficiency']['all']['input_tokens']['median'], 0)} | {fmt_num(skill['efficiency']['all']['input_tokens']['median'], 0)} | {fmt_num(bare['efficiency']['all']['input_tokens']['p95'], 0)} | {fmt_num(skill['efficiency']['all']['input_tokens']['p95'], 0)} |
| 输出 tokens | {fmt_num(bare['efficiency']['all']['output_tokens']['median'], 0)} | {fmt_num(skill['efficiency']['all']['output_tokens']['median'], 0)} | {fmt_num(bare['efficiency']['all']['output_tokens']['p95'], 0)} | {fmt_num(skill['efficiency']['all']['output_tokens']['p95'], 0)} |
| Episodes | {fmt_num(bare['efficiency']['all']['episodes']['median'])} | {fmt_num(skill['efficiency']['all']['episodes']['median'])} | {fmt_num(bare['efficiency']['all']['episodes']['p95'])} | {fmt_num(skill['efficiency']['all']['episodes']['p95'])} |

![效率比较](figures/efficiency.png)

## 环境与失败情况

`executions.csv` 同时记录正式结果和 retry archive。下表中的异常数是执行诊断计数，不是正确率分母；同一 formal trial 可经历多个 execution。

| 阶段 | 异常类别 | 阻断 reward | 执行数 |
|---|---|---:|---:|
{chr(10).join(env_lines)}

![环境异常](figures/environment_failures.png)

重点环境结论：裸跑存在大量 snapshot pause quota 异常，但许多已有有效 reward，不能计作任务失败；16 个原始无 reward 中，11 个由后续有效重跑替换，5 个仍未解决并按正式裁决记为 0。首次裸跑重评还出现过无效 key、transport、agent/verifier timeout，均在 `executions.csv` 中保留。原始 Skill job 的主要阻断是 183 个 E2B transport failure。恢复后的 3 个无 reward replacement 分别是 2 个 tmux session 丢失和 1 个 command-too-long；另保留 1 个未自动重跑的 `NotEnoughSpaceException`。

[查看环境故障样本与证据路径](case_studies/environment_cases.md)

## 轨迹案例

| 类型 | 任务 | 裸跑三次 | Skill 三次 | 证据分类 | 详情 |
|---|---|---|---|---|---|
{chr(10).join(case_lines)}

案例文件包含代表性成功/失败 trajectory、技能读取命令、初始 reasoning、关键命令、最终陈述和 verifier 摘要。分类是基于可见轨迹的行为标签，不把无轨迹基础设施失败解释为 agent 决策。

## 限制

- 每个配置仅 3 次采样，任务级 pass@3 转移的统计功效有限。
- 不同 job 的 attempts 没有共享随机种子或可验证的 attempt 身份，因此不做 attempt-to-attempt 因果配对。
- Skill 数据含 transport recovery，运行时段和控制面负载与裸跑不同；正确性可比较，效率差异应谨慎解释。
- 自动案例分类不能替代逐行人工代码审查，报告保留完整证据路径以便复核。
"""


def validate(
    bare: list[dict[str, Any]],
    skill: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    matrix: dict[str, int],
) -> None:
    for label, attempts in (("bare", bare), ("skill", skill)):
        if len(attempts) != 267:
            raise ValueError(f"{label}: expected 267 attempts, found {len(attempts)}")
        grouped = group_attempts(attempts)
        if len(grouped) != 89 or any(len(rows) != 3 for rows in grouped.values()):
            raise ValueError(f"{label}: expected 89 tasks with 3 attempts")
    if sum(row["reward"] == 1 for row in bare) != 88:
        raise ValueError("bare reward-1 anchor mismatch")
    if sum(row["reward"] is None for row in bare) != 0:
        raise ValueError("bare missing-reward anchor mismatch")
    if sum(row["reward"] == 1 for row in skill) != 118:
        raise ValueError("skill reward-1 anchor mismatch")
    if sum(row["reward"] is None for row in skill) != 4:
        raise ValueError("skill missing-reward anchor mismatch")
    if sum(matrix.values()) != 89:
        raise ValueError(f"transition matrix must cover 89 tasks: {matrix}")
    if len(task_rows) != 89:
        raise ValueError("expected 89 task rows")


def analyze(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bare = load_bare_attempts(
        args.bare_job, args.bare_adjudication, args.bare_recheck_root
    )
    skill = load_skill_attempts(args.skill_job, args.recovery_root)
    task_rows, matrix = build_task_rows(bare, skill)
    validate(bare, skill, task_rows, matrix)
    bare_metrics = run_metrics(bare, args.seed)
    skill_metrics = run_metrics(skill, args.seed + 10)
    bare_task = {row["task_name"]: row for row in task_rows}
    task_names = sorted(bare_task)
    bare_rates = [bare_task[name]["bare_success_rate"] for name in task_names]
    skill_rates = [bare_task[name]["skill_success_rate"] for name in task_names]
    cross = {
        "accuracy_delta": skill_metrics["conservative_accuracy"]
        - bare_metrics["conservative_accuracy"],
        "accuracy_relative_change": (
            skill_metrics["conservative_accuracy"] / bare_metrics["conservative_accuracy"] - 1
        ),
        "pass_at_3_delta": skill_metrics["pass_at_3"] - bare_metrics["pass_at_3"],
        "transition_matrix": matrix,
        "mcnemar_exact_p": exact_mcnemar_p(matrix["improved"], matrix["regressed"]),
        "accuracy_delta_ci95": paired_bootstrap_ci(
            bare_rates, skill_rates, args.seed + 20
        ),
    }
    executions = load_executions(
        args.bare_job,
        args.skill_job,
        args.recovery_root,
        args.bare_retries,
        args.bare_recheck_root,
        args.bare_recheck_retries,
        args.skill_retries,
    )
    cases = write_case_studies(output, bare, skill, task_rows)
    environment_case_path = write_environment_cases(output, executions)
    skill_trajectories = sum(row["has_trajectory"] for row in skill)
    skill_reads = sum(row["skill_read"] for row in skill)
    summary = {
        "schema_version": 2,
        "generated_from": {
            "bare_job": str(args.bare_job),
            "bare_adjudication": str(args.bare_adjudication),
            "bare_recheck_root": str(args.bare_recheck_root),
            "skill_job": str(args.skill_job),
            "recovery_root": str(args.recovery_root),
        },
        "missing_policy": "count_as_failure",
        "bootstrap_seed": args.seed,
        "bootstrap_samples": 10_000,
        "runs": {"bare": bare_metrics, "skill": skill_metrics},
        "bare_resolution": dict(Counter(row["source"] for row in bare)),
        "cross": cross,
        "skill_read": {
            "trajectory_attempts": skill_trajectories,
            "read_attempts": skill_reads,
            "read_rate_on_trajectories": skill_reads / skill_trajectories,
        },
        "environment": summarize_environment(executions),
        "environment_case_study": str(environment_case_path),
        "case_studies": cases,
    }
    attempt_fields = [
        "run", "task_name", "attempt_index", "trial_name", "status", "reward",
        "conservative_reward", "source", "raw_reward", "reward_resolution",
        "trial_dir", "original_trial_dir", "result_path", "verifier_path",
        "exception_type", "exception_category", "exception_message",
        "exception_blocks_reward", "started_at", "finished_at", "duration_sec",
        "input_tokens", "output_tokens", "cache_tokens", "episodes",
        "snapshot_status", "has_trajectory", "trajectory_path", "trajectory_steps",
        "skill_read", "skill_read_command", "verifier_excerpt",
    ]
    write_csv(output / "attempts.csv", sorted(bare + skill, key=lambda r: (r["run"], r["task_name"], r["attempt_index"])), attempt_fields)
    write_csv(output / "tasks.csv", task_rows)
    write_csv(output / "executions.csv", executions)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(
        report_markdown(summary, task_rows, cases), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "attempts": len(bare) + len(skill),
                "tasks": len(task_rows),
                "executions": len(executions),
                "bare_reward_1": bare_metrics["reward_1"],
                "skill_reward_1": skill_metrics["reward_1"],
                "matrix": matrix,
            },
            sort_keys=True,
        )
    )


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size, index=0)
    return ImageFont.load_default()


def new_chart(title: str, width: int = 1400, height: int = 850):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), "#f7f8fa")
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), title, fill="#17212b", font=font(34, True))
    return image, draw


def save_overview(output: Path, summary: dict[str, Any]) -> None:
    image, draw = new_chart("总体指标对比")
    metrics = [
        ("保守正确率", "conservative_accuracy"),
        ("有效评测正确率", "evaluated_accuracy"),
        ("pass@3", "pass_at_3"),
    ]
    colors = {"bare": "#3b6ea8", "skill": "#d05a47"}
    left, top, chart_h = 140, 180, 520
    for index, (label, key) in enumerate(metrics):
        group_x = left + index * 390
        for offset, run in enumerate(("bare", "skill")):
            value = float(summary["runs"][run][key])
            x = group_x + offset * 120
            y = top + chart_h * (1 - value)
            draw.rectangle((x, y, x + 82, top + chart_h), fill=colors[run])
            draw.text((x, y - 36), f"{value*100:.1f}%", fill="#17212b", font=font(22, True))
        draw.text((group_x - 10, top + chart_h + 24), label, fill="#17212b", font=font(22))
    draw.rectangle((1040, 80, 1070, 110), fill=colors["bare"])
    draw.text((1080, 77), "裸跑", fill="#17212b", font=font(22))
    draw.rectangle((1170, 80, 1200, 110), fill=colors["skill"])
    draw.text((1210, 77), "Skill", fill="#17212b", font=font(22))
    image.save(output / "figures" / "overview.png")


def save_success_distribution(output: Path, tasks: list[dict[str, str]]) -> None:
    image, draw = new_chart("每题三次成功次数分布")
    colors = {"bare": "#3b6ea8", "skill": "#d05a47"}
    counts = {run: Counter(int(float(row[f"{run}_successes"])) for row in tasks) for run in colors}
    left, top, base, scale = 150, 170, 720, 15
    for success_count in range(4):
        group_x = left + success_count * 280
        for offset, run in enumerate(("bare", "skill")):
            count = counts[run][success_count]
            x = group_x + offset * 90
            y = base - count * scale
            draw.rectangle((x, y, x + 68, base), fill=colors[run])
            draw.text((x + 16, y - 32), str(count), fill="#17212b", font=font(22, True))
        draw.text((group_x + 35, base + 25), f"{success_count}/3", fill="#17212b", font=font(24))
    image.save(output / "figures" / "success_distribution.png")


def save_transition_matrix(output: Path, summary: dict[str, Any]) -> None:
    image, draw = new_chart("任务级 pass@3 转移矩阵", 1100, 850)
    matrix = summary["cross"]["transition_matrix"]
    cells = [
        ("neither_pass", 170, 210, "共同未通过"),
        ("improved", 560, 210, "Skill 提升"),
        ("regressed", 170, 500, "Skill 退化"),
        ("both_pass", 560, 500, "共同通过"),
    ]
    max_count = max(matrix.values())
    for key, x, y, label in cells:
        count = matrix[key]
        strength = count / max_count
        color = (int(235 - 65 * strength), int(242 - 50 * strength), int(246 - 30 * strength))
        draw.rectangle((x, y, x + 320, y + 220), fill=color, outline="#687785", width=2)
        draw.text((x + 25, y + 30), label, fill="#17212b", font=font(25, True))
        draw.text((x + 125, y + 105), str(count), fill="#17212b", font=font(52, True))
    image.save(output / "figures" / "transition_matrix.png")


def save_task_delta(output: Path, tasks: list[dict[str, str]]) -> None:
    changed = [row for row in tasks if row["transition"] in ("improved", "regressed")]
    changed.sort(key=lambda row: (float(row["success_delta"]), row["task_name"]))
    image, draw = new_chart("状态变化任务的三次成功率差值", 1600, 1100)
    center, top, spacing, max_width = 950, 140, 54, 500
    draw.line((center, top - 20, center, top + spacing * len(changed)), fill="#687785", width=2)
    for index, row in enumerate(changed):
        delta = float(row["success_delta"])
        y = top + index * spacing
        width = abs(delta) * max_width
        color = "#2f8f64" if delta > 0 else "#c74f46"
        x0, x1 = (center, center + width) if delta > 0 else (center - width, center)
        draw.rectangle((x0, y, x1, y + 30), fill=color)
        draw.text((40, y), row["task_name"], fill="#17212b", font=font(19))
        draw.text((x1 + 12 if delta > 0 else x0 - 72, y), f"{delta:+.2f}", fill="#17212b", font=font(18, True))
    image.save(output / "figures" / "task_delta.png")


def save_environment(output: Path, summary: dict[str, Any]) -> None:
    image, draw = new_chart("主要执行异常（含 retry archives）", 1500, 1000)
    totals = Counter()
    for stage, entries in summary["environment"].items():
        for entry in entries:
            if entry["blocking"]:
                totals[(stage, entry["category"])] += int(entry["count"])
    rows = totals.most_common(12)
    max_count = max((count for _, count in rows), default=1)
    for index, ((stage, category), count) in enumerate(rows):
        y = 140 + index * 65
        width = 900 * count / max_count
        draw.text((30, y), compact(f"{stage}: {category}", 52), fill="#17212b", font=font(19))
        draw.rectangle((490, y, 490 + width, y + 34), fill="#765a96")
        draw.text((505 + width, y), str(count), fill="#17212b", font=font(19, True))
    image.save(output / "figures" / "environment_failures.png")


def save_efficiency(output: Path, summary: dict[str, Any]) -> None:
    image, draw = new_chart("效率中位数对比")
    keys = [("运行时间(分钟)", "duration_sec", 60), ("输入 tokens(万)", "input_tokens", 10000), ("输出 tokens(万)", "output_tokens", 10000), ("Episodes", "episodes", 1)]
    colors = {"bare": "#3b6ea8", "skill": "#d05a47"}
    for index, (label, key, divisor) in enumerate(keys):
        y = 160 + index * 150
        values = {
            run: (summary["runs"][run]["efficiency"]["all"][key]["median"] or 0) / divisor
            for run in colors
        }
        max_value = max(values.values()) or 1
        draw.text((50, y), label, fill="#17212b", font=font(22, True))
        for offset, run in enumerate(("bare", "skill")):
            bar_y = y + 38 + offset * 42
            width = 780 * values[run] / max_value
            draw.rectangle((300, bar_y, 300 + width, bar_y + 28), fill=colors[run])
            draw.text((315 + width, bar_y), f"{run} {values[run]:.2f}", fill="#17212b", font=font(18))
    image.save(output / "figures" / "efficiency.png")


def charts_only(output: Path) -> None:
    from PIL import Image

    _ = Image
    summary = read_json(output / "summary.json")
    tasks = load_csv(output / "tasks.csv")
    (output / "figures").mkdir(parents=True, exist_ok=True)
    save_overview(output, summary)
    save_success_distribution(output, tasks)
    save_transition_matrix(output, summary)
    save_task_delta(output, tasks)
    save_environment(output, summary)
    save_efficiency(output, summary)
    print(f"generated 6 charts under {output / 'figures'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bare-job", type=Path, default=DEFAULT_BARE_JOB)
    parser.add_argument("--skill-job", type=Path, default=DEFAULT_SKILL_JOB)
    parser.add_argument("--recovery-root", type=Path, default=DEFAULT_RECOVERY_ROOT)
    parser.add_argument("--bare-retries", type=Path, default=DEFAULT_BARE_RETRIES)
    parser.add_argument(
        "--bare-adjudication", type=Path, default=DEFAULT_BARE_ADJUDICATION
    )
    parser.add_argument(
        "--bare-recheck-root", type=Path, default=DEFAULT_BARE_RECHECK_ROOT
    )
    parser.add_argument(
        "--bare-recheck-retries", type=Path, default=DEFAULT_BARE_RECHECK_RETRIES
    )
    parser.add_argument("--skill-retries", type=Path, default=DEFAULT_SKILL_RETRIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260818)
    parser.add_argument("--charts-only", action="store_true")
    args = parser.parse_args()
    if args.charts_only:
        charts_only(args.output.resolve())
    else:
        analyze(args)


if __name__ == "__main__":
    main()
