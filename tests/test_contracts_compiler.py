import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, IntEnum
from typing import Annotated, Any, Literal, TypedDict

import pytest

from hexagenpy import Meta, Model
from hexagenpy.contracts import TypeCompiler, ir
from hexagenpy.errors import ContractError

S = ir.ScalarKind


@pytest.fixture
def compiler() -> TypeCompiler:
    return TypeCompiler()


@pytest.mark.parametrize(
    ("annotation", "kind"),
    [
        (str, S.STR),
        (int, S.INT),
        (float, S.FLOAT),
        (bool, S.BOOL),
        (bytes, S.BYTES),
        (dt.datetime, S.DATETIME),
        (dt.date, S.DATE),
        (dt.time, S.TIME),
        (dt.timedelta, S.TIMEDELTA),
        (uuid.UUID, S.UUID),
        (Decimal, S.DECIMAL),
    ],
)
def test_scalars(compiler: TypeCompiler, annotation: type, kind: ir.ScalarKind) -> None:
    assert compiler.compile(annotation) == ir.Scalar(kind)


def test_constraints(compiler: TypeCompiler) -> None:
    node = compiler.compile(Annotated[str, Meta(min_length=1, max_length=5, pattern="^a")])
    assert node == ir.Scalar(S.STR, ir.Constraints(min_length=1, max_length=5, pattern="^a"))
    number = compiler.compile(Annotated[int, Meta(gt=0, le=10, multiple_of=2)])
    assert isinstance(number, ir.Scalar)
    assert number.constraints == ir.Constraints(gt=0, le=10, multiple_of=2)
    assert not number.constraints.is_empty()
    assert ir.Constraints().is_empty()


def test_collections(compiler: TypeCompiler) -> None:
    assert compiler.compile(list[int]) == ir.ListOf(ir.Scalar(S.INT))
    assert compiler.compile(tuple[int, ...]) == ir.ListOf(ir.Scalar(S.INT))
    assert compiler.compile(set[str]) == ir.ListOf(ir.Scalar(S.STR), unique=True)
    assert compiler.compile(frozenset[str]) == ir.ListOf(ir.Scalar(S.STR), unique=True)
    assert compiler.compile(tuple[int, str]) == ir.TupleOf((ir.Scalar(S.INT), ir.Scalar(S.STR)))
    assert compiler.compile(dict[str, float]) == ir.MapOf(ir.Scalar(S.STR), ir.Scalar(S.FLOAT))
    bounded = compiler.compile(Annotated[list[int], Meta(max_length=3)])
    assert isinstance(bounded, ir.ListOf)
    assert bounded.constraints.max_length == 3


def test_optional_union_literal_any_none(compiler: TypeCompiler) -> None:
    assert compiler.compile(int | None) == ir.Nullable(ir.Scalar(S.INT))
    assert compiler.compile(int | str) == ir.UnionOf((ir.Scalar(S.INT), ir.Scalar(S.STR)))
    assert compiler.compile(int | str | None) == ir.Nullable(
        ir.UnionOf((ir.Scalar(S.INT), ir.Scalar(S.STR)))
    )
    assert compiler.compile(Literal["a", "b"]) == ir.LiteralOf(("a", "b"))
    assert compiler.compile(Any) == ir.AnyValue()
    assert compiler.compile(None) == ir.Void()


def test_enums(compiler: TypeCompiler) -> None:
    class Color(Enum):
        """Primary colors."""

        RED = "red"
        BLUE = "blue"

    class Level(IntEnum):
        LOW = 1

    assert compiler.compile(Color) == ir.Ref("Color")
    assert compiler.compile(Level) == ir.Ref("Level")
    color = compiler.definitions["Color"]
    assert isinstance(color, ir.EnumDef)
    assert color.members == (ir.EnumMember("RED", "red"), ir.EnumMember("BLUE", "blue"))
    assert color.description == "Primary colors."
    assert compiler.compile(Color) == ir.Ref("Color")  # idempotent


