"""Parameter sources, streaming, lifespan and other transport behaviour."""

from collections.abc import AsyncIterator, Callable, MutableMapping
from typing import Annotated, Any

import pytest

from hexagenpy import App, Controller, Meta, Model, Module, RequestContext, Scope, endpoint, provide
from hexagenpy.errors import ContractError
from hexagenpy.testing.http import HttpTestClient
from hexagenpy.transports.http import Body, Cookie, Header, HttpApp, HttpRequest, Path, Query


class Filters(Model):
    tags: list[str]


class Echo(Controller, prefix="/echo"):
    @endpoint(http="GET /params/{item_id}")
    async def params(
        self,
        item_id: Annotated[int, Path("item_id", description="Item")],
        tags: list[str],
        request_id: Annotated[str | None, Header()] = None,
        trace: Annotated[str | None, Header("X-Trace")] = None,
        session: Annotated[str | None, Cookie()] = None,
        page_size: Annotated[int, Query("page-size"), Meta(le=50)] = 10,
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "tags": tags,
            "request_id": request_id,
            "trace": trace,
            "session": session,
            "page_size": page_size,
        }

    @endpoint(http="POST /filters")
    async def filters(self, filters: Annotated[Filters, Body(description="Filters")]) -> int:
        return len(filters.tags)

    @endpoint(http="PUT /optional-body")
    async def optional_body(self, data: Filters | None = None) -> bool:
        return data is None

    @endpoint(http="DELETE /things/{id}")
    async def delete(self, id: int) -> None:
        return None

    @endpoint(http="GET /stream")
    async def stream(self, n: int) -> AsyncIterator[dict[str, int]]:
        for i in range(n):
            yield {"i": i}

    @endpoint(http="GET /broken-stream")
    async def broken_stream(self) -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("stream failed")

    @endpoint(http="GET /boom")
    async def boom(self) -> int:
        raise RuntimeError("secret detail")


class WhoAmI:
    def __init__(self, ctx: RequestContext) -> None:
        self.ctx = ctx


class Context(Controller):
    def __init__(self, who: WhoAmI) -> None:
        self.who = who

    @endpoint(http="GET /whoami")
    async def whoami(self) -> dict[str, Any]:
        ctx = self.who.ctx
        assert isinstance(ctx, HttpRequest)
        return {
            "transport": ctx.transport,
            "path": ctx.path,
            "agent": ctx.headers["user-agent"],
            "client": list(ctx.client or ()),
        }


def make_app(**kwargs: Any) -> HttpApp:
    module = Module(
        "echo", providers=[provide(WhoAmI, scope=Scope.REQUEST)], controllers=[Echo, Context]
    )
    return HttpApp(App(slices=[module]), **kwargs)


@pytest.fixture
async def client() -> AsyncIterator[HttpTestClient]:
    async with HttpTestClient(make_app()) as test_client:
        yield test_client


async def test_every_parameter_source(client: HttpTestClient) -> None:
    response = await client.get(
        "/echo/params/7?tags=a&tags=b&page-size=20",
        headers={"request-id": "r-1", "x-trace": "t-1", "cookie": "session=s-1; other=x"},
    )
    assert response.json() == {
        "id": 7,
        "tags": ["a", "b"],
        "request_id": "r-1",
        "trace": "t-1",
        "session": "s-1",
        "page_size": 20,
    }


async def test_parameter_errors_name_the_wire_location(client: HttpTestClient) -> None:
    missing = await client.get("/echo/params/7")
    assert missing.json()["errors"] == [
        {"location": "query", "field": "tags", "message": "Object missing required field `tags`"}
    ]
    too_big = await client.get("/echo/params/7?tags=a&page-size=500")
    assert too_big.json()["errors"][0]["field"] == "page-size"
    assert (await client.get("/echo/params/7?tags=a", headers={"cookie": "bad;;=="})).status == 200


async def test_body_marker_optional_body_and_void(client: HttpTestClient) -> None:
    assert (await client.post("/echo/filters", json={"tags": ["x", "y"]})).json() == 2
    assert (await client.put("/echo/optional-body")).json() is True
    assert (await client.put("/echo/optional-body", json={"tags": []})).json() is False
    deleted = await client.delete("/echo/things/1")
    assert (deleted.status, deleted.content) == (204, b"")
    assert "content-type" not in deleted.headers


async def test_streaming_ndjson(client: HttpTestClient) -> None:
    response = await client.get("/echo/stream?n=3")
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.lines() == [{"i": 0}, {"i": 1}, {"i": 2}]


async def test_error_mid_stream_ends_the_response(client: HttpTestClient) -> None:
    response = await client.get("/echo/broken-stream")
    assert (response.status, response.lines()) == (200, [1])


