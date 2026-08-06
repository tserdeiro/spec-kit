"""Loopback-only GraphQL fake used by tests; never imported by the runtime."""

from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any


@dataclass(frozen=True)
class FakeGraphQLResponse:
    """One deterministic response returned by the loopback GraphQL fixture."""

    body: dict[str, Any] | str | bytes
    status: int = 200
    headers: dict[str, str] | None = None
    delay_seconds: float = 0.0


class FakeGraphQLServer(AbstractContextManager["FakeGraphQLServer"]):
    """Loopback GraphQL fixture with headers, paging sequences, and request audit."""

    def __init__(
        self,
        response: dict[str, Any] | str | bytes | None = None,
        status: int = 200,
        *,
        responses: list[FakeGraphQLResponse] | None = None,
    ) -> None:
        initial = response if response is not None else {"data": {"viewer": {"id": "test"}}}
        self.responses = responses or [FakeGraphQLResponse(initial, status)]
        self.requests: list[dict[str, Any]] = []
        self.request_headers: list[dict[str, str]] = []
        self.request_methods: list[str] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def endpoint(self) -> str:
        if self._server is None:
            raise RuntimeError("fake server is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}/graphql"

    def __enter__(self) -> "FakeGraphQLServer":
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = {"invalid": True}
                fake.requests.append({"path": self.path, "payload": payload})
                fake.request_headers.append({key: value for key, value in self.headers.items()})
                fake.request_methods.append(self.command)
                response_index = min(len(fake.requests) - 1, len(fake.responses) - 1)
                configured = fake.responses[response_index]
                if configured.delay_seconds:
                    time.sleep(configured.delay_seconds)
                if isinstance(configured.body, bytes):
                    encoded = configured.body
                elif isinstance(configured.body, str):
                    encoded = configured.body.encode("utf-8")
                else:
                    encoded = json.dumps(configured.body).encode("utf-8")
                self.send_response(configured.status)
                self.send_header("Content-Type", "application/json")
                for key, value in (configured.headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    @property
    def has_non_query_request(self) -> bool:
        """Expose a simple audit assertion without logging request contents."""

        return any(not str(request["payload"].get("query", "")).lstrip().startswith("query ") for request in self.requests)
