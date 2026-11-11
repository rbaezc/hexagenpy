"""Starlette baseline: routing only, manual (minimal) validation.

This is the floor that FastAPI builds on; it shows the cost of FastAPI's own layers.
"""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


async def hello(_: Request) -> JSONResponse:
    return JSONResponse({"message": "hello"})


async def get_item(request: Request) -> JSONResponse:
    return JSONResponse({"id": request.path_params["item_id"]})


async def create_order(request: Request) -> JSONResponse:
    data = await request.json()
    if not isinstance(data.get("customer"), str) or float(data.get("total", -1)) < 0:
        return JSONResponse({"detail": "invalid order"}, status_code=422)
    if any(int(item["qty"]) <= 0 for item in data.get("items", [])):
        return JSONResponse({"detail": "invalid qty"}, status_code=422)
    return JSONResponse(data, status_code=201)


app = Starlette(
    routes=[
        Route("/json", hello),
        Route("/items/{item_id:int}", get_item),
        Route("/orders", create_order, methods=["POST"]),
    ]
)
