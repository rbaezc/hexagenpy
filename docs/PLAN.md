# hexagenpy — Plan maestro

> Framework de Python de la suite **HexaGen** para APIs REST, web, gRPC y GraphQL,
> construido sobre **Vertical Slices + Ports & Adapters**.
> Fuera de alcance: mobile y desktop.

Estado: **borrador v1.1** · Fecha: 2026-11-05

> **Relación con pyhexagen:** hexagenpy es su **reemplazo**. pyhexagen (scaffolder sobre
> FastAPI) se queda como está, en modo mantenimiento: solo correcciones críticas, sin
> funciones nuevas. Al publicar la v1.0 de hexagenpy se marca como *deprecated* y la
> suite deja de usarlo.

---

## 1. Visión

**"Un contrato, muchos transportes."**
Defines una vez un caso de uso tipado dentro de un slice, y hexagenpy lo expone por
REST (con OpenAPI), GraphQL, gRPC (con `.proto` generado), WebSocket/SSE y vistas web,
sin duplicar modelos y con la arquitectura HexaGen garantizada desde el framework.

```python
# app/slices/orders/presentation.py
from hexagenpy import Controller, endpoint
from .application import OrdersService
from .contracts import OrderIn, OrderOut


class OrdersController(Controller, prefix="/orders", tag="orders"):
    def __init__(self, service: OrdersService) -> None:
        self.service = service

    @endpoint(http="GET /{id}", graphql="query", grpc=True)
    async def get_order(self, id: int) -> OrderOut: ...

    @endpoint(http="POST /", graphql="mutation", grpc=True, status=201)
    async def create_order(self, data: OrderIn) -> OrderOut: ...
```

```python
# app/main.py
from hexagenpy import App
from app.slices import orders, users

app = App(slices=[orders.module, users.module])
# REST + /openapi.json · /graphql · gRPC :50051 · /ws  — misma definición
```

### Por qué es mejor que la alternativa
| Problema actual | FastAPI / Django / Litestar | hexagenpy |
|---|---|---|
| Multi-protocolo | REST + Strawberry + grpcio, cosidos a mano | Nativo desde un solo contrato |
| Modelos duplicados | Pydantic + tipos GraphQL + `.proto` | Un `Model` (msgspec) → todos los esquemas |
| Arquitectura | Libre (FastAPI) o acoplada (Django) | Slices y capas obligatorias, auditadas |
| DI | `Depends()` por request, solo HTTP | Contenedor con scopes, compartido por todos los transportes |
| Rendimiento | Pydantic en el camino crítico | msgspec + router compilado; núcleo Rust opcional |
| Testing | TestClient solo HTTP | `TestApp` para HTTP, GraphQL, gRPC y WS |
| Gobierno | Ninguno | Integración nativa con HexaCore Agent |

### No-objetivos (explícitos)
- Mobile y desktop.
- Panel de administración tipo Django (se puede evaluar después de la 1.0).
- ORM propio en la 1.0. La persistencia va por puertos con adaptadores; ver decisión D4.
- Servidor HTTP propio en Python puro. Se usa ASGI (Granian o Uvicorn) y, más adelante, un núcleo Rust.

---

## 2. Principios de diseño

1. **Contrato primero.** El tipo de Python es la fuente de verdad; OpenAPI, GraphQL SDL y `.proto` se *derivan*.
2. **Dominio sin framework.** `domain.py` no importa nada de hexagenpy; el framework vive en `presentation` y `module`.
3. **Explícito > mágico.** Nada de autodescubrimiento por imports implícitos; los slices se registran en `App(slices=[...])`.
4. **Async nativo, sync tolerado.** Los handlers sync se ejecutan en un threadpool; se prepara soporte para el Python free-threaded.
5. **Tipado estricto.** `mypy --strict` y `pyright` limpios en el framework y en el código generado.
6. **Cero costo por lo que no usas.** GraphQL, gRPC y web son *extras* (`pip install hexagenpy[grpc]`).
7. **Medible.** Cada fase de rendimiento se valida con benchmarks públicos y reproducibles.
8. **Reglas HexaGen.** Archivos ≤ 250 líneas, sin acoplamiento entre slices y dependencias de capa unidireccionales.

