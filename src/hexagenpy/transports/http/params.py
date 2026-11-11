"""Explicit parameter sources for HTTP, declared with ``Annotated``.

Most parameters need no marker: names in the path template come from the path,
structured types (Models, lists of Models, dicts) from the JSON body, and everything
else from the query string. Markers override that, or rename the wire name::

    @endpoint(http="GET /items")
    async def list_items(
        self,
        request_id: Annotated[str | None, Header("x-request-id")] = None,
        session: Annotated[str | None, Cookie()] = None,
        page_size: Annotated[int, Query("page-size"), Meta(le=100)] = 20,
    ) -> list[Item]: ...

Other transports ignore these markers (msgspec ignores unknown ``Annotated`` metadata).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, get_args, get_origin

__all__ = ["Body", "Cookie", "Header", "ParamMarker", "ParamSource", "Path", "Query", "marker_of"]


class ParamSource(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    BODY = "body"


@dataclass(frozen=True, slots=True)
class ParamMarker:
    source: ParamSource
    alias: str | None = None
    description: str | None = None


def Path(alias: str | None = None, *, description: str | None = None) -> ParamMarker:  # noqa: N802
    return ParamMarker(ParamSource.PATH, alias, description)


def Query(alias: str | None = None, *, description: str | None = None) -> ParamMarker:  # noqa: N802
    return ParamMarker(ParamSource.QUERY, alias, description)


def Header(alias: str | None = None, *, description: str | None = None) -> ParamMarker:  # noqa: N802
    """Header parameter; the default wire name is the parameter name with ``_`` -> ``-``."""
    return ParamMarker(ParamSource.HEADER, alias, description)


def Cookie(alias: str | None = None, *, description: str | None = None) -> ParamMarker:  # noqa: N802
    return ParamMarker(ParamSource.COOKIE, alias, description)


def Body(*, description: str | None = None) -> ParamMarker:  # noqa: N802
    return ParamMarker(ParamSource.BODY, None, description)


def marker_of(annotation: Any) -> ParamMarker | None:
    """Return the first ``ParamMarker`` in an ``Annotated`` type, if any."""
    if get_origin(annotation) is not Annotated:
        return None
    for meta in get_args(annotation)[1:]:
        if isinstance(meta, ParamMarker):
            return meta
    return None
