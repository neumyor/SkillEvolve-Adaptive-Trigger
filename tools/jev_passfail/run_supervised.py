#!/usr/bin/env python3
"""Launch a detached child and persist its PID, status, and combined log."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run_supervisor(args: argparse.Namespace, command: list[str]) -> int:
    if not command:
        raise ValueError("a child command is required after --")
    if os.getsid(0) != os.getpid():
        os.setsid()

    for path in (args.pid_file, args.status_file, args.log_file):
        if path.exists():
            raise FileExistsError(f"refusing to reuse existing job file: {path}")

    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    with args.log_file.open("ab", buffering=0) as log:
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        identity = {
            "supervisor_pid": os.getpid(),
            "child_pid": child.pid,
            "started_at_utc": started,
            "command": command,
        }
        atomic_json(args.pid_file, identity)
        log.write((json.dumps({"event": "started", **identity}) + "\n").encode())

        def forward(sig: int, _frame: Any) -> None:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, sig)
                except ProcessLookupError:
                    pass

        signal.signal(signal.SIGTERM, forward)
        signal.signal(signal.SIGINT, forward)

        status: dict[str, Any] = {
            **identity,
            "state": "running",
            "updated_at_utc": utc_now(),
        }
        atomic_json(args.status_file, status)
        while child.poll() is None:
            time.sleep(args.poll_seconds)
            status["updated_at_utc"] = utc_now()
            status["elapsed_seconds"] = round(time.monotonic() - args.started_monotonic, 3)
            atomic_json(args.status_file, status)

        exit_code = child.returncode
        status.update({
            "state": "complete" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "finished_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "elapsed_seconds": round(time.monotonic() - args.started_monotonic, 3),
        })
        atomic_json(args.status_file, status)
        log.write((json.dumps({"event": "finished", "exit_code": exit_code}) + "\n").encode())
    return exit_code


def launch(args: argparse.Namespace, command: list[str]) -> int:
    if not command:
        raise ValueError("a child command is required after --")
    supervisor_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--run-supervisor",
        "--pid-file", str(args.pid_file),
        "--status-file", str(args.status_file),
        "--log-file", str(args.log_file),
        "--poll-seconds", str(args.poll_seconds),
        "--",
        *command,
    ]
    process = subprocess.Popen(
        supervisor_command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(json.dumps({"supervisor_pid": process.pid, "state_file": str(args.status_file)}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-supervisor", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    args.started_monotonic = time.monotonic()
    result = run_supervisor(args, command) if args.run_supervisor else launch(args, command)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
