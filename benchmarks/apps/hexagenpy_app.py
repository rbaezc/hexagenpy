"""hexagenpy: the same three endpoints, declared as a slice."""

from typing import Annotated

from hexagenpy import App, Controller, Meta, Model, Module, endpoint
from hexagenpy.transports.http import HttpApp


class Item(Model):
    sku: str
    qty: Annotated[int, Meta(gt=0)]


class Order(Model):
    customer: str
    items: list[Item]
    total: Annotated[float, Meta(ge=0)]


class BenchController(Controller):
    @endpoint(http="GET /json")
    async def hello(self) -> dict[str, str]:
        return {"message": "hello"}

    @endpoint(http="GET /items/{item_id}")
    async def get_item(self, item_id: int) -> dict[str, int]:
        return {"id": item_id}

    @endpoint(http="POST /orders", status=201)
    async def create_order(self, order: Order) -> Order:
        return order


app = HttpApp(
    App(slices=[Module("bench", controllers=[BenchController])]),
    openapi_url=None,
)
