from collections.abc import MutableMapping
from typing import Any

from hexagenpy.testing.http import HttpTestClient
from hexagenpy.transports.http import HttpApp, cors
from tests.example.app import create_app

PREFLIGHT = {"access-control-request-method": "POST"}


def app_with(**options: Any) -> HttpApp:
    return HttpApp(create_app(), middleware=[cors(**options)])


async def test_simple_request_from_allowed_origin() -> None:
    async with HttpTestClient(
        app_with(allow_origins=["https://a.com"], expose_headers=["x-total"])
    ) as client:
        response = await client.get("/orders/1", headers={"origin": "https://a.com"})
        assert response.headers["access-control-allow-origin"] == "https://a.com"
        assert response.headers["vary"] == "Origin"
        assert response.headers["access-control-expose-headers"] == "x-total"

        other = await client.get("/orders/1", headers={"origin": "https://evil.com"})
        assert "access-control-allow-origin" not in other.headers
        no_origin = await client.get("/orders/1")
        assert "access-control-allow-origin" not in no_origin.headers


async def test_wildcard_and_credentials() -> None:
    async with HttpTestClient(app_with(allow_origins=["*"])) as client:
        response = await client.get("/orders/1", headers={"origin": "https://x.com"})
        assert response.headers["access-control-allow-origin"] == "*"
    async with HttpTestClient(app_with(allow_origins=["*"], allow_credentials=True)) as client:
        response = await client.get("/orders/1", headers={"origin": "https://x.com"})
        assert response.headers["access-control-allow-origin"] == "https://x.com"
        assert response.headers["access-control-allow-credentials"] == "true"


async def test_preflight() -> None:
    async with HttpTestClient(
        app_with(allow_origins=["https://a.com"], allow_headers=["Authorization"], max_age=60)
    ) as client:
        ok = await client.request(
            "OPTIONS",
            "/orders",
            headers={
                "origin": "https://a.com",
                **PREFLIGHT,
                "access-control-request-headers": "Content-Type, authorization",
            },
        )
        assert ok.status == 204
        assert ok.headers["access-control-allow-methods"] == "GET, POST, PUT, PATCH, DELETE"
        assert "authorization" in ok.headers["access-control-allow-headers"]
        assert ok.headers["access-control-max-age"] == "60"

        bad_header = await client.request(
            "OPTIONS",
            "/orders",
            headers={
                "origin": "https://a.com",
                **PREFLIGHT,
                "access-control-request-headers": "x-secret",
            },
        )
        assert bad_header.status == 403
        bad_origin = await client.request(
            "OPTIONS", "/orders", headers={"origin": "https://evil.com", **PREFLIGHT}
        )
        assert bad_origin.status == 403


async def test_preflight_with_any_header_echoes_request() -> None:
    async with HttpTestClient(app_with(allow_origins=["*"], allow_headers=["*"])) as client:
        response = await client.request(
            "OPTIONS",
            "/orders",
            headers={
                "origin": "https://a.com",
                **PREFLIGHT,
                "access-control-request-headers": "x-anything",
            },
        )
        assert response.headers["access-control-allow-headers"] == "x-anything"


async def test_non_http_scopes_pass_through() -> None:
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.shutdown"}

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    http = app_with(allow_origins=["*"])
    await http({"type": "websocket"}, receive, send)
    assert sent == [{"type": "websocket.close", "code": 1000}]