---

## 3. Arquitectura del framework

```
hexagenpy/
  core/          App, ciclo de vida (startup/shutdown), config, errores base
  contracts/     Model (msgspec), endpoint/@rpc, registro de contratos, introspección de tipos
  di/            Contenedor, scopes (app/request/transient), providers, overrides para tests
  slices/        Module (composition root por slice), registro, validación de capas
  transports/
    http/        Router (radix tree compilado), Request/Response, middlewares, ASGI adapter
    openapi/     Generador OpenAPI 3.1, Swagger UI/Scalar
    graphql/     Generador de schema, ejecutor, dataloaders, subscriptions
    grpc/        Generador .proto, servidor (grpclib), streaming, reflection, health
    ws/          WebSocket y SSE
    web/         Plantillas (Jinja2), estáticos, sesiones, formularios, CSRF
  security/      AuthN (JWT, OAuth2/OIDC, API keys), AuthZ (policies), CORS, rate limiting
  data/          Puertos de repositorio, Unit of Work, adaptadores SQLAlchemy async
  events/        Eventos de dominio, bus in-process, tareas en background
  observability/ Logging estructurado, OpenTelemetry (traces/metrics), health checks
  testing/       TestApp, clientes por transporte, fixtures pytest
  cli/           `hexapy`: new, slice, run, dev, export, doctor
```

### Layout de un proyecto hexagenpy (compatible con pyhexagen y HexaCore)
```
app/
  main.py
  config.py
  slices/<slice>/
    domain.py          entidades (dataclass frozen) + puertos (Protocol)
    application.py     casos de uso; dependen solo de puertos
    infrastructure.py  adaptadores (InMemory, SQL…)
    contracts.py       Models de entrada/salida (msgspec)
    presentation.py    Controller(s) multi-transporte
    module.py          composition root: providers + controllers
tests/
contracts/             artefactos exportados: <slice>.openapi.yaml, *.proto, schema.graphql
.hexagen/              estado y reglas de HexaCore
```

### Flujo de una petición
```
Transporte (HTTP | GraphQL | gRPC | WS)
   → decodificación (msgspec, una sola vez) → validación
   → scope de DI por request → Controller.endpoint
   → Application service → puertos → adaptadores
   ← resultado / DomainError
   ← codificación por transporte + mapeo de errores (HTTP status | GraphQL error | gRPC status)
```

---

## 4. Fases

Cada fase cierra con: tests verdes, `mypy --strict`, `ruff`, `check_architecture --strict`,
cobertura ≥ 90 % del código nuevo, docs de la fase y una entrada en el CHANGELOG.

### Fase 0 — Fundaciones · *~1 semana*
**Objetivo:** el repositorio listo para desarrollar con calidad desde el día 1.
- `pyproject.toml` (hatchling + uv), estructura `src/hexagenpy/`, extras opcionales.
- Herramientas: ruff, mypy strict, pyright, pytest, pytest-asyncio, coverage, pre-commit.
- CI (GitHub Actions): matriz de Python × Linux/Windows/macOS.
- Arnés de benchmarks (`benchmarks/`) con FastAPI, Litestar y Starlette como baseline.
- ADRs iniciales en `docs/adr/` (decisiones D1–D6 de la sección 6).
- Registro del proyecto en HexaCore (`.hexagen/`, reglas propias en `.hexagen/rules/`).

**Entregable:** repo vacío pero con todo el pipeline verde.

