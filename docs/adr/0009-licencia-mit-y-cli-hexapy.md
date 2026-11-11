# 9. Licencia MIT y CLI `hexapy` (D7, D8)

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** licensing, cli, suite

## Context

pyhexagen se publica con licencia MIT (Copyright Vortex Solutions). El framework de PHP de la suite usa el CLI `hexaphp`.

## Decision

hexagenpy usa la licencia MIT, con Copyright 2026 Vortex Solutions. El CLI se llama `hexapy` (paralelo a `hexaphp`) y también se puede ejecutar con `python -m hexagenpy`.

## Alternatives Considered

- Apache-2.0, que da protección explícita de patentes.
- Llamar al CLI `hexagenpy`, que es más largo, o `hx`, que puede chocar con otras herramientas.

## Consequences

Adopción sin fricción legal. El nombre del CLI es coherente en la suite.
