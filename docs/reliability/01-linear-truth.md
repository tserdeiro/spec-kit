# 01. Estados de Linear basados en una observación completa

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 1 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Una lectura fallida de GitHub se convierte en una lista vacía de PRs; una
casilla marcada puede completar una tarea cuyo PR sigue abierto. Un PR
mergeado prevalece sobre otro abierto y la consulta se limita a 200 PRs.

## Resultado y alcance

- Distinguir lectura completa sin PRs de lectura fallida o incompleta.
  Ante incertidumbre, conservar el estado remoto afectado y explicar por qué.
- Leer todos los PRs relevantes mediante paginación. Una respuesta parcial
  nunca habilita completar trabajo.
- Derivar el estado desde los PRs abiertos antes de considerar los mergeados.
  Definir la combinación de draft y ready para que trabajo todavía en
  desarrollo no se presente como íntegramente revisable.
- Aplicar la misma regla a tareas, bugs y chores; mantener reconciliación
  idempotente y fallos de Linear visibles que no abortan la entrega.
- Conservar los nombres actuales: feature `NNN-slug`, tarea
  `NNN-T###-slug`. Los números de feature son únicos por repositorio.

## Aceptación

Fixtures cubren PR mergeado más PR abierto, varios abiertos en estados
distintos, ausencia comprobada de PRs, GitHub inaccesible y paginación
interrumpida. Un repositorio por encima del antiguo límite conserva todos
sus PRs relevantes. Repetir una reconciliación sin cambios produce cero
operaciones. Se comprueba que la incertidumbre tampoco genera un estado
inventado al crear una Issue.

## Referencias

[Derivación](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py),
[GitHub](../../packages/spec-kit-linear/src/spec_kit_linear/github.py),
[bugs y chores](../../packages/spec-kit-linear/src/spec_kit_linear/work_items.py).
La validación remota de estos escenarios pertenece a la entrada 23.
