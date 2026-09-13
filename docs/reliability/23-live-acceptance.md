# 23. Validar el workflow estable desde la distribución publicada

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos aceptación integral y pendientes de 005 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [18](18-event-wiring.md), [20](20-distribution-payload.md), [21](21-developer-handoff.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Objetivo y alcance

Esta última spec es una entrega de validación y evidencia, no otro rediseño
del workflow. Verificar la distribución publicada después de los fixes,
preservando la evidencia anterior y registrando versiones exactas, comandos,
resultados y limitaciones. No repetir una prueba anterior como si acreditara
automáticamente el candidato nuevo.

## Escenarios de aceptación

- Instalación limpia y upgrade de consumidores temporales con los bundles
  publicados; comandos, intérpretes y eventos coherentes.
- Ejecución real de agentes de la matriz vigente, incluyendo los pendientes
  de Codex de la 005. Diferenciar agentes con y sin eventos.
- En un proyecto autorizado de Linear: draft, ready, merge, varios PRs por
  tarea, GitHub inaccesible, reconciliación y repetición sin operaciones.
- Retomar después de rama, commit, push, PR y review; cambio de agente,
  relevo humano y trabajo desde worktree.
- Corrección y propagación dentro de un stack; revisión y CI del candidato
  final; cierre de feature y merge humano.
- Guard local, hook de Git y rulesets probados por sus mecanismos respectivos.
  Registrar por separado assets, prueba sintética y evento real del agente.

## Evidencia y cierre

Usar únicamente repositorios y recursos de prueba autorizados. Documentar y
verificar la limpieza de lo creado. Medir intervenciones por tarea,
recuperación, exactitud de Linear, cobertura de revisión y tiempo hasta un PR
revisable. Cada fallo queda con reproducción y dueño;
un escenario no ejecutado se mantiene pendiente.

La reconciliación observada del 2026-09-11 cubrió operaciones reales de Linear
y handlers invocados por dispatcher; no ejercitó PRs GitHub ni disparo desde
el agente. Se conserva ese alcance exacto. Las validaciones remotas requieren
autorización concreta al ejecutarse; redactar esta entrada no las ejecuta.

## Referencias

[Evidencia Linear existente](../../validation/linear-observed-reconciliation.md),
[005](../../specs/005-developer-experience/tasks.md),
[conformance de bundles](../../scripts/conformance/bundles.sh),
[dogfooding](../dogfooding.md).
