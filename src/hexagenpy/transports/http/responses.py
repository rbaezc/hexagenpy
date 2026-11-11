"""Low-level ASGI response helpers and RFC 9457 Problem Details."""

from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping, Sequence
from http import HTTPStatus
from typing import Any

import msgspec

from hexagenpy.core.error_mapping import ErrorInfo
from hexagenpy.errors import ErrorKind
from hexagenpy.transports.http.binding import FieldError

__all__ = ["STATUS_BY_KIND", "problem_body", "send_bytes", "send_problem", "send_stream"]

Message = MutableMapping[str, Any]
Send = Callable[[Message], Awaitable[None]]
Headers = Sequence[tuple[bytes, bytes]]

STATUS_BY_KIND: dict[ErrorKind, int] = {
    ErrorKind.VALIDATION: 422,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.CONFLICT: 409,
    ErrorKind.UNAUTHENTICATED: 401,
    ErrorKind.PERMISSION_DENIED: 403,
    ErrorKind.BUSINESS_RULE: 422,
    ErrorKind.UNAVAILABLE: 503,
    ErrorKind.INTERNAL: 500,
}

JSON = b"application/json"
PROBLEM_JSON = b"application/problem+json"
NDJSON = b"application/x-ndjson"
_encoder = msgspec.json.Encoder()


class Problem(msgspec.Struct, omit_defaults=True):
    """RFC 9457 body. ``code`` (stable, machine-readable) and ``errors`` are extensions."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: list[dict[str, str]] | None = None
    details: dict[str, Any] | None = None


def problem_body(
    status: int,
    code: str,
    detail: str | None,
    *,
    errors: Sequence[FieldError] = (),
    details: dict[str, Any] | None = None,
) -> bytes:
    problem = Problem(
        type="about:blank",
        title=HTTPStatus(status).phrase,
        status=status,
        code=code,
        detail=detail,
        errors=[{"location": e.location, "field": e.field, "message": e.message} for e in errors]
        or None,
        details=details or None,
    )
    return _encoder.encode(problem)


async def send_bytes(
    send: Send,
    status: int,
    body: bytes,
    *,
    content_type: bytes | None = JSON,
    headers: Headers = (),
    head: bool = False,
) -> None:
    raw: list[tuple[bytes, bytes]] = [(b"content-length", str(len(body)).encode())]
    if content_type is not None and body:
        raw.append((b"content-type", content_type))
    raw.extend(headers)
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": b"" if head else body})


async def send_problem(
    send: Send,
    info: ErrorInfo,
    *,
    errors: Sequence[FieldError] = (),
    status: int | None = None,
    headers: Headers = (),
) -> None:
    code = status or STATUS_BY_KIND[info.kind]
    body = problem_body(code, info.code, info.message, errors=errors, details=dict(info.details))
    await send_bytes(send, code, body, content_type=PROBLEM_JSON, headers=headers)


async def send_stream(send: Send, status: int, items: AsyncIterator[Any]) -> None:
    """Stream items as NDJSON (one JSON document per line), chunked."""
    await send(
        {"type": "http.response.start", "status": status, "headers": [(b"content-type", NDJSON)]}
    )
    async for item in items:
        await send(
            {"type": "http.response.body", "body": _encoder.encode(item) + b"\n", "more_body": True}
        )
    await send({"type": "http.response.body", "body": b""})


def encode(value: Any) -> bytes:
    return _encoder.encode(value)
