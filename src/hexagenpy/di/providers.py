"""Provider declarations and their compiled resolution plans."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal, get_type_hints

from hexagenpy.errors import ResolutionError

__all__ = [
    "Plan",
    "Provider",
    "Scope",
    "compile_plan",
    "key_name",
    "provide",
    "provide_context",
    "provide_value",
]


class Scope(StrEnum):
    SINGLETON = "singleton"
    """One instance for the whole application, created at startup."""
    REQUEST = "request"
    """One instance per request/call, disposed when the request ends."""
    TRANSIENT = "transient"
    """A new instance every time it is injected."""


class _Unset:
    __slots__ = ()


UNSET: Final[Any] = _Unset()
FactoryKind = Literal["value", "context", "sync", "async", "gen", "agen"]


@dataclass(frozen=True, slots=True)
class Provider:
    """How to obtain the dependency registered under ``key``.

    ``scope=None`` means *auto*: singleton unless a dependency is request-scoped (used for
    controllers). ``owner`` is the slice that registered it (set by ``Module``).
    """

    key: Any
    factory: Callable[..., Any] | None = None
    scope: Scope | None = Scope.SINGLETON
    value: Any = UNSET
    context: bool = False
    owner: str | None = None


def provide(
    key: Any, factory: Callable[..., Any] | None = None, *, scope: Scope | None = Scope.SINGLETON
) -> Provider:
    """Register ``factory`` (default: ``key`` itself, which must be a class) for ``key``.

    Factories may be classes, functions, coroutine functions, or (async) generator
    functions; generators are torn down when their scope ends::

        provide(OrdersRepository, SqlOrdersRepository)
        provide(Session, open_session, scope=Scope.REQUEST)   # def open_session(): yield s
    """
    if factory is None:
        if not inspect.isclass(key):
            raise ResolutionError(f"provide({key!r}) needs a factory: the key is not a class")
        factory = key
    return Provider(key=key, factory=factory, scope=scope)


def provide_value(key: Any, value: Any) -> Provider:
    """Register an already-built singleton (settings, clients created elsewhere)."""
    return Provider(key=key, value=value, scope=Scope.SINGLETON)


def provide_context(key: Any) -> Provider:
    """Declare a request-scoped value supplied by the transport (e.g. the HTTP request)."""
    return Provider(key=key, scope=Scope.REQUEST, context=True)


def key_name(key: Any) -> str:
    name = getattr(key, "__qualname__", None)
    return name if isinstance(name, str) else repr(key)


@dataclass(frozen=True, slots=True)
class Dependency:
    param: str
    key: Any
    default: Any = UNSET

    @property
    def optional(self) -> bool:
        return self.default is not UNSET


@dataclass(frozen=True, slots=True)
class Plan:
    """A provider analysed once at build time, so resolution does no introspection."""

    provider: Provider
    kind: FactoryKind
    deps: tuple[Dependency, ...]
    scope: Scope

    @property
    def key(self) -> Any:
        return self.provider.key


def _factory_kind(factory: Callable[..., Any]) -> FactoryKind:
    if inspect.isasyncgenfunction(factory):
        return "agen"
    if inspect.isgeneratorfunction(factory):
        return "gen"
    if inspect.iscoroutinefunction(factory):
        return "async"
    return "sync"


def _dependencies(factory: Callable[..., Any]) -> tuple[Dependency, ...]:
    target = factory.__init__ if inspect.isclass(factory) else factory
    try:
        hints = get_type_hints(target, include_extras=False)
        signature = inspect.signature(factory)
    except (NameError, TypeError, ValueError) as exc:
        raise ResolutionError(f"cannot inspect factory {key_name(factory)}: {exc}") from exc
    deps: list[Dependency] = []
    for param in signature.parameters.values():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        has_default = param.default is not inspect.Parameter.empty
        if param.name not in hints:
            if has_default:
                continue
            raise ResolutionError(
                f"{key_name(factory)}: parameter {param.name!r} needs a type annotation to be "
                "injected"
            )
        deps.append(
            Dependency(param.name, hints[param.name], param.default if has_default else UNSET)
        )
    return tuple(deps)


def compile_plan(provider: Provider) -> Plan:
    if provider.value is not UNSET:
        return Plan(provider, "value", (), Scope.SINGLETON)
    if provider.context:
        return Plan(provider, "context", (), Scope.REQUEST)
    if provider.factory is None:
        raise ResolutionError(f"provider for {key_name(provider.key)} has no factory")
    kind = _factory_kind(provider.factory)
    deps = _dependencies(provider.factory)
    # scope=None (auto) is settled by the graph analysis; SINGLETON is a placeholder.
    return Plan(provider, kind, deps, provider.scope or Scope.SINGLETON)
