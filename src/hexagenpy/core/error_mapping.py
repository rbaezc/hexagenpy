"""Maps any exception raised by a handler to a transport-neutral :class:`ErrorInfo`."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import msgspec

from hexagenpy.errors import DomainError, ErrorKind

__all__ = ["ErrorInfo", "ErrorMapper"]

logger = logging.getLogger("hexagenpy.errors")


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    kind: ErrorKind
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict[str, Any])


class ErrorMapper:
    """Translate exceptions without leaking internals.

    Order: :class:`DomainError` (carries its own kind) → ``msgspec.ValidationError`` →
    user ``error_map`` entries (matched along the MRO) → ``INTERNAL``, logged with
    traceback and returned with a generic message.
    """

    def __init__(self, error_map: Mapping[type[BaseException], ErrorKind] | None = None) -> None:
        self._map = dict(error_map or {})

    def to_info(self, exc: BaseException) -> ErrorInfo:
        if isinstance(exc, DomainError):
            return ErrorInfo(exc.kind, exc.code, exc.message, exc.details)
        if isinstance(exc, msgspec.ValidationError):
            return ErrorInfo(ErrorKind.VALIDATION, "validation_failed", str(exc))
        for klass in type(exc).__mro__:
            kind = self._map.get(klass)
            if kind is not None:
                return ErrorInfo(kind, kind.value, str(exc) or kind.value)
        logger.error("unhandled exception", exc_info=exc)
        return ErrorInfo(ErrorKind.INTERNAL, "internal_error", "internal server error")
