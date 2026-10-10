#!/usr/bin/env python3
"""Author one skill package through OpenClaw inside a Tencent E2B sandbox."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import io
import json
import os
import re
import shlex
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from e2b import AsyncSandbox
from e2b.sandbox.commands.command_handle import CommandExitException


DEFAULT_API_BASE = "https://llm-center.modelbest.co/llm/v1"
DEFAULT_MODEL = "qwen3.6-flash-distill"
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<meta>.*?)\n---\n", re.S)

AUTHORING_ROOT = "/workspace/skill-authoring"
AUTHORING_SKILL_ROOT = "/opt/openclaw-skills"
OUTPUT_ROOT = "/workspace/output"
ARTIFACT_ROOT = "/workspace/artifacts"
STATE_ROOT = "/workspace/openclaw-state"


# The proxy keeps provider request/response bodies inside the sandbox's artifact
# directory. It intentionally does not record Authorization headers.
MODEL_PROXY = r'''import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = os.environ["UPSTREAM_API_BASE"].rstrip("/")
API_KEY = os.environ["UPSTREAM_API_KEY"]
ARTIFACTS = Path(os.environ["RAW_ARTIFACT_DIR"])
LOCK = threading.Lock()

def append(name, value):
    with LOCK, (ARTIFACTS / name).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")

class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        return

    def do_POST(self):
        request_id = uuid.uuid4().hex
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            logged_request = json.loads(body)
        except json.JSONDecodeError:
            logged_request = {"raw_request_text": body.decode("utf-8", "replace")}
        append("raw_model_requests.jsonl", {"request_id": request_id, "path": self.path, "body": logged_request})
        request = urllib.request.Request(
            UPSTREAM + self.path,
            data=body,
            headers={"Authorization": "Bearer " + API_KEY, "Content-Type": self.headers.get("Content-Type", "application/json")},
            method="POST",
        )
        status, headers, response_body, transport_error = 0, {}, b"", None
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                status, headers, response_body = response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            status, headers, response_body = error.code, dict(error.headers or {}), error.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            transport_error = f"{type(error).__name__}: {error}"
            response_body = json.dumps({"error": {"message": transport_error}}).encode()
        text = response_body.decode("utf-8", "replace")
        try:
            logged_response = json.loads(text)
        except json.JSONDecodeError:
            logged_response = {"raw_response_text": text}
        append("raw_model_responses.jsonl", {
            "request_id": request_id, "http_status": status, "transport_error": transport_error,
            "retry_after": headers.get("Retry-After"), "body": logged_response,
        })
        self.send_response(status or 502)
        self.send_header("Content-Type", headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("MODEL_PROXY_PORT", "18080"))), Proxy).serve_forever()
'''


def build_prompt(skill_name: str) -> str:
    return f"""Create one reusable Agent Skills package named `{skill_name}`.

First read `/opt/openclaw-skills/skill-creator/SKILL.md` and use its applicable
authoring guidance. The only task information provided is the public instruction
at `{AUTHORING_ROOT}/instruction.md`; inspect it and any other files explicitly
visible in this authoring workspace as needed.

Write the finished package only below `{OUTPUT_ROOT}/skills/{skill_name}/`.
It must contain `{OUTPUT_ROOT}/skills/{skill_name}/SKILL.md` with YAML
frontmatter containing `name: {skill_name}` and a useful `description`. You may
also create task-useful `scripts/`, `references/`, `assets/`, or `evals/` files.

