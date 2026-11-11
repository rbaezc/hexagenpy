"""Application layer: use cases. Depends only on domain ports."""

from tests.example.slices.orders.domain import (
    Order,
    OrderLine,
    OrderNotFoundError,
    OrdersRepository,
)


class OrdersService:
    def __init__(self, repository: OrdersRepository) -> None:
        self._repository = repository

    async def create(self, customer: str, lines: list[tuple[str, int]]) -> Order:
        if not lines:
            raise ValueError("an order needs at least one line")
        order = Order(
            id=await self._repository.next_id(),
            customer=customer,
            lines=tuple(OrderLine(sku, qty) for sku, qty in lines),
        )
        await self._repository.add(order)
        return order

    async def get(self, order_id: int) -> Order:
        order = await self._repository.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"order {order_id} does not exist")
        return order
