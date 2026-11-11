from pathlib import Path

import pytest

from hexagenpy import (
    BusinessRuleViolation,
    Conflict,
    Controller,
    DomainError,
    ErrorKind,
    Module,
    NotFound,
    PermissionDenied,
    Settings,
    Unauthenticated,
    Unavailable,
    ValidationFailed,
    endpoint,
    load_settings,
    provide,
)
from hexagenpy.core import ErrorMapper
from hexagenpy.core.config import read_env_file
from hexagenpy.errors import ConfigurationError, ContractError

# ------------------------------------------------------------------ settings


class AppSettings(Settings):
    database_url: str
    debug: bool = False
    workers: int = 1
    hosts: list[str] = []


def test_env_file_parsing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n\nexport A=1\nB='quoted # not a comment'\nC=\"x\"\nD=value # trailing\nE=\n",
        encoding="utf-8",
    )
    assert read_env_file(env) == {
        "A": "1",
        "B": "quoted # not a comment",
        "C": "x",
        "D": "value",
        "E": "",
    }
    assert read_env_file(tmp_path / "missing.env") == {}
    (tmp_path / "bad.env").write_text("NOVALUE\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"bad.env:1: expected KEY=VALUE"):
        read_env_file(tmp_path / "bad.env")


def test_load_settings_precedence_and_coercion(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("APP_DATABASE_URL=sqlite://file\nAPP_WORKERS=2\n", encoding="utf-8")
    settings = load_settings(
        AppSettings,
        prefix="APP_",
        env_file=env,
        environ={"APP_WORKERS": "8", "APP_DEBUG": "true", "APP_HOSTS": '["a.com", "b.com"]'},
    )
    assert settings == AppSettings(
        database_url="sqlite://file", debug=True, workers=8, hosts=["a.com", "b.com"]
    )


def test_load_settings_errors_and_invalid_json() -> None:
    with pytest.raises(ConfigurationError, match=r"invalid settings for AppSettings \(APP_\*\)"):
        load_settings(AppSettings, prefix="APP_", env_file=None, environ={})
    with pytest.raises(ConfigurationError, match="workers"):
        load_settings(AppSettings, env_file=None, environ={"DATABASE_URL": "x", "WORKERS": "lots"})
    with pytest.raises(ConfigurationError, match="hosts"):
        load_settings(AppSettings, env_file=None, environ={"DATABASE_URL": "x", "HOSTS": "[oops"})


def test_load_settings_reads_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SVC_DATABASE_URL", "postgres://env")
    settings = load_settings(AppSettings, prefix="SVC_", env_file=None)
    assert settings.database_url == "postgres://env"


# ------------------------------------------------------------------ errors


@pytest.mark.parametrize(
    ("cls", "kind", "code"),
    [
        (ValidationFailed, ErrorKind.VALIDATION, "validation_failed"),
        (NotFound, ErrorKind.NOT_FOUND, "not_found"),
        (Conflict, ErrorKind.CONFLICT, "conflict"),
        (Unauthenticated, ErrorKind.UNAUTHENTICATED, "unauthenticated"),
        (PermissionDenied, ErrorKind.PERMISSION_DENIED, "permission_denied"),
        (BusinessRuleViolation, ErrorKind.BUSINESS_RULE, "business_rule_violation"),
        (Unavailable, ErrorKind.UNAVAILABLE, "unavailable"),
    ],
)
def test_domain_error_kinds(cls: type[DomainError], kind: ErrorKind, code: str) -> None:
    error = cls("boom")
    assert (error.kind, error.code, error.message, dict(error.details)) == (kind, code, "boom", {})
    assert repr(error) == f"{cls.__name__}('boom', code={code!r})"
    assert ErrorMapper().to_info(error).kind is kind


def test_error_mapper_mro_and_internal(caplog: pytest.LogCaptureFixture) -> None:
    class StockError(Exception):
        pass

    class OutOfStockError(StockError):
        pass

    mapper = ErrorMapper({StockError: ErrorKind.CONFLICT})
    info = mapper.to_info(OutOfStockError("no stock"))
    assert (info.kind, info.code, info.message) == (ErrorKind.CONFLICT, "conflict", "no stock")
    assert mapper.to_info(StockError()).message == "conflict"

    internal = mapper.to_info(RuntimeError("secret connection string"))
    assert internal.kind is ErrorKind.INTERNAL
    assert "secret" not in internal.message
    assert "unhandled exception" in caplog.text


# ------------------------------------------------------------------ module


class Ping(Controller):
    @endpoint()
    async def ping(self) -> str:
        return "pong"


class Dep:
    pass


def test_module_validation() -> None:
    with pytest.raises(ContractError, match="must be snake_case"):
        Module("Orders")
    with pytest.raises(ContractError, match="is not a Controller subclass"):
        Module("x", controllers=[Dep])  # type: ignore[list-item]
    with pytest.raises(ContractError, match=r"exports .* are not provided"):
        Module("x", exports=[Dep])


def test_module_providers_are_owned() -> None:
    module = Module(
        "orders", providers=[Dep, provide(int, lambda: 1)], controllers=[Ping], exports=[Dep]
    )
    owned = module.all_providers()
    assert [(p.key, p.owner) for p in owned] == [(Dep, "orders"), (int, "orders"), (Ping, "orders")]
    assert owned[-1].scope is None  # controllers use the auto scope
