"""Build evidence bundles for Tencent TB2.1 skill regressions and improvements."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_ANALYSIS = Path(
    "/data2/liyishan/tbench2-openclaw-min/artifacts/"
    "tb21_tencent_skill_comparison_20260818"
)
DEFAULT_SKILL_ROOT = Path(
    "/data2/liyishan/tbench2-openclaw-min/artifacts/tencent-openclaw-skills/"
    "tb21_tencent_claude_authoring_full_20260817_003000/skills"
)
DEFAULT_OUTPUT = Path(
    "/data2/liyishan/tbench2-openclaw-min/artifacts/"
    "tb21_tencent_skill_case_studies_20260818"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def compact(value: Any, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def quote(value: Any, fallback: str = "无") -> str:
    text = compact(value) or fallback
    return "\n".join(f"> {line}" for line in text.splitlines())


def reward_value(row: dict[str, str]) -> float | None:
    value = row.get("reward", "")
    return float(value) if value else None


def trajectory_summary(path: Path, task_name: str) -> dict[str, Any]:
    trajectory = json.loads(path.read_text(encoding="utf-8"))
    agent_steps = [step for step in trajectory.get("steps", []) if step.get("source") == "agent"]
    commands: list[str] = []
    skill_read_command = ""
    skill_path = f"/opt/openclaw-skills/{task_name}/SKILL.md"
    evidence_steps: list[dict[str, str]] = []
    for step in agent_steps:
        step_commands = []
        for call in step.get("tool_calls") or []:
            arguments = call.get("arguments") or {}
            command = arguments.get("keystrokes")
            if isinstance(command, str) and command.strip():
                normalized = command.strip()
                commands.append(normalized)
                step_commands.append(normalized)
                if skill_path in normalized and not skill_read_command:
                    skill_read_command = normalized
        evidence_steps.append(
            {
                "step_id": str(step.get("step_id") or ""),
                "reasoning": compact(step.get("reasoning_content"), 500),
                "message": compact(step.get("message"), 500),
                "commands": compact("\n".join(step_commands), 800),
                "observation": compact(step.get("observation"), 800),
            }
        )

    selected_indices: list[int] = []
    if evidence_steps:
        selected_indices.append(0)
    for index, step in enumerate(evidence_steps):
        combined = f"{step['commands']} {step['message']}".lower()
        if skill_path.lower() in combined or any(
            token in combined
            for token in ("pytest", "make test", "ctest", "verify", "diff ", "curl ")
        ):
            selected_indices.append(index)
    if evidence_steps:
        selected_indices.append(len(evidence_steps) - 1)
    selected_indices = list(dict.fromkeys(selected_indices))[:10]
    return {
        "steps": len(trajectory.get("steps") or []),
        "initial_reasoning": next(
            (compact(step.get("reasoning_content"), 900) for step in agent_steps if step.get("reasoning_content")),
            "",
        ),
        "final_message": next(
            (compact(step.get("message"), 900) for step in reversed(agent_steps) if step.get("message")),
            "",
        ),
        "skill_read": bool(skill_read_command),
        "skill_read_command": compact(skill_read_command, 500),
        "commands": [compact(command, 400) for command in commands[:16]],
        "evidence_steps": [evidence_steps[index] for index in selected_indices],
    }


def choose_representative(rows: list[dict[str, Any]], reward: float) -> dict[str, Any]:
    candidates = [row for row in rows if reward_value(row) == reward]
    if not candidates:
        raise ValueError(f"no reward={reward} representative for {rows[0]['task_name']}")
    candidates.sort(
        key=lambda row: (
            float(row["duration_sec"]) if row.get("duration_sec") else float("inf"),
            row["trial_name"],
        )
    )
    return candidates[len(candidates) // 2]


def copy_required(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_attempt(
    task_dir: Path, row: dict[str, str]
) -> tuple[dict[str, Any], dict[str, str]]:
    run = row["run"]
    attempt_index = int(row["attempt_index"])
    relative_dir = Path("raw") / run / f"attempt-{attempt_index}"
    destination = task_dir / relative_dir
    trajectory_source = Path(row["trajectory_path"])
    result_source = Path(row["result_path"])
    verifier_source = Path(row["verifier_path"]) if row.get("verifier_path") else None
    copy_required(trajectory_source, destination / "trajectory.json")
    copy_required(result_source, destination / "result.json")
    verifier_copy = ""
    if verifier_source and verifier_source.is_file():
        copy_required(verifier_source, destination / "verifier-test-stdout.txt")
        verifier_copy = str(relative_dir / "verifier-test-stdout.txt")

    metadata = {
        "run": run,
        "task_name": row["task_name"],
        "attempt_index": attempt_index,
        "reward": reward_value(row),
        "source": row["source"],
        "trial_name": row["trial_name"],
        "original_trial_dir": row["original_trial_dir"],
        "source_trial_dir": row["trial_dir"],
        "source_trajectory": row["trajectory_path"],
        "source_result": row["result_path"],
        "source_verifier": row.get("verifier_path") or None,
        "exception_type": row.get("exception_type") or None,
        "exception_category": row.get("exception_category") or None,
        "skill_read": row.get("skill_read") == "True",
    }
    (destination / "source.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    copied = dict(row)
    copied.update(
        {
            "bundle_trajectory": str(relative_dir / "trajectory.json"),
            "bundle_result": str(relative_dir / "result.json"),
            "bundle_verifier": verifier_copy,
            "bundle_source_metadata": str(relative_dir / "source.json"),
        }
    )
    return trajectory_summary(trajectory_source, row["task_name"]), copied


def render_evidence_steps(summary: dict[str, Any]) -> str:
    sections = []
    for step in summary["evidence_steps"]:
        sections.extend(
            [
                f"#### Step {step['step_id'] or 'N/A'}",
                "",
                "推理/说明：",
                "",
                quote(step["reasoning"] or step["message"]),
                "",
                "命令：",
                "",
                quote(step["commands"]),
                "",
                "Observation：",
                "",
                quote(step["observation"]),
                "",
            ]
        )
    return "\n".join(sections)


def render_representative(
    label: str,
    row: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    verifier = row["bundle_verifier"]
    return f"""### {label}

