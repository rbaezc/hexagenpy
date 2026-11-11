"""``ContractRegistry``: every operation and named type of an application."""

import difflib
from collections.abc import Iterator, Mapping

from hexagenpy.contracts import ir
from hexagenpy.contracts.compiler import TypeCompiler
from hexagenpy.contracts.endpoint import Controller
from hexagenpy.contracts.operations import build_operations
from hexagenpy.errors import ContractError

__all__ = ["ContractRegistry"]


class ContractRegistry:
    """Compiled contracts of an application; the input of every transport generator."""

    def __init__(self) -> None:
        self._compiler = TypeCompiler()
        self._operations: dict[str, ir.Operation] = {}

    @property
    def definitions(self) -> Mapping[str, ir.NamedDef]:
        return self._compiler.definitions

    @property
    def operations(self) -> Mapping[str, ir.Operation]:
        return self._operations

    def add_controller(self, controller: type[Controller], slice_name: str) -> list[ir.Operation]:
        operations = build_operations(controller, slice_name, self._compiler)
        for op in operations:
            if op.id in self._operations:
                other = self._operations[op.id].controller.__qualname__
                raise ContractError(
                    f"duplicate operation {op.id!r} in {controller.__qualname__} and {other}"
                )
            self._operations[op.id] = op
        return operations

    def compile_type(self, annotation: object) -> ir.TypeRef:
        """Compile an extra type (e.g. a response envelope) into this registry."""
        return self._compiler.compile(annotation)

    def operation(self, operation_id: str) -> ir.Operation:
        try:
            return self._operations[operation_id]
        except KeyError:
            close = difflib.get_close_matches(operation_id, self._operations, n=3)
            hint = f"; did you mean {', '.join(map(repr, close))}?" if close else ""
            raise ContractError(f"unknown operation {operation_id!r}{hint}") from None

    def for_transport(self, transport: str) -> Iterator[ir.Operation]:
        return (op for op in self._operations.values() if transport in op.bindings)

    def resolve(self, ref: ir.Ref) -> ir.NamedDef:
        return self._compiler.definitions[ref.name]
