"""Segment-trie router, built once at startup.

* Static paths are resolved with one dict lookup.
* Dynamic paths walk a trie of segments; static segments win over ``{param}``
  segments, with backtracking (``/users/me`` beats ``/users/{id}``).
* A path that exists with other methods yields 405 and the ``Allow`` list.
* ``HEAD`` falls back to ``GET``. Trailing slashes are ignored (``/a/`` == ``/a``).
"""

import re
from dataclasses import dataclass

from hexagenpy.errors import ContractError

__all__ = ["Match", "Router"]

_PARAM = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class _Node[T]:
    __slots__ = ("methods", "param", "param_name", "static", "template")

    def __init__(self) -> None:
        self.static: dict[str, _Node[T]] = {}
        self.param: _Node[T] | None = None
        self.param_name: str | None = None
        self.methods: dict[str, T] = {}
        self.template: str | None = None


@dataclass(frozen=True, slots=True)
class Match[T]:
    """Result of a lookup: ``target`` is None when the path or method did not match."""

    target: T | None
    params: dict[str, str]
    allowed: tuple[str, ...] = ()

    @property
    def path_found(self) -> bool:
        return self.target is not None or bool(self.allowed)


def _split(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


class Router[T]:
    def __init__(self) -> None:
        self._root: _Node[T] = _Node()
        self._static: dict[str, dict[str, T]] = {}

    def add(self, method: str, template: str, target: T) -> None:
        node = self._root
        names: list[str] = []
        for segment in _split(template):
            match = _PARAM.match(segment)
            if match is None:
                if "{" in segment or "}" in segment:
                    raise ContractError(f"invalid path segment {segment!r} in {template!r}")
                node = node.static.setdefault(segment, _Node())
                continue
            name = match[1]
            if name in names:
                raise ContractError(f"duplicate path parameter {{{name}}} in {template!r}")
            names.append(name)
            if node.param is None:
                node.param, node.param_name = _Node(), name
            elif node.param_name != name:
                raise ContractError(
                    f"{template!r}: parameter {{{name}}} conflicts with {{{node.param_name}}} "
                    "at the same position in another route"
                )
            node = node.param
        if method in node.methods:
            raise ContractError(f"route {method} {template} is declared twice")
        node.methods[method] = target
        node.template = template
        if not names:
            self._static.setdefault(_normalize(template), {})[method] = target

    def match(self, method: str, path: str) -> Match[T]:
        methods = self._static.get(_normalize(path))
        params: dict[str, str] = {}
        if methods is None:
            node = self._walk(self._root, _split(path), 0, params)
            if node is None:
                return Match(None, {})
            methods = node.methods
        target = methods.get(method)
        if target is None and method == "HEAD":
            target = methods.get("GET")
        if target is None:
            allowed: set[str] = set(methods)
            if "GET" in methods:
                allowed.add("HEAD")
            return Match(None, {}, tuple(sorted(allowed)))
        return Match(target, params)

    def _walk(
        self, node: _Node[T], segments: list[str], index: int, params: dict[str, str]
    ) -> _Node[T] | None:
        if index == len(segments):
            return node if node.methods else None
        segment = segments[index]
        child = node.static.get(segment)
        if child is not None:
            found = self._walk(child, segments, index + 1, params)
            if found is not None:
                return found
        if node.param is not None and node.param_name is not None:
            params[node.param_name] = segment
            found = self._walk(node.param, segments, index + 1, params)
            if found is not None:
                return found
            del params[node.param_name]
        return None

    def routes(self) -> list[tuple[str, str, T]]:
        """Every (method, template, target), for introspection and docs."""
        found: list[tuple[str, str, T]] = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            found.extend((m, node.template or "/", t) for m, t in node.methods.items())
            stack.extend(node.static.values())
            if node.param is not None:
                stack.append(node.param)
        return sorted(found, key=lambda r: (r[1], r[0]))


def _normalize(path: str) -> str:
    return "/" + "/".join(_split(path))
