from collections.abc import AsyncIterator

import pytest

from hexagenpy.testing.http import HttpTestClient
from hexagenpy.transports.http import HttpApp
from tests.example.app import create_app

ORDER = {"customer": "ACME", "lines": [{"sku": "A-1", "qty": 2}]}


@pytest.fixture
async def client() -> AsyncIterator[HttpTestClient]:
    async with HttpTestClient(HttpApp(create_app())) as test_client:
        yield test_client
