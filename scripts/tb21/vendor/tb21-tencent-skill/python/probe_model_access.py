"""Probe a ModelBest endpoint from an existing Tencent E2B sandbox."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex

from e2b import AsyncSandbox


async def probe(sandbox_id: str) -> None:
    sandbox = await AsyncSandbox._cls_connect_sandbox(sandbox_id, timeout=900)
    payload = {
        "model": os.environ["MODEL_NAME"],
        "messages": [{"role": "user", "content": "Reply with OK only."}],
        "max_tokens": 8,
    }
    runner = """import json, os, urllib.error, urllib.request
body = os.environ['MODEL_PAYLOAD'].encode()
request = urllib.request.Request(
    os.environ['MODEL_API_BASE'].rstrip('/') + '/chat/completions',
    data=body,
    headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'], 'Content-Type': 'application/json'},
    method='POST',
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        status, raw = response.status, response.read()
except urllib.error.HTTPError as error:
    status, raw = error.code, error.read()
try:
    data = json.loads(raw)
except Exception:
    data = {}
print(json.dumps({
    'status': status,
    'has_choices': bool(data.get('choices')),
    'model': data.get('model'),
    'message_keys': sorted(((data.get('choices') or [{}])[0].get('message') or {}).keys()),
    'error_type': (data.get('error') or {}).get('type'),
}))
"""
    try:
        result = await sandbox.commands.run(
            "python3 -c " + shlex.quote(runner),
            envs={
                "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
                "MODEL_API_BASE": os.environ["MODEL_API_BASE"],
                "MODEL_PAYLOAD": json.dumps(payload),
            },
            timeout=150,
            user="root",
        )
        print(result.stdout.strip())
    finally:
        await sandbox.pause(keep_memory=False)
        print("sandbox_state=paused_filesystem")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sandbox_id")
    args = parser.parse_args()
    asyncio.run(probe(args.sandbox_id))


if __name__ == "__main__":
    main()
