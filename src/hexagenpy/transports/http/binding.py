"""Per-operation HTTP binding, compiled at startup.

At request time the hot path does exactly two validation passes: one
``msgspec.convert`` for every path/query/header/cookie value (with lossless text
coercion, ``"42"`` -> ``42``) and one ``msgspec.json.decode`` for the body.
"""

import re
from dataclasses import dataclass
from typing import Any

import msgspec

from hexagenpy.contracts import ir
from hexagenpy.contracts.endpoint import HttpBinding
from hexagenpy.errors import ContractError
from hexagenpy.transports.http.params import ParamMarker, ParamSource, marker_of
from hexagenpy.transports.http.request import HttpError, HttpRequest

__all__ = ["FieldError", "OperationBinder", "ParamBinding", "RequestValidationError"]

_PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_MSGSPEC_PATH = re.compile(r" - at `\$\.?([^`]*)`$")
_BODYLESS = frozenset({"GET", "HEAD", "DELETE", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class FieldError:
    location: str
    field: str
    message: str


class RequestValidationError(Exception):
    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__("; ".join(f"{e.location}.{e.field}: {e.message}" for e in errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class ParamBinding:
    name: str
    source: ParamSource
    wire_name: str
    param: ir.Param
    is_list: bool
    description: str | None


def _is_structured(node: ir.TypeRef) -> bool:
    match node:
        case ir.Nullable(inner=inner):
            return _is_structured(inner)
        case ir.Ref() | ir.MapOf() | ir.TupleOf() | ir.AnyValue():
            return True
        case ir.ListOf(item=item) | ir.UnionOf(variants=(item, *_)):
            return _is_structured(item)
        case _:
            return False


def _is_list(node: ir.TypeRef) -> bool:
    return isinstance(node, ir.ListOf) or (
        isinstance(node, ir.Nullable) and isinstance(node.inner, ir.ListOf)
    )


def _source(param: ir.Param, marker: ParamMarker | None, path_names: set[str]) -> ParamSource:
    if marker is not None:
        return marker.source
    if param.name in path_names:
        return ParamSource.PATH
    return ParamSource.BODY if _is_structured(param.type) else ParamSource.QUERY


def _wire_name(param: ir.Param, source: ParamSource, marker: ParamMarker | None) -> str:
    if marker is not None and marker.alias:
        return marker.alias.lower() if source is ParamSource.HEADER else marker.alias
    return param.name.replace("_", "-") if source is ParamSource.HEADER else param.name


class OperationBinder:
    def __init__(self, op: ir.Operation, http: HttpBinding) -> None:
        self.operation = op
        where = f"{op.id} ({http.method} {http.path})"
        path_names = set(_PATH_PARAM.findall(http.path))
        self.params: list[ParamBinding] = []
        self.body: ParamBinding | None = None
        for param in op.params:
            marker = marker_of(param.py_type)
            source = _source(param, marker, path_names)
            binding = ParamBinding(
                name=param.name,
                source=source,
                wire_name=_wire_name(param, source, marker),
                param=param,
                is_list=_is_list(param.type),
                description=marker.description if marker else None,
            )
            if source is ParamSource.BODY:
                if self.body is not None:
                    raise ContractError(f"{where}: only one body parameter is allowed")
                if http.method in _BODYLESS:
                    raise ContractError(f"{where}: {http.method} endpoints cannot take a body")
                self.body = binding
            else:
                if source is ParamSource.PATH and binding.wire_name not in path_names:
                    raise ContractError(f"{where}: no {{{binding.wire_name}}} in the path")
                self.params.append(binding)
        self._params_type: type[Any] = self._build_params_type(op.name)
        self._body_decoder = (
            msgspec.json.Decoder(self.body.param.py_type) if self.body is not None else None
        )

    def _build_params_type(self, name: str) -> type:
        fields: list[tuple[str, Any] | tuple[str, Any, Any]] = [
            (b.name, b.param.py_type)
            if b.param.required
            else (b.name, b.param.py_type, b.param.default)
            for b in self.params
        ]
        return msgspec.defstruct(f"{name}HttpParams", fields, kw_only=True)

    async def bind(self, request: HttpRequest) -> dict[str, Any]:
        """Validate the request into handler keyword arguments."""
        raw: dict[str, Any] = {}
        for b in self.params:
            value = self._raw_value(request, b)
            if value is not None:
                raw[b.name] = value
        try:
            params: Any = msgspec.convert(raw, self._params_type, strict=False)
        except msgspec.ValidationError as exc:
            raise RequestValidationError([self._param_error(str(exc))]) from None
        kwargs = {b.name: getattr(params, b.name) for b in self.params}
        if self.body is not None:
            kwargs[self.body.name] = await self._decode_body(request, self.body)
        return kwargs

    @staticmethod
    def _raw_value(request: HttpRequest, b: ParamBinding) -> Any:
        match b.source:
            case ParamSource.PATH:
                return request.path_params.get(b.wire_name)
            case ParamSource.QUERY:
                values = request.query.get(b.wire_name)
                if values is None:
                    return None
                return values if b.is_list else values[-1]
            case ParamSource.HEADER:
                return request.headers.get(b.wire_name)
            case _:
                return request.cookies.get(b.wire_name)

    def _param_error(self, message: str) -> FieldError:
        match = _MSGSPEC_PATH.search(message)
        field_path = match[1] if match else ""
        text = _MSGSPEC_PATH.sub("", message)
        missing = re.search(r"missing required field `([^`]+)`", text)
        name = (missing[1] if missing else field_path).split(".", 1)[0].split("[", 1)[0]
        for b in self.params:
            if b.name == name:
                rest = field_path[len(name) :] if not missing else ""
                return FieldError(b.source.value, b.wire_name + rest, text)
        return FieldError("request", field_path, text)  # pragma: no cover - defensive

    async def _decode_body(self, request: HttpRequest, b: ParamBinding) -> Any:
        data = await request.body()
        if not data:
            if b.param.required:
                raise RequestValidationError([FieldError("body", "", "request body is required")])
            return b.param.default
        content_type = request.content_type
        if (
            content_type
            and content_type != "application/json"
            and not content_type.endswith("+json")
        ):
            raise HttpError(
                415,
                f"unsupported media type {content_type!r}; send JSON",
                code="unsupported_media_type",
            )
        assert self._body_decoder is not None
        try:
            return self._body_decoder.decode(data)
        except msgspec.ValidationError as exc:
            match = _MSGSPEC_PATH.search(str(exc))
            text = _MSGSPEC_PATH.sub("", str(exc))
            raise RequestValidationError(
                [FieldError("body", match[1] if match else "", text)]
            ) from None
        except msgspec.DecodeError as exc:
            raise RequestValidationError(
                [FieldError("body", "", f"malformed JSON: {exc}")]
            ) from None
