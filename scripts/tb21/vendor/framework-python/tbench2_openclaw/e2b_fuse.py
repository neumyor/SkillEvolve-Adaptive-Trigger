"""FUSE 在 E2B Harbor environment 中使用的 workspace 适配层。

Harbor 内置的 E2B environment 负责创建 sandbox 和执行命令，但不理解
FUSE 的 ``--mounts-json``。本适配层在 sandbox 创建后上传 parent、candidate
和 evidence 目录，并对声明为只读的目录移除写权限。
"""

from __future__ import annotations

import json
import io
import os
from pathlib import Path
from pathlib import PurePosixPath
import shlex
import shutil
import tarfile
from typing import Any

from e2b import AsyncSandbox
from e2b.sandbox.commands.command_handle import CommandExitException
from harbor.environments.base import ExecResult
from harbor.environments.e2b import E2BEnvironment


# 腾讯 AGS 的控制面 key 使用 ark_ 前缀；仅关闭 SDK 本地格式检查，服务端认证不变。
if os.getenv("E2B_API_KEY", "").startswith("ark_"):
    os.environ.setdefault("E2B_VALIDATE_API_KEY", "false")


class E2BFuseEnvironment(E2BEnvironment):
    """在 E2B sandbox 中提供 FUSE workspace 的 Harbor environment。"""

    uses_shared_openclaw_runtime = True
    HIDE_EVALUATION_PATHS = True
    AGENT_USER = "nobody"

    _ALLOWED_TARGETS = {
        "/workspace/parent": True,
        "/workspace/evidence": True,
        "/workspace/candidate": False,
    }

    @classmethod
    def _target_read_only(cls, target: str) -> bool | None:
        """返回允许挂载目标的只读策略；未知目标返回 ``None``。"""
        if target in cls._ALLOWED_TARGETS:
            return cls._ALLOWED_TARGETS[target]
        # 正式验证和 OpenClaw 运行时只需要这两个受限的只读前缀。
        if target in {"/opt/openclaw-runtime", "/opt/openclaw-skills"} or target.startswith(
            "/opt/openclaw-skills/"
        ):
            return True
        return None

    def __init__(self, *args: Any, mounts_json: Any = None, **kwargs: Any) -> None:
        self._fuse_mounts = self._parse_mounts(mounts_json)
        task_env_config = kwargs.get("task_env_config")
        if task_env_config is not None:
            task_env_config.allow_internet = True
        super().__init__(*args, **kwargs)
        # Tencent Terminal-Bench runtime images expose root, not Harbor's
        # generic E2B default user. Verifier test uploads use this identity.
        self._fs_user = os.getenv("HARBOR_E2B_FS_USER", "root")

    @classmethod
    def _parse_mounts(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, list):
            raise ValueError("E2B FUSE mounts must be a list")
        mounts: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("E2B FUSE mount must be an object")
            target = str(item.get("target", ""))
            expected_read_only = cls._target_read_only(target)
            if expected_read_only is None:
                raise ValueError(f"E2B FUSE mount target is not allowed: {target}")
            if bool(item.get("read_only")) != expected_read_only:
                mode = "read-only" if expected_read_only else "read-write"
                raise ValueError(f"E2B FUSE mount requires {mode}: {target}")
            source = Path(str(item.get("source", "")))
            if source.is_symlink() or not source.is_dir():
                raise ValueError(f"E2B FUSE mount source is not a directory: {source}")
            resolved = source.resolve()
            for path in resolved.rglob("*"):
                if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                    raise ValueError(f"E2B FUSE mount source contains unsafe path: {path}")
            mounts.append({"source": resolved, "target": target, "read_only": expected_read_only})
        return mounts

    async def start(self, force_build: bool) -> None:
        """创建 E2B sandbox 并上传 FUSE workspace。"""
        if not os.getenv("E2B_API_KEY"):
            raise RuntimeError("E2B_API_KEY is required for the e2b environment")
        # 腾讯 AGS 的预置模板不兼容 Harbor 的 alias_exists/build API，直接创建。
        await self._create_sandbox()
        await self._sandbox.files.make_dir("/app", user="root")
        await self._sandbox.files.make_dir("/workspace", user="root")
        activated = await super().exec(
            "/mnt/cfs/agent-tools/bin/activate-agent-tools && command -v openclaw",
            cwd="/app",
            timeout_sec=120,
        )
        if activated.return_code != 0:
            raise RuntimeError("failed to activate shared E2B OpenClaw runtime")
        if self.HIDE_EVALUATION_PATHS:
            hidden = await super().exec(
                "rm -rf -- /solution /tests /logs/agent /logs/verifier /logs/artifacts",
                cwd="/app",
                timeout_sec=30,
            )
            if hidden.return_code != 0:
                raise RuntimeError("failed to hide sensitive evaluation paths in E2B sandbox")
            app_user = await super().exec(
                "chown nobody:nogroup /app && chmod 700 /app",
                cwd="/app",
                timeout_sec=30,
            )
            if app_user.return_code != 0:
                raise RuntimeError("E2B image does not provide the nobody runtime user")
        for mount in self._fuse_mounts:
            target = str(mount["target"])
            await self._sandbox.files.make_dir(target, user="root")
            await self._upload_dir_as_root(mount["source"], target)
            if mount["read_only"]:
                result = await super().exec(f"chmod -R a-w -- {target}", timeout_sec=30)
                if result.return_code != 0:
                    raise RuntimeError(f"failed to lock E2B workspace: {target}")
            else:
                result = await super().exec(
                    f"chown -R nobody:nogroup -- {target} && chmod -R u+rwX,go-rX -- {target}",
                    cwd="/app",
                    timeout_sec=30,
                )
                if result.return_code != 0:
                    raise RuntimeError(f"failed to enable E2B candidate workspace: {target}")

    async def stop(self, delete: bool) -> None:
        """删除 sandbox 前把所有可写 FUSE mount 同步回宿主目录。

        Args:
            delete: 是否销毁远端 sandbox，由 Harbor 生命周期传入。
        """
        try:
            if self._sandbox:
                for mount in self._fuse_mounts:
                    if not mount["read_only"]:
                        await self.export_directory(str(mount["target"]), Path(mount["source"]))
        finally:
            await super().stop(delete)

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
    ) -> ExecResult:
        """以非 root 用户执行 agent 命令，使只读检查具有真实语义。"""
        if not self._sandbox:
            raise RuntimeError("Sandbox not found. Please start the environment first.")
        handle = await self._sandbox.commands.run(
            cmd=command,
            background=True,
            cwd=cwd or "/app",
            envs=self._merge_env(env),
            timeout=timeout_sec or 0,
            user=os.getenv("E2B_AGENT_USER", self.AGENT_USER),
        )
        try:
            result = await handle.wait()
        except CommandExitException as exc:
            result = exc
        return ExecResult(
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.exit_code,
        )

    async def download_dir(self, source_dir: str, target_dir: Path | str) -> None:
        """Skip Harbor's hidden agent-log path for isolated FUSE runs.

        FUSE exports its needed OpenClaw state and protocol result explicitly
        before the sandbox is deleted. Harbor otherwise tries to download the
        deliberately removed `/logs/agent` and emits a misleading warning.
        Formal E2B runs keep the standard Harbor behavior.
        """
        if self.HIDE_EVALUATION_PATHS and source_dir == "/logs/agent":
            return
        await super().download_dir(source_dir=source_dir, target_dir=target_dir)

    async def _upload_dir_as_root(self, source: Path, target: str) -> None:
        """通过 envd 文件 API 以 root 用户上传目录内容。"""
        for directory in sorted(path for path in source.rglob("*") if path.is_dir()):
            relative = PurePosixPath(directory.relative_to(source).as_posix())
            await self._sandbox.files.make_dir(
                str(PurePosixPath(target) / relative),
                user="root",
            )
        for file_path in sorted(source.rglob("*")):
            if not file_path.is_file():
                continue
            relative = PurePosixPath(file_path.relative_to(source).as_posix())
            target_path = str(PurePosixPath(target) / relative)
            await self._sandbox.files.write(target_path, file_path.read_bytes(), user="root")

    async def export_directory(self, remote_root: str, local_root: Path) -> None:
        """把远端目录以 tar 形式原样下载到受控宿主目录。

        Args:
            remote_root: sandbox 内待导出的绝对目录。
            local_root: 对应 trial artifact 或 writable mount 的宿主目录。
        """
        if not self._sandbox:
            raise RuntimeError("Sandbox not found. Cannot export artifacts.")
        archive = f"/tmp/fuse-export-{abs(hash((remote_root, str(local_root))))}.tar"
        quoted_remote = shlex.quote(remote_root)
        quoted_archive = shlex.quote(archive)
        packed = await super().exec(
            f"test -d {quoted_remote} && tar -C {quoted_remote} -cf {quoted_archive} .",
            cwd="/tmp",
            timeout_sec=120,
        )
        if packed.return_code != 0:
            return
        payload = await self._sandbox.files.read(archive, format="bytes", user="root")
        if not isinstance(payload, (bytes, bytearray)):
            raise RuntimeError("E2B artifact download did not return bytes")
        if local_root.exists():
            for child in local_root.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        else:
            local_root.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(bytes(payload)), mode="r:") as archive_file:
            destination = local_root.resolve()
            safe_members = []
            for member in archive_file.getmembers():
                target = (destination / member.name).resolve()
                if target != destination and destination not in target.parents:
                    raise ValueError("E2B artifact archive contains path escape")
                # OpenClaw state may contain convenience symlinks. Artifacts only
                # need original regular files (especially session JSONL/config),
                # so links and special nodes are skipped without dereferencing.
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    continue
                safe_members.append(member)
            archive_file.extractall(destination, members=safe_members, filter="data")

    async def _create_sandbox(self) -> None:
        """显式传入腾讯 AGS 凭据，兼容 ``ark_`` 格式的控制面 key。"""
        image = os.getenv("E2B_IMAGE") or self.task_env_config.docker_image
        if not image:
            raise RuntimeError("Tencent E2B requires environment.docker_image")
        metadata = {
            "environment_name": self.environment_name,
            "session_id": self.session_id,
            "x-custom-config": json.dumps({
                "image": image,
                "imageRegistryType": "enterprise",
                "command": ["/bin/sh", "-c"],
                "args": ["/mnt/envd -port 49983"],
                "resources": {
                    "cpu": str(self.task_env_config.cpus),
                    "memory": f"{self.task_env_config.memory_mb // 1024}Gi",
                },
            }),
            "x-mounts": json.dumps([{
                "name": "cfs",
                "mountPath": "/mnt/cfs/agent-tools",
                "subPath": "agent-tools",
                "readOnly": True,
            }]),
            "purpose": "fuse-harbor-e2b",
        }
        self._sandbox = await AsyncSandbox.create(
            template=os.getenv("E2B_TEMPLATE", "code-agent-cfs2-new"),
            metadata=metadata,
            timeout=86_400,
            allow_internet_access=self.task_env_config.allow_internet,
            api_key=os.environ["E2B_API_KEY"],
            validate_api_key=False,
            domain=os.getenv("E2B_DOMAIN", "ap-beijing.tencentags.com"),
        )


class E2BFormalEnvironment(E2BFuseEnvironment):
    """保留 task/verifier 路径的正式验证 E2B environment。

    诊断和演化隐藏评测私有路径并以非 root 用户运行；正式验证则由 Harbor
    正常管理 task、agent 和 verifier 生命周期，只复用共享 CFS runtime 及
    只读 candidate skill 上传能力。
    """

    HIDE_EVALUATION_PATHS = False
    AGENT_USER = "root"