### Fase 1 — Núcleo: contratos, DI y slices · *~3 semanas*
**Objetivo:** la columna vertebral, todavía sin transporte de red.
- `Model` sobre `msgspec.Struct`: validación, constraints (`Annotated[int, Gt(0)]`), alias, defaults.
- Introspección de tipos → representación intermedia (**Contract IR**), neutral al transporte. Es la pieza clave: de ella salen OpenAPI, GraphQL y proto.
- `@endpoint` / `Controller`: metadatos de transporte encima del IR.
- Contenedor de DI: providers por tipo/Protocol, scopes, factories async, overrides para tests, detección de ciclos al arrancar.
- `Module` por slice + `App`: registro explícito, ciclo de vida (`on_startup` y `on_shutdown` con lifespan), config tipada desde env/`.env`.
- Jerarquía de errores de dominio (`DomainError`, `NotFound`, `Conflict`, `ValidationFailed`…), neutral al transporte.
- Validación de arquitectura al arrancar (opcional): el dominio no importa hexagenpy y no hay imports entre slices.

**Criterio de salida:** se puede invocar un caso de uso vía `TestApp.call("orders.create_order", …)` con DI y validación.

### Fase 2 — HTTP/REST + OpenAPI → **v0.1** · *~4 semanas*
**Objetivo:** reemplazar a FastAPI en un proyecto real.
- Adaptador ASGI 3; servidores soportados: Granian (recomendado) y Uvicorn.
- Router radix tree compilado al arrancar; parámetros de path, query, header, cookie y body.
- Request/Response, streaming, archivos, multipart, compresión.
- Middlewares (estilo ASGI puro, sin overhead de `BaseHTTPMiddleware`).
- Mapeo de `DomainError` → HTTP con Problem Details (RFC 9457).
- OpenAPI 3.1 generado desde el IR; UI con Scalar o Swagger; export a `contracts/<slice>.openapi.yaml` (formato de `define_contract` de HexaCore).
- Seguridad básica: CORS, API key y bearer/JWT.
- `TestApp` HTTP (httpx).
- **Benchmarks v0.1** publicados: JSON simple, validación de body, path params y DI con 3 niveles.

**Meta de rendimiento:** ≥ 1.5× el throughput de FastAPI en validación + serialización, con la misma infraestructura.

### Fase 3 — GraphQL → **v0.2** · *~3 semanas*
- Generación del schema desde el IR: queries y mutations por `@endpoint(graphql=…)`; tipos, inputs, enums, unions y nullability.
- Motor: evaluar `graphql-core` (estándar) contra un ejecutor propio compilado (decisión D5).
- DataLoaders integrados al scope de request (para evitar N+1).
- Subscriptions sobre WebSocket (protocolo `graphql-transport-ws`).
- Errores de dominio → `errors[].extensions.code`.
- Límites de profundidad y complejidad, persisted queries y GraphiQL.
- Export a `contracts/schema.graphql`.

### Fase 4 — gRPC → **v0.3** · *~4 semanas*
- Generación de `.proto` (proto3) desde el IR, con mapeo de tipos estable (`int → int64`, `datetime → Timestamp`, `Optional` → `optional`…).
- Servidor gRPC async (grpclib o grpcio.aio; decisión D6) en el mismo proceso que HTTP, en otro puerto, con ciclo de vida y DI compartidos.
- Los cuatro tipos de RPC: unary, server streaming, client streaming y bidi (vía `AsyncIterator`).
- Interceptores (auth, logging, tracing) unificados con los middlewares HTTP.
- Errores de dominio → `grpc.StatusCode` + rich error details.
- Reflection, health checking y gRPC-Web (opcional).
- Modo inverso: importar un `.proto` existente y generar los Models y el esqueleto del Controller.
- Política de compatibilidad: números de campo estables, guardados en `contracts/*.lock`, para no romper clientes.

### Fase 5 — Web (SSR) y tiempo real → **v0.4** · *~3 semanas*
- Plantillas Jinja2 con `@endpoint(http="GET /", view="orders/list.html")`.
- Archivos estáticos con hashing, sesiones (cookie firmada o backend), flash messages.
- Formularios con validación desde `Model`, CSRF.
- Integración amigable con htmx (respuestas parciales, cabeceras `HX-*`).
- WebSockets (canales y rooms) y SSE como transportes de primera clase.
- i18n (es/en), como en hexagenphp.

