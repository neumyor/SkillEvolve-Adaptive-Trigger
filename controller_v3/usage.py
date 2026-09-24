"""Shared token accounting for paired Controller experiments."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping


@dataclass
class TokenRecord:
    condition: str
    method: str
    stage: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    api_call: int = 1
    retry_count: int = 0
    cache_hit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class TokenLedger:
    def __init__(self, *, condition: str, method: str):
        self.condition = condition
        self.method = method
        self.records: list[TokenRecord] = []
        self._untracked: list[dict[str, str]] = []
        self._stage = "unknown"
        self._lock = threading.RLock()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        previous = self._stage
        self._stage = name
        try:
            yield
        finally:
            self._stage = previous

    def add(
        self,
        usage: dict[str, Any] | None,
        *,
        stage: str | None = None,
        metadata: dict[str, Any] | None = None,
        api_call: int = 1,
    ) -> TokenRecord:
        with self._lock:
            if not usage or not any(key in usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
                self.mark_untracked(stage or self._stage, "response did not include token usage")
            usage = usage or {}
            prompt = int(usage.get("prompt_tokens", 0) or 0)
            completion = int(usage.get("completion_tokens", 0) or 0)
            total = int(usage.get("total_tokens", prompt + completion) or prompt + completion)
            record = TokenRecord(
                condition=self.condition,
                method=self.method,
                stage=stage or self._stage,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                api_call=max(1, int(api_call)),
                metadata=dict(metadata or {}),
            )
            self.records.append(record)
            return record

    def mark_untracked(self, stage: str, reason: str = "") -> None:
        """Record a native call whose usage is outside this ledger."""
        with self._lock:
            self._untracked.append({"stage": str(stage), "reason": str(reason)})

    def merge(self, other: "TokenLedger | Mapping[str, Any]") -> None:
        payload = other.to_dict() if isinstance(other, TokenLedger) else dict(other)
        for raw in payload.get("records", []):
            if not isinstance(raw, Mapping):
                continue
            fields = {key: raw[key] for key in TokenRecord.__dataclass_fields__ if key in raw}
            self.records.append(TokenRecord(**fields))
        self._untracked.extend(dict(item) for item in payload.get("untracked", []) if isinstance(item, Mapping))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TokenLedger":
        ledger = cls(
            condition=str(payload.get("condition", "unknown")),
            method=str(payload.get("method", "unknown")),
        )
        ledger.merge(payload)
        return ledger

    def save(self, path: str | Path) -> None:
        target = Path(path)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def summary(self) -> dict[str, Any]:
        return {
            "prompt_tokens": sum(r.prompt_tokens for r in self.records),
            "completion_tokens": sum(r.completion_tokens for r in self.records),
            "total_tokens": sum(r.total_tokens for r in self.records),
            "api_calls": sum(r.api_call for r in self.records),
            "by_stage": {
                stage: {
                    "prompt_tokens": sum(r.prompt_tokens for r in self.records if r.stage == stage),
                    "completion_tokens": sum(r.completion_tokens for r in self.records if r.stage == stage),
                    "total_tokens": sum(r.total_tokens for r in self.records if r.stage == stage),
                    "api_calls": sum(r.api_call for r in self.records if r.stage == stage),
                }
                for stage in sorted({r.stage for r in self.records})
            },
            "untracked_calls": len(self._untracked),
            "untracked_stages": sorted({item["stage"] for item in self._untracked}),
            "cost_usable": not self._untracked,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "method": self.method,
            "records": [asdict(r) for r in self.records],
            "untracked": list(self._untracked),
            "summary": self.summary(),
        }


class LedgerLLM:
    """Proxy compatible with OpenAIChatAgent, adding each response to a ledger."""

    def __init__(self, client, ledger: TokenLedger):
        self.client = client
        self.ledger = ledger
        self.model = client.model
        self.base_url = client.base_url
        self.api_key = client.api_key

    @property
    def usage(self):
        return self.client.usage

    def stage(self, name: str):
        return self.ledger.stage(name)

    def respond(self, system: str, user: str, *, stage: str | None = None, metadata: dict[str, Any] | None = None):
        try:
            raw, usage = self.client.respond(system, user)
        except Exception as exc:
            self.ledger.mark_untracked(stage or "api", f"{type(exc).__name__}: response usage unavailable")
            raise
        for _ in range(int((usage or {}).get("failed_attempts", 0))):
            self.ledger.mark_untracked(stage or "api", "retry attempt usage unavailable")
        self.ledger.add(usage, stage=stage, metadata=metadata)
        return raw, usage
