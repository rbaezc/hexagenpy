"""``@endpoint`` and ``Controller``: how a slice declares its operations and transports.

::

    class OrdersController(Controller, prefix="/orders", tag="orders"):
        def __init__(self, service: OrdersService) -> None:
            self.service = service

        @endpoint(http="GET /{id}", graphql="query", grpc=True)
        async def get_order(self, id: int) -> OrderOut: ...

The decorator only records metadata; nothing is compiled until the ``App`` is built.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from hexagenpy.errors import ContractError

__all__ = [
    "Controller",
    "EndpointSpec",
    "GraphQLBinding",
    "GrpcBinding",
    "HttpBinding",
    "endpoint",
]

ENDPOINT_ATTR = "__hexagen_endpoint__"
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
GraphQLKind = Literal["query", "mutation", "subscription"]

_HTTP_RE = re.compile(r"^(?P<method>[A-Z]+)\s+(?P<path>/\S*)$")


@dataclass(frozen=True, slots=True)
class HttpBinding:
    method: str
    path: str
    """Path relative to the controller prefix; joined in :meth:`full_path`."""
    status: int

    def full_path(self, prefix: str) -> str:
        parts = (prefix.strip("/"), self.path.strip("/"))
        return "/" + "/".join(p for p in parts if p)


@dataclass(frozen=True, slots=True)
class GraphQLBinding:
    kind: GraphQLKind
    name: str | None = None


@dataclass(frozen=True, slots=True)
class GrpcBinding:
    name: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    http: HttpBinding | None = None
    graphql: GraphQLBinding | None = None
    grpc: GrpcBinding | None = None
    name: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    deprecated: bool = False

    def bindings(self) -> dict[str, Any]:
        found = {"http": self.http, "graphql": self.graphql, "grpc": self.grpc}
        return {key: value for key, value in found.items() if value is not None}


def parse_http(route: str, status: int | None) -> HttpBinding:
    match = _HTTP_RE.match(route.strip())
    if match is None or match["method"] not in HTTP_METHODS:
        raise ContractError(f"invalid http route {route!r}; expected e.g. 'GET /items/{{id}}'")
    return HttpBinding(match["method"], match["path"], status or 200)


def endpoint[F: Callable[..., Any]](
    *,
    http: str | None = None,
    graphql: GraphQLKind | None = None,
    grpc: bool | str = False,
    status: int | None = None,
    name: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    tags: tuple[str, ...] = (),
    deprecated: bool = False,
) -> Callable[[F], F]:
    """Declare a controller method as an operation exposed on the given transports.

    ``grpc`` may be ``True`` (method name derived from the operation) or the explicit
    gRPC method name. ``graphql`` selects the root type the field is added to.
    """
    if status is not None and http is None:
        raise ContractError("status= only applies to http endpoints")
    if graphql is not None and graphql not in ("query", "mutation", "subscription"):
        raise ContractError(f"invalid graphql kind {graphql!r}")
    spec = EndpointSpec(
        http=parse_http(http, status) if http is not None else None,
        graphql=GraphQLBinding(graphql) if graphql is not None else None,
        grpc=GrpcBinding(grpc if isinstance(grpc, str) else None) if grpc else None,
        name=name,
        summary=summary,
        description=description,
        tags=tags,
        deprecated=deprecated,
    )

    def decorate(fn: F) -> F:
        setattr(fn, ENDPOINT_ATTR, spec)
        return fn

    return decorate


@dataclass(frozen=True, slots=True)
class ControllerMeta:
    prefix: str = ""
    tags: tuple[str, ...] = ()
    endpoints: dict[str, EndpointSpec] = field(default_factory=dict[str, EndpointSpec])


class Controller:
    """Base class for the presentation layer of a slice.

    Subclass keywords: ``prefix`` (HTTP path prefix) and ``tag`` (OpenAPI tag and
    default grouping). Dependencies are declared in ``__init__`` and injected.
    """

    __hexagen_controller__: ClassVar[ControllerMeta] = ControllerMeta()

    def __init_subclass__(cls, *, prefix: str = "", tag: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if prefix and not prefix.startswith("/"):
            raise ContractError(f"{cls.__name__}: prefix must start with '/' (got {prefix!r})")
        endpoints: dict[str, EndpointSpec] = {}
        for klass in reversed(cls.__mro__):  # subclasses override parents
            for attr, value in vars(klass).items():
                target: object = getattr(value, "__func__", value)  # unwrap static/class
                spec = getattr(target, ENDPOINT_ATTR, None)
                if isinstance(spec, EndpointSpec):
                    endpoints[attr] = spec
        parent = cls.__hexagen_controller__
        cls.__hexagen_controller__ = ControllerMeta(
            prefix=prefix or parent.prefix,
            tags=(tag,) if tag else parent.tags,
            endpoints=endpoints,
        )
