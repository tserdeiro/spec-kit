# 09. Cerrar la feature desde el estado real de sus PRs

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 2, 5, 19 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [01](01-linear-truth.md), [08](08-task-close.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El cierre de feature sigue siendo prosa y puede apoyarse en casillas que se
marcaron antes del merge. La divergencia respecto del trunk exige una consulta
manual.

## Resultado y alcance

Extraer el cierre a un script idempotente. Para marcar listo el PR final,
verificar ledger completo con evidencia, lectura completa de PRs, ausencia
de PRs de tarea abiertos e integración comprobable de las entregas. Un draft
cerrado sin merge no equivale a una tarea integrada.

Actualizar el PR final con los resultados observados y mantener revisión
final y merge humanos. Mostrar carga y antigüedad de los PRs pendientes sin
imponer un tope. En contexto/status, informar los commits detrás del trunk
tras fetch; si no pudo refrescarse, decir que no se pudo verificar.
La divergencia se informa, sin merge automático.
El refresco de contexto hace fetch; no invoca el modo actual de
`task_base.py refresh` que también mergea y publica. Alinear la llamada de
inicio de feature con esta política para que no quede una excepción implícita.

## Aceptación

Una casilla marcada con PR abierto o entrega abandonada no permite cerrar.
GitHub incompleto no equivale a cero PRs. Repetir el cierre mantiene el mismo
gate y no mergea. Los stacks sin tope siguen admitidos. La consulta de
divergencia no modifica archivos ni mezcla ramas.

## Referencias

[Implement](../../presets/default/commands/implement.md),
[ledger](../../presets/default/scripts/python/ledger_check.py),
[merge ordenado](../../presets/default/scripts/python/merge_root_first.py),
[reporting](../../packages/spec-kit-linear/src/spec_kit_linear/reporting.py).