async def test_internal_errors_do_not_leak(client: HttpTestClient) -> None:
    response = await client.get("/echo/boom")
    assert response.status == 500
    assert response.json()["detail"] == "internal server error"
    assert b"secret" not in response.content


async def test_request_context_is_injected(client: HttpTestClient) -> None:
    response = await client.get("/whoami", headers={"user-agent": "pytest"})
    assert response.json() == {
        "transport": "http",
        "path": "/whoami",
        "agent": "pytest",
        "client": ["testclient", 50000],
    }


async def test_body_size_limit() -> None:
    async with HttpTestClient(make_app(max_body_size=10)) as client:
        response = await client.post("/echo/filters", json={"tags": ["a" * 20]})
        assert (response.status, response.json()["code"]) == (413, "payload_too_large")


async def test_body_limit_without_content_length_and_disconnect() -> None:
    http = make_app(max_body_size=5)
    request = HttpRequest(
        {"type": "http", "headers": []}, _chunks([b"abc", b"def"]), max_body_size=5
    )
    with pytest.raises(Exception, match="too large"):
        await request.body()
    gone = HttpRequest({"type": "http", "headers": []}, _disconnect)
    with pytest.raises(Exception, match="disconnected"):
        await gone.body()
    ok = HttpRequest({"type": "http", "headers": []}, _chunks([b"ab", b"c"]))
    assert await ok.body() == b"abc"
    assert await ok.body() == b"abc"  # cached
    assert http.max_body_size == 5


def _chunks(chunks: list[bytes]) -> Callable[[], Any]:
    pending = list(chunks)

    async def receive() -> dict[str, Any]:
        body = pending.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(pending)}

    return receive


async def _disconnect() -> dict[str, Any]:
    return {"type": "http.disconnect"}


async def test_app_not_started_returns_503() -> None:
    client = HttpTestClient(make_app())  # no lifespan: not entered
    response = await client.get("/echo/stream?n=1")
    assert (response.status, response.json()["code"]) == (503, "app_not_started")


async def test_lifespan_failures_are_reported() -> None:
    http = make_app()

    @http.app.on_startup
    def fail() -> None:
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError, match="lifespan startup failed: RuntimeError"):
        async with HttpTestClient(http):
            pass


async def test_lifespan_shutdown_failure_and_external_start() -> None:
    http = make_app()

    @http.app.on_shutdown
    def fail() -> None:
        raise RuntimeError("flush failed")

    with pytest.raises(RuntimeError, match="lifespan shutdown failed"):
        async with HttpTestClient(http):
            pass

    other = make_app()
    await other.app.start()  # started by someone else: lifespan must not stop it
    async with HttpTestClient(other):
        pass
    assert other.app.started
    await other.app.container.aclose()


async def test_websocket_scope_is_closed() -> None:
    sent: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    await make_app()({"type": "websocket"}, _disconnect, send)
    assert sent == [{"type": "websocket.close", "code": 1000}]


async def test_middleware_wraps_in_declaration_order() -> None:
    calls: list[str] = []

    def tag(name: str) -> Any:
        def factory(app: Any) -> Any:
            async def middleware(scope: Any, receive: Any, send: Any) -> None:
                calls.append(name)
                await app(scope, receive, send)

            return middleware

        return factory

    async with HttpTestClient(make_app(middleware=[tag("outer"), tag("inner")])) as client:
        await client.get("/echo/stream?n=0")
    assert calls[-2:] == ["outer", "inner"]


def test_contract_errors_at_construction() -> None:
    def app_with(controller: type[Controller]) -> None:
        HttpApp(App(slices=[Module("bad", controllers=[controller])]))

    class TwoBodies(Controller):
        @endpoint(http="POST /x")
        async def f(self, a: Filters, b: Filters) -> int:
            return 1

    class GetWithBody(Controller):
        @endpoint(http="GET /x")
        async def f(self, a: Filters) -> int:
            return 1

    class PathNotInTemplate(Controller):
        @endpoint(http="GET /x")
        async def f(self, a: Annotated[int, Path()]) -> int:
            return 1

    with pytest.raises(ContractError, match="only one body parameter"):
        app_with(TwoBodies)
    with pytest.raises(ContractError, match="GET endpoints cannot take a body"):
        app_with(GetWithBody)
    with pytest.raises(ContractError, match=r"no \{a\} in the path"):
        app_with(PathNotInTemplate)


async def test_openapi_and_docs_can_be_disabled() -> None:
    async with HttpTestClient(make_app(openapi_url=None)) as client:
        assert (await client.get("/openapi.json")).status == 404
    async with HttpTestClient(make_app(docs_url=None)) as client:
        assert (await client.get("/docs")).status == 404
        assert (await client.get("/openapi.json")).status == 200
