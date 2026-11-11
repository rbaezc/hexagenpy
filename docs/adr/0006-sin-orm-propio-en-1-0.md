# 6. Sin ORM propio en la 1.0; persistencia por puertos (D4)

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** data, persistence, scope

## Context

hexagenphp_framework incluye HexaORM. En Python, SQLAlchemy 2 async es maduro y estándar. Construir un ORM duplicaría un esfuerzo enorme y competiría con la meta principal (multi-transporte). Además, la arquitectura HexaGen exige que el dominio no dependa de la persistencia.

## Decision

La 1.0 define puertos genéricos (`Repository[T, ID]`, `UnitOfWork`) y entrega un adaptador oficial de SQLAlchemy 2 async con migraciones de Alembic. Un "HexaORM-py" ligero, para tener paridad con hexagenphp, se evalúa después de la 1.0.

## Alternatives Considered

- ORM propio desde la Fase 6.
- Integrar un ORM Active Record existente (por ejemplo, Tortoise).

## Consequences

Menos alcance y más foco. Los usuarios pueden usar cualquier librería de datos detrás de un puerto. La paridad de funciones con hexagenphp queda incompleta hasta después de la 1.0.
