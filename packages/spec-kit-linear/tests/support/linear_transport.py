"""In-memory urllib-compatible transport for deterministic client unit tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryResponse(AbstractContextManager["MemoryResponse"]):
    body: object
    status: int = 200
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.headers = self.headers or {"Content-Type": "application/json"}

    def read(self, amount: int = -1) -> bytes:
        if isinstance(self.body, bytes):
            return self.body if amount < 0 else self.body[:amount]
        if isinstance(self.body, str):
            encoded = self.body.encode("utf-8")
            return encoded if amount < 0 else encoded[:amount]
        encoded = json.dumps(self.body).encode("utf-8")
        return encoded if amount < 0 else encoded[:amount]

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "MemoryResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class ScriptedOpener:
    """Record each request and return a prescribed response or exception."""

    def __init__(self, outcomes: list[MemoryResponse | Exception]) -> None:
        self._outcomes: Iterator[MemoryResponse | Exception] = iter(outcomes)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: Any, *, timeout: float) -> MemoryResponse:
        payload = json.loads(request.data.decode("utf-8"))
        self.requests.append(
            {
                "method": request.get_method(),
                "headers": {key: value for key, value in request.header_items()},
                "payload": payload,
                "timeout": timeout,
            }
        )
        outcome = next(self._outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
