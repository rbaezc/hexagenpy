# hexagenpy — reglas del proyecto

Reglas propias del framework; tienen prioridad sobre las reglas genéricas de Python.

## Estructura del framework
- El código vive en `src/hexagenpy/<area>/` (core, contracts, di, slices, transports, security, data, events, observability, testing, cli).
- `core`, `contracts` y `di` no importan nada de `transports/*`. Las dependencias van de los transportes hacia el núcleo, nunca al revés.
- Cada transporte (`transports/http`, `graphql`, `grpc`, `ws`, `web`) depende solo del **Contract IR** y del núcleo, nunca de otro transporte.
- Las dependencias opcionales (graphql-core, jinja2, grpc) se importan solo dentro de su transporte; `import hexagenpy` no debe requerirlas.

## Código
- Archivos de 250 líneas como máximo; si crece, se divide por responsabilidad.
- `mypy --strict` y `pyright` strict limpios; nada de `Any` en la API pública salvo cuando esté justificado.
- API pública explícita mediante `__all__`; todo lo demás es privado (`_modulo.py` o `_nombre`).
- Sin estado global mutable; la configuración y el registro viven en `App` y en el contenedor.
- El camino crítico (request → respuesta) no reserva memoria evitable: se precalcula todo al arrancar.

## Tests
- Cada módulo nuevo llega con sus tests; la cobertura del código nuevo debe ser ≥ 90 %.
- Cualquier cambio en el camino crítico se valida con `python -m benchmarks.run` antes del merge.

## Apps generadas (layout de slice)
`app/slices/<slice>/{domain,application,infrastructure,contracts,presentation,module}.py`
- `domain.py` no importa hexagenpy.
- `application.py` depende solo de los puertos de `domain.py`.
