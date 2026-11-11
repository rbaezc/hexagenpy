"""Error types shared by every layer of hexagenpy.

Two families:

* **Framework errors** (:class:`HexagenError`): raised at startup or by misuse of the
  framework (bad contracts, missing providers, invalid configuration).
* **Domain errors** (:class:`DomainError`): raised by application code. They are
  transport-neutral; each transport maps their :class:`ErrorKind` to its own
  representation (HTTP status, GraphQL ``extensions.code``, gRPC status code).

Domain layers that must not import hexagenpy can raise their own exceptions and map
them with ``App(error_map={MyError: ErrorKind.CONFLICT})``.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, ClassVar

__all__ = [
    "BusinessRuleViolation",
    "ConfigurationError",
    "Conflict",
    "ContractError",
    "DomainError",
    "ErrorKind",
    "HexagenError",
    "NotFound",
    "PermissionDenied",
    "ResolutionError",
    "Unauthenticated",
    "Unavailable",
    "ValidationFailed",
]


class ErrorKind(StrEnum):
    """Transport-neutral error categories."""

    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    BUSINESS_RULE = "business_rule"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"


# ------------------------------------------------------------------ framework errors


class HexagenError(Exception):
    """Base class for errors caused by framework configuration or misuse."""


class ContractError(HexagenError):
    """A contract (type, endpoint or controller) cannot be compiled or exposed."""


class ResolutionError(HexagenError):
    """The dependency container cannot be built or a dependency cannot be resolved."""


class ConfigurationError(HexagenError):
    """Settings are missing or invalid."""


# ------------------------------------------------------------------ domain errors


class DomainError(Exception):
    """Base class for expected, client-facing errors raised by application code."""

    kind: ClassVar[ErrorKind] = ErrorKind.BUSINESS_RULE
    default_code: ClassVar[str] = "business_rule_violation"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details: Mapping[str, Any] = details or {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r}, code={self.code!r})"


class ValidationFailed(DomainError):
    kind = ErrorKind.VALIDATION
    default_code = "validation_failed"


class NotFound(DomainError):
    kind = ErrorKind.NOT_FOUND
    default_code = "not_found"


class Conflict(DomainError):
    kind = ErrorKind.CONFLICT
    default_code = "conflict"


class Unauthenticated(DomainError):
    kind = ErrorKind.UNAUTHENTICATED
    default_code = "unauthenticated"


class PermissionDenied(DomainError):
    kind = ErrorKind.PERMISSION_DENIED
    default_code = "permission_denied"


class BusinessRuleViolation(DomainError):
    kind = ErrorKind.BUSINESS_RULE
    default_code = "business_rule_violation"


class Unavailable(DomainError):
    kind = ErrorKind.UNAVAILABLE
    default_code = "unavailable"
