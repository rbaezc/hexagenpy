"""Billing slice: depends on another slice only through its exported service."""

from hexagenpy import Controller, Model, Module, endpoint
from tests.example.slices.orders.application import OrdersService


class Invoice(Model):
    order_id: int
    customer: str
    units: int


class BillingService:
    def __init__(self, orders: OrdersService) -> None:
        self._orders = orders

    async def invoice(self, order_id: int) -> Invoice:
        order = await self._orders.get(order_id)
        return Invoice(
            order_id=order.id,
            customer=order.customer,
            units=sum(line.qty for line in order.lines),
        )


class BillingController(Controller, prefix="/billing"):
    def __init__(self, service: BillingService) -> None:
        self.service = service

    @endpoint(http="GET /invoices/{order_id}", graphql="query")
    async def get_invoice(self, order_id: int) -> Invoice:
        return await self.service.invoice(order_id)


module = Module("billing", providers=[BillingService], controllers=[BillingController])
