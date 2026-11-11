from collections.abc import AsyncIterator
from typing import Any

import msgspec
import pytest

from hexagenpy import Controller, Model, endpoint
from hexagenpy.contracts import ContractRegistry, HttpBinding, ir
from hexagenpy.contracts.endpoint import parse_http
from hexagenpy.contracts.model import decode_json, encode_json, validate
from hexagenpy.errors import ContractError


class Item(Model):
    name: str


def registry_with(controller: type[Controller], slice_name: str = "shop") -> ContractRegistry:
    registry = ContractRegistry()
    registry.add_controller(controller, slice_name)
    return registry


# ------------------------------------------------------------------ @endpoint


@pytest.mark.parametrize(
    ("route", "method", "path"),
    [
        ("GET /", "GET", "/"),
        ("post /items", "POST", "/items"),
        ("DELETE /a/{id}", "DELETE", "/a/{id}"),
    ],
)
def test_parse_http(route: str, method: str, path: str) -> None:
    if route.split()[0].islower():
        with pytest.raises(ContractError, match="invalid http route"):
            parse_http(route, None)
        return
    assert parse_http(route, None) == HttpBinding(method, path, 200)


@pytest.mark.parametrize("route", ["GET", "FETCH /x", "/x", "GET x"])
def test_parse_http_rejects_bad_routes(route: str) -> None:
    with pytest.raises(ContractError):
        parse_http(route, None)


@pytest.mark.parametrize(
    ("prefix", "path", "expected"),
    [
        ("", "/", "/"),
        ("/orders", "/", "/orders"),
        ("/orders/", "/{id}", "/orders/{id}"),
        ("", "/x", "/x"),
    ],
)
def test_full_path(prefix: str, path: str, expected: str) -> None:
    assert HttpBinding("GET", path, 200).full_path(prefix) == expected


def test_endpoint_argument_validation() -> None:
    with pytest.raises(ContractError, match="status= only applies"):
        endpoint(status=201)
    with pytest.raises(ContractError, match="invalid graphql kind"):
        endpoint(graphql="mutate")  # type: ignore[arg-type]


def test_controller_prefix_must_be_absolute() -> None:
    with pytest.raises(ContractError, match="prefix must start with '/'"):

        class Bad(Controller, prefix="orders"):
            pass


def test_controller_inheritance_overrides_endpoints() -> None:
    class Base(Controller, prefix="/base", tag="base"):
        @endpoint(http="GET /a")
        async def a(self) -> int:
            return 1

        @endpoint(http="GET /b")
        async def b(self) -> int:
            return 2

    class Child(Base):
        @endpoint(http="GET /b2", grpc="GetB")
        async def b(self) -> int:
            return 3

    meta = Child.__hexagen_controller__
    assert meta.prefix == "/base"
    assert meta.tags == ("base",)
    assert set(meta.endpoints) == {"a", "b"}
    b_spec = meta.endpoints["b"]
    assert b_spec.http is not None
    assert b_spec.http.path == "/b2"
    assert b_spec.grpc is not None
    assert b_spec.grpc.name == "GetB"


# ------------------------------------------------------------------ operations


def test_operation_ir() -> None:
    class Shop(Controller, prefix="/items"):
        @endpoint(
            http="GET /{id}", name="fetch_item", summary="Fetch", tags=("x",), deprecated=True
        )
        async def get(self, id: int, expand: bool = False) -> Item | None:
            """Docstring is not used when description is given."""
            return None

        @endpoint(description="Explicit")
        async def plain(self) -> None:
            """Ignored."""

    registry = registry_with(Shop)
    op = registry.operation("shop.fetch_item")
    assert (op.name, op.handler, op.slice, op.controller) == ("fetch_item", "get", "shop", Shop)
    assert op.returns == ir.Nullable(ir.Ref("Item"))
    assert [(p.name, p.required, p.default) for p in op.params] == [
        ("id", True, ir.MISSING),
        ("expand", False, False),
    ]
    assert (op.summary, op.tags, op.deprecated, op.is_async, op.kind) == (
        "Fetch",
        ("x",),
        True,
        True,
        "unary",
    )
    assert op.description == "Docstring is not used when description is given."
    assert registry.operation("shop.plain").description == "Explicit"
    assert registry.operation("shop.plain").returns == ir.Void()
    assert [o.id for o in registry.for_transport("http")] == ["shop.fetch_item"]

    args: Any = validate({"id": "3"}, op.args_type, strict=False)
    assert (args.id, args.expand) == (3, False)
    with pytest.raises(msgspec.ValidationError):
        validate({}, op.args_type)


