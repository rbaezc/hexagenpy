"""``App``: assembles slices into contracts, a container and an invoker.

Construction compiles and validates everything (contracts, transport compatibility,
the dependency graph); ``start()`` builds singletons and runs startup hooks. Transports
(Phase 2+) wrap an ``App`` and call :meth:`App.invoke` or use :attr:`App.invoker`.
"""

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from hexagenpy.contracts import ir
from hexagenpy.contracts.compat import check_registry
from hexagenpy.contracts.registry import ContractRegistry
from hexagenpy.core.context import RequestContext
from hexagenpy.core.error_mapping import ErrorMapper
from hexagenpy.core.invoke import Invoker
from hexagenpy.di.container import Container, RequestScope
from hexagenpy.di.providers import Provider, provide, provide_context
from hexagenpy.errors import ContractError, ErrorKind
from hexagenpy.slices.module import Module

__all__ = ["App"]

type Hook = Callable[[], Awaitable[None] | None]


class App:
    """A hexagenpy application.

    ::

        app = App(slices=[orders.module, users.module],
                  providers=[provide_value(AppSettings, load_settings(AppSettings))])
    """

    def __init__(
        self,
        *,
        slices: Sequence[Module] = (),
        providers: Sequence[Provider | type] = (),
        error_map: Mapping[type[BaseException], ErrorKind] | None = None,
        name: str = "hexagenpy",
        version: str = "0.1.0",
    ) -> None:
        self.name = name
        self.version = version
        self.slices = _unique_slices(slices)
        self.contracts = ContractRegistry()
        for module in self.slices:
            for controller in module.controllers:
                self.contracts.add_controller(controller, module.name)
        issues = check_registry(self.contracts)
        if issues:
            raise ContractError(
                "contracts not representable on their transports:\n  - "
                + "\n  - ".join(map(str, issues))
            )
        app_providers = [p if isinstance(p, Provider) else provide(p) for p in providers]
        self.container = Container(
            [
                provide_context(RequestContext),
                *app_providers,
                *(p for m in self.slices for p in m.all_providers()),
            ],
            exports={m.name: frozenset(m.exports) for m in self.slices},
        )
        self.invoker = Invoker(self.container, self.contracts.operations)
        self.errors = ErrorMapper(error_map)
        self._on_startup: list[Hook] = []
        self._on_shutdown: list[Hook] = []

    # ------------------------------------------------------------------ introspection

    @property
    def operations(self) -> Mapping[str, ir.Operation]:
        return self.contracts.operations

    def operation(self, operation_id: str) -> ir.Operation:
        return self.contracts.operation(operation_id)

    # ------------------------------------------------------------------ lifecycle

    def on_startup[H: Hook](self, hook: H) -> H:
        self._on_startup.append(hook)
        return hook

    def on_shutdown[H: Hook](self, hook: H) -> H:
        self._on_shutdown.append(hook)
        return hook

    @property
    def started(self) -> bool:
        return self.container.started

    async def start(self) -> None:
        await self.container.start()
        try:
            for hook in self._on_startup:
                await _run_hook(hook)
        except BaseException:
            await self.container.aclose()
            raise

    async def stop(self) -> None:
        """Run shutdown hooks (in reverse order) even if one fails, then close the container."""
        errors: list[Exception] = []
        for hook in reversed(self._on_shutdown):
            try:
                await _run_hook(hook)
            except Exception as exc:
                errors.append(exc)
        await self.container.aclose()
        if errors:
            raise ExceptionGroup("shutdown hooks failed", errors)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator["App"]:
        await self.start()
        try:
            yield self
        finally:
            await self.stop()

    # ------------------------------------------------------------------ execution

    def request_scope(self, context: RequestContext | None = None) -> RequestScope:
        """Open a request scope; ``context`` defaults to a ``"local"`` RequestContext."""
        return self.container.request_scope({RequestContext: context or RequestContext("local")})

    async def invoke(self, operation_id: str, args: Any = None, *, strict: bool = True) -> Any:
        """Run one operation in its own request scope (convenience for scripts and tests).

        Streaming operations must be invoked through :attr:`invoker` with an explicit
        scope that stays open while the stream is consumed.
        """
        if self.operation(operation_id).kind == "stream":
            raise ContractError(f"{operation_id} is a stream; use app.invoker with a scope")
        async with self.request_scope() as scope:
            return await self.invoker.invoke(operation_id, args or {}, scope, strict=strict)


async def _run_hook(hook: Hook) -> None:
    result = hook()
    if inspect.isawaitable(result):
        await result


def _unique_slices(slices: Sequence[Module]) -> tuple[Module, ...]:
    seen: set[str] = set()
    for module in slices:
        if module.name in seen:
            raise ContractError(f"slice {module.name!r} is registered twice")
        seen.add(module.name)
    return tuple(slices)
