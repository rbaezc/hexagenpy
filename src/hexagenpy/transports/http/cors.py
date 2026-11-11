"""CORS as a pure ASGI middleware.

::

    HttpApp(app, middleware=[cors(allow_origins=["https://app.example.com"],
                                  allow_credentials=True)])
"""

from collections.abc import Sequence
from typing import Any

from hexagenpy.transports.http.request import Receive
from hexagenpy.transports.http.responses import Message, Send

__all__ = ["CORSMiddleware", "cors"]

SAFE_HEADERS = ("accept", "accept-language", "content-language", "content-type")


class CORSMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        allow_origins: Sequence[str],
        allow_methods: Sequence[str] = ("GET", "POST", "PUT", "PATCH", "DELETE"),
        allow_headers: Sequence[str] = (),
        allow_credentials: bool = False,
        expose_headers: Sequence[str] = (),
        max_age: int = 600,
    ) -> None:
        self.app = app
        self.any_origin = "*" in allow_origins
        self.origins = frozenset(allow_origins)
        self.methods = ", ".join(m.upper() for m in allow_methods).encode()
        self.any_header = "*" in allow_headers
        self.headers = frozenset(h.lower() for h in (*SAFE_HEADERS, *allow_headers))
        self.credentials = allow_credentials
        self.expose = ", ".join(expose_headers).encode()
        self.max_age = str(max_age).encode()

    def _allowed(self, origin: str) -> bool:
        return self.any_origin or origin in self.origins

    def _origin_headers(self, origin: bytes) -> list[tuple[bytes, bytes]]:
        if self.any_origin and not self.credentials:
            return [(b"access-control-allow-origin", b"*")]
        headers = [(b"access-control-allow-origin", origin), (b"vary", b"Origin")]
        if self.credentials:
            headers.append((b"access-control-allow-credentials", b"true"))
        return headers

    async def __call__(self, scope: Any, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        origin = headers.get(b"origin")
        if origin is None:
            await self.app(scope, receive, send)
            return
        requested_method = headers.get(b"access-control-request-method")
        if scope["method"] == "OPTIONS" and requested_method is not None:
            await self._preflight(origin, headers.get(b"access-control-request-headers"), send)
            return
        if not self._allowed(origin.decode("latin-1")):
            await self.app(scope, receive, send)
            return
        extra = self._origin_headers(origin)
        if self.expose:
            extra.append((b"access-control-expose-headers", self.expose))

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        await self.app(scope, receive, send_with_cors)

    async def _preflight(self, origin: bytes, requested: bytes | None, send: Send) -> None:
        requested_headers = [
            h.strip().lower() for h in (requested or b"").decode("latin-1").split(",") if h.strip()
        ]
        headers_ok = self.any_header or all(h in self.headers for h in requested_headers)
        if not self._allowed(origin.decode("latin-1")) or not headers_ok:
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"text/plain"), (b"content-length", b"22")],
                }
            )
            await send({"type": "http.response.body", "body": b"CORS request forbidden"})
            return
        allow_headers = (
            (requested or b"") if self.any_header else ", ".join(sorted(self.headers)).encode()
        )
        response_headers = [
            *self._origin_headers(origin),
            (b"access-control-allow-methods", self.methods),
            (b"access-control-allow-headers", allow_headers),
            (b"access-control-max-age", self.max_age),
            (b"content-length", b"0"),
        ]
        await send({"type": "http.response.start", "status": 204, "headers": response_headers})
        await send({"type": "http.response.body", "body": b""})


def cors(
    *,
    allow_origins: Sequence[str],
    allow_methods: Sequence[str] = ("GET", "POST", "PUT", "PATCH", "DELETE"),
    allow_headers: Sequence[str] = (),
    allow_credentials: bool = False,
    expose_headers: Sequence[str] = (),
    max_age: int = 600,
) -> Any:
    """Middleware factory for :class:`HttpApp`'s ``middleware=[...]``."""

    def factory(app: Any) -> CORSMiddleware:
        return CORSMiddleware(
            app,
            allow_origins=allow_origins,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
            allow_credentials=allow_credentials,
            expose_headers=expose_headers,
            max_age=max_age,
        )

    return factory
