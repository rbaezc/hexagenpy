"""Testing utilities: ``TestApp`` drives an ``App`` without any network transport.

::

    async def test_create_order() -> None:
        async with TestApp(app, overrides={OrdersRepository: FakeRepo()}) as client:
            order = await client.call("orders.create_order", data={"customer": "ACME"})
            assert order.customer == "ACME"

Per-transport clients (HTTP, GraphQL, gRPC) are added with each transport.
"""

from collections.abc import Mapping
from contextlib import ExitStack
from types import TracebackType
from typing import Any, Self

from hexagenpy.contracts.model import to_builtins
from hexagenpy.core.app import App
from hexagenpy.core.error_mapping import ErrorInfo

__all__ = ["TestApp"]


class TestApp:
    __test__ = False  # not a pytest test class

    def __init__(self, app: App, *, overrides: Mapping[object, Any] | None = None) -> None:
        self.app = app
        self._overrides = dict(overrides or {})
        self._stack = ExitStack()

    async def __aenter__(self) -> Self:
        for key, value in self._overrides.items():
            self._stack.enter_context(self.app.container.override(key, value))
        try:
            await self.app.start()
        except BaseException:
            self._stack.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self.app.stop()
        finally:
            self._stack.close()

    async def call(self, operation_id: str, /, **args: Any) -> Any:
        """Invoke an operation with keyword arguments; returns the handler's result."""
        return await self.app.invoke(operation_id, args)

    async def call_json(self, operation_id: str, /, **args: Any) -> Any:
        """Like :meth:`call`, but returns plain builtins (dicts/lists), as a client sees it."""
        return to_builtins(await self.call(operation_id, **args))

    async def call_error(self, operation_id: str, /, **args: Any) -> ErrorInfo:
        """Invoke an operation that is expected to fail; returns the mapped error."""
        try:
            await self.call(operation_id, **args)
        except Exception as exc:
            return self.app.errors.to_info(exc)
        raise AssertionError(f"{operation_id} did not raise")
