import threading
from typing import Any

import pytest

from hexagenpy import App, Controller, ErrorKind, Model, Module, NotFound, endpoint
from hexagenpy.contracts import ir
from hexagenpy.errors import ContractError
from hexagenpy.testing import TestApp
from tests.example.app import create_app
from tests.example.slices.orders.domain import Order, OrdersRepository

ORDER = {"customer": "ACME", "lines": [{"sku": "A-1", "qty": 2}, {"sku": "B-2", "qty": 3}]}


async def test_create_and_get_order_round_trip() -> None:
    async with TestApp(create_app()) as client:
        created = await client.call_json("orders.create_order", data=ORDER)
        assert created == {
            "id": 1,
            "customer": "ACME",
            "status": "new",
            "lines": [{"sku": "A-1", "qty": 2}, {"sku": "B-2", "qty": 3}],
        }
        fetched = await client.call("orders.get_order", id=1)
        assert fetched.customer == "ACME"


async def test_cross_slice_dependency_through_exports() -> None:
    async with TestApp(create_app()) as client:
        await client.call("orders.create_order", data=ORDER)
        invoice = await client.call_json("billing.get_invoice", order_id=1)
        assert invoice == {"order_id": 1, "customer": "ACME", "units": 5}


async def test_validation_errors_are_mapped() -> None:
    async with TestApp(create_app()) as client:
        bad_qty = {"customer": "ACME", "lines": [{"sku": "A", "qty": 0}]}
        error = await client.call_error("orders.create_order", data=bad_qty)
        assert error.kind is ErrorKind.VALIDATION
        assert "lines[0].qty" in error.message

        empty = await client.call_error("orders.create_order", data={"customer": "x", "lines": []})
        assert error.kind is empty.kind is ErrorKind.VALIDATION  # ValueError via error_map


async def test_domain_exception_mapped_through_error_map() -> None:
    async with TestApp(create_app()) as client:
        error = await client.call_error("orders.get_order", id=99)
        assert error.kind is ErrorKind.NOT_FOUND
        assert error.message == "order 99 does not exist"


async def test_sync_handler_runs_off_the_event_loop() -> None:
    main_thread = threading.get_ident()
    seen: list[int] = []

    class Probe(Controller):
        @endpoint()
        def where(self) -> int:
            seen.append(threading.get_ident())
            return 1

    async with TestApp(App(slices=[Module("probe", controllers=[Probe])])) as client:
        assert await client.call("probe.where") == 1
    assert len(seen) == 1
    assert seen[0] != main_thread


async def test_sync_handler_with_defaults_and_coercion() -> None:
    app = create_app()
    async with app.lifespan():
        text = await app.invoke(
            "orders.order_summary", {"id": "7", "verbose": "true"}, strict=False
        )
        assert text == "order 7 (verbose)"
        assert await app.invoke("orders.order_summary", {"id": 7}) == "order 7"


async def test_streaming_operation_through_invoker() -> None:
    app = create_app()
    async with app.lifespan(), app.request_scope() as scope:
        stream = await app.invoker.invoke("orders.countdown", {"start": 3}, scope)
        assert [value async for value in stream] == [3, 2, 1]


async def test_invoker_accepts_prevalidated_args_struct() -> None:
    app = create_app()
    compiled = app.invoker.compiled("orders.order_summary")
    assert compiled.param_names == ("id", "verbose")
    assert not compiled.controller_scoped
    args = compiled.operation.args_type(id=3, verbose=True)
    async with app.lifespan():
        assert await app.invoke("orders.order_summary", args) == "order 3 (verbose)"


async def test_streams_cannot_use_app_invoke() -> None:
    app = create_app()
    async with app.lifespan():
        with pytest.raises(ContractError, match="is a stream"):
            await app.invoke("orders.countdown", {"start": 1})


async def test_overrides_replace_dependencies() -> None:
    class FakeRepo:
        async def get(self, order_id: int) -> Order | None:
            return Order(id=order_id, customer="fake", lines=())

        async def add(self, order: Order) -> None:
            raise AssertionError("not used")

        async def next_id(self) -> int:
            return 0

    async with TestApp(create_app(), overrides={OrdersRepository: FakeRepo()}) as client:
        order = await client.call("orders.get_order", id=5)
        assert (order.id, order.customer) == (5, "fake")