- Reward：`{row['reward']}`
- Trial：`{row['trial_name']}`
- 来源类型：`{row['source']}`
- 原始轨迹：[trajectory.json]({row['bundle_trajectory']})
- Result：[result.json]({row['bundle_result']})
- Verifier：{f'[test-stdout.txt]({verifier})' if verifier else '原执行未产生 verifier 文件'}
- 实际读取 Skill：`{summary['skill_read']}`
- Skill 读取命令：`{summary['skill_read_command'] or '无'}`
- Trajectory steps：`{summary['steps']}`

初始推理：

{quote(summary['initial_reasoning'])}

最终陈述：

{quote(summary['final_message'])}

关键步骤：

{render_evidence_steps(summary)}
"""


def render_case_study(
    task: dict[str, str],
    rows: list[dict[str, Any]],
    summaries: dict[tuple[str, int], dict[str, Any]],
) -> str:
    task_name = task["task_name"]
    transition = task["transition"]
    bare = sorted((row for row in rows if row["run"] == "bare"), key=lambda row: int(row["attempt_index"]))
    skill = sorted((row for row in rows if row["run"] == "skill"), key=lambda row: int(row["attempt_index"]))
    if transition == "regressed":
        bare_rep = choose_representative(bare, 1.0)
        skill_rep = choose_representative(skill, 0.0)
        title = "退化"
        conclusion = (
            f"裸跑有 {task['bare_successes']}/3 次通过，而挂载 Skill 后为 0/3。"
            "这是本次三次采样中的严格退化；代表轨迹展示行为差异，但不能单独证明 Skill 是唯一因果因素。"
        )
    else:
        bare_rep = choose_representative(bare, 0.0)
        skill_rep = choose_representative(skill, 1.0)
        title = "Skill 成功"
        conclusion = (
            f"裸跑为 0/3，挂载 Skill 后有 {task['skill_successes']}/3 次通过。"
            "这是本次三次采样中的严格提升；代表轨迹用于说明 Skill 被如何读取和执行。"
        )

    table_rows = []
    for row in bare + skill:
        reward_label = row["reward"] if row["reward"] else "missing"
        verifier = (
            f"[stdout]({row['bundle_verifier']})" if row["bundle_verifier"] else "未产生"
        )
        table_rows.append(
            f"| {row['run']} | {row['attempt_index']} | {reward_label} | "
            f"{row['source']} | {row['skill_read']} | [traj]({row['bundle_trajectory']}) | "
            f"[result]({row['bundle_result']}) | {verifier} |"
        )
    skill_reads = sum(row.get("skill_read") == "True" for row in skill)
    bare_key = (bare_rep["run"], int(bare_rep["attempt_index"]))
    skill_key = (skill_rep["run"], int(skill_rep["attempt_index"]))
    return f"""# {task_name}: {title}案例

