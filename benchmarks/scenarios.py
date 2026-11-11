"""Benchmark scenarios shared by every framework app.

All apps must implement exactly these three endpoints with the same semantics:

* ``json``  - ``GET /json``         -> 200 ``{"message": "hello"}``
* ``path``  - ``GET /items/{id}``   -> 200 ``{"id": <int>}`` (id parsed as int)
* ``body``  - ``POST /orders``      -> 201 echo of a validated order
  (customer: str, items: list[{sku: str, qty: int > 0}], total: float >= 0)
"""

import json
from dataclasses import dataclass, field

ORDER = {
    "customer": "ACME Corp",
    "items": [{"sku": f"SKU-{i}", "qty": i + 1} for i in range(10)],
    "total": 1234.5,
}


@dataclass(frozen=True)
class Scenario:
    name: str
    method: str
    path: str
    expected_status: int
    body: bytes = b""
    headers: list[tuple[bytes, bytes]] = field(default_factory=list)


SCENARIOS: dict[str, Scenario] = {
    "json": Scenario("json", "GET", "/json", 200),
    "path": Scenario("path", "GET", "/items/42", 200),
    "body": Scenario(
        "body",
        "POST",
        "/orders",
        201,
        body=json.dumps(ORDER).encode(),
        headers=[(b"content-type", b"application/json")],
    ),
}
