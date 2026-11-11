"""FastAPI baseline (Pydantic v2 validation)."""

from fastapi import FastAPI
from pydantic import BaseModel, Field


class Item(BaseModel):
    sku: str
    qty: int = Field(gt=0)


class Order(BaseModel):
    customer: str
    items: list[Item]
    total: float = Field(ge=0)


app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


@app.get("/json")
async def hello() -> dict[str, str]:
    return {"message": "hello"}


@app.get("/items/{item_id}")
async def get_item(item_id: int) -> dict[str, int]:
    return {"id": item_id}


@app.post("/orders", status_code=201)
async def create_order(order: Order) -> Order:
    return order
