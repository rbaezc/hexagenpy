# hexagenpy

> **Un contrato, muchos transportes.** El framework de Python de la suite **HexaGen**:
> REST, GraphQL, gRPC y Web sobre Vertical Slices + Ports & Adapters.

**Estado:** pre-alpha. Fases 0 y 1 completas (contratos, DI, slices); sigue la Fase 2
(HTTP/REST + OpenAPI). Ver la [hoja de ruta](docs/PLAN.md).

hexagenpy es el reemplazo de [pyhexagen](https://github.com/rbaezc/pyhexagen),
el scaffolder sobre FastAPI, que pasa a modo mantenimiento.

## La idea

```python
class OrdersController(Controller, prefix="/orders"):
    def __init__(self, service: OrdersService) -> None:
        self.service = service

    @endpoint(http="POST /", graphql="mutation", grpc=True, status=201)
    async def create_order(self, data: OrderIn) -> OrderOut: ...
```

Una sola definición genera REST + OpenAPI 3.1, un schema GraphQL y un servicio
gRPC con su `.proto`, con la misma validación (msgspec), la misma inyección de
dependencias y el mismo mapeo de errores de dominio.

El núcleo ya funciona sin transporte de red (`TestApp`, `app.invoke`); los transportes
HTTP, GraphQL y gRPC llegan en las Fases 2 a 4. La app de referencia está en
[`tests/example/`](tests/example/).

## Desarrollo

Requiere Python 3.12+.

```bash
# con uv (recomendado)
uv sync --group dev
uv run pytest

# o con venv + pip
python -m venv .venv
.venv/Scripts/activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e . --group dev
```

| Tarea | Comando |
|---|---|
| Tests + cobertura | `pytest --cov` |
| Lint / formato | `ruff check .` · `ruff format .` |
| Tipos | `mypy` · `pyright` |
| Benchmarks | `python -m benchmarks.run` (ver [benchmarks/](benchmarks/README.md)) |

Reglas de arquitectura (HexaGen): archivos de 250 líneas como máximo, sin imports
entre slices y el dominio sin depender del framework. Se auditan con HexaCore
Agent (`check_architecture --strict`).

## Documentación
- [Plan maestro y fases](docs/PLAN.md)
- [Decisiones de arquitectura (ADRs)](docs/adr/)

## Licencia
MIT
