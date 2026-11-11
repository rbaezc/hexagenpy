from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import Protocol

import pytest

from hexagenpy.di import (
    Container,
    Provider,
    Scope,
    provide,
    provide_context,
    provide_value,
)
from hexagenpy.errors import ResolutionError


class Config:
    def __init__(self) -> None:
        self.url = "sqlite://"


class Repo(Protocol):
    def name(self) -> str: ...


class SqlRepo:
    def __init__(self, config: Config) -> None:
        self.config = config

    def name(self) -> str:
        return "sql"


class Service:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo


class Request:
    def __init__(self, path: str) -> None:
        self.path = path


class Handler:
    def __init__(self, service: Service, request: Request) -> None:
        self.service = service
        self.request = request


def basic() -> list[Provider]:
    return [provide(Config), provide(Repo, SqlRepo), provide(Service)]


async def test_singletons_are_built_once_at_start() -> None:
    container = Container(basic())
    with pytest.raises(ResolutionError, match="not started"):
        await container.resolve(Service)
    await container.start()
    await container.start()  # idempotent
    service = await container.resolve(Service)
    assert service is await container.resolve(Service)
    assert service.repo.name() == "sql"
    assert container.scope_of(Service) is Scope.SINGLETON
    assert Service in container
    await container.aclose()
    assert not container.started


async def test_request_and_transient_scopes() -> None:
    counter = iter(range(100))

    def make_id() -> int:
        return next(counter)

    container = Container(
        [
            *basic(),
            provide_context(Request),
            provide(Handler, scope=Scope.REQUEST),
            provide(int, make_id, scope=Scope.TRANSIENT),
        ]
    )
    await container.start()
    async with container.request_scope({Request: Request("/a")}) as scope:
        handler = await scope.resolve(Handler)
        assert handler is await scope.resolve(Handler)
        assert handler.request.path == "/a"
        assert handler.service is await container.resolve(Service)
        assert await scope.resolve(int) != await scope.resolve(int)
    async with container.request_scope({Request: Request("/b")}) as scope:
        assert (await scope.resolve(Handler)) is not handler
    assert await container.resolve(int) >= 0  # request-free transient outside a scope
    with pytest.raises(ResolutionError, match="request-scoped"):
        await container.resolve(Handler)
    async with container.request_scope() as scope:
        with pytest.raises(ResolutionError, match="was not supplied"):
            await scope.resolve(Request)


async def test_generator_factories_are_torn_down_in_reverse_order() -> None:
    events: list[str] = []

    class Pool:
        pass

    class Session:
        pass

    async def open_pool() -> AsyncIterator[Pool]:
        events.append("pool:open")
        yield Pool()
        events.append("pool:close")

    def open_session(pool: Pool) -> Iterator[Session]:
        events.append("session:open")
        yield Session()
        events.append("session:close")

    async def make_label() -> str:
        return "label"

    container = Container(
        [
            provide(Pool, open_pool),
            provide(Session, open_session, scope=Scope.REQUEST),
            provide(str, make_label),
        ]
    )
    await container.start()
    assert await container.resolve(str) == "label"
    async with container.request_scope() as scope:
        await scope.resolve(Session)
        assert events == ["pool:open", "session:open"]
    assert events[-1] == "session:close"
    await container.aclose()
    assert events == ["pool:open", "session:open", "session:close", "pool:close"]


async def test_failing_singleton_closes_what_was_opened() -> None:
    events: list[str] = []

    class Pool:
        pass

    def open_pool() -> Iterator[Pool]:
        yield Pool()
        events.append("closed")

    def broken(pool: Pool) -> int:
        raise RuntimeError("boom")

    container = Container([provide(Pool, open_pool), provide(int, broken)])
    with pytest.raises(RuntimeError, match="boom"):
        await container.start()
    assert events == ["closed"]
    assert not container.started


