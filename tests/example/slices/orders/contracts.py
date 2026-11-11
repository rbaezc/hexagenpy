"""Contracts: what clients send and receive (validated by msgspec)."""

from typing import Annotated

from hexagenpy import Meta, Model
from tests.example.slices.orders.domain import Order, OrderStatus


class LineIn(Model):
    sku: Annotated[str, Meta(min_length=1)]
    qty: Annotated[int, Meta(gt=0, description="Units ordered")]


class OrderIn(Model):
    """A new order."""

    customer: Annotated[str, Meta(min_length=1, max_length=120)]
    lines: list[LineIn]


class LineOut(Model):
    sku: str
    qty: int


class OrderOut(Model):
    """An order as seen by clients."""

    id: int
    customer: str
    status: OrderStatus
    lines: list[LineOut]

    @classmethod
    def from_domain(cls, order: Order) -> "OrderOut":
        return cls(
            id=order.id,
            customer=order.customer,
            status=order.status,
            lines=[LineOut(sku=line.sku, qty=line.qty) for line in order.lines],
        )
