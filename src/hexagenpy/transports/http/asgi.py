"""``HttpApp``: exposes an :class:`~hexagenpy.App` over HTTP as an ASGI 3 application.

::

    app = App(slices=[orders.module])
    http = HttpApp(app, middleware=[cors(allow_origins=["https://example.com"])])

    # granian --interface asgi myproject.main:http      (or: uvicorn myproject.main:http)
"""

from collections.abc import Callable, MutableMapping, Sequence
from typing import Any

from hexagenpy.core.app import App
from hexagenpy.core.error_mapping import ErrorInfo
from hexagenpy.errors import ErrorKind
from hexagenpy.transports.http.endpoint import HttpEndpoint, RawRoute, run_endpoint
from hexagenpy.transports.http.openapi import build_openapi, docs_html
from hexagenpy.transports.http.request import HttpRequest, Receive
from hexagenpy.transports.http.responses import Send, encode, send_bytes, send_problem
from hexagenpy.transports.http.router import Router

__all__ = ["ASGIApp", "HttpApp", "Middleware"]

Scope = MutableMapping[str, Any]
ASGIApp = Callable[[Scope, Receive, Send], Any]
Middleware = Callable[[ASGIApp], ASGIApp]
Target = HttpEndpoint | RawRoute


class HttpApp:
    def __init__(
        self,
        app: App,
        *,
        middleware: Sequence[Middleware] = (),
        openapi_url: str | None = "/openapi.json",
        docs_url: str | None = "/docs",
        max_body_size: int = 1 << 20,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        self.app = app
        self.max_body_size = max_body_size
        self.title = title or app.name
        self.description = description
        self.router: Router[Target] = Router()
        self.endpoints: list[HttpEndpoint] = []
        for op in app.contracts.for_transport("http"):
            endpoint = HttpEndpoint.build(app, op)
            self.endpoints.append(endpoint)
            self.router.add(endpoint.binding.method, endpoint.binding.path, endpoint)
        self._openapi: dict[str, Any] | None = None
        if openapi_url is not None:
            self.router.add("GET", openapi_url, RawRoute(self._serve_openapi))
            if docs_url is not None:
                page = docs_html(self.title, openapi_url).encode()
                self.router.add(
                    "GET", docs_url, RawRoute(_static(page, b"text/html; charset=utf-8"))
                )
        self._owns_lifecycle = False
        asgi: ASGIApp = self._dispatch
        for factory in reversed(middleware):
            asgi = factory(asgi)
        self._asgi = asgi

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._asgi(scope, receive, send)

    def openapi(self) -> dict[str, Any]:
        """The OpenAPI 3.1 document (built once, from the Contract IR)."""
        if self._openapi is None:
            self._openapi = build_openapi(self.app, self.endpoints, self.title, self.description)
        return self._openapi

    # ------------------------------------------------------------------ dispatch

    async def _dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind == "http":
            await self._http(scope, receive, send)
        elif kind == "lifespan":
            await self._lifespan(receive, send)
        else:  # websockets arrive in Phase 5
            await send({"type": "websocket.close", "code": 1000})

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        match = self.router.match(scope["method"], scope["path"])
        target = match.target
        if target is None:
            if match.allowed:
                info = ErrorInfo(
                    ErrorKind.VALIDATION,
                    "method_not_allowed",
                    f"{scope['method']} is not allowed on {scope['path']}",
                )
                allow = ", ".join(match.allowed).encode()
                await send_problem(send, info, status=405, headers=[(b"allow", allow)])
            else:
                info = ErrorInfo(
                    ErrorKind.NOT_FOUND, "route_not_found", f"no route for {scope['path']}"
                )
                await send_problem(send, info)
            return
        request = HttpRequest(scope, receive, match.params, max_body_size=self.max_body_size)
        if isinstance(target, RawRoute):
            await target.handler(request, send)
        elif not self.app.started:
            info = ErrorInfo(
                ErrorKind.UNAVAILABLE,
                "app_not_started",
                "the application has not started; is the ASGI lifespan enabled?",
            )
            await send_problem(send, info)
        else:
            await run_endpoint(self.app, target, request, send)

    async def _serve_openapi(self, request: HttpRequest, send: Send) -> None:
        await send_bytes(send, 200, encode(self.openapi()))

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    if not self.app.started:
                        await self.app.start()
                        self._owns_lifecycle = True
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": repr(exc)})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                try:
                    if self._owns_lifecycle:
                        await self.app.stop()
                except Exception as exc:
                    await send({"type": "lifespan.shutdown.failed", "message": repr(exc)})
                    return
                await send({"type": "lifespan.shutdown.complete"})
                return


def _static(body: bytes, content_type: bytes) -> Callable[[HttpRequest, Send], Any]:
    async def handler(request: HttpRequest, send: Send) -> None:
        await send_bytes(send, 200, body, content_type=content_type)

    return handler