You may reason from public information and make clearly bounded guesses. Do not
attempt to read, infer, reconstruct, request, or claim knowledge of hidden
evaluation content, hidden tests, gold patches, rewards, or verifier internals.
Do not solve or execute the benchmark task. This is a skill-authoring session,
not a Terminal-Bench evaluation. Finish by checking that the package exists in
the required output directory and briefly report what you created.
"""


def build_openclaw_config(*, model: str, proxy_base: str) -> dict[str, Any]:
    return {
        "agents": {"defaults": {"model": f"custom/{model}", "workspace": AUTHORING_ROOT}},
        "env": {"shellEnv": {"enabled": True}, "OPENCLAW_GATEWAY_TOKEN": "skill-authoring-token"},
        "models": {
            "providers": {
                "custom": {
                    "baseUrl": proxy_base,
                    "api": "openai-completions",
                    "apiKey": {"source": "env", "provider": "default", "id": "UPSTREAM_API_KEY"},
                    "models": [{
                        "id": model, "name": model, "reasoning": True, "input": ["text"],
                        "contextWindow": 256000, "maxTokens": 65536,
                    }],
                }
            }
        },
        "browser": {"headless": True, "noSandbox": True, "ssrfPolicy": {"dangerouslyAllowPrivateNetwork": True}},
        "tools": {
            "profile": "minimal",
            "alsoAllow": ["read", "exec", "process", "write", "edit", "apply_patch", "session_status"],
            "deny": ["group:web", "group:memory", "group:sessions", "group:ui", "group:automation", "group:messaging", "group:nodes", "agents_list", "subagents"],
            "exec": {"notifyOnExit": False, "notifyOnExitEmptySuccess": False},
        },
        "skills": {"load": {"extraDirs": [AUTHORING_SKILL_ROOT]}},
    }


def validate_generated_skill(skill_dir: Path, expected_name: str) -> dict[str, str]:
    path = skill_dir / "SKILL.md"
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        raise ValueError(f"generated skill is missing: {path}")
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("generated SKILL.md is missing YAML frontmatter")
    metadata = match.group("meta")
    name = re.search(r"(?m)^name:\s*(.+?)\s*$", metadata)
    description = re.search(r"(?m)^description:\s*(.*?)\s*$", metadata)
    if not name or not description:
        raise ValueError("generated SKILL.md requires non-empty name and description")
    if name.group(1).strip().strip("\"'") != expected_name:
        raise ValueError(f"generated skill name must be {expected_name}")
    description_text = description.group(1).strip().strip("\"'")
    if description_text in {"|", "|-", "|+", ">", ">-", ">+"}:
        continuation = re.search(
            r"(?m)^description:\s*[^\n]*\n((?:[ \t]+\S.*(?:\n|$))*)",
            metadata,
        )
        description_text = " ".join(
            line.strip() for line in (continuation.group(1).splitlines() if continuation else [])
        )
    if not description_text:
        raise ValueError("generated SKILL.md requires non-empty name and description")
    return {"skill_path": str(path), "skill_description": description_text}


def validate_inputs(args: argparse.Namespace) -> None:
    if not SKILL_NAME_RE.fullmatch(args.skill_name):
        raise SystemExit("skill name must contain lowercase letters, digits, and hyphens")
    if not args.instruction_file.is_file():
        raise SystemExit(f"instruction file does not exist: {args.instruction_file}")
    if not (args.skill_creator_dir / "SKILL.md").is_file():
        raise SystemExit(f"official skill-creator directory is missing SKILL.md: {args.skill_creator_dir}")
    if args.dry_run:
        return
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("E2B_API_KEY"):
        raise SystemExit("OPENAI_API_KEY and E2B_API_KEY must be set")


async def run_command(
    sandbox: AsyncSandbox,
    command: str,
    *,
    envs: dict[str, str] | None = None,
    user: str = "root",
    cwd: str | None = None,
    timeout: int = 120,
) -> Any:
    handle = await sandbox.commands.run(
        cmd=command,
        background=True,
        envs=envs,
        user=user,
        cwd=cwd,
        timeout=timeout,
    )
    try:
        result = await handle.wait()
    except CommandExitException as exc:
        result = exc
    if result.exit_code != 0:
        raise RuntimeError(result.stderr or result.stdout or f"sandbox command failed: {command}")
    return result


async def upload_tree(sandbox: AsyncSandbox, source: Path, target: str) -> None:
    await sandbox.files.make_dir(target, user="root")
    for directory in sorted(path for path in source.rglob("*") if path.is_dir()):
        relative = PurePosixPath(directory.relative_to(source).as_posix())
        await sandbox.files.make_dir(str(PurePosixPath(target) / relative), user="root")
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = PurePosixPath(path.relative_to(source).as_posix())
            await sandbox.files.write(str(PurePosixPath(target) / relative), path.read_bytes(), user="root")


async def export_tree(sandbox: AsyncSandbox, remote_root: str, local_root: Path) -> bool:
    archive = f"/tmp/skill-authoring-export-{abs(hash((remote_root, str(local_root))))}.tar"
    result = await sandbox.commands.run(
        cmd=f"test -d {shlex.quote(remote_root)} && tar -C {shlex.quote(remote_root)} -cf {shlex.quote(archive)} .",
        background=True,
        user="root",
        timeout=120,
    )
    try:
        completed = await result.wait()
    except CommandExitException as exc:
        completed = exc
    if completed.exit_code != 0:
        return False
    payload = await sandbox.files.read(archive, format="bytes", user="root")
    local_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(bytes(payload)), mode="r:") as source:
        destination = local_root.resolve()
        members = []
        for member in source.getmembers():
            target = (destination / member.name).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError("sandbox artifact archive contains path escape")
            if not (member.issym() or member.islnk() or member.isdev() or member.isfifo()):
                members.append(member)
        source.extractall(destination, members=members, filter="data")
    return True


def redact_artifacts(root: Path, secret: str) -> None:
    if not secret:
        return
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 20_000_000:
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if secret in value:
            path.write_text(value.replace(secret, "[REDACTED]"), encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def finalize_sandbox(sandbox: AsyncSandbox, retention: str) -> str:
    if retention == "pause":
        await sandbox.pause(keep_memory=False)
        return "paused_filesystem"
    if retention == "none":
        await sandbox.kill()
        return "deleted"
    raise ValueError(f"unsupported sandbox retention: {retention}")


async def async_main(args: argparse.Namespace) -> int:
    validate_inputs(args)
    if args.dry_run:
        print(json.dumps({
            "mode": "e2b_openclaw_skill_authoring", "skill_name": args.skill_name,
            "instruction_file": str(args.instruction_file), "skill_creator_dir": str(args.skill_creator_dir),
            "output_root": str(args.output_root), "uses_harbor": False, "runs_verifier": False,
        }, ensure_ascii=False))
        return 0

    api_key = os.environ["OPENAI_API_KEY"]
    audit_dir = args.output_root / "generation"
    sandbox: AsyncSandbox | None = None
    manifest: dict[str, Any] = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": "e2b_openclaw_skill_authoring",
        "skill_name": args.skill_name, "model": args.model, "api_base": args.api_base,
        "input": {"instruction_file": str(args.instruction_file), "skill_creator_dir": str(args.skill_creator_dir)},
        "uses_harbor": False, "runs_verifier": False,
    }
    try:
        metadata = {
            "purpose": "tb21-claude-skill-authoring",
            "x-custom-config": json.dumps({
                "image": os.getenv("E2B_IMAGE", "modelbest.tencentcloudcr.com/all-hands-ai/runtime/oh_v0.59.0_jqx9rkkdtc8zrris_9yzpn5kns890pwg6:latest"),
                "imageRegistryType": "enterprise", "command": ["/bin/sh", "-c"], "args": ["/mnt/envd -port 49983"],
                "resources": {"cpu": "1", "memory": "2Gi"},
            }),
        }
        if args.resume_sandbox_id:
            sandbox = await asyncio.wait_for(
                AsyncSandbox._cls_connect_sandbox(
                    args.resume_sandbox_id,
                    timeout=args.sandbox_create_timeout,
                    validate_api_key=False,
                    domain=os.getenv("E2B_DOMAIN", "ap-beijing.tencentags.com"),
                ),
                timeout=args.sandbox_create_timeout,
            )
            manifest["resumed_sandbox_id"] = args.resume_sandbox_id
        else:
            sandbox = await asyncio.wait_for(
                AsyncSandbox.create(
                    template=os.getenv("E2B_TEMPLATE", "code-agent-cfs2-new"), metadata=metadata,
                    timeout=args.timeout_sec + 600, allow_internet_access=True, api_key=os.environ["E2B_API_KEY"],
                    validate_api_key=False, domain=os.getenv("E2B_DOMAIN", "ap-beijing.tencentags.com"),
                ),
                timeout=args.sandbox_create_timeout,
            )
        manifest["sandbox_id"] = sandbox.sandbox_id
        await upload_tree(sandbox, args.skill_creator_dir, f"{AUTHORING_SKILL_ROOT}/skill-creator")
        await sandbox.files.make_dir(AUTHORING_ROOT, user="root")
        await sandbox.files.make_dir(OUTPUT_ROOT, user="root")
        await sandbox.files.make_dir(ARTIFACT_ROOT, user="root")
        await sandbox.files.make_dir(STATE_ROOT, user="root")
        await sandbox.files.write(f"{AUTHORING_ROOT}/instruction.md", args.instruction_file.read_bytes(), user="root")
        await sandbox.files.write(f"{AUTHORING_ROOT}/authoring_prompt.md", build_prompt(args.skill_name).encode(), user="root")
        await sandbox.files.write(f"{AUTHORING_ROOT}/model_proxy.py", MODEL_PROXY.encode(), user="root")
        await sandbox.files.write(
            f"{STATE_ROOT}/openclaw.json",
            json.dumps(build_openclaw_config(model=args.model, proxy_base=f"http://127.0.0.1:{args.proxy_port}"), indent=2).encode(),
            user="root",
        )
        # The Tencent shared-runtime activation installs command symlinks under
        # /usr/local/bin, so it must happen before switching to the unprivileged
        # authoring identity.
        await run_command(
            sandbox,
            "/mnt/cfs/agent-tools/bin/activate-agent-tools && command -v openclaw",
        )
        await run_command(
            sandbox,
            "chmod -R a-w -- /opt/openclaw-skills && "
            "mkdir -p /workspace/openclaw-home /workspace/output/skills /workspace/artifacts && "
            "chown -R nobody:nogroup /workspace/skill-authoring /workspace/output /workspace/artifacts /workspace/openclaw-state /workspace/openclaw-home && "
            "chmod 755 /workspace/skill-authoring /workspace/openclaw-state && chmod 700 /workspace/output",
        )
        proxy_env = {"UPSTREAM_API_KEY": api_key, "UPSTREAM_API_BASE": args.api_base, "RAW_ARTIFACT_DIR": ARTIFACT_ROOT, "MODEL_PROXY_PORT": str(args.proxy_port)}
        await run_command(
            sandbox,
            f"test -f {ARTIFACT_ROOT}/model_proxy.pid && kill $(cat {ARTIFACT_ROOT}/model_proxy.pid) || true",
        )
        await run_command(
            sandbox,
            f"nohup python3 {AUTHORING_ROOT}/model_proxy.py > {ARTIFACT_ROOT}/model_proxy.log 2>&1 & echo $! > {ARTIFACT_ROOT}/model_proxy.pid; sleep 1; kill -0 $(cat {ARTIFACT_ROOT}/model_proxy.pid)",
            envs=proxy_env,
        )
        agent_env = {
            "HOME": "/workspace/openclaw-home", "PATH": "/mnt/cfs/agent-tools/bin:/usr/local/bin:/usr/bin:/bin",
            "UPSTREAM_API_KEY": api_key, "OPENCLAW_STATE_DIR": STATE_ROOT,
            "OPENCLAW_CONFIG_PATH": f"{STATE_ROOT}/openclaw.json", "OPENCLAW_BUNDLED_SKILLS_DIR": AUTHORING_SKILL_ROOT,
            "OPENCLAW_DIAGNOSTICS": "false", "OPENCLAW_TOOLS_ALSO_ALLOW": "read,exec,process,write,edit,apply_patch,session_status",
        }
        shell_command = (
            "set -euo pipefail; "
            f"openclaw agent --local --json --session-id skill-authoring --thinking medium --timeout {args.timeout_sec} "
            f"--message \"$(cat {AUTHORING_ROOT}/authoring_prompt.md)\" 2>&1 | tee {ARTIFACT_ROOT}/openclaw.stdout.log"
        )
        await run_command(
            sandbox,
            f"bash -lc {shlex.quote(shell_command)}",
            envs=agent_env,
            user="nobody",
            cwd=AUTHORING_ROOT,
            timeout=args.timeout_sec + 60,
        )
        await export_tree(sandbox, OUTPUT_ROOT, args.output_root)
        await export_tree(sandbox, ARTIFACT_ROOT, audit_dir / "artifacts")
        await export_tree(sandbox, STATE_ROOT, audit_dir / "openclaw-state")
        skill = validate_generated_skill(args.output_root / "skills" / args.skill_name, args.skill_name)
        manifest.update(skill)
        manifest["generated_files"] = [str(path.relative_to(args.output_root)) for path in sorted(args.output_root.rglob("*")) if path.is_file()]
        manifest["sandbox_state"] = await finalize_sandbox(sandbox, args.sandbox_retention)
        redact_artifacts(args.output_root, api_key)
        write_json(audit_dir / "generation.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    except Exception as exc:
        manifest.update({"status": "failed", "error": str(exc), "sandbox_state": "not_created"})
        if sandbox:
            for remote, local in ((OUTPUT_ROOT, args.output_root), (ARTIFACT_ROOT, audit_dir / "artifacts"), (STATE_ROOT, audit_dir / "openclaw-state")):
                try:
                    await export_tree(sandbox, remote, local)
                except Exception:
                    pass
            try:
                manifest["sandbox_state"] = await finalize_sandbox(sandbox, args.sandbox_retention)
            except Exception as cleanup_error:
                manifest["sandbox_state"] = "cleanup_failed"
                manifest["cleanup_error"] = str(cleanup_error)
        redact_artifacts(args.output_root, api_key)
        write_json(audit_dir / "generation_error.json", manifest)
        raise
    finally:
        if sandbox:
            try:
                await sandbox.commands.run(
                    cmd=f"test -f {ARTIFACT_ROOT}/model_proxy.pid && kill $(cat {ARTIFACT_ROOT}/model_proxy.pid) || true",
                    user="root", timeout=30,
                )
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instruction-file", required=True, type=Path)
    parser.add_argument("--skill-creator-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--skill-name", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--sandbox-create-timeout", type=int, default=180)
    parser.add_argument("--sandbox-retention", choices=("pause", "none"), default="none")
    parser.add_argument("--proxy-port", type=int, default=18080)
    parser.add_argument("--resume-sandbox-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
