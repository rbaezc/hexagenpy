"""Builds IR :class:`~hexagenpy.contracts.ir.Operation` objects from controller methods."""

import dataclasses
import inspect
import re
from typing import Any, get_type_hints

import msgspec

from hexagenpy.contracts import ir
from hexagenpy.contracts.compiler import TypeCompiler
from hexagenpy.contracts.endpoint import Controller, EndpointSpec, HttpBinding
from hexagenpy.errors import ContractError

__all__ = ["build_operations"]

_PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ALLOWED_KINDS = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


def _pascal(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def build_operations(
    controller: type[Controller], slice_name: str, compiler: TypeCompiler
) -> list[ir.Operation]:
    meta = controller.__hexagen_controller__
    if not meta.endpoints:
        raise ContractError(f"{controller.__qualname__} declares no @endpoint methods")
    return [
        _build(controller, slice_name, attr, spec, compiler)
        for attr, spec in meta.endpoints.items()
    ]


def _build(
    controller: type[Controller],
    slice_name: str,
    attr: str,
    spec: EndpointSpec,
    compiler: TypeCompiler,
) -> ir.Operation:
    where = f"{controller.__qualname__}.{attr}"
    raw = inspect.getattr_static(controller, attr)
    if not inspect.isfunction(raw):
        raise ContractError(f"{where}: endpoints must be regular methods (not static/class)")
    fn = getattr(controller, attr)
    try:
        hints = get_type_hints(fn, include_extras=True)
    except (NameError, TypeError) as exc:
        raise ContractError(f"{where}: cannot resolve annotations: {exc}") from exc
    if "return" not in hints:
        raise ContractError(f"{where}: missing return annotation")

    params = _params(where, fn, hints, compiler)
    returns = _returns(where, fn, hints["return"], compiler)
    name = spec.name or attr
    meta = controller.__hexagen_controller__
    bindings = spec.bindings()
    if spec.http is not None:
        bindings["http"] = _http(where, spec.http, meta.prefix, params)

    return ir.Operation(
        id=f"{slice_name}.{name}",
        name=name,
        slice=slice_name,
        controller=controller,
        handler=attr,
        params=params,
        returns=returns,
        args_type=_args_type(name, params),
        is_async=inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn),
        kind="stream" if isinstance(returns, ir.Stream) else "unary",
        summary=spec.summary,
        description=spec.description or inspect.getdoc(fn),
        tags=spec.tags or meta.tags or (slice_name,),
        deprecated=spec.deprecated,
        bindings=bindings,
    )


def _params(
    where: str, fn: Any, hints: dict[str, Any], compiler: TypeCompiler
) -> tuple[ir.Param, ...]:
    result: list[ir.Param] = []
    for p in list(inspect.signature(fn).parameters.values())[1:]:  # skip self
        if p.kind not in _ALLOWED_KINDS:
            raise ContractError(f"{where}: *args/**kwargs and positional-only are not allowed")
        if p.name not in hints:
            raise ContractError(f"{where}: parameter {p.name!r} needs a type annotation")
        type_ref = compiler.compile(hints[p.name])
        if isinstance(type_ref, ir.Stream | ir.Void):
            raise ContractError(f"{where}: parameter {p.name!r} cannot be a stream or None")
        has_default = p.default is not inspect.Parameter.empty
        result.append(
            ir.Param(
                name=p.name,
                type=type_ref,
                py_type=hints[p.name],
                required=not has_default,
                default=p.default if has_default else ir.MISSING,
            )
        )
    return tuple(result)


def _returns(where: str, fn: Any, annotation: Any, compiler: TypeCompiler) -> ir.TypeRef:
    returns = compiler.compile(annotation)
    is_stream = isinstance(returns, ir.Stream)
    if inspect.isasyncgenfunction(fn) and not is_stream:
        raise ContractError(f"{where}: async generators must be annotated AsyncIterator[T]")
    if is_stream and not inspect.isasyncgenfunction(fn) and not inspect.iscoroutinefunction(fn):
        raise ContractError(f"{where}: streaming endpoints must be async")
    return returns


def _http(where: str, http: HttpBinding, prefix: str, params: tuple[ir.Param, ...]) -> HttpBinding:
    full = dataclasses.replace(http, path=http.full_path(prefix))
    names = {p.name for p in params}
    for path_param in _PATH_PARAM.findall(full.path):
        if path_param not in names:
            raise ContractError(f"{where}: path parameter {{{path_param}}} has no argument")
    return full


def _args_type(name: str, params: tuple[ir.Param, ...]) -> type:
    fields: list[tuple[str, Any] | tuple[str, Any, Any]] = [
        (p.name, p.py_type) if p.required else (p.name, p.py_type, p.default) for p in params
    ]
    return msgspec.defstruct(f"{_pascal(name)}Args", fields, kw_only=True)
