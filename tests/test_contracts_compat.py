from collections.abc import AsyncIterator
from typing import Any

import pytest

from hexagenpy import Controller, Model, endpoint
from hexagenpy.contracts import ContractRegistry, check_operation, check_registry
from hexagenpy.contracts.endpoint import GraphQLKind


class A(Model, tag=True):  # unions of Models must be tagged (unambiguous decoding)
    x: int


class B(Model, tag=True):
    y: str


class Holder(Model):
    first: dict[str, int]
    again: "list[Holder]" = []


def issues_for(
    returns: Any, *, param: Any = int, graphql: GraphQLKind | None = "query", grpc: bool = True
) -> list[str]:
    annotations = {"value": param, "return": returns}

    async def handler(self: Any, value: Any) -> Any:  # annotations set below
        return None

    handler.__annotations__ = annotations
    controller = type(
        "Probe", (Controller,), {"handler": endpoint(graphql=graphql, grpc=grpc)(handler)}
    )
    registry = ContractRegistry()
    registry.add_controller(controller, "probe")
    return [f"{i.transport}:{i.location}:{i.message}" for i in check_registry(registry)]


def test_http_only_accepts_everything() -> None:
    assert issues_for(dict[str, Any] | tuple[int, str], graphql=None, grpc=False) == []


def test_compatible_types_pass_everywhere() -> None:
    class Rich(Model):
        tags: list[str]
        a_or_b: A | B
        maybe: A | None = None
        counts: list[int] = []

    assert issues_for(Rich) == []  # as output, unions of Models are fine on every transport


@pytest.mark.parametrize(
    ("returns", "expected"),
    [
        (Any, "graphql:return:Any has no GraphQL type"),
        (dict[str, int], "graphql:return:GraphQL has no map type"),
        (tuple[int, str], "graphql:return:GraphQL has no tuple type"),
        (int | str, "graphql:return:GraphQL union members must be Models"),
    ],
)
def test_graphql_rules(returns: Any, expected: str) -> None:
    found = issues_for(returns, grpc=False)
    assert any(issue.startswith(expected) for issue in found), found


def test_graphql_input_unions_are_rejected() -> None:
    found = issues_for(int, param=A | B, grpc=False)
    assert found == ["graphql:param 'value':GraphQL input types cannot be unions"]


@pytest.mark.parametrize(
    ("returns", "expected"),
    [
        (Any, "grpc:return:Any has no proto3 type"),
        (tuple[int, str], "grpc:return:proto3 has no tuple type"),
        (list[int] | None, "grpc:return:repeated/map fields cannot be null"),
        (list[list[int]], "grpc:return[]:nested repeated or nullable items"),
        (list[int | None], "grpc:return[]:nested repeated or nullable items"),
        (dict[str, list[int]], "grpc:return{value}:nested repeated"),
        (dict[float, int], "grpc:return:proto3 map keys must be str, int or bool"),
        (A | list[int], "grpc:return:oneof members cannot be lists or maps"),
    ],
)
def test_grpc_rules(returns: Any, expected: str) -> None:
    found = issues_for(returns, graphql=None)
    assert any(issue.startswith(expected) for issue in found), found


def test_grpc_accepts_maps_unions_and_recursion() -> None:
    assert issues_for(dict[str, A], graphql=None) == []
    assert issues_for(A | B, graphql=None) == []
    assert issues_for(dict[int, str] | None, graphql=None) != []  # nullable map


def test_nested_issues_report_field_path_once_per_type() -> None:
    found = issues_for(list[Holder], grpc=False)
    assert found == ["graphql:Holder.first:GraphQL has no map type; use a list of key/value Models"]


def test_graphql_subscription_kind_rules() -> None:
    class Feed(Controller):
        @endpoint(graphql="subscription")
        async def not_a_stream(self) -> int:
            return 1

        @endpoint(graphql="query")
        async def stream_as_query(self) -> AsyncIterator[int]:
            yield 1

        @endpoint(graphql="subscription", grpc=True)
        async def ok(self) -> AsyncIterator[A]:
            yield A(x=1)

    registry = ContractRegistry()
    registry.add_controller(Feed, "feed")
    messages = {i.operation: i.message for i in check_registry(registry)}
    assert messages == {
        "feed.not_a_stream": "subscriptions must return AsyncIterator",
        "feed.stream_as_query": "streams require graphql='subscription'",
    }
    assert check_operation(registry, registry.operation("feed.ok")) == []
    issue = check_registry(registry)[0]
    assert str(issue).startswith("[graphql] feed.not_a_stream -> return: ")
