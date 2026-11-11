"""Compiled HTTP endpoints and their execution (the request hot path)."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from hexagenpy.contracts import ir
from hexagenpy.contracts.endpoint import HttpBinding
from hexagenpy.core.app import App
from hexagenpy.core.context import RequestContext
from hexagenpy.core.error_mapping import ErrorInfo
from hexagenpy.core.invoke import CompiledOperation
from hexagenpy.errors import ErrorKind
from hexagenpy.transports.http.binding import OperationBinder, RequestValidationError
from hexagenpy.transports.http.request import HttpError, HttpRequest
from hexagenpy.transports.http.responses import (
    Message,
    Send,
    encode,
    send_bytes,
    send_problem,
    send_stream,
)

__all__ = ["HttpEndpoint", "RawRoute", "run_endpoint"]

logger = logging.getLogger("hexagenpy.http")


@dataclass(frozen=True, slots=True)
class HttpEndpoint:
    compiled: CompiledOperation
    binding: HttpBinding
    binder: OperationBinder
    is_stream: bool
    is_void: bool

    @property
    def operation(self) -> ir.Operation:
        return self.compiled.operation

    @classmethod
    def build(cls, app: App, op: ir.Operation) -> "HttpEndpoint":
        binding: HttpBinding = op.bindings["http"]
        return cls(
            compiled=app.invoker.compiled(op.id),
            binding=binding,
            binder=OperationBinder(op, binding),
            is_stream=op.kind == "stream",
            is_void=isinstance(op.returns, ir.Void),
        )

    @property
    def status(self) -> int:
        """Declared status; ``None``-returning endpoints default to 204 No Content."""
        if self.is_void and self.binding.status == 200:
            return 204
        return self.binding.status


@dataclass(frozen=True, slots=True)
class RawRoute:
    """A framework-internal route (OpenAPI document, docs UI)."""

    handler: Callable[[HttpRequest, Send], Awaitable[None]]


async def run_endpoint(app: App, endpoint: HttpEndpoint, request: HttpRequest, send: Send) -> None:
    started = False

    async def tracking_send(message: Message) -> None:
        nonlocal started
        started = True
        await send(message)

    try:
        kwargs = await endpoint.binder.bind(request)
        async with app.container.request_scope({RequestContext: request}) as scope:
            result = await app.invoker.call(endpoint.compiled, kwargs, scope)
            if endpoint.is_stream:
                await send_stream(tracking_send, endpoint.status, result)
                return
        if endpoint.is_void:
            await send_bytes(send, endpoint.status, b"", content_type=None)
            return
        body = encode(result)
        await send_bytes(send, endpoint.status, body, head=request.method == "HEAD")
    except RequestValidationError as exc:
        info = ErrorInfo(ErrorKind.VALIDATION, "request_validation_failed", "invalid request")
        await send_problem(send, info, errors=exc.errors)
    except HttpError as exc:
        await send_problem(
            send, ErrorInfo(ErrorKind.VALIDATION, exc.code, exc.detail), status=exc.status
        )
    except Exception as exc:
        if started:  # headers already sent: the only option is to end the stream
            logger.error("error while streaming %s", endpoint.operation.id, exc_info=exc)
            await send({"type": "http.response.body", "body": b""})
            return
        await send_problem(send, app.errors.to_info(exc))
