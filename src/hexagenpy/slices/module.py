"""``Module``: the composition root of a vertical slice.

::

    # app/slices/orders/module.py
    module = Module(
        "orders",
        providers=[provide(OrdersRepository, InMemoryOrdersRepository), OrdersService],
        controllers=[OrdersController],
        exports=[OrdersService],          # what other slices may inject
    )

Everything a slice registers is private to it unless listed in ``exports``; the
container rejects any other cross-slice dependency at startup.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from hexagenpy.contracts.endpoint import Controller
from hexagenpy.di.providers import Provider, provide
from hexagenpy.errors import ContractError

__all__ = ["Module"]

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Module:
    name: str
    providers: Sequence[Provider | type] = ()
    controllers: Sequence[type[Controller]] = ()
    exports: Sequence[Any] = ()
    description: str | None = None

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ContractError(f"slice name {self.name!r} must be snake_case")
        for controller in self.controllers:
            is_controller = isinstance(controller, type) and issubclass(controller, Controller)  # pyright: ignore[reportUnnecessaryIsInstance]
            if not is_controller:
                raise ContractError(f"{self.name}: {controller!r} is not a Controller subclass")
        registered = {p.key if isinstance(p, Provider) else p for p in self.providers}
        missing = [e for e in self.exports if e not in registered]
        if missing:
            raise ContractError(f"{self.name}: exports {missing!r} are not provided by the slice")

    def all_providers(self) -> list[Provider]:
        """Providers owned by this slice, controllers included (auto scope)."""
        owned = [
            replace(p if isinstance(p, Provider) else provide(p), owner=self.name)
            for p in self.providers
        ]
        owned += [replace(provide(c, scope=None), owner=self.name) for c in self.controllers]
        return owned
