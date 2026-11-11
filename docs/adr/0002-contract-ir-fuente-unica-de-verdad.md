# 2. Contract IR como fuente única de verdad multi-transporte

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** architecture, contracts, core

## Context

El objetivo central es definir un caso de uso una vez y exponerlo por REST, GraphQL, gRPC, WebSocket y web. Cada transporte tiene su propio sistema de esquemas (OpenAPI, SDL, proto3), con semánticas distintas de nullability, uniones y streaming.

## Decision

Los tipos de Python (Models msgspec y firmas de `@endpoint`) se compilan al arrancar en una representación intermedia neutral, el **Contract IR**. OpenAPI, el schema GraphQL y los `.proto` se derivan del IR. Ningún transporte lee tipos de Python directamente ni depende de otro transporte. Un tipo que no se pueda mapear a un transporte habilitado hace fallar el arranque con un error claro.

## Alternatives Considered

- Que cada transporte introspeccione los tipos de Python por su cuenta.
- Schema-first: escribir `.proto` y SDL a mano y generar Python.

## Consequences

El IR se diseña en la Fase 1 con casos de prueba de los tres esquemas desde el inicio. Agregar un transporte nuevo consiste en escribir un adaptador sobre el IR. El IR se vuelve la API interna más sensible: cualquier cambio exige pasar los tests de los tres generadores.
