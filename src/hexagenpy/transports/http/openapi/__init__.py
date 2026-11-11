"""OpenAPI 3.1 generation from the Contract IR, and the interactive docs page."""

import html

from hexagenpy.transports.http.openapi.document import PROBLEM_SCHEMA, build_openapi
from hexagenpy.transports.http.openapi.schema import SchemaBuilder

__all__ = ["PROBLEM_SCHEMA", "SchemaBuilder", "build_openapi", "docs_html"]

_SCALAR_CDN = "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1"


def docs_html(title: str, openapi_url: str) -> str:
    """Interactive API reference (Scalar), loaded from a CDN."""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)} - API reference</title>
  </head>
  <body>
    <script id="api-reference" data-url="{html.escape(openapi_url, quote=True)}"></script>
    <script src="{_SCALAR_CDN}"></script>
  </body>
</html>
"""
