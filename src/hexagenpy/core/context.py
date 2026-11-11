"""``RequestContext``: transport-neutral information about the current call.

Every transport supplies one per request (HTTP supplies ``HttpRequest``, a subclass).
Any request-scoped provider or controller can inject it::

    class AuditService:
        def __init__(self, ctx: RequestContext) -> None:
            self.request_id = ctx.headers.get("x-request-id")

Depending on ``RequestContext`` makes the dependent request-scoped automatically.
"""

from collections.abc import Mapping
from typing import Any

__all__ = ["RequestContext"]


class RequestContext:
    """Metadata of the current call, independent of the transport."""

    __slots__ = ("_headers", "principal", "state", "transport")

    def __init__(
        self,
        transport: str,
        headers: Mapping[str, str] | None = None,
        *,
        principal: Any = None,
    ) -> None:
        self.transport = transport
        self._headers: Mapping[str, str] | None = headers
        self.principal = principal
        """The authenticated identity, set by security middleware (Phase 7)."""
        self.state: dict[str, Any] = {}
        """Free-form per-request storage for middleware and handlers."""

    @property
    def headers(self) -> Mapping[str, str]:
        """Lower-cased header (HTTP) or metadata (gRPC) names to values."""
        if self._headers is None:
            self._headers = self._load_headers()
        return self._headers

    def _load_headers(self) -> Mapping[str, str]:
        return {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(transport={self.transport!r})"
