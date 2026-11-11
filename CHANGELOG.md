# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
el proyecto sigue [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Fase 1 — Núcleo: contratos, DI y slices
- **Contract IR** (`hexagenpy.contracts.ir`): representación neutral de tipos y operaciones (ADR 0002).
- `TypeCompiler`: tipos de Python → IR sobre `msgspec.inspect` (Structs, dataclasses, TypedDict,
  enums, constraints, uniones etiquetadas, genéricos `Page[T]`, recursión, `__contract_name__`).
- `Model` (msgspec), `@endpoint` y `Controller` con bindings para http, graphql y grpc.
- Chequeo de compatibilidad por transporte: GraphQL y proto3 rechazan al arrancar los tipos que
  no pueden representar, con la ruta exacta del campo.
- Contenedor de DI: scopes singleton/request/transient, scope auto para controllers, factories
  async y generadoras con teardown, `provide_context`, overrides, y detección de dependencias
  faltantes, ciclos, singletons que capturan valores request y acceso entre slices sin `exports`.
- `Module` (composition root por slice) y `App` (lifecycle, hooks, `invoke`).
- `Invoker`: camino único de ejecución para todos los transportes; los handlers sync van a un hilo.
- Errores de dominio neutrales (`NotFound`, `Conflict`…) + `ErrorMapper` con `error_map` para
  dominios que no importan hexagenpy; los errores internos no filtran detalles.
- `Settings` + `load_settings` (entorno y `.env`, coerción tipada, JSON para listas y dicts).
- `hexagenpy.testing.TestApp`.
- App de ejemplo con el layout de slice HexaGen en `tests/example/`.

### Fase 0 — Fundaciones
- Estructura del paquete (`src/hexagenpy`), `py.typed` y CLI `hexapy --version`.
- Tooling: ruff, mypy strict, pyright strict, pytest + cobertura ≥ 90 %, pre-commit.
- CI en GitHub Actions: Python 3.12–3.14 en Linux, Windows y macOS, benchmarks smoke y build del wheel.
- Arnés de benchmarks in-process ASGI con baselines de FastAPI, Litestar y Starlette.
- ADRs D1–D8 y registro del proyecto en HexaCore (`.hexagen/`).
