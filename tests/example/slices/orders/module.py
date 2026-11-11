"""Composition root of the orders slice."""

from hexagenpy import Module, provide
from tests.example.slices.orders.application import OrdersService
from tests.example.slices.orders.domain import OrdersRepository
from tests.example.slices.orders.infrastructure import InMemoryOrdersRepository
from tests.example.slices.orders.presentation import OrdersController

module = Module(
    "orders",
    providers=[provide(OrdersRepository, InMemoryOrdersRepository), OrdersService],
    controllers=[OrdersController],
    exports=[OrdersService],
)
