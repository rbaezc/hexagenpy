# 8. Motor gRPC: prototipar grpclib frente a grpcio.aio (D6)

- **Status:** proposed
- **Date:** 2026-11-05
- **Tags:** grpc, transport

## Context

gRPC requiere HTTP/2 y no corre sobre ASGI. Hay dos opciones viables:

- **grpclib:** asyncio puro y ligero; no necesita el codegen en C. Su mantenimiento es más pequeño.
- **grpcio.aio:** la implementación oficial de Google, la más madura y completa (reflection, health, xDS), pero pesada y con un modelo de servicio basado en codegen.

## Decision

Se pospone hasta la Fase 4. Se prototipan ambos detrás de un puerto interno `GrpcServer`, y se miden el throughput unary y de streaming, el tamaño de la instalación y la compatibilidad con reflection y health. El servidor gRPC corre en el mismo proceso que el HTTP, en un puerto aparte, y comparte el ciclo de vida y el contenedor de DI.

## Alternatives Considered

- Elegir grpcio.aio ahora por madurez.
- Elegir grpclib ahora por ligereza.

## Consequences

El extra `hexagenpy[grpc]` queda vacío hasta la Fase 4. Gracias al puerto interno se podría cambiar de motor sin afectar a los usuarios.
