"""Builds the OpenAPI 3.1 document of an HTTP app from its compiled endpoints."""

from collections.abc import Sequence
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from hexagenpy.core.app import App
from hexagenpy.transports.http.openapi.schema import SchemaBuilder
from hexagenpy.transports.http.params import ParamSource

if TYPE_CHECKING:
    from hexagenpy.transports.http.endpoint import HttpEndpoint

__all__ = ["PROBLEM_SCHEMA", "build_openapi"]

PROBLEM_SCHEMA: dict[str, Any] = {
    "title": "Problem",
    "description": "RFC 9457 problem details.",
    "type": "object",
    "properties": {
        "type": {"type": "string", "default": "about:blank"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "code": {"type": "string", "description": "Stable, machine-readable error code."},
        "detail": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "field": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["location", "field", "message"],
            },
        },
        "details": {"type": "object"},
    },
    "required": ["title", "status", "code"],
}

_PROBLEM_REF = {"$ref": "#/components/schemas/Problem"}


def _problem_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": _PROBLEM_REF}},
    }


def _operation(endpoint: "HttpEndpoint", schemas: SchemaBuilder) -> dict[str, Any]:
    op = endpoint.operation
    spec: dict[str, Any] = {"operationId": op.id, "tags": list(op.tags)}
    if op.summary:
        spec["summary"] = op.summary
    if op.description:
        spec["description"] = op.description
    if op.deprecated:
        spec["deprecated"] = True

    parameters: list[dict[str, Any]] = []
    for b in endpoint.binder.params:
        param: dict[str, Any] = {
            "name": b.wire_name,
            "in": b.source.value,
            "required": b.source is ParamSource.PATH or b.param.required,
            "schema": schemas.schema(b.param.type),
        }
        if b.description:
            param["description"] = b.description
        if b.is_list and b.source is ParamSource.QUERY:
            param["style"], param["explode"] = "form", True
        parameters.append(param)
    if parameters:
        spec["parameters"] = parameters

    body = endpoint.binder.body
    if body is not None:
        request_body: dict[str, Any] = {
            "required": body.param.required,
            "content": {"application/json": {"schema": schemas.schema(body.param.type)}},
        }
        if body.description:
            request_body["description"] = body.description
        spec["requestBody"] = request_body

    status = str(endpoint.status)
    success: dict[str, Any] = {"description": HTTPStatus(endpoint.status).phrase}
    if not endpoint.is_void:
        media = "application/x-ndjson" if endpoint.is_stream else "application/json"
        success["content"] = {media: {"schema": schemas.schema(op.returns)}}
    responses: dict[str, Any] = {status: success}
    if parameters or body is not None:
        responses["422"] = _problem_response("Validation error")
    responses["default"] = _problem_response("Error")
    spec["responses"] = responses
    return spec


def build_openapi(
    app: App,
    endpoints: Sequence["HttpEndpoint"],
    title: str,
    description: str | None = None,
) -> dict[str, Any]:
    schemas = SchemaBuilder(app.contracts)
    paths: dict[str, dict[str, Any]] = {}
    for endpoint in sorted(endpoints, key=lambda e: (e.binding.path, e.binding.method)):
        item = paths.setdefault(endpoint.binding.path, {})
        item[endpoint.binding.method.lower()] = _operation(endpoint, schemas)

    tags = sorted({tag for e in endpoints for tag in e.operation.tags})
    info: dict[str, Any] = {"title": title, "version": app.version}
    if description:
        info["description"] = description
    return {
        "openapi": "3.1.0",
        "info": info,
        "tags": [{"name": tag} for tag in tags],
        "paths": paths,
        "components": {
            "schemas": {**dict(sorted(schemas.components.items())), "Problem": PROBLEM_SCHEMA}
        },
    }
