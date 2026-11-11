# 5. ASGI 3, con Granian como servidor por defecto (D3)

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** server, http, performance

## Context

Escribir un servidor HTTP/1.1 y HTTP/2 en Python puro es costoso y lento. El ecosistema ya tiene servidores ASGI maduros: Uvicorn (el estándar) y Granian (escrito en Rust, con mayor throughput y soporte de HTTP/2).

## Decision

hexagenpy expone una app ASGI 3 estándar. `hexapy run` usa Granian por defecto (`hexagenpy[server]`) y Uvicorn queda soportado (`hexagenpy[uvicorn]`). En la Fase 9 se evalúa una integración directa con Granian (RSGI) y el núcleo `hexagenpy-core` en Rust para el router y el parsing.

## Alternatives Considered

- Servidor propio en Python puro.
- Servidor propio en Rust desde el día uno.
- Solo Uvicorn.

## Consequences

Es compatible con cualquier despliegue ASGI y con las herramientas de pruebas existentes. El rendimiento del servidor queda en manos de Granian, y el framework se concentra en su propio overhead. gRPC no corre sobre ASGI: tiene su propio servidor en el mismo proceso (ver ADR de gRPC).
