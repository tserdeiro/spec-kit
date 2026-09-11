# Fase 7: varios devs y monorepos

Parte de la [propuesta de confiabilidad](../reliability.md). Punto 17, más el
18 si la fase 0 decide soportar los prefijos. Depende de la fase 3 (draft
adoptable) y de la identidad de Linear.

## Problemática

- El README presenta la asignación en Linear como el semáforo contra
  pisadas, pero `implement` toma la primera tarea sin marcar sin mirar a
  quién está asignada. Dos personas podrían arrancar la misma tarea.
- Upstream permite ramas con prefijo (`autor/app/003-slug`) para monorepos.
  De nuestro lado, algunas rutas lo aceptan y otras no: el patrón de tarea,
  el listado del stack y la línea de sesión esperan que la rama empiece por
  `NNN-`. Un consumidor que use el prefijo dejaría de proyectar a Linear sin
  aviso. Además hay un solo team de Linear por repositorio.

## Solución recomendada

- Antes de implementar, comparar el assignee de la tarea con el usuario de
  Linear y con el trabajo abierto de la feature; una diferencia produce un
  diagnóstico útil, no un bloqueo mudo. Varios devs trabajan en features
  distintas; el relevo dentro de una feature es explícito: reasignar en
  Linear y adoptar el draft.
- Si se soportan los prefijos: un único contrato de nombres aplicado en
  inicio, descubrimiento de PRs, propagación, merge, guards, revisión y
  Linear, con fixtures compartidas. Mientras no se necesite más de un team,
  declararlo y que el onboarding detecte la incompatibilidad.

## Decisiones que necesitan respuesta

Decidido el 2026-09-11: se soporta el prefijo de upstream; un solo team por
repositorio hasta que haya una necesidad real.

## Anexo

- Evidencia: [`README.md:239`](../../README.md:239),
  [`README.md:401`](../../README.md:401),
  [`task_base.py:43`](../../presets/default/scripts/python/task_base.py:43);
  [`git-config.yml:10`](../../.specify/extensions/git/git-config.yml:10),
  [`discovery.py:13`](../../packages/spec-kit-linear/src/spec_kit_linear/discovery.py:13),
  [`work_state.py:63`](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:63),
  [`_common.py:149`](../../presets/default/scripts/python/_common.py:149).
- Aceptación: dos devs en la misma feature reciben un diagnóstico antes de
  pisarse; una feature con el prefijo admitido por upstream atraviesa todo
  el recorrido, también desde un worktree; dos apps no se confunden por
  compartir número o slug.

## Entrada para /speckit.specify

Coordinar a varios devs: `implement` verifica asignación y trabajo abierto
antes de tomar una tarea y explica cualquier discrepancia; relevo explícito
por reasignación; y, si se decidió, un contrato único de nombres de rama con
prefijo de monorepo aplicado en todo el recorrido.