def test_enum_values_must_be_str_or_int(compiler: TypeCompiler) -> None:
    class Ratio(Enum):
        HALF = 0.5

    with pytest.raises(ContractError, match="all str or all int"):
        compiler.compile(Ratio)


def test_objects_fields_defaults_and_metadata(compiler: TypeCompiler) -> None:
    class Item(Model):
        """An item.

        Spans lines."""

        sku: Annotated[str, Meta(description="Stock keeping unit", examples=["A-1"])]
        qty: int = 1
        tags: list[str] = []
        note: Annotated[str | None, Meta(title="Note")] = None

    assert compiler.compile(Item) == ir.Ref("Item")
    item = compiler.definitions["Item"]
    assert isinstance(item, ir.ObjectDef)
    assert item.description == "An item. Spans lines."
    sku, qty, tags, note = item.fields
    assert (sku.required, sku.default, sku.description, sku.examples) == (
        True,
        ir.MISSING,
        "Stock keeping unit",
        ("A-1",),
    )
    assert (qty.required, qty.default) == (False, 1)
    assert tags.default == []
    assert note.description == "Note"
    assert note.type == ir.Nullable(ir.Scalar(S.STR))


def test_dataclass_typeddict_and_struct_without_docs(compiler: TypeCompiler) -> None:
    @dataclass
    class Point:
        x: int
        y: int

    class Payload(TypedDict):
        name: str

    class Bare(Model):
        a: int

    for cls in (Point, Payload, Bare):
        assert compiler.compile(cls) == ir.Ref(cls.__name__)
    bare = compiler.definitions["Bare"]
    point = compiler.definitions["Point"]
    assert isinstance(bare, ir.ObjectDef)
    assert isinstance(point, ir.ObjectDef)
    assert bare.description is None  # auto-generated signature doc is ignored
    assert point.description is None


class Node(Model):  # module level: forward references resolve against module globals
    name: str
    children: "list[Node]" = []


def test_recursive_types(compiler: TypeCompiler) -> None:
    assert compiler.compile(Node) == ir.Ref("Node")
    node = compiler.definitions["Node"]
    assert isinstance(node, ir.ObjectDef)
    assert node.fields[1].type == ir.ListOf(ir.Ref("Node"))


def test_generic_models_get_specialized_names(compiler: TypeCompiler) -> None:
    class Order(Model):
        id: int

    class Page[T](Model):
        items: list[T]
        total: int

    assert compiler.compile(Page[Order]) == ir.Ref("PageOrder")
    assert compiler.compile(Page[int]) == ir.Ref("PageInt")
    page = compiler.definitions["PageOrder"]
    assert isinstance(page, ir.ObjectDef)
    assert page.fields[0].type == ir.ListOf(ir.Ref("Order"))


def test_name_collisions_and_contract_name(compiler: TypeCompiler) -> None:
    def make() -> type[Model]:
        class Item(Model):
            a: int

        return Item

    first, second = make(), make()
    compiler.compile(first)
    with pytest.raises(ContractError, match="two different types are exposed as 'Item'"):
        compiler.compile(second)

    class Renamed(Model):
        __contract_name__ = "BillingItem"
        a: int

    assert compiler.compile(Renamed) == ir.Ref("BillingItem")


def test_tagged_unions_keep_tags(compiler: TypeCompiler) -> None:
    class Card(Model, tag="card"):
        last4: str

    class Cash(Model, tag="cash"):
        amount: float

    assert compiler.compile(Card | Cash) == ir.UnionOf((ir.Ref("Card"), ir.Ref("Cash")))
    card = compiler.definitions["Card"]
    assert isinstance(card, ir.ObjectDef)
    assert (card.tag_field, card.tag) == ("type", "card")


def test_unsupported_types(compiler: TypeCompiler) -> None:
    class Opaque:
        pass

    with pytest.raises(ContractError, match="unsupported type"):
        compiler.compile(Opaque)


def test_missing_sentinel_repr() -> None:
    assert repr(ir.MISSING) == "MISSING"
