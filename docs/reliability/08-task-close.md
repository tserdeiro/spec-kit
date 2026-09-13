# 08. Cerrar la tarea con revisión y checks vigentes

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 7 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [02](02-review-context.md), [04](04-review-findings.md), [07](07-resumable-loop.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El loop puede modificar el candidato después de revisarlo y marcar el PR
listo con evidencia anterior.

## Resultado y decisiones

Automatizar esta secuencia: cambios y evidencia de tests → commit final
(incluida la casilla y evidencia determinista) → push → revisión del candidato
→ checks → `ready`. El resultado de revisión permanece en la sesión y el
PR; no requiere otro commit que invalide el candidato revisado.

Verificar `HEAD` y `merge-base` con el mecanismo existente del motor,
veredicto concluyente y ausencia de hallazgos bloqueantes. Un cambio posterior,
también en Markdown, exige evidencia vigente. Los PRs afectados por una
propagación dentro del stack pasan por la misma comprobación antes de volver
a declararse listos. No introducir una excepción de ledger en esta entrega.

Los checks exigibles aprobados permiten seguir; pendientes esperan; fallidos
o no verificables conservan el draft con diagnóstico. Distinguir un repo
sin checks de una lectura fallida y documentar qué checks exige el cierre,
incluidos los que el CI solo ejecuta al salir de draft. La solución no debe
depender de un evento que el propio cierre impide disparar.

## Aceptación

Un cambio tras la revisión, un `merge-base` distinto, review inconclusa o CI
no verificable impiden `ready`. Reanudar después de un timeout no duplica
operaciones. Un repo sin checks tiene resultado explícito. Cada PR del stack
usa evidencia de su propio candidato.

## Referencias

[Implement](../../presets/default/commands/implement.md),
[sesiones y drift](../../packages/spec-kit-code-review/src/spec_kit_code_review/session.py),
[ledger](../../presets/default/scripts/python/ledger_check.py).
