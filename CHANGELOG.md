# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
el proyecto sigue [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Fase 0 — Fundaciones
- Estructura del paquete (`src/hexagenpy`), `py.typed` y CLI `hexapy --version`.
- Tooling: ruff, mypy strict, pyright strict, pytest + cobertura ≥ 90 %, pre-commit.
- CI en GitHub Actions: Python 3.12–3.14 en Linux, Windows y macOS, benchmarks smoke y build del wheel.
- Arnés de benchmarks in-process ASGI con baselines de FastAPI, Litestar y Starlette.
- ADRs D1–D8 y registro del proyecto en HexaCore (`.hexagen/`).
