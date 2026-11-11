# Benchmarks

Benchmarks **in-process sobre ASGI**: el runner llama a la app directamente con
`scope/receive/send`, sin sockets ni servidor. Así se mide solo el overhead del
framework (routing, validación, DI, serialización) de forma reproducible en
Windows, Linux, macOS y CI.

Las pruebas de carga end-to-end (Granian + `oha`/`wrk`) se añaden en la Fase 2.

## Escenarios
| Nombre | Petición | Qué mide |
|---|---|---|
| `json` | `GET /json` | Routing + serialización mínima |
| `path` | `GET /items/42` | Parámetros de path con conversión a `int` |
| `body` | `POST /orders` (10 items) | Decodificación + validación + respuesta |

Cada framework tiene una app equivalente en `apps/<framework>_app.py`. La app de
`hexagenpy` se añade cuando exista el transporte HTTP (Fase 2); hasta entonces
el runner la omite.

## Uso
```bash
pip install -e . --group bench          # o: uv sync --group bench
python -m benchmarks.run
python -m benchmarks.run -f fastapi litestar -s body -n 20000
python -m benchmarks.run --json benchmarks/results/latest.json
```

## Metas (ver docs/PLAN.md)
- v0.1: ≥ 1.5× FastAPI en `body`.
- v1.0: ≥ 3× FastAPI en `body` y p99 menor que Litestar.
