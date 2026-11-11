"""``HttpTestClient``: in-process HTTP client for an ASGI app (no sockets, no extra deps).

::

    async with HttpTestClient(HttpApp(app)) as client:
        response = await client.post("/orders", json={"customer": "ACME", "lines": [...]})
        assert response.status == 201
        assert response.json()["id"] == 1
"""

import asyncio
import json as jsonlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlencode

import msgspec

from hexagenpy.transports.http.asgi import ASGIApp
from hexagenpy.transports.http.responses import Message

__all__ = ["HttpTestClient", "TestResponse"]


@dataclass(frozen=True, slots=True)
class TestResponse:
    __test__ = False

    status: int
    headers: Mapping[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode()

    def json(self) -> Any:
        return jsonlib.loads(self.content)

    def lines(self) -> list[Any]:
        """Decode an NDJSON (streaming) body."""
        return [jsonlib.loads(line) for line in self.content.splitlines() if line]


class HttpTestClient:
    """Drives the ASGI app directly, running its lifespan on enter/exit."""

    __test__ = False

    def __init__(self, app: ASGIApp, *, base_headers: Mapping[str, str] | None = None) -> None:
        self.app = app
        self.base_headers = dict(base_headers or {})
        self._to_app: asyncio.Queue[Message] = asyncio.Queue()
        self._from_app: asyncio.Queue[Message] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        scope = {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}
        self._task = asyncio.create_task(self.app(scope, self._to_app.get, self._from_app.put))
        await self._event("startup")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._event("shutdown")
        if self._task is not None:
            await self._task

    async def _event(self, event: str) -> None:
        await self._to_app.put({"type": f"lifespan.{event}"})
        reply = await self._from_app.get()
        if reply["type"] == f"lifespan.{event}.failed":
            raise RuntimeError(f"lifespan {event} failed: {reply.get('message')}")

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        content: bytes | None = None,
        query: Mapping[str, str | list[str]] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> TestResponse:
        all_headers = {**self.base_headers, **(headers or {})}
        body = content or b""
        if json is not None:
            body = msgspec.json.encode(json)
            all_headers.setdefault("content-type", "application/json")
        if body:
            all_headers["content-length"] = str(len(body))
        path, _, raw_query = path.partition("?")
        if query:
            raw_query = urlencode(query, doseq=True)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": raw_query.encode(),
            "headers": [
                (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in all_headers.items()
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "state": {},
        }
        return await _call(self.app, scope, body)

    async def get(self, path: str, **kwargs: Any) -> TestResponse:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> TestResponse:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> TestResponse:
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> TestResponse:
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> TestResponse:
        return await self.request("DELETE", path, **kwargs)


async def _call(app: ASGIApp, scope: dict[str, Any], body: bytes) -> TestResponse:
    received = False
    status = 0
    headers: dict[str, str] = {}
    chunks: list[bytes] = []

    async def receive() -> Message:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
            for key, value in message.get("headers", []):
                name = key.decode("latin-1").lower()
                text = value.decode("latin-1")
                headers[name] = f"{headers[name]}, {text}" if name in headers else text
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return TestResponse(status, headers, b"".join(chunks))
