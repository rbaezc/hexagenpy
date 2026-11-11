# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
el proyecto sigue [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Fase 2a — Transporte HTTP/REST + OpenAPI
- `HttpApp`: app ASGI 3 sobre cualquier `App`; lifespan, middlewares ASGI puros y 503
  `app_not_started` si el lifespan no está activo. Probado con Uvicorn y Granian.
- Router de trie de segmentos compilado al arrancar: estáticas en O(1), backtracking,
  405 con `Allow`, `HEAD` → `GET` y conflictos de rutas detectados al arrancar.
- Binding por operación: path, query (listas con claves repetidas), headers, cookies y body
  JSON. Se infiere la fuente y se puede declarar con `Path/Query/Header/Cookie/Body` y alias.
  Dos pasadas de msgspec por request.
- Errores como Problem Details (RFC 9457) con `code` estable y `errors[]` con ubicación y
  campo exacto (`body` → `lines[0].qty`); 404/405/413/415/422/500 sin filtrar detalles internos.
- Respuestas JSON con msgspec, 204 automático para `None` y streams `AsyncIterator` como NDJSON.
- `RequestContext` neutral (núcleo) y `HttpRequest`, inyectables por DI.
- OpenAPI 3.1 generado desde el Contract IR (JSON Schema 2020-12: constraints, nullables,
  uniones con discriminator, enums, tipos recursivos) y referencia interactiva en `/docs`.
- Middleware CORS (preflight, credenciales, expose headers).
- `hexagenpy.testing.http.HttpTestClient`: cliente in-process sin dependencias.
- Benchmarks in-process: en `body`, ~6.7× FastAPI y ~5.3× Litestar (Windows, Python 3.14).

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
