from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
from typing import Any

import yaml

from harbor.environments.docker.docker import DockerEnvironment
from fuse.evolver import LeakageDetector


FORBIDDEN_DEFINITION_PATTERNS = (
    re.compile(r"(^|[\s'\"])(\.\./|/solution|/tests|/logs/verifier)", re.I),
    re.compile(r"docker\.sock|privileged\s*:\s*true|network_mode\s*:\s*host", re.I),
    re.compile(r"\bpid\s*:\s*host|\bipc\s*:\s*host|\benv_file\s*:", re.I),
    re.compile(r"\b(?:openai|anthropic|api)[_-]?(?:api[_-]?)?key\b", re.I),
)
SENSITIVE_ENV_NAME = re.compile(r"(?:api[_-]?key|token|secret|credential|password)", re.I)
SUSPICIOUS_IMAGE_ROOTS = {"solution", "tests", "verifier"}
SUSPICIOUS_IMAGE_NAMES = {"ground_truth", "ground-truth", "reference_answer", "reward.txt", "reward.json"}


class SecureDiagnosticDockerEnvironment(DockerEnvironment):
    """Docker environment that fail-closes around public diagnostic evidence."""

    MOUNT_POLICY = {"/opt/openclaw-runtime": True}
    ALLOW_PROVIDER_NETWORK = False

    # 强制关闭网络、MCP 和外部 skill，并只允许显式只读 runtime mount。
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._hardening_compose_path: Path | None = None
        task_env_config = kwargs.get("task_env_config")
        if task_env_config is not None:
            # Diagnosis and JSON-action evolution use no network. The
            # OpenClaw-native A/B adapter opts into provider egress because
            # OpenClaw itself performs the model request inside the sandbox.
            if not self.ALLOW_PROVIDER_NETWORK:
                task_env_config.allow_internet = False
            task_env_config.mcp_servers = []
            task_env_config.skills_dir = None
        mounts = kwargs.get("mounts_json") or []
        for mount in mounts:
            target = str(mount.get("target", ""))
            if target not in self.MOUNT_POLICY:
                raise ValueError(f"diagnostic environment rejected mount target: {target}")
            expected_read_only = self.MOUNT_POLICY[target]
            if bool(mount.get("read_only")) != expected_read_only:
                mode = "read-only" if expected_read_only else "read-write"
                raise ValueError(f"diagnostic environment requires {mode} mount: {target}")
            self._validate_mount_source(mount, target)
        super().__init__(*args, **kwargs)

    # 校验显式 mount 的宿主来源；诊断环境默认只接受 runtime。
    def _validate_mount_source(self, mount: dict[str, Any], target: str) -> None:
        source = Path(str(mount.get("source", ""))).resolve()
        if not source.exists():
            raise ValueError(f"diagnostic mount source does not exist: {target}")

    # 将安全 override 放在 Compose 文件链末尾，保证限制不能被 task 配置覆盖。
    @property
    def _docker_compose_paths(self) -> list[Path]:
        paths = list(super()._docker_compose_paths)
        if self._hardening_compose_path is not None:
            paths.append(self._hardening_compose_path)
        return paths

    # 在构建前拒绝 symlink、上级路径、宿主控制接口和敏感配置模式。
    def _validate_definition(self) -> None:
        super()._validate_definition()
        environment_root = self.environment_dir.resolve()
        for path in environment_root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"diagnostic build context rejects symlink: {path}")
            if not path.is_file():
                continue
            resolved = path.resolve()
            if environment_root not in resolved.parents:
                raise ValueError(f"diagnostic build context escapes environment/: {path}")
            if path.name not in {"Dockerfile", "docker-compose.yaml", "docker-compose.yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in FORBIDDEN_DEFINITION_PATTERNS:
                if pattern.search(text):
                    raise ValueError(f"unsafe diagnostic environment definition: {path.name}")
            if path.name.startswith("docker-compose"):
                self._validate_compose(path, environment_root)

    # 结构化校验 Compose context、volume、build args 和环境变量来源。
    def _validate_compose(self, path: Path, environment_root: Path) -> None:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        services = value.get("services") if isinstance(value, dict) else None
        if not isinstance(services, dict):
            raise ValueError("diagnostic docker-compose must contain services")
        main = services.get("main") or {}
        if not isinstance(main, dict):
            raise ValueError("diagnostic docker-compose main service must be an object")
        if main.get("volumes"):
            raise ValueError("diagnostic task compose cannot add main-service volumes")
        build = main.get("build")
        if isinstance(build, str):
            context = build
        elif isinstance(build, dict):
            context = str(build.get("context", "."))
            dockerfile = str(build.get("dockerfile", "Dockerfile"))
            dockerfile_path = (environment_root / dockerfile).resolve()
            if environment_root != dockerfile_path and environment_root not in dockerfile_path.parents:
                raise ValueError("diagnostic Dockerfile must stay within environment/")
            build_args = build.get("args") or {}
            if isinstance(build_args, dict):
                for name, item in build_args.items():
                    if SENSITIVE_ENV_NAME.search(str(name)) or item is None or "${" in str(item):
                        raise ValueError("diagnostic build args must be non-sensitive literals")
            elif build_args:
                raise ValueError("diagnostic build args must be a literal object")
        else:
            context = "."
        context_path = (environment_root / context).resolve()
        if context_path != environment_root:
            raise ValueError("diagnostic build context must be exactly task environment/")
        environment = main.get("environment") or {}
        if isinstance(environment, dict):
            names = environment.keys()
            inherited = any(item is None or "${" in str(item) for item in environment.values())
        else:
            entries = [str(item) for item in environment]
            names = [item.split("=", 1)[0] for item in entries]
            inherited = any("=" not in item or "${" in item for item in entries)
        if any(SENSITIVE_ENV_NAME.search(str(name)) for name in names):
            raise ValueError("diagnostic task compose cannot expose credential-like environment variables")
        if inherited:
            raise ValueError("diagnostic task compose environment values must be static literals")

    # 生成非 root、只读根文件系统、drop capabilities 和 masked mounts 配置。
    def _write_hardening_compose_file(self) -> Path:
        masked_volumes = [
            {"type": "tmpfs", "target": "/solution", "tmpfs": {"mode": 256}},
            {"type": "tmpfs", "target": "/tests", "tmpfs": {"mode": 256}},
            {"type": "tmpfs", "target": "/logs/verifier", "tmpfs": {"mode": 256}},
            {"type": "tmpfs", "target": "/logs/artifacts", "tmpfs": {"mode": 256}},
        ]
        # Native OpenClaw needs the new trial's agent log mount for its state
        # and transcript. Other secure agents keep it fully masked.
        if not self.ALLOW_PROVIDER_NETWORK:
            masked_volumes.insert(
                2,
                {"type": "tmpfs", "target": "/logs/agent", "tmpfs": {"mode": 256}},
            )
        else:
            masked_volumes.insert(
                2,
                {
                    "type": "tmpfs",
                    "target": "/logs/agent",
                    # Compose's tmpfs mapping only accepts mode. Use 0777 on
                    # this empty per-trial transcript mount so uid 65532 can
                    # create its own OpenClaw state below it.
                    "tmpfs": {"mode": 511},
                },
            )
        compose = {
            "services": {
                "main": {
                    "user": "65532:65532",
                    "read_only": True,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                    "tmpfs": [
                        "/app:rw,nosuid,nodev,mode=0700,uid=65532,gid=65532",
                        "/tmp:rw,nosuid,nodev,mode=0700,uid=65532,gid=65532",
                    ],
                    "volumes": masked_volumes,
                }
            }
        }
        path = self.trial_paths.trial_dir / "docker-compose-diagnostic-hardening.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(compose, indent=2) + "\n", encoding="utf-8")
        return path

    # 构建镜像后先执行宿主侧扫描，确认无敏感内容才启动诊断容器。
    async def start(self, force_build: bool) -> None:
        self._hardening_compose_path = self._write_hardening_compose_file()
        if self._mounts_json:
            self._mounts_compose_path = self._write_mounts_compose_file()
        # Native OpenClaw A/B runs use the task's declared prebuilt runtime
        # image when available; rebuilding an apt-based task image would add
        # unrelated latency to the harness comparison.
        self._use_prebuilt = bool(
            self.ALLOW_PROVIDER_NETWORK
            and not force_build
            and getattr(self.task_env_config, "docker_image", None)
        )
        lock = self._image_build_locks.setdefault(self.environment_name, asyncio.Lock())
        async with lock:
            if not self._use_prebuilt:
                await self._run_docker_compose_command(["build"])
        await self._scan_built_image()
        try:
            await self._run_docker_compose_command(["down", "--remove-orphans"])
        except RuntimeError:
            pass
        # 只启动刚刚扫描通过的镜像，禁止 Compose 在扫描后隐式重新构建。
        await self._run_docker_compose_command(["up", "--detach", "--wait", "--no-build"])

    # 解析 Compose 生成的镜像 ID，并在独立宿主流程中扫描其 rootfs。
    async def _scan_built_image(self) -> None:
        result = await self._run_docker_compose_command(["config", "--images"])
        image_refs = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        image_id = await asyncio.to_thread(_resolve_image_id, image_refs)
        if image_id is None and self._use_prebuilt:
            await self._run_docker_compose_command(["pull", "main"])
            image_id = await asyncio.to_thread(_resolve_image_id, image_refs)
        if image_id is None:
            raise RuntimeError("unable to resolve diagnostic image for post-build scan")
        await asyncio.to_thread(_scan_image_archive, image_id, os.getenv("FUSE_EVOLVER_LEAKAGE_MANIFEST"))


class SecureEvolutionDockerEnvironment(SecureDiagnosticDockerEnvironment):
    """只额外开放 parent/candidate/evidence workspace 的演化 sandbox。"""

    MOUNT_POLICY = {
        "/opt/openclaw-runtime": True,
        "/workspace/parent": True,
        "/workspace/candidate": False,
        "/workspace/evidence": True,
    }

    # 仅接受宿主生成的 proposal/evidence 精确目录结构。
    def _validate_mount_source(self, mount: dict[str, Any], target: str) -> None:
        super()._validate_mount_source(mount, target)
        if target == "/opt/openclaw-runtime":
            return
        source = Path(str(mount.get("source", ""))).resolve()
        if target == "/workspace/parent" and source.parts[-2:] != ("parent", "skill"):
            raise ValueError("evolution parent mount must be a proposal parent/skill directory")
        if target == "/workspace/candidate" and source.parts[-2:] != ("candidate", "skill"):
            raise ValueError("evolution candidate mount must be a proposal candidate/skill directory")
        if target == "/workspace/evidence" and source.name != "evidence":
            raise ValueError("evolution evidence mount must use the generated evidence directory")


class OpenClawEvolutionDockerEnvironment(SecureEvolutionDockerEnvironment):
    """Secure evolution mounts with provider egress for native OpenClaw.

    OpenClaw's CLI performs the OpenAI-compatible request from inside the
    task container, unlike the JSON-action evolver whose client runs on the
    trusted host. This A/B-only environment keeps the same masked mounts,
    non-root hardening and image scan while allowing that provider request.
    Web/search/sub-agent tools remain denied by the OpenClaw adapter.
    """

    ALLOW_PROVIDER_NETWORK = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        task_env_config = kwargs.get("task_env_config")
        if task_env_config is not None:
            task_env_config.allow_internet = True
            prebuilt_image = os.getenv("FUSE_OPENCLAW_PREBUILT_IMAGE", "").strip()
            if prebuilt_image:
                task_env_config.docker_image = prebuilt_image
        super().__init__(*args, **kwargs)


class OpenClawFormalDockerEnvironment(DockerEnvironment):
    """Formal Harbor environment with an optional dependency-prewarmed image.

    Formal validation still uses Harbor's normal test and verifier mounts. The
    adapter only replaces the task's public runtime image when the trusted host
    provides ``FUSE_FORMAL_PREBUILT_IMAGE``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        task_env_config = kwargs.get("task_env_config")
        prebuilt_image = os.getenv("FUSE_FORMAL_PREBUILT_IMAGE", "").strip()
        self._formal_prebuilt_override = bool(prebuilt_image)
        if task_env_config is not None and prebuilt_image:
            task_env_config.docker_image = prebuilt_image
        super().__init__(*args, **kwargs)

    async def stop(self, delete: bool) -> None:
        if not self._formal_prebuilt_override or self._keep_containers:
            await super().stop(delete)
            return
        await self._chown_to_host_user("/logs", recursive=True)
        command = ["down"]
        if delete:
            command.extend(["--volumes", "--remove-orphans"])
        try:
            await self._run_docker_compose_command(command)
        except RuntimeError as error:
            self.logger.warning(f"Docker compose down failed: {error}")


# 将 Compose 的镜像引用解析为本地不可变镜像 ID，避免依赖已创建容器的 `compose images`。
def _resolve_image_id(image_refs: list[str]) -> str | None:
    for image_ref in image_refs:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        match = re.fullmatch(r"(?:sha256:)?([0-9a-f]{64})", result.stdout.strip(), re.I)
        if match:
            return match.group(1)
    return None


# 导出未启动镜像的文件系统，检查敏感目录、文件名、canary 和内容指纹。
def _scan_image_archive(image_id: str, manifest_path: str | None) -> None:
    fingerprints: set[str] = set()
    canaries: set[str] = set()
    if manifest_path:
        value = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        fingerprints = set(value.get("fingerprints") or [])
        canaries = {str(item) for item in value.get("canaries") or [] if item}
    detector = LeakageDetector(fingerprints=fingerprints, canaries=canaries)
    container_id = ""
    with tempfile.TemporaryDirectory(prefix="fuse-image-scan-") as temp_dir:
        archive_path = Path(temp_dir) / "rootfs.tar"
        try:
            created = subprocess.run(["docker", "create", image_id, "true"], capture_output=True, text=True, check=True)
            container_id = created.stdout.strip()
            subprocess.run(["docker", "export", "-o", str(archive_path), container_id], check=True)
            with tarfile.open(archive_path, "r") as archive:
                for member in archive:
                    path = PurePosixPath("/" + member.name.lstrip("./"))
                    parts = [part.lower() for part in path.parts if part != "/"]
                    if parts and parts[0] in SUSPICIOUS_IMAGE_ROOTS:
                        raise ValueError(f"diagnostic image contains forbidden root: /{parts[0]}")
                    if path.name.lower() in SUSPICIOUS_IMAGE_NAMES:
                        raise ValueError(f"diagnostic image contains forbidden evaluation artifact: {path.name}")
                    if not member.isfile() or member.size > 10 * 1024 * 1024 or not (fingerprints or canaries):
                        continue
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    text = extracted.read().decode("utf-8", errors="ignore")
                    if detector.contains_leakage(text):
                        raise ValueError("diagnostic image contains sensitive evaluation content")
        finally:
            if container_id:
                subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True)