def test_graph_errors() -> None:
    with pytest.raises(ResolutionError, match="registered twice"):
        Container([provide(Config), provide(Config)])
    with pytest.raises(ResolutionError, match=r"Service needs Repo \(parameter 'repo'\)"):
        Container([provide(Service)])
    with pytest.raises(ResolutionError, match="singleton Handler depends on request-scoped"):
        Container([*basic(), provide_context(Request), provide(Handler)])


def test_cycles_are_reported_with_path() -> None:
    class A:
        def __init__(self, b: "B") -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    globals().update(A=A, B=B)  # forward reference resolution
    try:
        with pytest.raises(ResolutionError, match=r"dependency cycle: .*A -> .*B -> .*A"):
            Container([provide(A), provide(B)])
    finally:
        del globals()["A"], globals()["B"]


async def test_auto_scope_follows_dependencies() -> None:
    container = Container(
        [
            *basic(),
            provide_context(Request),
            provide(Handler, scope=None),
            provide_value(float, 1.5),
        ]
    )
    assert container.scope_of(Handler) is Scope.REQUEST
    assert container.scope_of(float) is Scope.SINGLETON
    auto_singleton = Container([provide(Config, scope=None)])
    assert auto_singleton.scope_of(Config) is Scope.SINGLETON


async def test_optional_dependencies_keep_defaults() -> None:
    class Cache:
        pass

    class WithDefaults:
        def __init__(self, cache: Cache | None = None, retries=3) -> None:  # type: ignore[no-untyped-def]
            self.cache = cache
            self.retries = retries

    container = Container([provide(WithDefaults)])
    await container.start()
    value = await container.resolve(WithDefaults)
    assert (value.cache, value.retries) == (None, 3)


def test_factory_validation() -> None:
    with pytest.raises(ResolutionError, match="needs a factory"):
        provide("not-a-class")
    with pytest.raises(ResolutionError, match="has no factory"):
        Container([Provider(key=int)])

    def untyped(x):  # type: ignore[no-untyped-def]
        return x

    with pytest.raises(ResolutionError, match="needs a type annotation"):
        Container([provide(int, untyped)])

    def unresolvable(x: "Missing") -> int:  # type: ignore[name-defined]  # noqa: F821
        return 1

    with pytest.raises(ResolutionError, match="cannot inspect factory"):
        Container([provide(int, unresolvable)])

    def variadic(*args: int, **kwargs: int) -> int:
        return 1

    assert Container([provide(int, variadic)]).scope_of(int) is Scope.SINGLETON


def test_slice_visibility_requires_exports() -> None:
    providers = [
        replace(provide(Config), owner="core"),
        replace(provide(Repo, SqlRepo), owner="core"),
        replace(provide(Service), owner="orders"),
    ]
    with pytest.raises(ResolutionError, match="private to slice 'core'"):
        Container(providers)
    Container(providers, exports={"core": frozenset({Repo})})
    app_level = [provide(Config), replace(provide(Repo, SqlRepo), owner="orders")]
    Container(app_level)  # app-level providers are visible to every slice


async def test_overrides() -> None:
    class FakeRepo:
        def name(self) -> str:
            return "fake"

    container = Container(basic())
    with container.override(Repo, FakeRepo()):
        await container.start()
        assert (await container.resolve(Service)).repo.name() == "fake"
        with (
            pytest.raises(ResolutionError, match="before the container starts"),
            container.override(Repo, FakeRepo()),
        ):
            pass
        await container.aclose()
    with container.override(Repo, provide(Repo, FakeRepo)):
        await container.start()
        assert (await container.resolve(Service)).repo.name() == "fake"
        await container.aclose()
    await container.start()
    assert (await container.resolve(Service)).repo.name() == "sql"
    await container.aclose()

    with (
        pytest.raises(ResolutionError, match="override provider key"),
        container.override(Repo, provide(SqlRepo)),
    ):
        pass
    with (
        pytest.raises(ResolutionError, match="is not registered"),
        container.override(Handler, object()),
    ):
        pass


def test_context_values_must_be_declared() -> None:
    container = Container(basic())
    with pytest.raises(ResolutionError, match="not declared with provide_context"):
        container.request_scope({Request: Request("/")})
