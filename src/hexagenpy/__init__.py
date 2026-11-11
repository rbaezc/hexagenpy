"""hexagenpy: HexaGen framework for Python.

One contract, many transports: REST, GraphQL, gRPC and Web on Vertical Slices.
"""

from hexagenpy.__about__ import __version__
from hexagenpy.contracts import Controller, Meta, Model, endpoint
from hexagenpy.core import App, Settings, load_settings
from hexagenpy.di import Scope, provide, provide_context, provide_value
from hexagenpy.errors import (
    BusinessRuleViolation,
    Conflict,
    DomainError,
    ErrorKind,
    NotFound,
    PermissionDenied,
    Unauthenticated,
    Unavailable,
    ValidationFailed,
)
from hexagenpy.slices import Module

__all__ = [
    "App",
    "BusinessRuleViolation",
    "Conflict",
    "Controller",
    "DomainError",
    "ErrorKind",
    "Meta",
    "Model",
    "Module",
    "NotFound",
    "PermissionDenied",
    "Scope",
    "Settings",
    "Unauthenticated",
    "Unavailable",
    "ValidationFailed",
    "__version__",
    "endpoint",
    "load_settings",
    "provide",
    "provide_context",
    "provide_value",
]
