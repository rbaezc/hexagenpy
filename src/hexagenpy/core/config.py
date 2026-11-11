"""Typed settings loaded from environment variables and an optional ``.env`` file.

::

    class AppSettings(Settings):
        database_url: str
        debug: bool = False
        allowed_hosts: list[str] = []

    settings = load_settings(AppSettings, prefix="APP_")
    # APP_DATABASE_URL=..., APP_DEBUG=true, APP_ALLOWED_HOSTS='["a.com","b.com"]'

Precedence: real environment > ``.env`` file > field defaults.
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path

import msgspec

from hexagenpy.errors import ConfigurationError

__all__ = ["Settings", "load_settings", "read_env_file"]


class Settings(msgspec.Struct, kw_only=True):
    """Base class for application settings."""


def read_env_file(path: str | Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines; supports comments, ``export`` and quoted values."""
    values: dict[str, str] = {}
    file = Path(path)
    if not file.is_file():
        return values
    for number, raw in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            raise ConfigurationError(f"{file}:{number}: expected KEY=VALUE")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


def _coerce(text: str) -> object:
    """Structured values (lists, dicts) may be written as JSON."""
    if text[:1] in "[{":
        try:
            parsed: object = json.loads(text)
        except json.JSONDecodeError:
            return text
        return parsed
    return text


def load_settings[S: Settings](
    cls: type[S],
    *,
    prefix: str = "",
    env_file: str | Path | None = ".env",
    environ: Mapping[str, str] | None = None,
) -> S:
    source = dict(read_env_file(env_file)) if env_file is not None else {}
    source.update(os.environ if environ is None else environ)
    data: dict[str, object] = {}
    for name in cls.__struct_fields__:
        env_name = f"{prefix}{name}".upper()
        if env_name in source:
            data[name] = _coerce(source[env_name])
    try:
        return msgspec.convert(data, cls, strict=False)
    except msgspec.ValidationError as exc:
        raise ConfigurationError(f"invalid settings for {cls.__name__} ({prefix}*): {exc}") from exc
