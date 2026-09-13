# 21. Coordinar la asignación y el relevo de una feature

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 17, 18, 19 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [05](05-work-item-branches.md), [07](07-resumable-loop.md), [13](13-review-routing.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

La asignación de Linear se presenta como coordinación, pero el loop puede
tomar una tarea sin comprobar quién la tiene ni qué trabajo ya está abierto.

## Resultado y decisiones

Verificar identidad del usuario de Linear, asignación y trabajo abierto
antes de tomar una tarea. Si pertenece a otra persona, detener el inicio
con una explicación y el relevo requerido. Una tarea sin asignación requiere
resolver esa asignación antes de iniciar el trabajo compartido.

El relevo consiste en reasignar explícitamente y adoptar rama/PR existentes.
Un ejecutor activo por feature; diferentes features pueden tener distintos
responsables. Detectar conflictos observables antes de mutar, sin presentar
una consulta de asignación como un lock distribuido ni crear un servicio de
coordinación.

Conservar feature `NNN-slug`, tarea `NNN-T###-slug`, números únicos por
repositorio y un team. La rama nativa de una Issue no cambia por el relevo.
Los PRs listos no tienen tope. Sin identidad verificable, informar qué parte
de la coordinación no puede garantizarse.

## Aceptación

Dos identidades distintas sobre una tarea asignada reciben resultados
coherentes antes de crear ramas. Un relevo autorizado continúa el draft
existente. Un fallo de autenticación no se interpreta como tarea libre.
La misma operación desde un worktree respeta las ramas ya ocupadas.

## Referencias

[Inicio de tarea](../../presets/default/scripts/python/task_base.py),
[cliente Linear](../../packages/spec-kit-linear/src/spec_kit_linear/linear_client.py),
[descubrimiento](../../packages/spec-kit-linear/src/spec_kit_linear/discovery.py),
[README](../../README.md).
