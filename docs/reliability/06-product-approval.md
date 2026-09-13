# 06. Publicar el plan después de la aprobación de producto

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 3, 11 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Los comandos de producto commitean sus borradores y `implement` crea un
gate si falta. La publicación deja de ser prueba de un cierre de producto
si la propia implementación puede producirla.

## Resultado y decisiones

El flujo de producto es `specify → clarify → plan → tasks → analyze`.
Spec, plan y tareas se refinan localmente. Al terminar las verificaciones,
el agente presenta el resultado y espera aprobación explícita de producto.
Solo entonces commitea los artefactos de la feature, los publica y abre o
actualiza su PR draft mediante la rutina de PR existente.

Modificar coordinadamente los commits de cierre y la elegibilidad de hooks
para que un auto-commit no publique el borrador antes de esa decisión.
Mantener la sincronización revisada de Linear y la asignación requeridas
por el contrato de producto antes de entregar a desarrollo.

`implement` exige el gate abierto y artefactos publicados coherentes;
si falta, devuelve el cierre de producto pendiente y no lo crea.
Cambios posteriores de alcance requieren nueva aprobación antes de publicar.
La publicación posterior a aprobación es el registro del handoff; no se
agrega un sistema paralelo de aprobaciones.

Alinear visión, constitución, README, templates y contrato de autorización:
el agente ejecuta la mecánica autorizada; aprobación y merge son humanos.
Los borradores de discovery de `assess` son distintos de estos artefactos.

## Aceptación

Antes de aprobar no hay commit/publicación automática de spec, plan y tareas.
Después, repetir el cierre conserva el mismo PR y no duplica operaciones.
Una sesión nueva puede continuar desde lo publicado. `implement` sin gate,
con gate cerrado o con artefactos de producto modificados sin publicar no
inicia tareas.

## Referencias

[Tasks](../../presets/default/commands/tasks.md),
[PR](../../presets/default/commands/pr.md),
[implement](../../presets/default/commands/implement.md),
[constitución](../../.specify/memory/constitution.md),
[visión](../vision.md), [AGENTS](../../AGENTS.md).
