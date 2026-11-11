"""The dependency container: singletons for the app, plus one ``RequestScope`` per call."""

from collections.abc import Generator, Iterable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from types import TracebackType
from typing import Any, Self, cast

from hexagenpy.di.graph import build_plans
from hexagenpy.di.providers import Plan, Provider, Scope, compile_plan, key_name, provide_value
from hexagenpy.errors import ResolutionError

__all__ = ["Container", "RequestScope"]


class Container:
    """Validates the provider graph on construction and builds singletons on ``start()``.

    ::

        container = Container([provide(Repo, SqlRepo), provide(Service)])
        await container.start()
        async with container.request_scope() as scope:
            service = await scope.resolve(Service)
        await container.aclose()
    """

    def __init__(
        self,
        providers: Iterable[Provider] = (),
        *,
        exports: Mapping[str, frozenset[object]] | None = None,
    ) -> None:
        self._plans = build_plans(providers, exports or {})
        self._singletons: dict[object, Any] = {}
        self._stack = AsyncExitStack()
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def __contains__(self, key: object) -> bool:
        return key in self._plans

    def scope_of(self, key: object) -> Scope:
        return self._plan(key).scope

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Create every singleton, dependencies first. Fails fast on factory errors."""
        if self._started:
            return
        try:
            for key, plan in self._plans.items():
                if plan.scope is Scope.SINGLETON:
                    self._singletons[key] = await self._build(plan, None, self._stack)
        except BaseException:
            await self.aclose()
            raise
        self._started = True

    async def aclose(self) -> None:
        """Tear down singletons created by generator factories, in reverse order."""
        self._started = False
        self._singletons.clear()
        await self._stack.aclose()
        self._stack = AsyncExitStack()

    @contextmanager
    def override(self, key: object, value: Any) -> Generator[None]:
        """Replace a dependency (typically in tests). Only allowed before ``start()``.

        ``value`` may be an instance or a :class:`Provider` for the same key.
        """
        if self._started:
            raise ResolutionError("override() must be used before the container starts")
        previous = self._plan(key)
        provider = value if isinstance(value, Provider) else provide_value(key, value)
        if provider.key is not key:
            raise ResolutionError(f"override provider key must be {key_name(key)}")
        self._plans[key] = compile_plan(provider)
        try:
            yield
        finally:
            self._plans[key] = previous

    # ------------------------------------------------------------------ resolution

    def request_scope(self, context: Mapping[object, Any] | None = None) -> "RequestScope":
        return RequestScope(self, context or {})

    async def resolve[T](self, key: type[T]) -> T:
        """Resolve outside any request: singletons and request-free transients only."""
        return cast(T, await self.resolve_in(key, None))

    def _plan(self, key: object) -> Plan:
        try:
            return self._plans[key]
        except KeyError:
            raise ResolutionError(f"{key_name(key)} is not registered") from None

    async def resolve_in(self, key: object, request: "RequestScope | None") -> Any:
        """Resolve ``key`` within ``request`` (or outside any request when ``None``)."""
        plan = self._plan(key)
        if plan.scope is Scope.SINGLETON:
            if not self._started:
                raise ResolutionError("container not started; call await container.start()")
            return self._singletons[key]
        if plan.scope is Scope.TRANSIENT:
            stack = request.exit_stack if request is not None else self._stack
            return await self._build(plan, request, stack)
        if request is None:
            raise ResolutionError(f"{key_name(key)} is request-scoped; resolve it in a scope")
        if key in request.cache:
            return request.cache[key]
        if plan.kind == "context":
            raise ResolutionError(f"context value {key_name(key)} was not supplied by the caller")
        value = await self._build(plan, request, request.exit_stack)
        request.cache[key] = value
        return value

    async def _build(
        self, plan: Plan, request: "RequestScope | None", stack: AsyncExitStack
    ) -> Any:
        if plan.kind == "value":
            return plan.provider.value
        kwargs: dict[str, Any] = {}
        for dep in plan.deps:
            if dep.key not in self._plans:  # optional and unregistered: keep the default
                continue
            if self._plans[dep.key].scope is Scope.SINGLETON and not self._started:
                kwargs[dep.param] = self._singletons[dep.key]  # built earlier in start()
            else:
                kwargs[dep.param] = await self.resolve_in(dep.key, request)
        factory = plan.provider.factory
        assert factory is not None
        if plan.kind == "sync":
            return factory(**kwargs)
        if plan.kind == "async":
            return await factory(**kwargs)
        if plan.kind == "gen":
            return stack.enter_context(contextmanager(factory)(**kwargs))
        return await stack.enter_async_context(asynccontextmanager(factory)(**kwargs))


class RequestScope:
    """Per-request cache of request-scoped dependencies, disposed on exit."""

    def __init__(self, container: Container, context: Mapping[object, Any]) -> None:
        for key in context:
            if key not in container or container.scope_of(key) is not Scope.REQUEST:
                raise ResolutionError(
                    f"{key_name(key)} is not declared with provide_context(); cannot be supplied"
                )
        self._container = container
        self.cache: dict[object, Any] = dict(context)
        self.exit_stack = AsyncExitStack()

    async def resolve[T](self, key: type[T]) -> T:
        return cast(T, await self._container.resolve_in(key, self))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.cache.clear()
        await self.exit_stack.__aexit__(exc_type, exc, tb)
