"""Contract IR: the transport-neutral description of types and operations (ADR 0002).

Python types are compiled into these nodes once, at startup. OpenAPI, GraphQL SDL and
proto3 are generated from the IR; transports never inspect Python types themselves.

Type references (:data:`TypeRef`) are small immutable trees. Named types (objects and
enums) live in the registry and are referenced by name with :class:`Ref`, which also
makes recursive types representable.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Literal

__all__ = [
    "MISSING",
    "AnyValue",
    "Constraints",
    "EnumDef",
    "EnumMember",
    "FieldDef",
    "ListOf",
    "LiteralOf",
    "MapOf",
    "NamedDef",
    "Nullable",
    "ObjectDef",
    "Operation",
    "Param",
    "Ref",
    "Scalar",
    "ScalarKind",
    "Stream",
    "TupleOf",
    "TypeRef",
    "UnionOf",
    "Void",
]


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final[Any] = _Missing()
"""Sentinel for "no default value"."""


class ScalarKind(StrEnum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    BYTES = "bytes"
    DATETIME = "datetime"
    DATE = "date"
    TIME = "time"
    TIMEDELTA = "timedelta"
    UUID = "uuid"
    DECIMAL = "decimal"


@dataclass(frozen=True, slots=True)
class Constraints:
    """Validation constraints, already enforced by msgspec; kept for schema generation."""

    gt: float | None = None
    ge: float | None = None
    lt: float | None = None
    le: float | None = None
    multiple_of: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None

    def is_empty(self) -> bool:
        return self == _NO_CONSTRAINTS


_NO_CONSTRAINTS: Final = Constraints()


# ------------------------------------------------------------------ type references


@dataclass(frozen=True, slots=True)
class Scalar:
    kind: ScalarKind
    constraints: Constraints = _NO_CONSTRAINTS


@dataclass(frozen=True, slots=True)
class ListOf:
    item: "TypeRef"
    constraints: Constraints = _NO_CONSTRAINTS
    unique: bool = False


@dataclass(frozen=True, slots=True)
class TupleOf:
    """Fixed-length, heterogeneous tuple (not representable in GraphQL or proto)."""

    items: tuple["TypeRef", ...]


@dataclass(frozen=True, slots=True)
class MapOf:
    key: "TypeRef"
    value: "TypeRef"
    constraints: Constraints = _NO_CONSTRAINTS


@dataclass(frozen=True, slots=True)
class Nullable:
    inner: "TypeRef"


@dataclass(frozen=True, slots=True)
class Ref:
    """Reference to a named definition (:class:`ObjectDef` or :class:`EnumDef`)."""

    name: str


@dataclass(frozen=True, slots=True)
class UnionOf:
    variants: tuple["TypeRef", ...]


@dataclass(frozen=True, slots=True)
class LiteralOf:
    values: tuple[str | int | bool, ...]


@dataclass(frozen=True, slots=True)
class AnyValue:
    """Untyped value (``typing.Any``); rejected by GraphQL and gRPC."""


@dataclass(frozen=True, slots=True)
class Void:
    """No value: an operation returning ``None``."""


@dataclass(frozen=True, slots=True)
class Stream:
    """Asynchronous stream of items (``AsyncIterator[T]``); only valid at operation level."""

    item: "TypeRef"


type TypeRef = (
    Scalar
    | ListOf
    | TupleOf
    | MapOf
    | Nullable
    | Ref
    | UnionOf
    | LiteralOf
    | AnyValue
    | Void
    | Stream
)


# ------------------------------------------------------------------ named definitions


@dataclass(frozen=True, slots=True)
class FieldDef:
    name: str
    wire_name: str
    type: TypeRef
    required: bool = True
    default: Any = MISSING
    description: str | None = None
    examples: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class ObjectDef:
    name: str
    fields: tuple[FieldDef, ...]
    py_type: type
    description: str | None = None
    tag_field: str | None = None
    tag: str | int | None = None


@dataclass(frozen=True, slots=True)
class EnumMember:
    name: str
    value: str | int


@dataclass(frozen=True, slots=True)
class EnumDef:
    name: str
    members: tuple[EnumMember, ...]
    py_type: type
    description: str | None = None


type NamedDef = ObjectDef | EnumDef


# ------------------------------------------------------------------ operations


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    type: TypeRef
    py_type: Any
    required: bool = True
    default: Any = MISSING


@dataclass(frozen=True, slots=True)
class Operation:
    """A use case exposed by a controller, independent of any transport.

    ``bindings`` holds per-transport metadata keyed by transport name
    (``"http"``, ``"graphql"``, ``"grpc"``), declared with ``@endpoint``.
    """

    id: str
    name: str
    slice: str
    controller: type
    handler: str
    params: tuple[Param, ...]
    returns: TypeRef
    args_type: type
    is_async: bool
    kind: Literal["unary", "stream"] = "unary"
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    deprecated: bool = False
    bindings: Mapping[str, Any] = field(default_factory=dict[str, Any])