async def test_operations_are_compiled_with_bindings() -> None:
    app = create_app()
    assert set(app.operations) == {
        "orders.create_order",
        "orders.get_order",
        "orders.order_summary",
        "orders.countdown",
        "billing.get_invoice",
    }
    create = app.operation("orders.create_order")
    assert create.bindings["http"].path == "/orders"
    assert create.bindings["http"].status == 201
    assert create.description == "Create an order."
    assert create.tags == ("orders",)
    assert app.operation("billing.get_invoice").tags == ("billing",)
    assert isinstance(app.operation("orders.countdown").returns, ir.Stream)
    assert {"OrderIn", "OrderOut", "LineIn", "LineOut", "OrderStatus", "Invoice"} <= set(
        app.contracts.definitions
    )


async def test_lifecycle_hooks_run_in_order() -> None:
    events: list[str] = []
    app = create_app()

    @app.on_startup
    def first() -> None:
        events.append("start-1")

    @app.on_startup
    async def second() -> None:
        events.append("start-2")

    @app.on_shutdown
    async def closing() -> None:
        events.append("stop-1")

    @app.on_shutdown
    def closing_last_registered() -> None:
        events.append("stop-2")

    async with app.lifespan():
        started_inside = app.started
    assert started_inside
    assert app.started is False
    assert events == ["start-1", "start-2", "stop-2", "stop-1"]


async def test_failing_startup_hook_closes_container() -> None:
    app = create_app()

    @app.on_startup
    def boom() -> None:
        raise RuntimeError("cannot connect")

    with pytest.raises(RuntimeError, match="cannot connect"):
        await app.start()
    assert not app.started


async def test_shutdown_errors_are_grouped_and_all_hooks_run() -> None:
    app = create_app()
    ran: list[str] = []

    @app.on_shutdown
    def ok() -> None:
        ran.append("ok")

    @app.on_shutdown
    def bad() -> None:
        raise RuntimeError("bad")

    await app.start()
    with pytest.raises(ExceptionGroup) as group:
        await app.stop()
    assert ran == ["ok"]
    assert not app.started
    assert isinstance(group.value.exceptions[0], RuntimeError)


def test_duplicate_slices_are_rejected() -> None:
    from tests.example.slices.orders.module import module

    with pytest.raises(ContractError, match="registered twice"):
        App(slices=[module, module])


def test_incompatible_contracts_fail_at_construction() -> None:
    class WithMap(Model):
        values: dict[str, int]

    class Bad(Controller):
        @endpoint(graphql="query")
        async def stats(self) -> WithMap:
            return WithMap(values={})

    with pytest.raises(ContractError, match=r"\[graphql\] bad.stats -> WithMap.values"):
        App(slices=[Module("bad", controllers=[Bad])])


async def test_domain_errors_raised_directly() -> None:
    class Strict(Controller):
        @endpoint()
        async def find(self, key: str) -> str:
            raise NotFound(f"{key} missing", code="key_missing", details={"key": key})

    async with TestApp(App(slices=[Module("strict", controllers=[Strict])])) as client:
        error = await client.call_error("strict.find", key="k")
    assert (error.kind, error.code, error.details) == (
        ErrorKind.NOT_FOUND,
        "key_missing",
        {"key": "k"},
    )


async def test_call_error_requires_failure() -> None:
    async with TestApp(create_app()) as client:
        await client.call("orders.create_order", data=ORDER)
        with pytest.raises(AssertionError, match="did not raise"):
            await client.call_error("orders.get_order", id=1)


async def test_test_app_restores_overrides_when_start_fails() -> None:
    app = create_app()

    @app.on_startup
    def boom() -> None:
        raise RuntimeError("x")

    fake: Any = object()
    with pytest.raises(RuntimeError):
        async with TestApp(app, overrides={OrdersRepository: fake}):
            pass
    async with app.container.request_scope():
        pass  # container is usable again; override was rolled back
    with app.container.override(OrdersRepository, fake):
        pass
