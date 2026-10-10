"""Tencent E2B environment for a mounted OpenClaw skill trial."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tbench2_openclaw.e2b_fuse import E2BFormalEnvironment


class TencentOpenClawSkillEnvironment(E2BFormalEnvironment):
    """Keep the Tencent filesystem after an OpenClaw skill trial."""

    def __init__(self, *args: Any, snapshot_retries: int = 1, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._snapshot_retries = max(1, int(snapshot_retries))
        self._persist_sandboxes = os.getenv("TBENCH_PERSIST_SANDBOXES", "0") == "1"

    def _snapshot_path(self) -> Path:
        return self.trial_paths.trial_dir / "snapshot.json"

    def _write_snapshot_record(self, value: dict[str, Any]) -> None:
        path = self._snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    async def stop(self, delete: bool) -> None:
        if not delete or getattr(self, "_sandbox", None) is None:
            await super().stop(delete)
            return

        if not self._persist_sandboxes:
            self._write_snapshot_record(
                {
                    "status": "deleted",
                    "artifact_type": "none",
                    "source_sandbox_id": getattr(self._sandbox, "sandbox_id", None),
                    "environment_name": self.environment_name,
                    "session_id": self.session_id,
                    "job_id": self.trial_paths.trial_dir.parent.name,
                    "trial_id": self.trial_paths.trial_dir.name,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "paused sandbox retention disabled",
                }
            )
            await super().stop(delete)
            return

        sandbox = self._sandbox
        last_error: Exception | None = None
        for attempt in range(1, self._snapshot_retries + 1):
            try:
                await sandbox.pause(keep_memory=False)
                self._write_snapshot_record(
                    {
                        "status": "paused_filesystem",
                        "artifact_type": "e2b_paused_sandbox",
                        "persistent_sandbox_id": sandbox.sandbox_id,
                        "source_sandbox_id": sandbox.sandbox_id,
                        "environment_name": self.environment_name,
                        "session_id": self.session_id,
                        "job_id": self.trial_paths.trial_dir.parent.name,
                        "trial_id": self.trial_paths.trial_dir.name,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "attempts": attempt,
                    }
                )
                self._sandbox = None
                return
            except Exception as exc:
                last_error = exc
                if attempt < self._snapshot_retries:
                    await asyncio.sleep(attempt)

        self._write_snapshot_record(
            {
                "status": "failed",
                "source_sandbox_id": getattr(sandbox, "sandbox_id", None),
                "environment_name": self.environment_name,
                "session_id": self.session_id,
                "job_id": self.trial_paths.trial_dir.parent.name,
                "trial_id": self.trial_paths.trial_dir.name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "attempts": self._snapshot_retries,
                "error": str(last_error),
            }
        )
        # Keep an unpaused sandbox for inspection.
        self._sandbox = None
