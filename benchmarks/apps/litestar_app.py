"""Litestar baseline (msgspec validation, the fastest mainstream competitor)."""

from typing import Annotated

import msgspec
from litestar import Litestar, get, post


class Item(msgspec.Struct):
    sku: str
    qty: Annotated[int, msgspec.Meta(gt=0)]


class Order(msgspec.Struct):
    customer: str
    items: list[Item]
    total: Annotated[float, msgspec.Meta(ge=0)]


@get("/json")
async def hello() -> dict[str, str]:
    return {"message": "hello"}


@get("/items/{item_id:int}")
async def get_item(item_id: int) -> dict[str, int]:
    return {"id": item_id}


@post("/orders", status_code=201)
async def create_order(data: Order) -> Order:
    return data


app = Litestar([hello, get_item, create_order], openapi_config=None, logging_config=None)
