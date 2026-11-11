# 4. msgspec para modelos y validación (D2)

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** contracts, performance, validation

## Context

La validación y la serialización son el costo dominante en el camino crítico de una API. El baseline medido (`benchmarks/results/baseline.json`, escenario `body`) da FastAPI/Pydantic 5,061 ops/s, Litestar/msgspec 8,285 ops/s y Starlette sin validación real 11,558 ops/s.

## Decision

`hexagenpy.Model` se construye sobre `msgspec.Struct`. Las restricciones se declaran con `Annotated[..., Meta(...)]` y la decodificación JSON valida en una sola pasada. Para interoperar se ofrece un adaptador opcional de Pydantic (`hexagenpy[pydantic]`), que acepta `BaseModel` en los contratos y avisa de su costo.

## Alternatives Considered

- Pydantic v2: el ecosistema más grande, pero es más lento y sus objetos son más pesados.
- attrs + cattrs: flexible, pero no decodifica y valida JSON en una sola pasada.
- Validador propio: demasiado costo de mantenimiento.

## Consequences

Se obtiene validación y serialización entre las más rápidas del ecosistema, y el JSON Schema de msgspec sirve de base para el IR. Los usuarios que vienen de Pydantic tienen que aprender una API ligeramente distinta. Los validadores personalizados complejos van en el `__post_init__` o en el dominio.
