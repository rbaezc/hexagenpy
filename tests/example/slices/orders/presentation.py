"""Presentation layer: one controller, exposed on every transport."""

from collections.abc import AsyncIterator

from hexagenpy import Controller, endpoint
from tests.example.slices.orders.application import OrdersService
from tests.example.slices.orders.contracts import OrderIn, OrderOut


class OrdersController(Controller, prefix="/orders", tag="orders"):
    def __init__(self, service: OrdersService) -> None:
        self.service = service

    @endpoint(http="POST /", graphql="mutation", grpc=True, status=201)
    async def create_order(self, data: OrderIn) -> OrderOut:
        """Create an order."""
        order = await self.service.create(data.customer, [(ln.sku, ln.qty) for ln in data.lines])
        return OrderOut.from_domain(order)

    @endpoint(http="GET /{id}", graphql="query", grpc=True)
    async def get_order(self, id: int) -> OrderOut:
        return OrderOut.from_domain(await self.service.get(id))

    @endpoint(http="GET /{id}/summary")
    def order_summary(self, id: int, verbose: bool = False) -> str:
        """A sync handler: runs in a worker thread."""
        return f"order {id}" + (" (verbose)" if verbose else "")

    @endpoint(graphql="subscription", grpc=True)
    async def countdown(self, start: int) -> AsyncIterator[int]:
        for value in range(start, 0, -1):
            yield value
