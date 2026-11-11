"""``Model``: the base class for contract types (ADR 0004).

A thin layer over :class:`msgspec.Struct`: keyword-only construction, validation on
decode and fast encoding. Constraints are declared with ``Annotated``::

    from typing import Annotated
    from hexagenpy import Meta, Model

    class OrderIn(Model):
        customer: Annotated[str, Meta(min_length=1, description="Customer name")]
        total: Annotated[float, Meta(ge=0)]

Set ``__contract_name__`` to expose the type under a different public name, e.g. to
resolve a clash between two slices that both define ``Item``.
"""

from typing import Any, ClassVar

import msgspec

__all__ = ["Meta", "Model", "decode_json", "encode_json", "to_builtins", "validate"]

Meta = msgspec.Meta


class Model(msgspec.Struct, kw_only=True):
    """Base class for request and response contracts."""

    __contract_name__: ClassVar[str | None] = None


def validate[T](data: Any, type_: type[T], *, strict: bool = True) -> T:
    """Validate already-decoded data (dicts, lists, scalars) against ``type_``.

    ``strict=False`` allows the lossless coercions needed for text sources such as
    query strings and environment variables (``"42"`` -> ``42``).
    """
    return msgspec.convert(data, type_, strict=strict)


def decode_json[T](data: bytes | str, type_: type[T]) -> T:
    """Decode and validate JSON in a single pass."""
    return msgspec.json.decode(data, type=type_)


def encode_json(value: Any) -> bytes:
    return msgspec.json.encode(value)


def to_builtins(value: Any) -> Any:
    """Convert models (and nested values) to plain dicts, lists and scalars."""
    return msgspec.to_builtins(value)
