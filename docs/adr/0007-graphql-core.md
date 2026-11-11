# 7. graphql-core como motor GraphQL (D5)

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** graphql, transport

## Context

El transporte GraphQL (Fase 3) necesita parser, validador y ejecutor conformes a la especificación. graphql-core es la implementación de referencia en Python, y sobre ella se construyen Strawberry y Ariadne.

## Decision

Se usa `graphql-core` (`hexagenpy[graphql]`). El schema se construye programáticamente desde el Contract IR, sin decoradores de Strawberry. Solo si los benchmarks muestran que el ejecutor es el cuello de botella se evaluará un ejecutor compilado propio, que podría cachear planes por documento.

## Alternatives Considered

- Strawberry: añade una segunda capa de tipos que compite con el IR.
- Ejecutor propio desde el inicio.

## Consequences

Conformidad con la especificación desde el primer día y menos código propio. El rendimiento queda acotado por graphql-core hasta que se justifique optimizarlo.
