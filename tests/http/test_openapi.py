import datetime as dt
import uuid
from decimal import Decimal
from enum import IntEnum
from typing import Annotated, Any, Literal

from hexagenpy import App, Controller, Meta, Model, Module, endpoint
from hexagenpy.contracts import ContractRegistry, ir
from hexagenpy.transports.http import HttpApp, Query
from hexagenpy.transports.http.openapi import SchemaBuilder
from tests.example.app import create_app


def schema_of(annotation: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = ContractRegistry()
    node = registry.compile_type(annotation)
    builder = SchemaBuilder(registry)
    return builder.schema(node), builder.components


def test_scalar_and_constraint_schemas() -> None:
    assert schema_of(Annotated[str, Meta(min_length=1, max_length=3, pattern="^a")])[0] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 3,
        "pattern": "^a",
    }
    assert schema_of(Annotated[int, Meta(gt=0, le=9, multiple_of=3)])[0] == {
        "type": "integer",
        "exclusiveMinimum": 0,
        "maximum": 9,
        "multipleOf": 3,
    }
    assert schema_of(Annotated[float, Meta(ge=0, lt=1)])[0] == {
        "type": "number",
        "minimum": 0,
        "exclusiveMaximum": 1,
    }
    assert schema_of(bytes)[0] == {"type": "string", "contentEncoding": "base64"}
    assert schema_of(dt.datetime)[0]["format"] == "date-time"
    assert schema_of(uuid.UUID)[0]["format"] == "uuid"
    assert schema_of(Decimal)[0]["format"] == "decimal"


def test_collection_union_literal_schemas() -> None:
    assert schema_of(Annotated[list[int], Meta(min_length=1)])[0] == {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 1,
    }
    assert schema_of(set[str])[0]["uniqueItems"] is True
    assert schema_of(tuple[int, str])[0] == {
        "type": "array",
        "prefixItems": [{"type": "integer"}, {"type": "string"}],
        "minItems": 2,
        "maxItems": 2,
    }
    assert schema_of(dict[str, int])[0] == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }
    assert schema_of(dict[int, int])[0]["propertyNames"] == {"type": "integer"}
    assert schema_of(int | None)[0] == {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    assert schema_of(int | str)[0] == {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    assert schema_of(Literal["a", "b"])[0] == {"enum": ["a", "b"]}
    assert schema_of(Any)[0] == {}


class Card(Model, tag="card"):
    last4: str


class Cash(Model, tag="cash"):
    amount: float


class Priority(IntEnum):
    LOW = 1
    HIGH = 2


class Ticket(Model):
    """A support ticket."""

    title: Annotated[str, Meta(description="Short title", examples=["Broken"])]
    priority: Priority = Priority.LOW
    payment: Card | Cash | None = None
    children: "list[Ticket]" = []


def test_object_enum_recursive_and_discriminated_components() -> None:
    schema, components = schema_of(Ticket)
    assert schema == {"$ref": "#/components/schemas/Ticket"}
    ticket = components["Ticket"]
    assert ticket["description"] == "A support ticket."
    assert ticket["required"] == ["title"]
    assert ticket["properties"]["title"] == {
        "type": "string",
        "description": "Short title",
        "examples": ["Broken"],
    }
    assert ticket["properties"]["priority"] == {
        "$ref": "#/components/schemas/Priority",
        "default": 1,
    }
    assert ticket["properties"]["children"]["items"] == {"$ref": "#/components/schemas/Ticket"}
    payment = ticket["properties"]["payment"]["anyOf"][0]
    assert payment["discriminator"] == {
        "propertyName": "type",
        "mapping": {"card": "#/components/schemas/Card", "cash": "#/components/schemas/Cash"},
    }
    assert components["Card"]["properties"]["type"] == {"const": "card"}
    assert components["Card"]["required"] == ["type", "last4"]
    assert components["Priority"] == {"title": "Priority", "type": "integer", "enum": [1, 2]}


def test_stream_and_void_schemas() -> None:
    builder = SchemaBuilder(ContractRegistry())
    assert builder.schema(ir.Stream(ir.Scalar(ir.ScalarKind.INT))) == {"type": "integer"}
    assert builder.schema(ir.Void()) == {}


def test_document_for_example_app() -> None:
    doc = HttpApp(create_app(), title="Shop", description="Example").openapi()
    assert doc["info"] == {"title": "Shop", "version": "0.1.0", "description": "Example"}
    assert doc["tags"] == [{"name": "billing"}, {"name": "orders"}]
    assert sorted(doc["paths"]) == [
        "/billing/invoices/{order_id}",
        "/orders",
        "/orders/{id}",
        "/orders/{id}/summary",
    ]
    get_order = doc["paths"]["/orders/{id}"]["get"]
    assert get_order["parameters"] == [
        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
    ]
    assert set(get_order["responses"]) == {"200", "422", "default"}
    summary = doc["paths"]["/orders/{id}/summary"]["get"]
    assert summary["parameters"][1] == {
        "name": "verbose",
        "in": "query",
        "required": False,
        "schema": {"type": "boolean"},
    }
    assert "Problem" in doc["components"]["schemas"]


def test_document_details() -> None:
    class Docs(Controller):
        @endpoint(http="GET /items", summary="List items", deprecated=True)
        async def items(
            self, tags: Annotated[list[str], Query(description="Tag filter")]
        ) -> list[int]:
            return []

        @endpoint(http="DELETE /items/{id}")
        async def delete(self, id: int) -> None:
            return None

        @endpoint(http="GET /ping")
        async def ping(self) -> str:
            return "pong"

    http = HttpApp(App(slices=[Module("docs", controllers=[Docs])]))
    doc = http.openapi()
    assert http.openapi() is doc  # cached
    items = doc["paths"]["/items"]["get"]
    assert (items["summary"], items["deprecated"]) == ("List items", True)
    assert items["parameters"][0] == {
        "name": "tags",
        "in": "query",
        "required": True,
        "schema": {"type": "array", "items": {"type": "string"}},
        "description": "Tag filter",
        "style": "form",
        "explode": True,
    }
    delete = doc["paths"]["/items/{id}"]["delete"]
    assert delete["responses"]["204"] == {"description": "No Content"}
    assert set(doc["paths"]["/ping"]["get"]["responses"]) == {"200", "default"}
