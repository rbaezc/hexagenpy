"""Infrastructure layer: adapters that conform to domain ports."""

import itertools

from tests.example.slices.orders.domain import Order


class InMemoryOrdersRepository:
    def __init__(self) -> None:
        self._orders: dict[int, Order] = {}
        self._ids = itertools.count(1)

    async def get(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    async def add(self, order: Order) -> None:
        self._orders[order.id] = order

    async def next_id(self) -> int:
        return next(self._ids)
