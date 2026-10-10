"""OpenClaw-native evolution adapter used for harness A/B experiments."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harbor.models.agent.context import AgentContext

from fuse.evolver import EVOLUTION_META_SKILL_VERSION, load_evolution_meta_skill

from .clean_openclaw import CleanOpenClaw


class OpenClawEvolutionAgent(CleanOpenClaw):
    """Run agentic evolution through OpenClaw's native tool loop.

    The host remains responsible for calculating the candidate diff and for
    creating the EvolutionSubmission. OpenClaw only edits the mounted
    candidate workspace and leaves an execution transcript for auditing.
    """

    @staticmethod
    def name() -> str:
        return "fuse-openclaw-agentic-evolver"

    def version(self) -> str:
        return "3.1.0-openclaw-ab"

    def __init__(
        self,
        *,
        logs_dir: Path,
        model_name: str,
        diagnostic_report_path: str,
        api_base: str | None = None,
        meta_skill_path: str | None = None,
        meta_skill_version: str = EVOLUTION_META_SKILL_VERSION,
        max_tool_calls: int = 100,
        max_seconds: int = 1800,
        **kwargs: Any,
    ) -> None:
        # OpenClaw needs an explicit provider prefix to register the ModelBest
        # compatible endpoint; the experiment still records the requested
        # DeepSeek model name unchanged in the Harbor command/audit.
        openclaw_model = model_name if "/" in model_name else f"custom/{model_name}"
        super().__init__(logs_dir=logs_dir, model_name=openclaw_model, **kwargs)
        self.requested_model = model_name
        self.api_base = api_base or os.getenv("CUSTOM_BASE_URL", "https://api.openai.com/v1")
        self.diagnostic_report_path = Path(diagnostic_report_path).resolve()
        self.meta_skill_path = Path(meta_skill_path).resolve() if meta_skill_path else None
        self.meta_skill_version = str(meta_skill_version)
        self.max_tool_calls = int(max_tool_calls)
        self.max_seconds = int(max_seconds)
        if not 1 <= self.max_tool_calls <= 100:
            raise ValueError("max_tool_calls must be between 1 and 100")
        if not 1 <= self.max_seconds <= 1800:
            raise ValueError("max_seconds must be between 1 and 1800")

    async def setup(self, environment) -> None:
        # The immutable runtime is already mounted. Avoid the installed-agent
        # upload path because this sandbox intentionally has a read-only root.
        result = await environment.exec(
            "set -eu; "
            "test -x /opt/openclaw-runtime/bin/openclaw; "
            "test -x /opt/openclaw-runtime/bin/node; "
            "test -r /workspace/parent/SKILL.md; "
            "test -r /workspace/evidence/current_trajectory.jsonl; "
            "test -w /workspace/candidate; "
            "touch /workspace/candidate/.fuse-openclaw-write-check; "
            "rm /workspace/candidate/.fuse-openclaw-write-check; "
            "test ! -r /solution && test ! -r /tests && "
            "test ! -r /logs/verifier && test ! -r /logs/artifacts; "
            "rm -rf /tmp/openclaw-workspace; "
            "mkdir -p /tmp/openclaw-workspace/skill; "
            "cp -a /workspace/candidate/. /tmp/openclaw-workspace/skill/",
            timeout_sec=30,
        )
        if result.return_code != 0:
            raise RuntimeError("OpenClaw evolution sandbox permission self-check failed")

    async def run(self, instruction: str, environment, context: AgentContext) -> None:
        if not self.diagnostic_report_path.is_file():
            raise FileNotFoundError(self.diagnostic_report_path)
        report = json.loads(self.diagnostic_report_path.read_text(encoding="utf-8"))
        if str(report.get("schema_version")) != "3":
            raise ValueError("OpenClaw evolution requires an EvolverReport v3 diagnosis")
        if self.meta_skill_version != EVOLUTION_META_SKILL_VERSION:
            raise ValueError("unsupported evolution meta-skill version")
        meta_skill, meta_sha = load_evolution_meta_skill(self.meta_skill_path)
        prompt = _build_openclaw_prompt(
            instruction=instruction,
            diagnostic_report=report,
            meta_skill=meta_skill,
            meta_sha=meta_sha,
            max_tool_calls=self.max_tool_calls,
            max_seconds=self.max_seconds,
        )
        try:
            await super().run(prompt, environment, context)
        except Exception as exc:
            await self._sync_candidate_from_workspace(environment)
            self._write_marker({"status": "failed", "error": str(exc), "meta_skill": {"version": self.meta_skill_version, "sha256": meta_sha}})
            raise
        await self._sync_candidate_from_workspace(environment)
        self._write_marker({
            "status": "completed",
            "meta_skill": {"version": self.meta_skill_version, "sha256": meta_sha},
            "workspace": "/tmp/openclaw-workspace",
            "native_tools": ["read", "exec", "write", "edit", "apply_patch"],
            "budget": {"max_tool_calls": self.max_tool_calls, "max_seconds": self.max_seconds},
        })
        context.metadata = {"evolution_harness": "openclaw", "evolution_status": "completed"}

    def create_run_agent_commands(self, instruction: str):
        # CleanOpenClaw reads these values while constructing both the config
        # patch and command cwd. Restore the host environment immediately so
        # concurrent Harbor jobs cannot inherit the experiment settings.
        values = {
            "HOME": "/tmp/openclaw-home",
            "PATH": "/opt/openclaw-runtime/bin:/usr/local/bin:/usr/bin:/bin",
            "CUSTOM_BASE_URL": self.api_base,
            "CUSTOM_API": "openai-completions",
            "CUSTOM_CONTEXT_WINDOW": "256000",
            "CUSTOM_MAX_TOKENS": "65536",
            "CUSTOM_REASONING": "false",
            "OPENCLAW_WORKSPACE_DIR": "/tmp/openclaw-workspace",
            "OPENCLAW_BUNDLED_SKILLS_DIR": self.EMPTY_SKILLS_DIR,
            "OPENCLAW_REQUIRE_SKILL_USE": "0",
            "OPENCLAW_TOOLS_ALLOW": "read,exec,process,write,edit,apply_patch,session_status",
            "OPENCLAW_TOOLS_DENY": (
                "group:web,group:memory,group:sessions,group:ui,group:automation,"
                "group:messaging,group:nodes,agents_list,subagents"
            ),
        }
        previous = {key: os.environ.get(key) for key in values}
        try:
            os.environ.update(values)
            commands = super().create_run_agent_commands(instruction)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        if len(commands) > 1 and "openclaw agent \\\n" in commands[1].command:
            commands[1].command = commands[1].command.replace(
                "openclaw agent \\\n",
                f"openclaw agent \\\n  --timeout {self.max_seconds} \\\n",
                1,
            )
        for command in commands:
            env = dict(command.env or {})
            env.update(values)
            command.env = env
            command.cwd = "/tmp/openclaw-workspace"
        return commands

    async def _sync_candidate_from_workspace(self, environment) -> None:
        result = await environment.exec(
            "set -eu; "
            "test -f /tmp/openclaw-workspace/skill/SKILL.md; "
            "if find -P /tmp/openclaw-workspace/skill -type l -o "
            "-type b -o -type c -o -type p -o -type s | grep -q .; then exit 91; fi; "
            "find /workspace/candidate -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; "
            "find /tmp/openclaw-workspace/skill -mindepth 1 -maxdepth 1 "
            "-exec cp -a -- {} /workspace/candidate/ \\;",
            cwd="/tmp/openclaw-workspace",
            timeout_sec=30,
        )
        if result.return_code != 0:
            detail = " ".join(
                part.strip() for part in (result.stdout or "", result.stderr or "") if part and part.strip()
            )
            raise RuntimeError(
                "OpenClaw candidate workspace sync failed"
                + (f": {detail[-1200:]}" if detail else "")
            )

    def _write_marker(self, value: dict[str, Any]) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "openclaw_evolution_marker.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _build_openclaw_prompt(
    *,
    instruction: str,
    diagnostic_report: dict[str, Any],
    meta_skill: str,
    meta_sha: str,
    max_tool_calls: int,
    max_seconds: int,
) -> str:
    locked = {
        key: diagnostic_report.get(key)
        for key in (
            "trajectory_id",
            "target_profile",
            "capability_assessment",
            "diagnosis",
            "attribution",
            "diagnostic_checks",
            "patch_decision",
        )
    }
    return f"""{meta_skill}

