# 3. Python 3.12 como versión mínima (D1)

- **Status:** accepted
- **Date:** 2026-11-05
- **Tags:** platform, python

## Context

A noviembre de 2026 las versiones soportadas de CPython son de la 3.10 a la 3.15. Las 3.10 y 3.11 están cerca del fin de soporte. La 3.12 introduce la sintaxis de genéricos PEP 695, que simplifica el tipado del contenedor de DI y de los contratos, y trae mejoras de rendimiento. La 3.13 y la 3.14 ofrecen builds free-threaded (sin GIL).

## Decision

`requires-python = ">=3.12"`. CI prueba 3.12, 3.13 y 3.14 en Linux, Windows y macOS. Desde la Fase 9 se agregan los builds free-threaded (3.13t y 3.14t) a la matriz.

## Alternatives Considered

- 3.10+ (igual que pyhexagen): más alcance, pero sin PEP 695 y con soporte a punto de terminar.
- 3.13+: permite free-threading desde el inicio, pero excluye a muchos entornos de producción actuales.

## Consequences

Se puede usar `type X = ...` y `class Foo[T]:` en todo el código. Los proyectos en 3.10 o 3.11 tendrán que actualizar Python para migrar desde pyhexagen.