def test_unknown_operation_suggests_close_matches() -> None:
    class Shop(Controller):
        @endpoint()
        async def get_item(self) -> int:
            return 1

    registry = registry_with(Shop)
    with pytest.raises(ContractError, match=r"did you mean 'shop\.get_item'"):
        registry.operation("shop.get_itme")
    with pytest.raises(ContractError, match=r"unknown operation 'zzz'$"):
        registry.operation("zzz")


def test_duplicate_operations_are_rejected() -> None:
    class A(Controller):
        @endpoint()
        async def ping(self) -> int:
            return 1

    class B(Controller):
        @endpoint()
        async def ping(self) -> int:
            return 2

    registry = registry_with(A)
    with pytest.raises(ContractError, match=r"duplicate operation 'shop\.ping'"):
        registry.add_controller(B, "shop")


def test_extra_types_can_be_compiled() -> None:
    registry = ContractRegistry()
    assert registry.compile_type(Item) == ir.Ref("Item")
    assert isinstance(registry.resolve(ir.Ref("Item")), ir.ObjectDef)


def test_streams() -> None:
    class Feed(Controller):
        @endpoint(grpc=True)
        async def ticks(self, n: int) -> AsyncIterator[int]:
            yield n

        @endpoint(grpc=True)
        async def factory(self) -> AsyncIterator[Item]:
            return _items()

    registry = registry_with(Feed)
    ticks = registry.operation("shop.ticks")
    assert (ticks.kind, ticks.returns) == ("stream", ir.Stream(ir.Scalar(ir.ScalarKind.INT)))
    assert registry.operation("shop.factory").kind == "stream"


async def _items() -> AsyncIterator[Item]:
    yield Item(name="x")


def _bad_controller(body: str) -> type[Controller]:
    namespace: dict[str, Any] = {
        "Controller": Controller,
        "endpoint": endpoint,
        "Item": Item,
        "AsyncIterator": AsyncIterator,
    }
    exec(body, namespace)
    controller: type[Controller] = namespace["Bad"]
    return controller


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("class Bad(Controller):\n    pass", "declares no @endpoint"),
        ("class Bad(Controller):\n    @endpoint()\n    async def f(self): ...", "missing return"),
        (
            "class Bad(Controller):\n    @endpoint()\n    async def f(self, x) -> int: ...",
            "needs a type annotation",
        ),
        (
            "class Bad(Controller):\n    @endpoint()\n    async def f(self, *a: int) -> int: ...",
            r"\*args",
        ),
        (
            "class Bad(Controller):\n    @staticmethod\n    @endpoint()\n"
            "    async def f() -> int: ...",
            "regular methods",
        ),
        (
            "class Bad(Controller):\n    @endpoint()\n    async def f(self) -> 'Nope': ...",
            "cannot resolve annotations",
        ),
        (
            "class Bad(Controller):\n    @endpoint()\n"
            "    async def f(self) -> int:\n        yield 1",
            "AsyncIterator",
        ),
        (
            "class Bad(Controller):\n    @endpoint()\n    def f(self) -> AsyncIterator[int]: ...",
            "must be async",
        ),
        (
            "class Bad(Controller):\n    @endpoint()\n    async def f(self, s: AsyncIterator[int])"
            " -> int: ...",
            "cannot be a stream",
        ),
        (
            "class Bad(Controller):\n    @endpoint(http='GET /{id}')\n"
            "    async def f(self) -> int: ...",
            r"path parameter \{id\}",
        ),
    ],
)
def test_invalid_controllers(body: str, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        registry_with(_bad_controller(body))


def test_json_helpers() -> None:
    raw = encode_json(Item(name="a"))
    assert raw == b'{"name":"a"}'
    assert decode_json(raw, Item) == Item(name="a")
