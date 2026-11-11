"""The example application, assembled from its slices."""

from hexagenpy import App, ErrorKind
from tests.example.slices.billing import module as billing
from tests.example.slices.orders import module as orders
from tests.example.slices.orders.domain import OrderNotFoundError


def create_app() -> App:
    return App(
        slices=[orders.module, billing.module],
        error_map={OrderNotFoundError: ErrorKind.NOT_FOUND, ValueError: ErrorKind.VALIDATION},
        name="example",
    )
