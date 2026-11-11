"""``HttpRequest``: the HTTP flavour of :class:`~hexagenpy.core.context.RequestContext`.

Everything is parsed lazily from the ASGI scope, so requests that never read headers,
cookies or the body pay nothing for them.
"""

from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qsl

from hexagenpy.core.context import RequestContext

__all__ = ["HttpError", "HttpRequest"]

Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]


class HttpError(Exception):
    """An HTTP-level failure (malformed request, body too large, unsupported media type)."""

    def __init__(self, status: int, detail: str, *, code: str = "http_error") -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code


class HttpRequest(RequestContext):
    __slots__ = ("_body", "_cookies", "_max_body", "_query", "_receive", "path_params", "scope")

    def __init__(
        self,
        scope: MutableMapping[str, Any],
        receive: Receive,
        path_params: Mapping[str, str] | None = None,
        *,
        max_body_size: int = 1 << 20,
    ) -> None:
        super().__init__("http")
        self.scope = scope
        self._receive = receive
        self.path_params: Mapping[str, str] = path_params or {}
        self._max_body = max_body_size
        self._body: bytes | None = None
        self._query: dict[str, list[str]] | None = None
        self._cookies: dict[str, str] | None = None

    # ------------------------------------------------------------------ request line

    @property
    def method(self) -> str:
        method: str = self.scope["method"]
        return method

    @property
    def path(self) -> str:
        path: str = self.scope["path"]
        return path

    @property
    def client(self) -> tuple[str, int] | None:
        client: tuple[str, int] | None = self.scope.get("client")
        return client

    # ------------------------------------------------------------------ lazily parsed parts

    def _load_headers(self) -> Mapping[str, str]:
        headers: dict[str, str] = {}
        for raw_name, raw_value in self.scope.get("headers", ()):
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
            headers[name] = f"{headers[name]}, {value}" if name in headers else value
        return headers

    @property
    def query(self) -> Mapping[str, list[str]]:
        """Query parameters; repeated keys keep every value in order."""
        if self._query is None:
            parsed: dict[str, list[str]] = {}
            raw = self.scope.get("query_string", b"").decode("latin-1")
            for key, value in parse_qsl(raw, keep_blank_values=True):
                parsed.setdefault(key, []).append(value)
            self._query = parsed
        return self._query

    @property
    def cookies(self) -> Mapping[str, str]:
        if self._cookies is None:
            jar: SimpleCookie = SimpleCookie()
            header = self.headers.get("cookie")
            if header:
                try:
                    jar.load(header)
                except Exception:  # malformed cookies are ignored, as browsers do
                    jar = SimpleCookie()
            self._cookies = {key: morsel.value for key, morsel in jar.items()}
        return self._cookies

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    async def body(self) -> bytes:
        """Read the whole body once (cached); rejects bodies above ``max_body_size``."""
        if self._body is not None:
            return self._body
        declared = self.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_body:
            raise HttpError(413, "request body too large", code="payload_too_large")
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await self._receive()
            if message["type"] == "http.disconnect":
                raise HttpError(400, "client disconnected", code="client_disconnected")
            chunk: bytes = message.get("body", b"")
            size += len(chunk)
            if size > self._max_body:
                raise HttpError(413, "request body too large", code="payload_too_large")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        self._body = b"".join(chunks)
        return self._body
