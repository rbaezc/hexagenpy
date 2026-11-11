"""Compiles Python type annotations into Contract IR nodes.

msgspec does the heavy lifting (``msgspec.inspect.type_info`` understands Structs,
dataclasses, TypedDicts, enums, ``Annotated`` constraints, unions and recursion); this
module translates its type graph into IR and registers named definitions.
"""

import collections.abc
import enum
from typing import Any, get_args, get_origin

import msgspec
import msgspec.inspect as mi

from hexagenpy.contracts import ir
from hexagenpy.errors import ContractError

__all__ = ["TypeCompiler"]

_SCALARS: dict[type[mi.Type], ir.ScalarKind] = {
    mi.StrType: ir.ScalarKind.STR,
    mi.IntType: ir.ScalarKind.INT,
    mi.FloatType: ir.ScalarKind.FLOAT,
    mi.BoolType: ir.ScalarKind.BOOL,
    mi.BytesType: ir.ScalarKind.BYTES,
    mi.ByteArrayType: ir.ScalarKind.BYTES,
    mi.MemoryViewType: ir.ScalarKind.BYTES,
    mi.DateTimeType: ir.ScalarKind.DATETIME,
    mi.DateType: ir.ScalarKind.DATE,
    mi.TimeType: ir.ScalarKind.TIME,
    mi.TimeDeltaType: ir.ScalarKind.TIMEDELTA,
    mi.UUIDType: ir.ScalarKind.UUID,
    mi.DecimalType: ir.ScalarKind.DECIMAL,
}

_STREAM_ORIGINS = (collections.abc.AsyncIterator, collections.abc.AsyncGenerator)
_CONSTRAINT_ATTRS = ("gt", "ge", "lt", "le", "multiple_of", "min_length", "max_length")


def _constraints(info: mi.Type) -> ir.Constraints:
    values = {name: getattr(info, name, None) for name in _CONSTRAINT_ATTRS}
    return ir.Constraints(pattern=getattr(info, "pattern", None), **values)


def _doc(cls: type) -> str | None:
    doc = cls.__doc__
    if not doc or doc.startswith(cls.__name__ + "("):  # auto-generated signature docs
        return None
    return " ".join(doc.split())


def _contract_name(cls: Any) -> str:
    origin = getattr(cls, "__origin__", None)
    if origin is not None:  # parametrized generic, e.g. Page[Order] -> "PageOrder"
        parts = [_contract_name(a) if hasattr(a, "__name__") else str(a) for a in cls.__args__]
        return _contract_name(origin) + "".join(p[:1].upper() + p[1:] for p in parts)
    custom = getattr(cls, "__contract_name__", None)
    name: str = custom if isinstance(custom, str) else cls.__name__
    return name


