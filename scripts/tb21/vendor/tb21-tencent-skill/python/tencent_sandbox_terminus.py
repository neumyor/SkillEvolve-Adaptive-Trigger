"""Terminus-2 model backend that makes provider calls inside Tencent E2B."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import shlex
import uuid
from pathlib import Path
from typing import Any

from harbor.agents.terminus_2.terminus_2 import Terminus2
from harbor.environments.base import BaseEnvironment
from harbor.llms.base import BaseLLM, LLMResponse, OutputLengthExceededError
from harbor.models.metric import UsageInfo


def read_streamed_completion(response):
    """Consume provider SSE, rejecting missing DONE and empty visible content."""
    import json
    import time
    content, reasoning, data_lines = [], [], []
    result, finish, done = {}, None, False
    started = time.time()
    metrics = {"chunks": 0}
    for raw_line in response:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        if line or not data_lines:
            continue
        data = "\n".join(data_lines)
        data_lines.clear()
        if data == "[DONE]":
            done = True
            break
        event = json.loads(data)
        if event.get("error"):
            raise RuntimeError("Provider SSE error: " + json.dumps(event["error"]))
        metrics["chunks"] += 1
        metrics.setdefault("first_chunk_seconds", time.time() - started)
        result.update({k: event[k] for k in ("id", "model", "usage") if k in event})
        choice = (event.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        if delta.get("content"):
            metrics.setdefault("first_content_seconds", time.time() - started)
            content.append(delta["content"])
        if delta.get("reasoning_content"):
            reasoning.append(delta["reasoning_content"])
        if choice.get("finish_reason") is not None:
            finish = choice["finish_reason"]
    if not done:
        raise RuntimeError("Provider stream ended without DONE")
    if not content and finish != "length":
        raise RuntimeError("Provider stream has no visible content")
    metrics.update(finish_reason=finish, total_seconds=time.time() - started)
    result.update(choices=[{"index": 0, "finish_reason": finish, "message": {
        "role": "assistant", "content": "".join(content), "reasoning_content": "".join(reasoning)}}],
        stream_metrics=metrics)
    return result


class E2BSandboxLLM(BaseLLM):
    _RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
    _RETRY_DELAYS_SEC = (5, 10, 20, 40, 60)

    def __init__(
        self,
        environment: BaseEnvironment,
        logs_dir: Path,
        model_name: str,
        api_base: str,
        max_input_tokens: int,
        max_output_tokens: int,
        llm_call_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._environment = environment
        self._logs_dir = logs_dir
        self._model_name = model_name.removeprefix("openai/")
        self._api_base = api_base.rstrip("/")
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._call_kwargs = llm_call_kwargs or {}

    def get_model_context_limit(self) -> int:
        return self._max_input_tokens

    def get_model_output_limit(self) -> int | None:
        return self._max_output_tokens

    def _append_jsonl(self, name: str, value: dict[str, Any]) -> None:
        path = self._logs_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")

    async def _sandbox_file_operation(self, operation: Any, operation_name: str) -> Any:
        reconnect = getattr(self._environment, "run_with_e2b_reconnect", None)
        if reconnect is not None:
            return await reconnect(operation, operation_name=operation_name)
        return await operation()

    async def call(
        self,
        prompt: str,
        message_history: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        messages = list(message_history or [])
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": self._max_output_tokens,
        }
        for key in ("temperature", "top_p"):
            if key in self._call_kwargs:
                payload[key] = self._call_kwargs[key]
        if response_format is not None:
            payload["response_format"] = response_format
        extra_body = self._call_kwargs.get("extra_body")
        if isinstance(extra_body, dict):
            payload.update(extra_body)
        payload["stream"] = True

        request_id = uuid.uuid4().hex
        remote_request = f"/tmp/tb21-model-request-{request_id}.json"
        request_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await self._sandbox_file_operation(
            lambda: self._environment._sandbox.files.write(  # type: ignore[attr-defined]
                remote_request, request_payload, user="root"
            ),
            "files.write",
        )
        self._append_jsonl("raw_model_requests.jsonl", {"request_id": request_id, **payload})

        response: dict[str, Any] = {}
        status = 0
        try:
            for attempt in range(1, len(self._RETRY_DELAYS_SEC) + 2):
                remote_response = f"/tmp/tb21-model-response-{request_id}-{attempt}.json"
                runner = inspect.getsource(read_streamed_completion) + f"""\nimport json, os, socket, urllib.error, urllib.request