## 结论

{conclusion}

- 裸跑三次：`{task['bare_successes']}/3`
- Skill 三次：`{task['skill_successes']}/3`
- Skill 实际读取：`{skill_reads}/3`
- 对应完整 Skill：[SKILL.md](skill/SKILL.md)（同目录保留附属 scripts/assets）

## 六次原始证据

| 运行 | Attempt | Reward | Canonical 来源 | Skill read | 原始 Trajectory | Result | Verifier |
|---|---:|---:|---|---:|---|---|---|
{chr(10).join(table_rows)}

## 代表轨迹对照

{render_representative('裸跑代表 attempt', bare_rep, summaries[bare_key])}

{render_representative('Skill 代表 attempt', skill_rep, summaries[skill_key])}

## 判读边界

- 本页正文只摘录可见的 reasoning、命令、observation 和 verifier 证据；完整原文以上述 `trajectory.json` 为准。
- 两个 job 的 attempt ID 不可随机配对，因此代表轨迹是行为对照，不是严格的逐 attempt 因果配对。
- Reward 和异常状态来自 canonical `attempts.csv`；retry archives 不重复计入三次正式结果。
"""


def build(args: argparse.Namespace) -> None:
    analysis = args.analysis.resolve()
    skill_root = args.skill_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")

    tasks = [
        row
        for row in read_csv(analysis / "tasks.csv")
        if row["transition"] in {"regressed", "improved"}
    ]
    selected_names = {row["task_name"] for row in tasks}
    attempts = [
        row
        for row in read_csv(analysis / "attempts.csv")
        if row["task_name"] in selected_names
    ]
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in attempts:
        grouped[row["task_name"]].append(row)
    if len(tasks) != 13 or Counter(row["transition"] for row in tasks) != Counter(
        {"regressed": 6, "improved": 7}
    ):
        raise ValueError("expected 6 regressions and 7 improvements")
    if len(attempts) != 78 or any(len(grouped[name]) != 6 for name in selected_names):
        raise ValueError("expected six canonical attempts for each selected task")

    output.mkdir(parents=True)
    bundle_rows: list[dict[str, Any]] = []
    manifest_tasks = []
    report_rows = []
    for task in sorted(tasks, key=lambda row: (row["transition"], row["task_name"])):
        task_name = task["task_name"]
        category = "regressions" if task["transition"] == "regressed" else "successes"
        task_dir = output / category / task_name
        source_skill = skill_root / task_name
        if not (source_skill / "SKILL.md").is_file():
            raise FileNotFoundError(source_skill / "SKILL.md")
        shutil.copytree(source_skill, task_dir / "skill")
        summaries: dict[tuple[str, int], dict[str, Any]] = {}
        copied_rows = []
        for row in sorted(
            grouped[task_name], key=lambda value: (value["run"], int(value["attempt_index"]))
        ):
            summary, copied = copy_attempt(task_dir, row)
            summaries[(row["run"], int(row["attempt_index"]))] = summary
            copied_rows.append(copied)
            bundle_prefix = Path(category) / task_name
            root_relative = dict(copied)
            for field in (
                "bundle_trajectory",
                "bundle_result",
                "bundle_verifier",
                "bundle_source_metadata",
            ):
                if root_relative[field]:
                    root_relative[field] = str(bundle_prefix / root_relative[field])
            bundle_rows.append(
                {
                    **root_relative,
                    "case_category": category,
                    "case_study": str(Path(category) / task_name / "case_study.md"),
                    "skill_copy": str(Path(category) / task_name / "skill" / "SKILL.md"),
                }
            )
        (task_dir / "case_study.md").write_text(
            render_case_study(task, copied_rows, summaries), encoding="utf-8"
        )
        manifest_tasks.append(
            {
                "task_name": task_name,
                "transition": task["transition"],
                "bare_successes": int(task["bare_successes"]),
                "skill_successes": int(task["skill_successes"]),
                "case_study": str(Path(category) / task_name / "case_study.md"),
                "skill_source": str(source_skill),
                "skill_copy": str(Path(category) / task_name / "skill"),
                "attempts": 6,
            }
        )
        report_rows.append(
            f"| {'退化' if task['transition'] == 'regressed' else '成功'} | `{task_name}` | "
            f"{task['bare_successes']}/3 | {task['skill_successes']}/3 | "
            f"[案例]({category}/{task_name}/case_study.md) | "
            f"[Skill]({category}/{task_name}/skill/SKILL.md) |"
        )

    fieldnames = list(bundle_rows[0])
    with (output / "attempts_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(bundle_rows)
    manifest = {
        "schema_version": 1,
        "analysis_source": str(analysis),
        "skill_source": str(skill_root),
        "task_count": len(tasks),
        "regressions": 6,
        "successes": 7,
        "canonical_attempts": len(bundle_rows),
        "trajectory_files": len(bundle_rows),
        "result_files": len(bundle_rows),
        "verifier_files": sum(bool(row["bundle_verifier"]) for row in bundle_rows),
        "tasks": manifest_tasks,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(
        f"""# Tencent TB2.1 Skill 退化与成功 Case Studies

