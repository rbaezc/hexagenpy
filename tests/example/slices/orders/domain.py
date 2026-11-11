"""Domain layer: entities and ports. Must not import hexagenpy."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class OrderStatus(Enum):
    NEW = "new"
    PAID = "paid"


@dataclass(frozen=True)
class OrderLine:
    sku: str
    qty: int


@dataclass(frozen=True)
class Order:
    id: int
    customer: str
    lines: tuple[OrderLine, ...]
    status: OrderStatus = OrderStatus.NEW


class OrderNotFoundError(Exception):
    """Raised by the domain; mapped to NOT_FOUND via App(error_map=...)."""


class OrdersRepository(Protocol):
    async def get(self, order_id: int) -> Order | None: ...

    async def add(self, order: Order) -> None: ...

    async def next_id(self) -> int: ...
