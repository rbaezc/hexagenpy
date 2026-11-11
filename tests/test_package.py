import re
import runpy

import pytest

import hexagenpy
from hexagenpy.cli import main


def test_version_is_pep440() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?(\.dev\d+)?", hexagenpy.__version__)


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert hexagenpy.__version__ in capsys.readouterr().out


def test_cli_without_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "hexapy" in capsys.readouterr().out


def test_python_dash_m_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["hexagenpy"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("hexagenpy", run_name="__main__")
    assert exc.value.code == 0