### Fase 6 — Datos, eventos y tareas → **v0.5** · *~4 semanas*
- Puertos genéricos `Repository[T, ID]` y `UnitOfWork`.
- Adaptador oficial SQLAlchemy 2 async + Alembic (migraciones vía CLI).
- Transacciones por request o por caso de uso (decorador `@transactional`).
- Eventos de dominio: bus in-process, outbox pattern para publicarlos con fiabilidad.
- Background tasks y jobs programados (adaptadores: in-process, Redis/arq).
- Cache (puerto + adaptadores memoria/Redis).
- Paginación estándar (cursor/offset), consistente entre REST, GraphQL (Relay connections) y gRPC.

### Fase 7 — Seguridad y observabilidad → **v0.6** · *~3 semanas*
- AuthN: JWT, OAuth2/OIDC (authorization code + PKCE, client credentials), API keys y sesiones.
- AuthZ: policies declarativas por endpoint (`@endpoint(..., requires="orders:write")`), aplicadas igual en los cuatro transportes.
- Rate limiting, límites de tamaño, cabeceras de seguridad y timeouts.
- OpenTelemetry: traces y métricas automáticas por endpoint y transporte; logging JSON estructurado con correlation id.
- Health/readiness/liveness (HTTP + gRPC health).
- Auditoría de seguridad de dependencias en CI.

### Fase 8 — DX, CLI e integración HexaGen → **v0.8** · *~4 semanas*
- CLI `hexapy` (paralelo a `hexaphp`):
  - `hexapy new <proyecto>` · `hexapy slice <nombre> [campos…]` · `hexapy dev` (recarga en caliente)
  - `hexapy run` · `hexapy export openapi|graphql|proto` · `hexapy routes` · `hexapy doctor` · `hexapy migrate`
- Plantillas de slice idénticas al layout de HexaCore → `execute_scaffolding(stack="python")` genera código hexagenpy.
- Contribución a `hexacore_agent`: perfil `hexagenpy` en el detector de stacks, reglas en `docs/rules/stacks/hexagenpy.md` y comprobaciones de QA.
- **Reemplazo de pyhexagen:**
  - `hexapy new` y `hexapy slice` cubren todo lo que hacen `pyhexagen init` y `gen-resource` (paridad de funciones verificada con una checklist).
  - En `hexacore_agent`, el stack `python` pasa a generar código hexagenpy; pyhexagen queda como perfil *legacy*.
  - Guía y codemod de migración para proyectos existentes (routers FastAPI, DTOs de Pydantic, `dependency-injector`).
  - Aviso de deprecación en el README y en PyPI de pyhexagen al salir la v1.0.
- Capa de compatibilidad opcional para montar apps ASGI existentes (FastAPI o Starlette) bajo hexagenpy durante la migración.
- Extensión de VS Code (snippets y vista de contratos), opcional.

### Fase 9 — Rendimiento extremo → **v0.9** · *~6 semanas*
- Perfilado del camino crítico con los benchmarks de la Fase 2.
- `hexagenpy-core` en **Rust (PyO3 + maturin)**: router, parsing de HTTP y query, y codificación de respuestas. Wheels para las 3 plataformas, con fallback en Python puro.
- Integración profunda con Granian (sin el overhead de ASGI cuando es posible).
- Soporte y pruebas en Python free-threaded (sin GIL).
- **Meta:** ≥ 3× FastAPI en JSON/validación y latencia p99 menor que Litestar.

### Fase 10 — Estabilización → **v1.0** · *~3 semanas*
- Congelar la API pública y aplicar semver estricto.
- Documentación completa (MkDocs Material, es/en): tutorial, guías por transporte, referencia y recetas.
- Proyecto ejemplo de referencia (por ejemplo, un dominio de `hexa_travel`) expuesto por los 4 transportes.
- Publicación en PyPI, plantilla `hexapy new` y anuncio con benchmarks.