request_path = {remote_request!r}
response_path = {remote_response!r}
body = open(request_path, 'rb').read()
request = urllib.request.Request(
    {self._api_base + '/chat/completions'!r},
    data=body,
    headers={{'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'], 'Content-Type': 'application/json'}},
    method='POST',
)
try:
    with urllib.request.urlopen(request, timeout=600) as response:
        status = response.status
        if 'text/event-stream' not in response.headers.get('Content-Type', ''):
            raise RuntimeError('Provider did not return SSE')
        raw = json.dumps(read_streamed_completion(response)).encode('utf-8')
        retry_after = response.headers.get('Retry-After')
except urllib.error.HTTPError as error:
    status = error.code
    raw = error.read()
    retry_after = error.headers.get('Retry-After') if error.headers else None
    transport_error = None
except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError, RuntimeError) as error:
    status = 0
    raw = b''
    retry_after = None
    transport_error = f'{{type(error).__name__}}: {{error}}'
else:
    transport_error = None
open(response_path, 'w', encoding='utf-8').write(json.dumps({{
    'status': status,
    'retry_after': retry_after,
    'transport_error': transport_error,
    'body': raw.decode('utf-8', errors='replace'),
}}))
"""
                command = "python3 -c " + shlex.quote(runner)
                result = await self._environment.exec(
                    command,
                    env={"OPENAI_API_KEY": os.environ["OPENAI_API_KEY"]},
                    timeout_sec=620,
                    user="root",
                )
                if result.return_code == 0:
                    raw_envelope = await self._sandbox_file_operation(
                        lambda: self._environment._sandbox.files.read(  # type: ignore[attr-defined]
                            remote_response, format="bytes", user="root"
                        ),
                        "files.read",
                    )
                    envelope = json.loads(raw_envelope)
                else:
                    envelope = {
                        "status": 0,
                        "retry_after": None,
                        "transport_error": result.stderr or result.stdout or "sandbox runner failed",
                        "body": "",
                    }

                status = int(envelope.get("status") or 0)
                body = envelope.get("body") or ""
                try:
                    parsed = json.loads(body) if body else {}
                    response = parsed if isinstance(parsed, dict) else {"response": parsed}
                except json.JSONDecodeError:
                    response = {"raw_response_text": body}

                self._append_jsonl(
                    "raw_model_responses.jsonl",
                    {
                        "request_id": request_id,
                        "attempt": attempt,
                        "http_status": status,
                        "retry_after": envelope.get("retry_after"),
                        "transport_error": envelope.get("transport_error"),
                        **response,
                    },
                )
                await self._environment.exec(
                    f"rm -f {shlex.quote(remote_response)}",
                    user="root",
                )

                retryable = status in self._RETRYABLE_HTTP_STATUSES or status == 0
                if not retryable or attempt > len(self._RETRY_DELAYS_SEC):
                    break
                delay = self._retry_delay(attempt, envelope.get("retry_after"))
                await asyncio.sleep(delay)
        finally:
            await self._environment.exec(
                f"rm -f {shlex.quote(remote_request)}",
                user="root",
            )

        if status >= 300:
            raise RuntimeError(f"Tencent sandbox model request failed with HTTP {status}: {response}")
        if status == 0:
            raise RuntimeError(f"Tencent sandbox model request failed after retries: {response}")
        choice = response["choices"][0]
        message = choice.get("message") or {}
        if choice.get("finish_reason") == "length":
            raise OutputLengthExceededError(
                "Model reached max_tokens",
                truncated_response=message.get("content") or "",
            )
        usage = response.get("usage") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        return LLMResponse(
            content=message.get("content") or "",
            reasoning_content=message.get("reasoning_content"),
            model_name=response.get("model"),
            response_id=response.get("id"),
            usage=UsageInfo(
                prompt_tokens=usage.get("prompt_tokens", 0) or 0,
                completion_tokens=usage.get("completion_tokens", 0) or 0,
                cache_tokens=prompt_details.get("cached_tokens", 0) or 0,
                cost_usd=0.0,
            ),
        )

    def _retry_delay(self, attempt: int, retry_after: Any) -> float:
        try:
            provider_delay = float(retry_after)
        except (TypeError, ValueError):
            provider_delay = 0
        if 0 < provider_delay <= 300:
            return provider_delay
        return float(self._RETRY_DELAYS_SEC[attempt - 1])


class TencentSandboxTerminus2(Terminus2):
    """Terminus-2 whose LLM HTTP calls execute in its Tencent sandbox."""

    def __init__(
        self,
        *args: Any,
        api_base: str,
        model_info: dict[str, Any] | None = None,
        llm_call_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._tencent_api_base = api_base
        self._tencent_model_info = model_info or {}
        self._tencent_llm_call_kwargs = llm_call_kwargs or {}
        super().__init__(
            *args,
            api_base=api_base,
            model_info=model_info,
            llm_call_kwargs=llm_call_kwargs,
            **kwargs,
        )

    async def setup(self, environment: BaseEnvironment) -> None:
        self._llm = E2BSandboxLLM(
            environment=environment,
            logs_dir=self.logs_dir,
            model_name=self._model_name,
            api_base=self._tencent_api_base,
            max_input_tokens=int(self._tencent_model_info.get("max_input_tokens", 131072)),
            max_output_tokens=int(self._tencent_model_info.get("max_output_tokens", 65536)),
            llm_call_kwargs=self._tencent_llm_call_kwargs,
        )
        await super().setup(environment)


class TencentSkillTerminus2(TencentSandboxTerminus2):
    """Tencent-routed Terminus-2 that lets Harbor discover per-skill folders.

    The TaskSkill environment mounts one task directory at
    ``/opt/openclaw-skills/<task>/``. Each accepted skill is a
    ``<skill>/SKILL.md`` directory under it. Terminus-2's own
    ``_build_skills_section`` scans ``skills_dir`` at depth two, parses
    the YAML frontmatter, and appends ``<available_skills>`` to the
    initial prompt. Pointing ``skills_dir`` at the task directory is the
    whole activation; there is no single SKILL.md to name in the prompt.
    """

    def __init__(
        self,
        *args: Any,
        skills_dir: str = "/opt/openclaw-skills",
        skill_read_suffix: str = (
            "If an <available_skills> section is present, read the "
            "location of a relevant skill before executing task commands."
        ),
        **kwargs: Any,
    ) -> None:
        self._skill_read_suffix = skill_read_suffix.strip()
        self._selected_skills_dir = skills_dir.rstrip("/")
        super().__init__(*args, skills_dir=skills_dir, **kwargs)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: Any,
    ) -> None:
        get_task_skill = getattr(environment, "_task_skill_source", None)
        if callable(get_task_skill):
            source, target = get_task_skill()
            self.skills_dir = str(target)
            self._selected_skills_dir = str(target)
            self._append_skill_activation(str(target), str(source))
        else:
            self.skills_dir = self._selected_skills_dir
            self._append_skill_activation(self._selected_skills_dir, "")
        instruction = f"{instruction.rstrip()}\n\n{self._skill_read_suffix}"
        await super().run(instruction, environment, context)

    def _append_skill_activation(self, skills_dir: str,
                                 source_dir: str) -> None:
        path = self.logs_dir / "skill_activation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "skills_dir": skills_dir,
            "source_dir": source_dir,
            "load_stage": "native_discovery",
        }) + "\n")
