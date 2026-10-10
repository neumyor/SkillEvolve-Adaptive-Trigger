from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import ClassVar

from harbor.agents.installed.openclaw import OpenClaw
from harbor.agents.installed.base import ExecInput


class CleanOpenClaw(OpenClaw):
    """OpenClaw adapter with clean-skill and secret-handling guardrails.

    The base implementation comes from Mosi-AI/claw-harbor. This subclass keeps
    its provider/model setup, injects the upstream credential only into the
    OpenClaw process, and forces OpenClaw to use an empty bundled-skills dir.
    """

    EMPTY_SKILLS_DIR: ClassVar[str] = "/logs/agent/empty-skills"
    HOST_ENV_PASSTHROUGH: ClassVar[tuple[str, ...]] = (
        "CUSTOM_BASE_URL",
        "CUSTOM_CONTEXT_WINDOW",
        "CUSTOM_MAX_TOKENS",
        "CUSTOM_REASONING",
        "CUSTOM_API",
        "UPSTREAM_API_KEY",
        "OPENCLAW_STATE_DIR",
        "OPENCLAW_CONFIG_PATH",
        "OPENCLAW_SESSION_ID",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    )
    SECRET_CONFIG_ENV_KEYS: ClassVar[tuple[str, ...]] = (
        "OPENAI_API_KEY",
        "MODEL_BEST_API_KEY",
        "MY_PROXY_API_KEY",
        "OPENROUTER_API_KEY",
    )
    CURL_READY_CHECK: ClassVar[str] = (
        'curl -sf "${GATEWAY_URL}/ready" 2>/dev/null | grep -q \'"ready":true\''
    )
    CURL_READY_CHECK_NO_REDIRECT: ClassVar[str] = (
        'curl -sf "${GATEWAY_URL}/ready" | grep -q \'"ready":true\''
    )
    OUTPUT_GUARDRAIL: ClassVar[str] = """OpenClaw benchmark runtime guardrails:
- Keep every shell/tool observation compact. Do not print entire large files, binary files, dependency trees, package caches, logs, model weights, or generated artifacts.
- Before inspecting unknown-size content, check size or line count first. Prefer `rg`, `find ... | head`, `sed -n`, `head`, `tail`, and small Python snippets that print summaries.
- If command output might exceed about 200 lines or 20,000 characters, redirect it to a file and print only a concise summary plus the exact path.
- Never use unbounded recursive dumps such as `cat **/*`, `find /` without pruning, `ls -R` on large trees, or package-manager verbose output unless it is redirected and summarized.
"""
    DEFAULT_SKILL_USE_SUFFIX: ClassVar[str] = """Before acting on the task, you must inspect the available task-specific skill and use it as the execution protocol. Do not proceed directly from the task query without consulting the skill. Follow its applicable procedure and validators; adapt only when public environment evidence shows a conflict."""
    NODE_READY_FUNC: ClassVar[str] = """gateway_ready() {
  node - "$GATEWAY_URL/ready" <<'NODE'
const http = require("http");
const url = process.argv[2];
const req = http.get(url, { timeout: 1000 }, (res) => {
  let body = "";
  res.setEncoding("utf8");
  res.on("data", (chunk) => { body += chunk; });
  res.on("end", () => {
    process.exit(res.statusCode === 200 && body.includes('"ready":true') ? 0 : 1);
  });
});
req.on("timeout", () => {
  req.destroy();
  process.exit(1);
});
req.on("error", () => process.exit(1));
NODE
}
"""
    TOOLS_MERGE_NODE_SCRIPT: ClassVar[str] = (
        "const fs=require('fs');"
        "const cfg=process.argv[1];"
        "const patch=JSON.parse(process.env._HARBOR_TOOLS_PATCH);"
        "const base=fs.existsSync(cfg)?JSON.parse(fs.readFileSync(cfg,'utf8')):{};"
        "if(!base.tools)base.tools={};"
        "const tools=patch.tools||{};"
        "for(const[k,v]of Object.entries(tools)){"
        "if(k==='exec'&&v&&typeof v==='object'&&!Array.isArray(v)){"
        "base.tools.exec=Object.assign({},base.tools.exec||{},v);"
        "}else{base.tools[k]=v;}}"
        "if(patch.skills){"
        "if(!base.skills)base.skills={};"
        "if(patch.skills.load){"
        "base.skills.load=Object.assign({},base.skills.load||{},patch.skills.load);"
        "}}"
        "fs.writeFileSync(cfg,JSON.stringify(base,null,2));"
    )

    @staticmethod
    def name() -> str:
        return "openclaw"

    @property
    def _install_agent_template_path(self) -> Path:
        return Path(__file__).with_name("install-clean-openclaw.sh.j2")

    @staticmethod
    def _csv_env(name: str, default: str) -> list[str]:
        raw = os.environ.get(name, default)
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _build_tools_config(self) -> dict:
        tools: dict = {}
        tools["profile"] = os.environ.get("OPENCLAW_TOOLS_PROFILE", "minimal")
        allow = self._csv_env(
            "OPENCLAW_TOOLS_ALLOW",
            "exec,process,write,edit,apply_patch,session_status",
        )
        also_allow = self._csv_env("OPENCLAW_TOOLS_ALSO_ALLOW", "")
        if also_allow:
            tools["alsoAllow"] = also_allow
        else:
            tools["allow"] = allow
        tools["deny"] = self._csv_env(
            "OPENCLAW_TOOLS_DENY",
            (
                "read,group:web,group:memory,group:sessions,group:ui,"
                "group:automation,group:messaging,group:nodes,agents_list,subagents"
            ),
        )
        tools["exec"] = {
            **dict(tools.get("exec") or {}),
            "notifyOnExit": False,
            "notifyOnExitEmptySuccess": False,
        }
        return tools

    def _build_full_config_patch(self) -> dict:
        patch = super()._build_full_config_patch()
        workspace_dir = os.environ.get("OPENCLAW_WORKSPACE_DIR", "/app")
        patch.setdefault("agents", {}).setdefault("defaults", {})[
            "workspace"
        ] = workspace_dir
        env_patch = patch.setdefault("env", {})
        for secret_key in self.SECRET_CONFIG_ENV_KEYS:
            env_patch.pop(secret_key, None)
        providers = patch.setdefault("models", {}).setdefault("providers", {})
        custom_provider = providers.get("custom")
        if isinstance(custom_provider, dict):
            custom_provider["apiKey"] = {
                "source": "env",
                "provider": "default",
                "id": "UPSTREAM_API_KEY",
            }
        skills_dir = os.environ.get("OPENCLAW_BUNDLED_SKILLS_DIR", "").strip()
        if skills_dir and skills_dir != self.EMPTY_SKILLS_DIR:
            patch.setdefault("skills", {}).setdefault("load", {})[
                "extraDirs"
            ] = [skills_dir]
        patch["tools"] = self._build_tools_config()
        return patch

    def _build_tools_patch_command(self) -> str:
        config_patch = {"tools": self._build_tools_config()}
        skills_dir = os.environ.get("OPENCLAW_BUNDLED_SKILLS_DIR", "").strip()
        if skills_dir and skills_dir != self.EMPTY_SKILLS_DIR:
            config_patch["skills"] = {"load": {"extraDirs": [skills_dir]}}
        escaped_patch = shlex.quote(json.dumps(config_patch))
        escaped_script = shlex.quote(self.TOOLS_MERGE_NODE_SCRIPT)
        return (
            f"_HARBOR_TOOLS_PATCH={escaped_patch} "
            f"node -e {escaped_script} ~/.openclaw/openclaw.json"
        )

    async def setup(self, environment) -> None:
        # E2B uses the read-only shared CFS runtime activated by its environment.
        # Do not upload or install a second local OpenClaw bundle there.
        if getattr(environment, "uses_shared_openclaw_runtime", False):
            result = await environment.exec(
                command="command -v openclaw >/dev/null && command -v node >/dev/null",
                timeout_sec=30,
            )
            if result.return_code != 0:
                raise RuntimeError("shared E2B OpenClaw runtime is unavailable")
            return
        runtime_path = os.environ.get("OPENCLAW_RUNTIME_DIR")
        if runtime_path and Path(runtime_path).is_dir():
            await super().setup(environment)
            return

        bundle_path = os.environ.get("OPENCLAW_BUNDLE_TGZ")
        if bundle_path:
            bundle = Path(bundle_path)
            if bundle.is_file():
                await environment.exec(command="mkdir -p /installed-agent")
                await environment.upload_file(
                    source_path=bundle,
                    target_path="/installed-agent/openclaw-node-bundle.tgz",
                )
        await super().setup(environment)

    # 仅在挂载了真实 task skill 时，在原始 user query 后追加 skill 使用要求。
    def _augment_instruction_with_skill(self, instruction: str, skills_dir: str) -> str:
        enabled = os.environ.get("OPENCLAW_REQUIRE_SKILL_USE", "1").strip().lower()
        skills_src = os.environ.get("OPENCLAW_BUNDLED_SKILLS_SRC_DIR", "").strip()
        if not skills_src or skills_dir == self.EMPTY_SKILLS_DIR or enabled in {"0", "false", "no", "off"}:
            return instruction
        suffix = os.environ.get("OPENCLAW_SKILL_USE_SUFFIX", self.DEFAULT_SKILL_USE_SUFFIX).strip()
        return f"{instruction.rstrip()}\n\n{suffix}" if suffix else instruction

    # 构造正式 executor 命令，并将 guardrail 放前、skill-use suffix 放在 user query 后。
    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        skills_dir = os.environ.get("OPENCLAW_BUNDLED_SKILLS_DIR", self.EMPTY_SKILLS_DIR)
        augmented_instruction = self._augment_instruction_with_skill(instruction, skills_dir)
        guarded_instruction = f"{self.OUTPUT_GUARDRAIL}\n\n{augmented_instruction}"
        commands = super().create_run_agent_commands(guarded_instruction)
        workspace_dir = os.environ.get("OPENCLAW_WORKSPACE_DIR", "/app")
        session_id = os.environ.get("OPENCLAW_SESSION_ID", "harbor")
        for command in commands:
            env = dict(command.env or {})
            for key in self.HOST_ENV_PASSTHROUGH:
                value = os.environ.get(key)
                if value:
                    env.setdefault(key, value)
            env["OPENCLAW_BUNDLED_SKILLS_DIR"] = skills_dir
            env["OPENCLAW_DIAGNOSTICS"] = "false"
            env["PI_BASH_MAX_OUTPUT_CHARS"] = os.environ.get(
                "OPENCLAW_BASH_MAX_OUTPUT_CHARS",
                os.environ.get("PI_BASH_MAX_OUTPUT_CHARS", "20000"),
            )
            env["OPENCLAW_BASH_PENDING_MAX_OUTPUT_CHARS"] = os.environ.get(
                "OPENCLAW_BASH_PENDING_MAX_OUTPUT_CHARS",
                "8000",
            )
            command.env = env
            command.cwd = workspace_dir
            command.command = command.command.replace(
                "--session-id harbor",
                f"--session-id {shlex.quote(session_id)}",
            )

        if commands:
            preamble = ""
            if skills_dir == self.EMPTY_SKILLS_DIR:
                preamble = f"mkdir -p {self.EMPTY_SKILLS_DIR} && "
            commands[0].command = (
                preamble + commands[0].command + " && " + self._build_tools_patch_command()
            )
        if len(commands) > 1 and 'exit "$AGENT_EXIT"' in commands[1].command:
            commands[1].command = commands[1].command.replace(
                'GATEWAY_URL="http://localhost:${GATEWAY_PORT}"\n',
                (
                    'GATEWAY_URL="http://localhost:${GATEWAY_PORT}"\n'
                    f"{self.NODE_READY_FUNC}\n"
                ),
            )
            commands[1].command = commands[1].command.replace(
                self.CURL_READY_CHECK,
                "gateway_ready",
            )
            commands[1].command = commands[1].command.replace(
                self.CURL_READY_CHECK_NO_REDIRECT,
                "gateway_ready",
            )
            commands[1].command = commands[1].command.replace(
                'exit "$AGENT_EXIT"',
                (
                    'SESSION_FILE="${OPENCLAW_STATE_DIR:-/logs/agent/openclaw-state}/agents/main/sessions/'
                    '${OPENCLAW_SESSION_ID:-harbor}.jsonl"\n'
                    'if [ -f "$SESSION_FILE" ]; then\n'
                    '  printf "FUSE_OPENCLAW_METRICS tool_calls=%s parent_reads=%s app_mentions=%s candidate_writes=%s\\n" '
                    '    "$(grep -o toolCall "$SESSION_FILE" | wc -l)" '
                    '    "$(grep -o "/workspace/parent/SKILL.md" "$SESSION_FILE" | wc -l)" '
                    '    "$(grep -o "/app" "$SESSION_FILE" | wc -l)" '
                    '    "$(grep -oE "/tmp/openclaw-workspace/skill/[^\\\" ]+" "$SESSION_FILE" | wc -l)"\n'
                    'fi\n'
                    'chmod -R a+rX "${OPENCLAW_STATE_DIR:-/logs/agent/openclaw-state}" '
                    "2>/dev/null || true\n"
                    'exit "$AGENT_EXIT"'
                ),
            )
        return commands

    def _find_session_jsonl(self) -> Path | None:
        try:
            return super()._find_session_jsonl()
        except PermissionError as exc:
            print(f"Skipping OpenClaw session discovery: {exc}")
            return None