You are running the OpenClaw-native A/B evolution harness. This is a fresh
evolution session, not a new diagnosis. The host has locked the diagnosis
below; do not revise its root cause or attribution.

Public task instruction:
{instruction}

Locked diagnosis (host-issued, read-only):
{json.dumps(locked, ensure_ascii=False, indent=2)}

Meta-skill identity: version={EVOLUTION_META_SKILL_VERSION}, sha256={meta_sha}

Workspace protocol:
- Read and edit the complete skill copy at /tmp/openclaw-workspace/skill/SKILL.md.
- The host synchronizes only /tmp/openclaw-workspace/skill back to the real
  candidate after the session; do not edit /workspace/candidate directly.
- /workspace/parent is the immutable parent copy for comparison.
- Read /workspace/evidence/current_trajectory.jsonl and, if present,
  /workspace/evidence/history_index.json plus the listed history files.
- You may use the public task environment under /app for bounded probes.
- Edit only /tmp/openclaw-workspace/skill. Do not modify parent or evidence.
- Never access /solution, /tests, /logs/verifier, /logs/artifacts, host files,
  other containers, reward, result, oracle, or ground truth.

Work agentically: inspect the skill, examine the public evidence, run a small
diagnostic probe when useful, and make the smallest general skill edit that is
supported by the locked diagnosis. Preserve all public contracts. If no safe
general edit is justified, leave candidate unchanged. Before finishing,
inspect the actual diff and provide a concise final summary with either
candidate or no_changes. The host will compute the authoritative action from
the real filesystem diff; do not claim a candidate without writing files.

Important convergence rules for this native session:
- The deliverable is /tmp/openclaw-workspace/skill/SKILL.md and its complete
  supporting files. A file written under /app is only a temporary public probe;
  it is not an evolution result and must not be treated as the candidate.
- Once the locked diagnosis and a public probe support a general correction,
  edit the skill workspace immediately, then run validation against that edited
  workspace. Do not spend the remaining turns repeatedly redesigning the probe.
- Public containers may mount /app with noexec. Put compiled test binaries in
  /tmp (for example /tmp/skill-probe-bin) and execute them there. Treat a
  compiler exit code without an executable runtime check as incomplete.
- Before stopping, run a bounded diff against /workspace/parent and make the
  final text explicit in this exact form:
  EVOLUTION_ACTION: candidate|no_changes
  CHANGED_PATHS: comma-separated relative paths or empty
  SELF_CHECKS: concise list of checks actually run

Native tool budget: at most {max_tool_calls} tool calls and {max_seconds} seconds.
At the budget boundary, stop probing, inspect the diff, and finish.
"""
