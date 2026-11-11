"""The example app over HTTP: happy paths and every error class."""

from hexagenpy.testing.http import HttpTestClient
from tests.http.conftest import ORDER


async def test_create_get_and_cross_slice(client: HttpTestClient) -> None:
    created = await client.post("/orders", json=ORDER)
    assert created.status == 201
    assert created.headers["content-type"] == "application/json"
    assert created.json() == {
        "id": 1,
        "customer": "ACME",
        "status": "new",
        "lines": [{"sku": "A-1", "qty": 2}],
    }
    fetched = await client.get("/orders/1")
    assert (fetched.status, fetched.json()["id"]) == (200, 1)
    invoice = await client.get("/billing/invoices/1")
    assert invoice.json() == {"order_id": 1, "customer": "ACME", "units": 2}


async def test_sync_handler_and_query_coercion(client: HttpTestClient) -> None:
    response = await client.get("/orders/5/summary", query={"verbose": "true"})
    assert (response.status, response.json()) == (200, "order 5 (verbose)")
    plain = await client.get("/orders/5/summary/")
    assert plain.json() == "order 5"


async def test_head_returns_headers_without_body(client: HttpTestClient) -> None:
    await client.post("/orders", json=ORDER)
    response = await client.request("HEAD", "/orders/1")
    assert response.status == 200
    assert response.content == b""
    assert int(response.headers["content-length"]) > 0


async def test_domain_error_becomes_problem(client: HttpTestClient) -> None:
    response = await client.get("/orders/99")
    assert response.status == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "code": "not_found",
        "detail": "order 99 does not exist",
    }


async def test_value_error_mapped_by_error_map(client: HttpTestClient) -> None:
    response = await client.post("/orders", json={"customer": "x", "lines": []})
    assert (response.status, response.json()["code"]) == (422, "validation")


async def test_path_validation(client: HttpTestClient) -> None:
    response = await client.get("/orders/abc")
    assert response.status == 422
    assert response.json()["errors"] == [
        {"location": "path", "field": "id", "message": "Expected `int`, got `str`"}
    ]


async def test_body_validation_reports_nested_field(client: HttpTestClient) -> None:
    bad = {"customer": "ACME", "lines": [{"sku": "A", "qty": 0}]}
    response = await client.post("/orders", json=bad)
    assert response.status == 422
    body = response.json()
    assert body["code"] == "request_validation_failed"
    assert body["errors"] == [
        {"location": "body", "field": "lines[0].qty", "message": "Expected `int` >= 1"}
    ]


async def test_missing_body_malformed_json_and_media_type(client: HttpTestClient) -> None:
    missing = await client.post("/orders")
    assert missing.json()["errors"][0]["message"] == "request body is required"

    malformed = await client.post(
        "/orders", content=b"{bad", headers={"content-type": "application/json"}
    )
    assert malformed.status == 422
    assert malformed.json()["errors"][0]["message"].startswith("malformed JSON")

    form = await client.post(
        "/orders", content=b"a=1", headers={"content-type": "application/x-www-form-urlencoded"}
    )
    assert (form.status, form.json()["code"]) == (415, "unsupported_media_type")

    vendor_json = await client.post(
        "/orders",
        content=b'{"customer":"x","lines":[{"sku":"a","qty":1}]}',
        headers={"content-type": "application/vnd.x+json"},
    )
    assert vendor_json.status == 201


async def test_routing_errors(client: HttpTestClient) -> None:
    missing = await client.get("/nope")
    assert (missing.status, missing.json()["code"]) == (404, "route_not_found")
    not_allowed = await client.delete("/orders/1")
    assert not_allowed.status == 405
    assert not_allowed.headers["allow"] == "GET, HEAD"
    assert not_allowed.json()["code"] == "method_not_allowed"


async def test_openapi_and_docs_are_served(client: HttpTestClient) -> None:
    doc = await client.get("/openapi.json")
    assert doc.status == 200
    assert doc.json()["openapi"] == "3.1.0"
    docs = await client.get("/docs")
    assert docs.headers["content-type"].startswith("text/html")
    assert b'data-url="/openapi.json"' in docs.content
