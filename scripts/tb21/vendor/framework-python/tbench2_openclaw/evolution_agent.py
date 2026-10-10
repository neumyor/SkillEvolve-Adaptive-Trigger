from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import time
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from fuse.evolver import (
    BUDGET_FINALIZATION_SECONDS,
    EVOLUTION_META_SKILL_VERSION,
    MAX_REFUSED_TOOL_ACTIONS,
    MAX_SCHEMA_RETRIES,
    ConfirmedLeakage,
    EvolutionSubmission,
    EvolverReport,
    LeakageDetector,
    ToolObservation,
    _append_schema_retry,
    _command_denial_reason,
    _issue_code,
    _parse_action,
    _required_object,
    _required_text,
    _truncate,
    build_evolution_session_messages,
    compact_model_messages,
    load_evolution_meta_skill,
)
from fuse.model_client import openai_compatible_chat

from .evolver_agent import _load_leakage_detector


class HarborEvolutionAgent(BaseAgent):
    """在独立可写 skill workspace 中运行 agentic evolution。"""

    # 返回 Harbor 注册使用的 agent 名称。
    @staticmethod
    def name() -> str:
        return "fuse-agentic-evolver"

    # 返回独立演化 Agent 的协议版本。
    def version(self) -> str:
        return "3.0.0"

    # 读取锁定诊断、预算和宿主泄漏清单。
    def __init__(
        self,
        *,
        logs_dir: Path,
        model_name: str,
        diagnostic_report_path: str,
        api_base: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        max_tool_calls: int = 100,
        max_seconds: int = 1800,
        leakage_manifest_path: str | None = None,
        meta_skill_path: str | None = None,
        meta_skill_version: str = EVOLUTION_META_SKILL_VERSION,
        attempt: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)
        self.diagnostic_report_path = Path(diagnostic_report_path)
        self.api_base = api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key_env = api_key_env
        self.max_tool_calls = int(max_tool_calls)
        self.max_seconds = int(max_seconds)
        if not 1 <= self.max_tool_calls <= 100: raise ValueError("max_tool_calls must be between 1 and 100")
        if not 1 <= self.max_seconds <= 1800: raise ValueError("max_seconds must be between 1 and 1800")
        self.leakage_detector = _load_leakage_detector(leakage_manifest_path)
        self.meta_skill_path = Path(meta_skill_path).resolve() if meta_skill_path else None
        self.meta_skill_version = str(meta_skill_version)
        self.attempt = int(attempt)

    # 验证 parent/evidence 只读、candidate 可写，且敏感目录仍不可访问。
    async def setup(self, environment: BaseEnvironment) -> None:
        result = await environment.exec(
            "set -eu; test -r /workspace/parent/SKILL.md; test -r /workspace/evidence/current_trajectory.jsonl; "
            "test -r /workspace/candidate/SKILL.md; "
            "test ! -w /workspace/parent/SKILL.md; test ! -w /workspace/evidence/current_trajectory.jsonl; "
            "touch /workspace/candidate/.fuse-write-check; rm /workspace/candidate/.fuse-write-check; "
            "for p in /solution /tests /logs/agent /logs/verifier /logs/artifacts; do "
            "if test -r \"$p\" || test -w \"$p\" || test -x \"$p\"; then exit 90; fi; done",
            timeout_sec=30,
        )
        if result.return_code != 0:
            raise RuntimeError("evolution sandbox permission self-check failed")

    # 运行全新 agentic session，并只保存提交元数据和工具审计。
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        api_key = os.getenv(self.api_key_env)
        if not api_key: raise RuntimeError(f"trusted host is missing {self.api_key_env}")
        diagnostic_value = json.loads(self.diagnostic_report_path.read_text(encoding="utf-8"))
        if str(diagnostic_value.get("schema_version")) != "3":
            raise ValueError("evolution requires EvolverReport v3 diagnosis")
        diagnostic_report = _trusted_diagnostic_report(diagnostic_value)
        meta_skill, meta_sha = load_evolution_meta_skill(self.meta_skill_path)
        if self.meta_skill_version != EVOLUTION_META_SKILL_VERSION:
            raise ValueError("unsupported evolution meta-skill version")
        messages = build_evolution_session_messages(
            diagnostic_report=diagnostic_report,
            public_instruction=instruction,
            meta_skill=meta_skill,
            meta_sha=meta_sha,
        )
        started = time.monotonic()
        tool_calls = invalid = refused = 0
        turns: list[dict[str, Any]] = []
        finalization_requested = False
        write_reminder_sent = False
        candidate_rejections = 0
        initial_fingerprint = await self._candidate_fingerprint(environment)
        candidate_changed = False
        try:
            while time.monotonic() - started < self.max_seconds:
                if (
                    not write_reminder_sent
                    and not candidate_changed
                    and tool_calls >= min(40, max(1, self.max_tool_calls - 1))
                ):
                    messages.append({
                        "role": "user",
                        "content": (
                            "The candidate workspace is still byte-identical to parent after 40 tool calls. "
                            "Use a shell command now to edit /workspace/candidate, then inspect the real diff. "
                            "Do not submit candidate based only on a proposed change; submit no_changes only if "
                            "you have decided no safe general edit is justified."
                        ),
                    })
                    write_reminder_sent = True
                if not finalization_requested and (
                    tool_calls >= max(1, self.max_tool_calls - 2)
                    or self.max_seconds - (time.monotonic() - started) <= BUDGET_FINALIZATION_SECONDS
                ):
                    prompt = (
                        "The candidate workspace is still unchanged. Use one tool call to write the supported "
                        "skill edit and verify the diff before submitting. If no safe general edit is justified, "
                        "submit no_changes."
                        if not candidate_changed
                        else "Submit candidate or no_changes now; stop using tools."
                    )
                    messages.append({"role": "user", "content": prompt})
                    finalization_requested = True
                raw = self._call(api_key, compact_model_messages(messages), started)
                if self.leakage_detector.contains_leakage(raw): raise ConfirmedLeakage("evolution response contaminated")
                try:
                    action = _parse_action(raw)
                    if action.get("action") == "tool":
                        if tool_calls >= self.max_tool_calls:
                            refused += 1
                            if refused >= MAX_REFUSED_TOOL_ACTIONS: break
                            messages.extend([{"role": "assistant", "content": raw}, {"role": "user", "content": "tool_budget_exhausted"}])
                            continue
                        command, purpose = _required_text(action, "command"), _required_text(action, "purpose")
                        observation = await self._execute_tool(environment, tool_calls + 1, command, purpose)
                        tool_calls += 1
                        candidate_changed = (await self._candidate_fingerprint(environment)) != initial_fingerprint
                        turns.append({"action": action, "observation": observation.to_dict()})
                        messages.extend([{"role": "assistant", "content": raw}, {"role": "user", "content": json.dumps({"tool_observation": observation.to_dict()}, ensure_ascii=False)}])
                        continue
                    if action.get("action") == "submit":
                        value = dict(_required_object(action, "evolution"))
                        value["meta_skill"] = {"version": self.meta_skill_version, "sha256": meta_sha}
                        submission = EvolutionSubmission.from_dict(value, meta_skill_sha256=meta_sha)
                        candidate_changed = (await self._candidate_fingerprint(environment)) != initial_fingerprint
                        if submission.action == "candidate" and not candidate_changed:
                            candidate_rejections += 1
                            turns.append({"invalid_evolution_response": {"issue_code": "candidate_not_written"}})
                            if candidate_rejections >= MAX_SCHEMA_RETRIES:
                                break
                            messages.extend([
                                {"role": "assistant", "content": raw},
                                {
                                    "role": "user",
                                    "content": (
                                        "candidate_not_written: the candidate workspace is unchanged. "
                                        "Edit /workspace/candidate with a shell command, run a real diff, "
                                        "then submit candidate with relative changed paths."
                                    ),
                                },
                            ])
                            continue
                        turns.append({"submission": asdict(submission)})
                        self._write_outputs(submission, turns, messages, tool_calls, invalid, started, candidate_changed)
                        context.metadata = {"evolution_action": submission.action}
                        return
                    raise ValueError("evolution action must be tool or submit")
                except (TypeError, ValueError) as exc:
                    invalid += 1
                    issue = _issue_code(exc)
                    turns.append({"invalid_evolution_response": {"issue_code": issue, "raw": _truncate(raw, 4000)}})
                    if invalid >= MAX_SCHEMA_RETRIES: break
                    _append_schema_retry(messages, raw, issue)
            self._write_incomplete(turns, messages, tool_calls, invalid, started, candidate_changed)
            context.metadata = {"evolution_action": "incomplete"}
        except ConfirmedLeakage:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            (self.logs_dir / "contamination.json").write_text(
                json.dumps({"status": "confirmed_contamination", "attempt": self.attempt}, indent=2) + "\n",
                encoding="utf-8",
            )
            raise

    # 在 evolution sandbox 中执行受限命令；权限拒绝仅形成普通 observation。
    async def _execute_tool(
        self, environment: BaseEnvironment, number: int, command: str, purpose: str,
    ) -> ToolObservation:
        denied = _command_denial_reason(command)
        if denied:
            return ToolObservation(f"evolution-probe:{number}", "evolution", command, purpose, "", f"permission denied: {denied}", 126, True)
        result = await environment.exec(command, cwd="/workspace/candidate", timeout_sec=120)
        observation = ToolObservation(
            f"evolution-probe:{number}", "evolution", command, purpose,
            _truncate(result.stdout), _truncate(result.stderr), result.return_code,
        )
        if self.leakage_detector.contains_leakage(observation.to_dict()):
            raise ConfirmedLeakage("evolution tool output contaminated")
        return observation

    # 在隔离容器内部计算 candidate 指纹；宿主进程本身看不到 /workspace 挂载点。
    async def _candidate_fingerprint(self, environment: BaseEnvironment) -> str:
        result = await environment.exec(
            "set -eu; find -P /workspace/candidate -type f -exec sha256sum '{}' + | LC_ALL=C sort | sha256sum",
            cwd="/workspace/candidate",
            timeout_sec=30,
        )
        if result.return_code != 0:
            return f"error:{result.return_code}:{result.stderr[:200]}"
        return result.stdout.strip()

    # 调用宿主侧模型代理，并只使用本演化会话的独立时间预算。
    def _call(self, api_key: str, messages: list[dict[str, str]], started: float) -> str:
        remaining = max(1, int(self.max_seconds - (time.monotonic() - started)))
        return openai_compatible_chat(
            api_key=api_key,
            base_url=self.api_base,
            model=self.model_name or "",
            messages=messages,
            timeout_sec=min(300, remaining),
            response_format={"type": "json_object"},
        )

    # 持久化合法提交和不包含正式验证信息的演化审计。
    def _write_outputs(
        self,
        submission: EvolutionSubmission,
        turns: list[dict[str, Any]],
        messages: list[dict[str, str]],
        tool_calls: int,
        invalid: int,
        started: float,
        candidate_changed: bool = False,
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "evolution_submission.json").write_text(
            json.dumps(asdict(submission), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        audit = {
            "status": "submitted",
            "turns": turns,
            "message_count": len(messages),
            "fresh_context": True,
            "tools": ["shell"],
            "budget": {
                "tool_calls": tool_calls,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "invalid_responses": invalid,
                "candidate_workspace_changed": candidate_changed,
            },
        }
        (self.logs_dir / "evolution_audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )

    # 在预算或 schema 重试耗尽时保存不可晋升的结果。
    def _write_incomplete(
        self,
        turns: list[dict[str, Any]],
        messages: list[dict[str, str]],
        tool_calls: int,
        invalid: int,
        started: float,
        candidate_changed: bool = False,
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        value = {
            "status": "incomplete",
            "turns": turns,
            "message_count": len(messages),
            "fresh_context": True,
            "budget": {
                "tool_calls": tool_calls,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "invalid_responses": invalid,
                "candidate_workspace_changed": candidate_changed,
            },
        }
        (self.logs_dir / "evolution_audit.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )


# 将宿主已验证的诊断字典恢复为只读 dataclass；不在演化阶段重新判定语义。
def _trusted_diagnostic_report(value: dict[str, Any]) -> EvolverReport:
    from fuse.evolver import (
        Attribution,
        CapabilityAssessment,
        CapabilityAssumption,
        Diagnosis,
        DiagnosticChecks,
        EvidenceClaim,
        PatchDecision,
    )

    capability = value["capability_assessment"]
    diagnosis = value["diagnosis"]
    attribution = value["attribution"]
    return EvolverReport(
        schema_version="3",
        status=str(value["status"]),
        trajectory_id=str(value["trajectory_id"]),
        attempt=int(value["attempt"]),
        meta_skill=dict(value["meta_skill"]),
        target_profile=dict(value["target_profile"]),
        capability_assessment=CapabilityAssessment(
            str(capability["overall_fit"]),
            [CapabilityAssumption(**item) for item in capability.get("assumptions", [])],
            str(capability["summary"]),
        ),
        diagnosis=Diagnosis(
            str(diagnosis["root_cause_class"]), str(diagnosis["summary"]),
            list(diagnosis.get("hypotheses", [])),
            [EvidenceClaim(**item) for item in diagnosis.get("evidence", [])],
            [EvidenceClaim(**item) for item in diagnosis.get("counterevidence", [])],
            float(diagnosis.get("confidence", 0)),
        ),
        attribution=Attribution(
            str(attribution["primary_module"]), list(attribution.get("secondary_modules", [])),
            list(attribution.get("evidence_refs", [])), str(attribution["rationale"]),
        ),
        diagnostic_checks=DiagnosticChecks(**value["diagnostic_checks"]),
        patch_decision=PatchDecision(**value["patch_decision"]),
        evolution=None,
        proposal=None,
        integrity_gate=dict(value.get("integrity_gate") or {}),
        budget_usage=dict(value.get("budget_usage") or {}),
    )