class TypeCompiler:
    """Translates Python types into IR, collecting named definitions by name."""

    def __init__(self) -> None:
        self.definitions: dict[str, ir.NamedDef] = {}
        self._owners: dict[str, Any] = {}

    def compile(self, annotation: Any) -> ir.TypeRef:
        """Compile an annotation, including ``AsyncIterator[T]`` stream returns."""
        if annotation is None or annotation is type(None):
            return ir.Void()
        if get_origin(annotation) in _STREAM_ORIGINS:
            return ir.Stream(self.compile(get_args(annotation)[0]))
        try:
            info = mi.type_info(annotation)
        except (TypeError, ValueError) as exc:
            raise ContractError(f"unsupported type {annotation!r}: {exc}") from exc
        return self._translate(info, {})

    # ------------------------------------------------------------------ internals

    def _translate(self, info: mi.Type, seen: dict[int, str]) -> ir.TypeRef:
        if isinstance(info, mi.Metadata):
            return self._translate(info.type, seen)
        kind = _SCALARS.get(type(info))
        if kind is not None:
            return ir.Scalar(kind, _constraints(info))
        return self._translate_composite(info, seen)

    def _translate_composite(self, info: mi.Type, seen: dict[int, str]) -> ir.TypeRef:
        tr = self._translate
        match info:
            case mi.ListType() | mi.VarTupleType() | mi.FrozenSetType() | mi.SetType():
                unique = isinstance(info, mi.SetType | mi.FrozenSetType)
                return ir.ListOf(tr(info.item_type, seen), _constraints(info), unique)
            case mi.TupleType():
                return ir.TupleOf(tuple(tr(t, seen) for t in info.item_types))
            case mi.DictType():
                key, value = tr(info.key_type, seen), tr(info.value_type, seen)
                return ir.MapOf(key, value, _constraints(info))
            case mi.UnionType():
                return self._union(info, seen)
            case mi.LiteralType():
                return ir.LiteralOf(tuple(v for v in info.values if v is not None))
            case mi.EnumType():
                return self._enum(info.cls)
            case mi.StructType() | mi.DataclassType() | mi.TypedDictType() | mi.NamedTupleType():
                return self._object(info, seen)
            case mi.AnyType():
                return ir.AnyValue()
            case mi.NoneType():
                return ir.Void()
            case _:
                raise ContractError(f"unsupported type in contract: {info!r}")

    def _union(self, info: mi.UnionType, seen: dict[int, str]) -> ir.TypeRef:
        variants = [t for t in info.types if not isinstance(t, mi.NoneType)]
        nullable = len(variants) != len(info.types)
        translated = tuple(self._translate(t, seen) for t in variants)
        inner: ir.TypeRef = translated[0] if len(translated) == 1 else ir.UnionOf(translated)
        return ir.Nullable(inner) if nullable else inner

    def _register(self, name: str, owner: Any, definition: ir.NamedDef) -> None:
        previous = self._owners.get(name)
        if previous is not None and previous != owner:
            raise ContractError(
                f"two different types are exposed as {name!r}: {previous!r} and {owner!r}; "
                "set __contract_name__ on one of them"
            )
        self._owners[name] = owner
        self.definitions[name] = definition

    def _enum(self, cls: type[enum.Enum]) -> ir.Ref:
        name = _contract_name(cls)
        if self._owners.get(name) != cls:
            # msgspec already guarantees all-str or all-int values
            members = tuple(ir.EnumMember(m.name, m.value) for m in cls)
            self._register(name, cls, ir.EnumDef(name, members, cls, _doc(cls)))
        return ir.Ref(name)

    def _object(
        self,
        info: mi.StructType | mi.DataclassType | mi.TypedDictType | mi.NamedTupleType,
        seen: dict[int, str],
    ) -> ir.Ref:
        cls = info.cls
        name = _contract_name(cls)
        if id(cls) in seen or self._owners.get(name) == cls:
            return ir.Ref(name)
        self._register(name, cls, ir.ObjectDef(name, (), cls))  # placeholder for recursion
        seen[id(cls)] = name
        fields = tuple(self._field(f, seen) for f in info.fields)
        self.definitions[name] = ir.ObjectDef(
            name=name,
            fields=fields,
            py_type=cls,
            description=_doc(getattr(cls, "__origin__", cls)),
            tag_field=info.tag_field if isinstance(info, mi.StructType) else None,
            tag=info.tag if isinstance(info, mi.StructType) else None,
        )
        return ir.Ref(name)

    def _field(self, f: mi.Field, seen: dict[int, str]) -> ir.FieldDef:
        description: str | None = None
        examples: tuple[Any, ...] = ()
        # getattr: msgspec types this dict without parameters
        schema: dict[str, Any] | None = getattr(f.type, "extra_json_schema", None)
        if schema:
            description = schema.get("description") or schema.get("title")
            examples = tuple(schema.get("examples", ()))
        if f.default is not msgspec.NODEFAULT:
            default: Any = f.default
        elif f.default_factory is not msgspec.NODEFAULT:
            default = f.default_factory()
        else:
            default = ir.MISSING
        return ir.FieldDef(
            name=f.name,
            wire_name=f.encode_name,
            type=self._translate(f.type, seen),
            required=f.required,
            default=default,
            description=description,
            examples=examples,
        )
