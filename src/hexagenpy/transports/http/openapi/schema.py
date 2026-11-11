"""Contract IR -> JSON Schema 2020-12 (the dialect of OpenAPI 3.1)."""

import contextlib
from typing import Any

import msgspec

from hexagenpy.contracts import ir
from hexagenpy.contracts.registry import ContractRegistry

__all__ = ["SchemaBuilder"]

_SCALARS: dict[ir.ScalarKind, dict[str, Any]] = {
    ir.ScalarKind.STR: {"type": "string"},
    ir.ScalarKind.INT: {"type": "integer"},
    ir.ScalarKind.FLOAT: {"type": "number"},
    ir.ScalarKind.BOOL: {"type": "boolean"},
    ir.ScalarKind.BYTES: {"type": "string", "contentEncoding": "base64"},
    ir.ScalarKind.DATETIME: {"type": "string", "format": "date-time"},
    ir.ScalarKind.DATE: {"type": "string", "format": "date"},
    ir.ScalarKind.TIME: {"type": "string", "format": "time"},
    ir.ScalarKind.TIMEDELTA: {"type": "string", "format": "duration"},
    ir.ScalarKind.UUID: {"type": "string", "format": "uuid"},
    ir.ScalarKind.DECIMAL: {"type": "string", "format": "decimal"},
}

_NUMERIC = {
    "gt": "exclusiveMinimum",
    "ge": "minimum",
    "lt": "exclusiveMaximum",
    "le": "maximum",
    "multiple_of": "multipleOf",
}
_STRING = {"min_length": "minLength", "max_length": "maxLength", "pattern": "pattern"}
_ARRAY = {"min_length": "minItems", "max_length": "maxItems"}
_OBJECT = {"min_length": "minProperties", "max_length": "maxProperties"}


def _apply(schema: dict[str, Any], constraints: ir.Constraints, names: dict[str, str]) -> None:
    for attr, keyword in names.items():
        value = getattr(constraints, attr)
        if value is not None:
            schema[keyword] = value


class SchemaBuilder:
    """Builds schemas, referencing named types under ``#/components/schemas``."""

    def __init__(self, registry: ContractRegistry) -> None:
        self._registry = registry
        self.components: dict[str, dict[str, Any]] = {}

    def schema(self, node: ir.TypeRef) -> dict[str, Any]:
        schema: dict[str, Any]
        match node:
            case ir.Scalar(kind=kind, constraints=constraints):
                schema = dict(_SCALARS[kind])
                is_text = kind is ir.ScalarKind.STR
                _apply(schema, constraints, _STRING if is_text else _NUMERIC)
                return schema
            case ir.ListOf(item=item, constraints=constraints, unique=unique):
                schema = {"type": "array", "items": self.schema(item)}
                _apply(schema, constraints, _ARRAY)
                if unique:
                    schema["uniqueItems"] = True
                return schema
            case ir.TupleOf(items=items):
                prefix = [self.schema(i) for i in items]
                return {
                    "type": "array",
                    "prefixItems": prefix,
                    "minItems": len(items),
                    "maxItems": len(items),
                }
            case ir.MapOf(key=key, value=value, constraints=constraints):
                schema = {"type": "object", "additionalProperties": self.schema(value)}
                if not (isinstance(key, ir.Scalar) and key.kind is ir.ScalarKind.STR):
                    schema["propertyNames"] = self.schema(key)
                _apply(schema, constraints, _OBJECT)
                return schema
            case ir.Nullable(inner=inner):
                return {"anyOf": [self.schema(inner), {"type": "null"}]}
            case ir.Ref(name=name):
                self._component(name)
                return {"$ref": f"#/components/schemas/{name}"}
            case ir.UnionOf(variants=variants):
                return self._union(variants)
            case ir.LiteralOf(values=values):
                return {"enum": list(values)}
            case ir.Stream(item=item):
                return self.schema(item)
            case ir.AnyValue() | ir.Void():
                return {}

    def _union(self, variants: tuple[ir.TypeRef, ...]) -> dict[str, Any]:
        schemas = [self.schema(v) for v in variants]
        defs = [self._registry.resolve(v) if isinstance(v, ir.Ref) else None for v in variants]
        objects = [d for d in defs if isinstance(d, ir.ObjectDef)]
        if len(objects) == len(variants) and all(o.tag_field for o in objects):
            mapping = {str(o.tag): f"#/components/schemas/{o.name}" for o in objects}
            return {
                "oneOf": schemas,
                "discriminator": {"propertyName": objects[0].tag_field, "mapping": mapping},
            }
        return {"anyOf": schemas}

    def _component(self, name: str) -> None:
        if name in self.components:
            return
        self.components[name] = {}  # placeholder: recursive types reference themselves
        definition = self._registry.resolve(ir.Ref(name))
        if isinstance(definition, ir.EnumDef):
            values = [m.value for m in definition.members]
            kind = "integer" if all(isinstance(v, int) for v in values) else "string"
            schema: dict[str, Any] = {"type": kind, "enum": values}
        else:
            schema = self._object(definition)
        if definition.description:
            schema["description"] = definition.description
        self.components[name] = {"title": name, **schema}

    def _object(self, definition: ir.ObjectDef) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        if definition.tag_field is not None:
            properties[definition.tag_field] = {"const": definition.tag}
            required.append(definition.tag_field)
        for f in definition.fields:
            prop = self.schema(f.type)
            if f.description:
                prop["description"] = f.description
            if f.examples:
                prop["examples"] = list(f.examples)
            if f.default is not ir.MISSING:
                with contextlib.suppress(TypeError):  # non-serializable defaults are skipped
                    prop["default"] = msgspec.to_builtins(f.default)
            properties[f.wire_name] = prop
            if f.required:
                required.append(f.wire_name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema
