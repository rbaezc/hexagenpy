"""Transport compatibility rules over the Contract IR (ADR 0002).

Every transport has a different type system. Instead of degrading silently, the app
refuses to start when an operation is bound to a transport that cannot represent one
of its types, and explains why. HTTP/JSON can represent every IR type.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal

from hexagenpy.contracts import ir
from hexagenpy.contracts.registry import ContractRegistry

__all__ = ["CompatIssue", "check_operation", "check_registry"]

Direction = Literal["input", "output"]
_MAP_KEYS = frozenset({ir.ScalarKind.STR, ir.ScalarKind.INT, ir.ScalarKind.BOOL})


@dataclass(frozen=True, slots=True)
class CompatIssue:
    transport: str
    operation: str
    location: str
    message: str

    def __str__(self) -> str:
        return f"[{self.transport}] {self.operation} -> {self.location}: {self.message}"


type Rule = Callable[[ir.TypeRef, ir.TypeRef | None, Direction], str | None]


def _graphql_rule(node: ir.TypeRef, parent: ir.TypeRef | None, direction: Direction) -> str | None:
    match node:
        case ir.AnyValue():
            return "Any has no GraphQL type; use a Model"
        case ir.MapOf():
            return "GraphQL has no map type; use a list of key/value Models"
        case ir.TupleOf():
            return "GraphQL has no tuple type; use a Model"
        case ir.UnionOf() if direction == "input":
            return "GraphQL input types cannot be unions"
        case ir.UnionOf() if not all(isinstance(v, ir.Ref) for v in node.variants):
            return "GraphQL union members must be Models"
        case ir.Stream() if parent is not None:
            return "streams are only allowed as the return type of a subscription"
        case _:
            return None


def _grpc_rule(node: ir.TypeRef, parent: ir.TypeRef | None, direction: Direction) -> str | None:
    repeated = isinstance(parent, ir.ListOf | ir.MapOf)
    match node:
        case ir.AnyValue():
            return "Any has no proto3 type; use a Model"
        case ir.TupleOf():
            return "proto3 has no tuple type; use a Model"
        case ir.Nullable(inner=ir.ListOf() | ir.MapOf()):
            return "repeated/map fields cannot be null in proto3; drop Optional (empty = none)"
        case ir.ListOf() | ir.MapOf() | ir.Nullable() if repeated:
            return "nested repeated or nullable items need a wrapper Model in proto3"
        case ir.MapOf(key=key) if not (isinstance(key, ir.Scalar) and key.kind in _MAP_KEYS):
            return "proto3 map keys must be str, int or bool"
        case ir.UnionOf() if any(isinstance(v, ir.ListOf | ir.MapOf) for v in node.variants):
            return "oneof members cannot be lists or maps; wrap them in a Model"
        case _:
            return None


_RULES: dict[str, Rule] = {"graphql": _graphql_rule, "grpc": _grpc_rule}


def _children(node: ir.TypeRef) -> Iterator[tuple[str, ir.TypeRef]]:
    match node:
        case ir.ListOf(item=item) | ir.Stream(item=item):
            yield "[]", item
        case ir.MapOf(key=key, value=value):
            yield "{key}", key
            yield "{value}", value
        case ir.Nullable(inner=inner):
            yield "", inner
        case ir.UnionOf(variants=variants) | ir.TupleOf(items=variants):
            for index, variant in enumerate(variants):
                yield f"<{index}>", variant
        case _:
            return


class _Walker:
    def __init__(self, registry: ContractRegistry, transport: str, op: ir.Operation) -> None:
        self.registry = registry
        self.transport = transport
        self.op = op
        self.rule = _RULES[transport]
        self.seen: set[tuple[str, Direction]] = set()
        self.issues: list[CompatIssue] = []

    def walk(
        self, node: ir.TypeRef, parent: ir.TypeRef | None, location: str, direction: Direction
    ) -> None:
        message = self.rule(node, parent, direction)
        if message is not None:
            self.issues.append(CompatIssue(self.transport, self.op.id, location, message))
            return
        if isinstance(node, ir.Ref):
            self._walk_definition(node, location, direction)
            return
        for suffix, child in _children(node):
            self.walk(child, node, location + suffix, direction)

    def _walk_definition(self, ref: ir.Ref, location: str, direction: Direction) -> None:
        if (ref.name, direction) in self.seen:
            return
        self.seen.add((ref.name, direction))
        definition = self.registry.resolve(ref)
        if isinstance(definition, ir.ObjectDef):
            for f in definition.fields:
                self.walk(f.type, None, f"{ref.name}.{f.name}", direction)


def check_operation(registry: ContractRegistry, op: ir.Operation) -> list[CompatIssue]:
    """Check one operation against every transport it is bound to."""
    issues: list[CompatIssue] = []
    for transport in op.bindings:
        if transport not in _RULES:
            continue
        walker = _Walker(registry, transport, op)
        for param in op.params:
            walker.walk(param.type, None, f"param {param.name!r}", "input")
        walker.walk(op.returns, None, "return", "output")
        issues.extend(walker.issues)
    issues.extend(_graphql_kind_issues(op))
    return issues


def _graphql_kind_issues(op: ir.Operation) -> list[CompatIssue]:
    binding = op.bindings.get("graphql")
    if binding is None:
        return []
    is_subscription = binding.kind == "subscription"
    if is_subscription and op.kind != "stream":
        return [CompatIssue("graphql", op.id, "return", "subscriptions must return AsyncIterator")]
    if op.kind == "stream" and not is_subscription:
        return [CompatIssue("graphql", op.id, "return", "streams require graphql='subscription'")]
    return []


def check_registry(registry: ContractRegistry) -> list[CompatIssue]:
    return [i for op in registry.operations.values() for i in check_operation(registry, op)]
