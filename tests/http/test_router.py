import pytest

from hexagenpy.errors import ContractError
from hexagenpy.transports.http.router import Router


def build() -> Router[str]:
    router: Router[str] = Router()
    router.add("GET", "/", "root")
    router.add("GET", "/users", "list")
    router.add("POST", "/users", "create")
    router.add("GET", "/users/me", "me")
    router.add("GET", "/users/{id}", "get")
    router.add("DELETE", "/users/{id}", "delete")
    router.add("GET", "/users/{id}/posts/{post_id}", "post")
    router.add("GET", "/files/{name}/raw", "raw")
    router.add("GET", "/files/static/meta", "meta")
    return router


@pytest.mark.parametrize(
    ("method", "path", "target", "params"),
    [
        ("GET", "/", "root", {}),
        ("GET", "/users", "list", {}),
        ("GET", "/users/", "list", {}),
        ("POST", "/users", "create", {}),
        ("GET", "/users/me", "me", {}),
        ("GET", "/users/42", "get", {"id": "42"}),
        ("DELETE", "/users/42", "delete", {"id": "42"}),
        ("GET", "/users/7/posts/9", "post", {"id": "7", "post_id": "9"}),
        ("HEAD", "/users/7", "get", {"id": "7"}),
        ("GET", "/files/static/raw", "raw", {"name": "static"}),  # backtracking
        ("GET", "/files/static/meta", "meta", {}),
    ],
)
def test_matches(method: str, path: str, target: str, params: dict[str, str]) -> None:
    match = build().match(method, path)
    assert (match.target, match.params) == (target, params)
    assert match.path_found


def test_not_found_and_method_not_allowed() -> None:
    router = build()
    missing = router.match("GET", "/nope/x")
    assert (missing.target, missing.allowed, missing.path_found) == (None, (), False)
    assert router.match("GET", "/users/1/posts").target is None
    assert router.match("GET", "/files/x/other").target is None
    not_allowed = router.match("PUT", "/users/42")
    assert not_allowed.target is None
    assert not_allowed.allowed == ("DELETE", "GET", "HEAD")
    assert not_allowed.path_found
    assert router.match("PATCH", "/users").allowed == ("GET", "HEAD", "POST")


def test_route_conflicts() -> None:
    router: Router[str] = Router()
    router.add("GET", "/a/{id}", "x")
    with pytest.raises(ContractError, match="declared twice"):
        router.add("GET", "/a/{id}", "y")
    with pytest.raises(ContractError, match=r"\{key\} conflicts with \{id\}"):
        router.add("POST", "/a/{key}", "z")
    with pytest.raises(ContractError, match="duplicate path parameter"):
        router.add("GET", "/b/{x}/{x}", "z")
    with pytest.raises(ContractError, match="invalid path segment"):
        router.add("GET", "/c/pre{x}", "z")


def test_routes_listing() -> None:
    routes = [(m, p) for m, p, _ in build().routes()]
    assert ("GET", "/users/{id}") in routes
    assert routes == sorted(routes, key=lambda r: (r[1], r[0]))
