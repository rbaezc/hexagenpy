"""Minimal in-process ASGI driver: no sockets, only framework overhead is measured."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from benchmarks.scenarios import Scenario

Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[MutableMapping[str, Any], Receive, Send], Awaitable[None]]


def build_scope(scenario: Scenario) -> dict[str, Any]:
    path, _, query = scenario.path.partition("?")
    headers = [(b"host", b"bench.local"), *scenario.headers]
    if scenario.body:
        headers.append((b"content-length", str(len(scenario.body)).encode()))
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": scenario.method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query.encode(),
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
        "state": {},
    }


async def call(app: ASGIApp, scenario: Scenario) -> tuple[int, bytes]:
    """Perform one request and return (status, body)."""
    sent = False
    status = 0
    chunks: list[bytes] = []

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": scenario.body, "more_body": False}

    async def send(message: Message) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(build_scope(scenario), receive, send)
    return status, b"".join(chunks)


class Lifespan:
    """Runs the ASGI lifespan protocol so apps that need startup work correctly."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._outbox: asyncio.Queue[Message] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def _run(self) -> None:
        scope = {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}
        try:
            await self._app(scope, self._inbox.get, self._outbox.put)
        except Exception:  # apps without lifespan support may raise
            await self._outbox.put({"type": "lifespan.unsupported"})

    async def __aenter__(self) -> "Lifespan":
        self._task = asyncio.create_task(self._run())
        await self._inbox.put({"type": "lifespan.startup"})
        message = await self._outbox.get()
        if message["type"] == "lifespan.startup.failed":
            raise RuntimeError(f"lifespan startup failed: {message.get('message')}")
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._inbox.put({"type": "lifespan.shutdown"})
        if self._task is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._outbox.get(), timeout=2)
            self._task.cancel()