**Total estimado:** de 38 a 42 semanas de una persona a tiempo completo. Con ayuda de IA y foco, es razonable apuntar a una **v0.1 usable en ~2 meses**.

---

## 5. Hitos de versión

| Versión | Contenido | Uso posible |
|---|---|---|
| v0.1 | Núcleo + REST + OpenAPI | Reemplazar FastAPI en APIs nuevas |
| v0.2 | + GraphQL | APIs con frontends React (reacthexagen) |
| v0.3 | + gRPC | Comunicación entre microservicios de la suite |
| v0.4 | + Web SSR / WS / SSE | Sitios y paneles internos |
| v0.5 | + Datos, eventos, tareas | Apps de negocio completas |
| v0.6 | + Seguridad y observabilidad | Producción |
| v0.8 | + CLI e integración HexaCore | Adopción en toda la suite |
| v1.0 | + núcleo Rust, docs, API estable | Lanzamiento público |

---

## 6. Decisiones pendientes (se convierten en ADRs en la Fase 0)

| ID | Decisión | Recomendación |
|---|---|---|
| D1 | Versión mínima de Python | **3.12+** (genéricos PEP 695, rendimiento); probar también en 3.13t/3.14t free-threaded |
| D2 | Librería de modelos | **msgspec** (velocidad); adaptador opcional de Pydantic para interoperar |
| D3 | Servidor | ASGI con **Granian** por defecto y Uvicorn soportado; núcleo Rust en la Fase 9 |
| D4 | ORM | No construir ORM en la 1.0; SQLAlchemy por puertos. Evaluar un "HexaORM-py" ligero (paridad con hexagenphp) después de la 1.0 |
| D5 | Motor GraphQL | Empezar con `graphql-core`; ejecutor compilado propio solo si los benchmarks lo justifican |
| D6 | Motor gRPC | `grpclib` (async puro, sin codegen C) frente a `grpcio.aio` (oficial, más maduro). Prototipar ambos en la Fase 4 |
| D7 | Licencia | MIT (igual que pyhexagen) |
| D8 | Nombre del CLI | `hexapy` (paralelo a `hexaphp`) |

---

## 7. Riesgos y mitigación

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Alcance enorme (4 transportes) | Alto | Releases incrementales; cada transporte es un extra independiente sobre el mismo IR |
| El Contract IR no cubre bien los tres esquemas | Alto | Diseñarlo en la Fase 1 con casos de prueba de OpenAPI, GraphQL y proto desde el inicio |
| Diferencias semánticas entre transportes (nullability, streaming, uniones) | Medio | Matriz de compatibilidad documentada; errores claros al arrancar si un tipo no es mapeable |
| Rendimiento prometido no alcanzado | Medio | Benchmarks en CI desde la Fase 2; no publicar metas sin datos |
| Ecosistema pequeño frente a FastAPI | Medio | Compatibilidad ASGI y capa de montaje de apps existentes; adaptador Pydantic |
| Mantenimiento de wheels Rust | Medio | maturin + cibuildwheel; fallback en Python puro siempre funcional |

---

## 8. Métricas de éxito para la 1.0
- Throughput ≥ 3× FastAPI en el benchmark de validación JSON; p99 menor que Litestar.
- Overhead de arranque < 150 ms con 50 slices.
- Cobertura ≥ 90 %; `mypy --strict` limpio; 0 violaciones en `check_architecture --strict`.
- Un endpoint definido una vez funciona en los 4 transportes con tests en cada uno.
- Al menos un producto `hexa_*` migrado desde pyhexagen y en producción.
- Paridad total con pyhexagen, lo que permite marcarlo como deprecated.

---

## 9. Próximo paso
Arrancar la **Fase 0**: crear el repositorio con `pyproject.toml`, CI, el arnés de benchmarks
y los ADRs D1–D8, previa confirmación de las decisiones de la sección 6.
