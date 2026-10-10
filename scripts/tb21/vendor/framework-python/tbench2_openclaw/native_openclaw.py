"""FUSE 诊断和演化共用的原生 OpenClaw 运行配置。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harbor.models.agent.context import AgentContext

from .clean_openclaw import CleanOpenClaw


class FuseNativeOpenClaw(CleanOpenClaw):
    """统一 provider SecretRef、runtime、session 和 artifact 持久化。"""

    def __init__(
        self,
        *,
        logs_dir: Path,
        model_name: str,
        api_base: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        session_id: str,
        max_seconds: int,
        environment_backend: str = "docker",
        openclaw_workspace: str = "/tmp/openclaw-workspace",
        tools_allow: str = "read,exec,process,write,edit,apply_patch",
        **kwargs: Any,
    ) -> None:
        requested_model = str(model_name)
        openclaw_model = requested_model if "/" in requested_model else f"custom/{requested_model}"
        super().__init__(
            logs_dir=logs_dir,
            model_name=openclaw_model,
            agent_timeout_sec=max_seconds,
            **kwargs,
        )
        self.requested_model = requested_model
        self.api_base = api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key_env = str(api_key_env)
        self.session_id = str(session_id)
        self.max_seconds = int(max_seconds)
        self.environment_backend = str(environment_backend).strip().lower()
        self.openclaw_workspace = str(openclaw_workspace)
        self.tools_allow = str(tools_allow)
        if self.environment_backend not in {"docker", "e2b"}:
            raise ValueError("environment_backend must be docker or e2b")
        if not 1 <= self.max_seconds <= 1800:
            raise ValueError("max_seconds must be between 1 and 1800")
        self.EMPTY_SKILLS_DIR = "/tmp/openclaw-empty-skills"

    async def setup(self, environment: Any) -> None:
        result = await environment.exec(
            f"mkdir -p {self.openclaw_workspace} {self.EMPTY_SKILLS_DIR}",
            timeout_sec=30,
        )
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout or "failed to prepare OpenClaw workspace")
        await super().setup(environment)

    async def run(self, instruction: str, environment: Any, context: AgentContext) -> None:
        await super().run(instruction, environment, context)
        await self.persist_native_session(environment)

    def create_run_agent_commands(self, instruction: str):
        """构造仅在 OpenClaw 进程环境中携带上游凭据的命令。

        Args:
            instruction: 作为首条 user query 交给原生 OpenClaw 的任务导航。
        """
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"trusted host is missing {self.api_key_env}")
        state_dir = (
            "/tmp/openclaw-state"
            if self.environment_backend == "e2b"
            else "/logs/agent/openclaw-state"
        )
        path = (
            "/mnt/cfs/agent-tools/bin:/usr/local/bin:/usr/bin:/bin"
            if self.environment_backend == "e2b"
            else "/opt/openclaw-runtime/bin:/usr/local/bin:/usr/bin:/bin"
        )
        values = {
            "HOME": "/tmp/openclaw-home",
            "PATH": path,
            "CUSTOM_BASE_URL": self.api_base,
            "CUSTOM_API": "openai-completions",
            "CUSTOM_CONTEXT_WINDOW": "256000",
            "CUSTOM_MAX_TOKENS": "65536",
            "CUSTOM_REASONING": "true",
            "UPSTREAM_API_KEY": api_key,
            "OPENCLAW_STATE_DIR": state_dir,
            "OPENCLAW_CONFIG_PATH": f"{state_dir}/openclaw.json",
            "OPENCLAW_SESSION_ID": self.session_id,
            "OPENCLAW_WORKSPACE_DIR": self.openclaw_workspace,
            "OPENCLAW_BUNDLED_SKILLS_DIR": os.getenv(
                "OPENCLAW_BUNDLED_SKILLS_DIR", self.EMPTY_SKILLS_DIR
            ),
            "OPENCLAW_REQUIRE_SKILL_USE": "1"
            if os.getenv("OPENCLAW_BUNDLED_SKILLS_SRC_DIR", "").strip()
            else "0",
            "OPENCLAW_TOOLS_ALLOW": self.tools_allow,
            "OPENCLAW_TOOLS_DENY": (
                "group:web,group:memory,group:sessions,group:ui,group:automation,"
                "group:messaging,group:nodes,agents_list,subagents"
            ),
        }
        if self.environment_backend == "e2b":
            # The shared CFS OpenClaw 2026.7.1-2 runtime is validated through
            # its native --local entrypoint; its standalone gateway cold start
            # does not expose /ready reliably in the Tencent AGS image.
            values["OPENCLAW_USE_LOCAL"] = "true"
            values["OPENCLAW_TOOLS_ALSO_ALLOW"] = self.tools_allow
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
        for command in commands:
            command.command = command.command.replace(
                "~/.openclaw/openclaw.json",
                f"{state_dir}/openclaw.json",
            )
            if self.environment_backend == "e2b":
                command.command = command.command.replace(
                    "/logs/agent/openclaw-state",
                    state_dir,
                ).replace(
                    "/logs/agent/openclaw.txt",
                    f"{state_dir}/openclaw.txt",
                ).replace(
                    "/logs/agent",
                    state_dir,
                )
            env = dict(command.env or {})
            env.update(values)
            command.env = env
        return commands

    async def persist_native_session(self, environment: Any) -> Path | None:
        """在 sandbox 删除前把 E2B session 和协议结果原样导出到 trial。

        Args:
            environment: 当前 Harbor environment。

        Returns:
            宿主可见的原生 session JSONL；未找到时为 ``None``。
        """
        if self.environment_backend == "e2b":
            exporter = getattr(environment, "export_directory", None)
            if exporter is None:
                raise RuntimeError("E2B OpenClaw environment cannot export native artifacts")
            await exporter("/tmp/openclaw-state", self.logs_dir / "openclaw-state")
            # OpenClaw may successfully submit the protocol result and then fail
            # while producing its final assistant turn (for example, provider
            # rate limiting). Export the fresh result directory independently of
            # the command exit code so the host can still validate that result.
            await exporter(
                f"{self.openclaw_workspace}/result",
                self.logs_dir / "openclaw-result",
            )
        preferred = sorted(self.logs_dir.rglob(f"{self.session_id}.jsonl"))
        if preferred:
            return preferred[-1]
        fallback = sorted(self.logs_dir.rglob("*.jsonl"))
        return fallback[-1] if fallback else None
