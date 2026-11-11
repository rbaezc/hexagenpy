"""Static analysis of the provider graph, done once when the container is built.

Fails fast, before serving any request, on: duplicate keys, missing dependencies,
cycles, singletons that capture request-scoped values, and cross-slice access to
dependencies a slice did not export.
"""

from collections.abc import Iterable, Mapping
from dataclasses import replace

from hexagenpy.di.providers import Plan, Provider, Scope, compile_plan, key_name
from hexagenpy.errors import ResolutionError

__all__ = ["build_plans"]


def build_plans(
    providers: Iterable[Provider], exports: Mapping[str, frozenset[object]]
) -> dict[object, Plan]:
    plans: dict[object, Plan] = {}
    for provider in providers:
        if provider.key in plans:
            raise ResolutionError(f"{key_name(provider.key)} is registered twice")
        plans[provider.key] = compile_plan(provider)
    errors = _missing_and_visibility(plans, exports)
    if errors:
        raise ResolutionError("invalid dependency graph:\n  - " + "\n  - ".join(errors))
    order = _topological_order(plans)
    return _settle_scopes(plans, order)


def _missing_and_visibility(
    plans: Mapping[object, Plan], exports: Mapping[str, frozenset[object]]
) -> list[str]:
    errors: list[str] = []
    for plan in plans.values():
        owner = plan.provider.owner
        for dep in plan.deps:
            target = plans.get(dep.key)
            if target is None:
                if not dep.optional:
                    errors.append(
                        f"{key_name(plan.key)} needs {key_name(dep.key)} "
                        f"(parameter {dep.param!r}), which is not registered"
                    )
                continue
            dep_owner = target.provider.owner
            if dep_owner is None or dep_owner == owner:
                continue
            if dep.key not in exports.get(dep_owner, frozenset()):
                errors.append(
                    f"{key_name(plan.key)} (slice {owner or 'app'!r}) depends on "
                    f"{key_name(dep.key)}, which is private to slice {dep_owner!r}; "
                    f"add it to that Module's exports"
                )
    return errors


def _topological_order(plans: Mapping[object, Plan]) -> list[object]:
    """Dependencies first. Raises on cycles, reporting the full path."""
    order: list[object] = []
    state: dict[object, int] = {}  # 1 = visiting, 2 = done

    def visit(key: object, path: list[object]) -> None:
        mark = state.get(key)
        if mark == 2:
            return
        if mark == 1:
            cycle = [*path[path.index(key) :], key]
            raise ResolutionError("dependency cycle: " + " -> ".join(map(key_name, cycle)))
        state[key] = 1
        for dep in plans[key].deps:
            if dep.key in plans:
                visit(dep.key, [*path, key])
        state[key] = 2
        order.append(key)

    for key in plans:
        visit(key, [])
    return order


def _settle_scopes(plans: dict[object, Plan], order: list[object]) -> dict[object, Plan]:
    """Resolve auto scopes and reject singletons that would capture request values."""
    needs_request: dict[object, bool] = {}
    for key in order:  # dependencies are settled before their dependents
        plan = plans[key]
        request_deps = [d.key for d in plan.deps if needs_request.get(d.key, False)]
        if plan.provider.scope is None:
            scope = Scope.REQUEST if request_deps else Scope.SINGLETON
            plan = plans[key] = replace(plan, scope=scope)
        if plan.scope is Scope.SINGLETON and request_deps:
            raise ResolutionError(
                f"singleton {key_name(key)} depends on request-scoped "
                f"{key_name(request_deps[0])}; make it Scope.REQUEST or inject a factory"
            )
        needs_request[key] = plan.scope is Scope.REQUEST or bool(request_deps)
    return {key: plans[key] for key in order}
