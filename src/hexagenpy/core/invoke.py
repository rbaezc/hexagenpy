"""``Invoker``: the single, transport-agnostic path that executes an operation.

Every transport (HTTP, GraphQL, gRPC, WebSocket, tests) ends here, so validation,
dependency resolution and handler execution behave identically everywhere::

    validated args  ->  controller (from the request scope)  ->  handler  ->  result
"""

import asyncio
import functools
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import msgspec

from hexagenpy.contracts import ir
from hexagenpy.di.container import Container, RequestScope
from hexagenpy.di.providers import Scope

__all__ = ["CompiledOperation", "Invoker"]


@dataclass(frozen=True, slots=True)
class CompiledOperation:
    """An operation with everything the hot path needs precomputed."""

    operation: ir.Operation
    param_names: tuple[str, ...]
    controller_scoped: bool
    """True when the controller must be built per request (it has request deps)."""

    def bind_args(self, args: Any, *, strict: bool = True) -> dict[str, Any]:
        """Validate raw args (mapping or args Struct) into handler keyword arguments."""
        args_type: type[Any] = self.operation.args_type
        if not isinstance(args, args_type):
            validated: Any = msgspec.convert(args, args_type, strict=strict)
        else:
            validated = args
        return {name: getattr(validated, name) for name in self.param_names}


class Invoker:
    def __init__(self, container: Container, operations: Mapping[str, ir.Operation]) -> None:
        self._container = container
        self._compiled = {
            op_id: CompiledOperation(
                operation=op,
                param_names=tuple(p.name for p in op.params),
                controller_scoped=container.scope_of(op.controller) is not Scope.SINGLETON,
            )
            for op_id, op in operations.items()
        }

    def compiled(self, operation_id: str) -> CompiledOperation:
        return self._compiled[operation_id]

    async def invoke(
        self,
        operation_id: str,
        args: Any,
        scope: RequestScope,
        *,
        strict: bool = True,
    ) -> Any:
        """Run an operation inside ``scope``.

        Returns the handler result; for streaming operations, the async iterator itself
        (the transport consumes it while ``scope`` is still open).
        """
        compiled = self._compiled[operation_id]
        return await self.call(compiled, compiled.bind_args(args, strict=strict), scope)

    async def call(
        self, compiled: CompiledOperation, kwargs: dict[str, Any], scope: RequestScope
    ) -> Any:
        """Run an operation with already-validated keyword arguments (transport hot path)."""
        controller: Any = await self._container.resolve_in(compiled.operation.controller, scope)
        handler: Callable[..., Any] = getattr(controller, compiled.operation.handler)
        op = compiled.operation
        if op.kind == "stream":
            result = handler(**kwargs)
            return await result if asyncio.iscoroutine(result) else result
        if op.is_async:
            return await handler(**kwargs)
        # Sync handlers never block the event loop (principle 4).
        return await asyncio.to_thread(functools.partial(handler, **kwargs))
