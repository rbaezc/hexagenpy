# 1. hexagenpy reemplaza a pyhexagen

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** roadmap, pyhexagen, suite

## Context

La suite HexaGen tiene pyhexagen, un scaffolder que genera proyectos sobre FastAPI + Pydantic + dependency-injector. No ofrece multi-protocolo (GraphQL, gRPC), duplica modelos entre capas y depende de un framework externo cuyo diseño no controlamos.

## Decision

hexagenpy es el framework nativo de Python de la suite y reemplaza a pyhexagen. pyhexagen pasa a modo mantenimiento (solo correcciones críticas) y se marca como deprecated en README y PyPI al publicarse hexagenpy v1.0. El stack `python` de hexacore_agent generará código hexagenpy; pyhexagen queda como perfil legacy.

## Alternatives Considered

- Seguir evolucionando pyhexagen sobre FastAPI
- Convertir pyhexagen en plugin de Litestar

## Consequences

Hay que alcanzar paridad de funciones (init, gen-resource, mapeo de excepciones, logging estructurado, CI) antes de deprecar. Se necesita una guía y un codemod de migración FastAPI → hexagenpy. La suite controla todo el stack de Python.