本包基于修正后的 canonical 对照数据，覆盖全部 6 个严格退化题和 7 个严格提升题。每题包含完整 Skill 目录、裸跑三次与 Skill 三次的原始 `trajectory.json`、对应 `result.json`、已有的 verifier stdout，以及一份证据导向的中文对照分析。

| 类型 | Task | 裸跑 | Skill | Case study | 对应 Skill |
|---|---|---:|---:|---|---|
{chr(10).join(report_rows)}

## 文件说明

- `attempts_manifest.csv`：78 条 canonical attempt 的原始远端路径与包内路径。
- `manifest.json`：任务清单、来源和文件计数。
- `regressions/<task>/case_study.md`：退化题对照分析。
- `successes/<task>/case_study.md`：Skill 后成功题对照分析。
- 每题的 `skill/` 是对应技能目录的完整副本，不只包含 `SKILL.md`。
- 每题的 `raw/<run>/attempt-N/trajectory.json` 是原始 trajectory 的直接副本，未做摘要或重写。

## 口径

- 退化：裸跑 pass@3=1、Skill pass@3=0。
- 成功：裸跑 pass@3=0、Skill pass@3=1。
- retry archive 不重复计入正式三次；裸跑 recheck 和 Skill transport replacement 按 canonical 映射取最终正式结果。
- `circuit-fibsqrt` 的一条裸跑裁决 0 原执行没有 verifier 文件，包内如实保留 result 和 trajectory，并在案例中标记 verifier 未产生。
""",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "tasks": len(tasks),
                "attempts": len(bundle_rows),
                "trajectory_files": len(bundle_rows),
                "verifier_files": manifest["verifier_files"],
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
