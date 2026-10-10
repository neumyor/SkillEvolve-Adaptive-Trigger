from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from fuse.evolver import (
    META_SKILL_VERSION,
    MAX_CAPABILITY_PROBES,
    MAX_REFUSED_TOOL_ACTIONS,
    MAX_SCHEMA_RETRIES,
    Attribution,
    CapabilityAssessment,
    ConfirmedLeakage,
    Diagnosis,
    DiagnosticChecks,
    EvolverReport,
    LeakageDetector,
    TargetProfile,
    ToolObservation,
    _append_schema_retry,
    _augment_capability_assessment,
    _audit,
    _budget_finalization_prompt,
    _command_denial_reason,
    _inconclusive_report,
    _initial_payload,
    _issue_code,
    _parse_action,
    _report_base,
    _required_object,
    _required_text,
    _truncate,
    _validate_checkpoint_consistency,
    build_evidence_registry,
    compute_patch_decision,
    load_meta_skill,
)
from fuse.model_client import openai_compatible_chat
from fuse.schemas import load_trajectory


class HarborEvolverAgent(BaseAgent):
    """在独立 Harbor sandbox 中只执行 v3 诊断与归因。"""

    # 返回 Harbor 注册使用的 agent 名称。
    @staticmethod
    def name() -> str:
        return "fuse-evolver"

    # 返回 Harbor agent 协议版本。
    def version(self) -> str:
        return "3.0.0"

    # 读取公开输入路径、预算和宿主泄漏清单。
    def __init__(
        self,
        *,
        logs_dir: Path,
        model_name: str,
        skill_dir: str,
        trajectory_path: str,
        trajectory_id: str,
        target_profile_path: str,
        api_base: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        max_tool_calls: int = 50,
        max_seconds: int = 1800,
        leakage_manifest_path: str | None = None,
        retry_feedback_path: str | None = None,
        attempt: int = 1,
        meta_skill_path: str | None = None,
        meta_skill_version: str = META_SKILL_VERSION,
        **kwargs: Any,
    ) -> None:
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)
        self.skill_dir = Path(skill_dir)
        self.trajectory_path = Path(trajectory_path)
        self.trajectory_id = trajectory_id
        self.target_profile_path = Path(target_profile_path)
        self.api_base = api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key_env = api_key_env
        self.max_tool_calls = int(max_tool_calls)
        self.max_seconds = int(max_seconds)
        if not 1 <= self.max_tool_calls <= 50: raise ValueError("max_tool_calls must be between 1 and 50")
        if not 1 <= self.max_seconds <= 1800: raise ValueError("max_seconds must be between 1 and 1800")
        self.retry_feedback = _read_retry_feedback(retry_feedback_path)
        self.attempt = int(attempt)
        if not 1 <= self.attempt <= 3: raise ValueError("attempt must be between 1 and 3")
        self.leakage_detector = _load_leakage_detector(leakage_manifest_path)
        self.meta_skill_path = Path(meta_skill_path).resolve() if meta_skill_path else None
        self.meta_skill_version = str(meta_skill_version)

    # 验证 `/app` 可写且敏感及日志挂载不可访问。
    async def setup(self, environment: BaseEnvironment) -> None:
        result = await environment.exec(
            "umask 077; touch /app/.fuse-write-check && rm /app/.fuse-write-check; "
            "for p in /solution /tests /logs/agent /logs/verifier /logs/artifacts; do "
            "if test -r \"$p\" || test -w \"$p\" || test -x \"$p\"; then exit 90; fi; done",
            timeout_sec=30,
        )
        if result.return_code != 0:
            raise RuntimeError("diagnostic sandbox permission self-check failed")

    # 加载公开输入并执行一次 v3 diagnosis-only 会话。
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        api_key = os.getenv(self.api_key_env)
        if not api_key: raise RuntimeError(f"trusted host is missing {self.api_key_env}")
        trajectory = load_trajectory(self.trajectory_path)
        target = TargetProfile(**json.loads(self.target_profile_path.read_text(encoding="utf-8")))
        meta_skill, meta_sha = load_meta_skill(self.meta_skill_path)
        clean_trajectory = [
            type(step).from_dict(item)
            for step, item in zip(trajectory, self.leakage_detector.sanitize_value([value.to_dict() for value in trajectory]))
        ]
        try:
            if self.leakage_detector.contains_leakage({"instruction": instruction}):
                raise ConfirmedLeakage("confirmed sensitive input")
            report, audit = await self._run_diagnosis(
                instruction, environment, api_key, clean_trajectory, target, meta_skill, meta_sha,
            )
            if self.leakage_detector.contains_leakage(report.to_dict()) or self.leakage_detector.contains_leakage(audit):
                raise ConfirmedLeakage("confirmed sensitive output")
            self._write_outputs(report, audit)
            context.metadata = {"evolver_status": report.status, "report_path": str(self.logs_dir / "evolver_report.json")}
        except ConfirmedLeakage:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            (self.logs_dir / "contamination.json").write_text(
                json.dumps({"status": "confirmed_contamination", "attempt": self.attempt}, indent=2) + "\n",
                encoding="utf-8",
            )
            raise

    # 运行 capability/causal 状态机并在锁定诊断后立即结束。
    async def _run_diagnosis(
        self,
        instruction: str,
        environment: BaseEnvironment,
        api_key: str,
        trajectory: list[Any],
        target: TargetProfile,
        meta_skill: str,
        meta_sha: str,
    ) -> tuple[EvolverReport, dict[str, Any]]:
        started = time.monotonic()
        registry = build_evidence_registry(instruction, self.skill_dir, target, trajectory)
        messages = [
            {"role": "system", "content": meta_skill},
            {"role": "user", "content": _initial_payload(
                self.trajectory_id, registry, meta_sha, self.retry_feedback, self.meta_skill_version,
            )},
        ]
        observations: list[ToolObservation] = []
        turns: list[dict[str, Any]] = []
        capability: CapabilityAssessment | None = None
        checkpoint: tuple[Diagnosis, Attribution, DiagnosticChecks] | None = None
        invalid = refused = 0
        finalization_requested = False
        while time.monotonic() - started < self.max_seconds and checkpoint is None:
            guidance = _budget_finalization_prompt(
                len(observations), self.max_tool_calls, time.monotonic() - started,
                self.max_seconds, capability is not None, finalization_requested,
            )
            if guidance:
                messages.append({"role": "user", "content": guidance})
                finalization_requested = True
            raw = self._call(api_key, messages, started)
            if self.leakage_detector.contains_leakage(raw): raise ConfirmedLeakage("diagnostic response contaminated")
            try:
                action = _parse_action(raw)
                kind = action.get("action")
                if kind == "tool":
                    phase = str(action.get("phase", ""))
                    command, purpose = _required_text(action, "command"), _required_text(action, "purpose")
                    if phase not in {"capability", "causal"}: raise ValueError("tool phase is required")
                    if phase == "causal" and capability is None: raise ValueError("capability checkpoint required before causal probe")
                    if phase == "capability" and capability is not None: raise ValueError("capability phase is locked")
                    if phase == "capability" and sum(item.phase == "capability" for item in observations) >= MAX_CAPABILITY_PROBES:
                        raise ValueError("capability probe limit reached")
                    if len(observations) >= self.max_tool_calls:
                        refused += 1
                        if refused >= MAX_REFUSED_TOOL_ACTIONS: break
                        messages.extend([{"role": "assistant", "content": raw}, {"role": "user", "content": "tool_budget_exhausted"}])
                        continue
                    observation = await self._execute_probe(environment, len(observations) + 1, phase, command, purpose)
                    observations.append(observation)
                    registry.add(observation.evidence_id, observation.to_dict(), kind="probe", phase=phase)
                    turns.append(action)
                    messages.extend([{"role": "assistant", "content": raw}, {"role": "user", "content": json.dumps({"tool_observation": observation.to_dict()}, ensure_ascii=False)}])
                    continue
                if kind == "capability_checkpoint":
                    if capability is not None: raise ValueError("capability checkpoint already locked")
                    capability = _augment_capability_assessment(
                        CapabilityAssessment.from_dict(_required_object(action, "capability_assessment"), registry),
                        target,
                        instruction,
                    )
                    turns.append(action)
                    messages.extend([{"role": "assistant", "content": raw}, {"role": "user", "content": "capability_checkpoint_accepted; causal phase is now available"}])
                    continue
                if kind == "diagnosis_checkpoint":
                    if capability is None: raise ValueError("capability checkpoint required before diagnosis checkpoint")
                    diagnosis = Diagnosis.from_dict(_required_object(action, "diagnosis"), registry)
                    attribution = Attribution.from_dict(_required_object(action, "attribution"), registry)
                    checks = DiagnosticChecks.from_dict(_required_object(action, "diagnostic_checks"), registry)
                    _validate_checkpoint_consistency(capability, diagnosis, attribution, checks)
                    checkpoint = diagnosis, attribution, checks
                    turns.append(action)
                    break
                raise ValueError("unsupported diagnostic action")
            except (TypeError, ValueError) as exc:
                invalid += 1
                issue_code = _issue_code(exc)
                turns.append(
                    {
                        "invalid_diagnostic_response": {
                            "issue_code": issue_code,
                            "raw": _truncate(raw, 4000),
                        }
                    }
                )
                if invalid >= MAX_SCHEMA_RETRIES: break
                _append_schema_retry(messages, raw, issue_code)
        if capability is None or checkpoint is None:
            report = _inconclusive_report(
                self.trajectory_id, self.attempt, target, meta_sha, capability,
                len(observations), time.monotonic() - started, invalid, self.meta_skill_version,
            )
            return report, _audit(self.attempt, "diagnosis_inconclusive", turns, observations, messages)
        diagnosis, attribution, checks = checkpoint
        decision = compute_patch_decision(capability, diagnosis, attribution, checks)
        base = _report_base(
            self.trajectory_id, self.attempt, target, meta_sha, capability, diagnosis, attribution,
            checks, decision, len(observations), time.monotonic() - started, invalid, self.meta_skill_version,
        )
        status = "inconclusive" if diagnosis.root_cause_class == "inconclusive" else "no_patch"
        issue_codes = ["diagnosis_only"] if decision.eligible else decision.reason_codes
        report = EvolverReport(
            status=status,
            evolution=None,
            proposal=None,
            integrity_gate={"passed": False, "issue_codes": issue_codes},
            **base,
        )
        return report, _audit(self.attempt, "diagnosis_locked", turns, observations, messages)

    # 在容器内执行一个 probe；策略拒绝只写审计记录。
    async def _execute_probe(
        self, environment: BaseEnvironment, number: int, phase: str, command: str, purpose: str,
    ) -> ToolObservation:
        evidence_id = f"probe:{number}"
        denied = _command_denial_reason(command)
        if denied: return ToolObservation(evidence_id, phase, command, purpose, "", f"permission denied: {denied}", 126, True)
        result = await environment.exec(command, cwd="/app", timeout_sec=120)
        observation = ToolObservation(evidence_id, phase, command, purpose, _truncate(result.stdout), _truncate(result.stderr), result.return_code)
        if self.leakage_detector.contains_leakage(observation.to_dict()): raise ConfirmedLeakage("probe contaminated")
        return observation

    # 调用宿主侧模型代理，并把超时限制在 attempt 剩余预算内。
    def _call(self, api_key: str, messages: list[dict[str, str]], started: float) -> str:
        remaining = max(1, int(self.max_seconds - (time.monotonic() - started)))
        return openai_compatible_chat(
            api_key=api_key, base_url=self.api_base, model=self.model_name or "",
            messages=messages, timeout_sec=min(300, remaining),
            response_format={"type": "json_object"},
        )

    # 写入 v3 diagnosis-only report 和不含敏感材料的审计结构。
    def _write_outputs(self, report: EvolverReport, audit: dict[str, Any]) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "evolver_report.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (self.logs_dir / "evolver_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# 从宿主清单加载敏感指纹和 canary。
def _load_leakage_detector(path_value: str | None) -> LeakageDetector:
    if not path_value: return LeakageDetector()
    value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    return LeakageDetector(fingerprints=set(value.get("fingerprints") or []), canaries=set(value.get("canaries") or []))


# 读取通用污染重试反馈，不暴露具体命中信息。
def _read_retry_feedback(path_value: str | None) -> str:
    if not path_value: return ""
    path = Path(path_value)
    if not path.is_file(): raise FileNotFoundError(path)
    value = path.read_text(encoding="utf-8").strip()
    return value
