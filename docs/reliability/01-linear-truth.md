# Fase 1: que Linear no mienta

Parte de la [propuesta de confiabilidad](../reliability.md). Punto 1.
Depende de la fase 0: la decisión sobre prefijos de monorepo define qué
nombres de rama reconoce la derivación que esta fase corrige.

## Problemática

Los estados de Linear se calculan desde lo observable: la casilla del
ledger, la rama y el PR de cada tarea. Hoy ese cálculo se equivoca en tres
situaciones:

- Si GitHub no responde, el sistema mira solo la casilla y marca la tarea
  como completada aunque su PR siga abierto.
- Si una tarea se partió en dos PRs y uno se mergeó, la marca completada
  aunque el otro siga abierto: el PR mergeado le gana al abierto.
- Lee como máximo 200 PRs y este repositorio ya tiene 115: en una o dos
  rondas más dejaría de ver trabajo real, sin avisar.

Cuando falla la comunicación con Linear, los scripts del loop ya siguen con
un aviso; lo que falta es que esa falla quede visible (fase 6).

## Solución recomendada

- Un PR abierto siempre gana, incluso sobre uno mergeado de la misma tarea.
  Es lo que hace Linear nativamente cuando una Issue tiene varios PRs.
- Si no se pudo leer GitHub, no se escribe el estado de esa tarea y el
  diagnóstico lo dice; nunca se inventa un "hecho".
- Se leen todos los PRs, con la misma regla que ya usan los scripts del
  preset: límite alto y, si la lectura queda incompleta, se avisa y no se
  actúa a medias.
- Repetir la reconciliación sin cambios sigue produciendo cero operaciones.

## Decisiones que necesitan respuesta

Decidido el 2026-09-11: se soporta el prefijo de upstream
(`autor/app/003-slug`). El patrón de rama de tarea y la lectura del stack
cambian en esta fase; el resto del contrato de nombres, en la fase 7.

## Anexo

- Evidencia:
  [`cli.py:945`](../../packages/spec-kit-linear/src/spec_kit_linear/cli.py:945),
  [`work_state.py:96`](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:96),
  [`work_state.py:131`](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:131),
  [`github.py:27`](../../packages/spec-kit-linear/src/spec_kit_linear/github.py:27),
  [`github.py:59`](../../packages/spec-kit-linear/src/spec_kit_linear/github.py:59);
  la paginación del preset en
  [`_common.py:137`](../../presets/default/scripts/python/_common.py:137).
- Aceptación: una tarea con un PR mergeado y otro abierto sigue en curso;
  una caída de GitHub no la completa; un repositorio con más PRs que el
  límite anterior conserva toda la pila; repetir sin cambios da cero
  operaciones. Validar contra un proyecto de prueba de Linear, además de
  fixtures.

## Entrada para /speckit.specify

Corregir la derivación de estados de la extensión Linear: un PR abierto
gana siempre, también sobre uno mergeado de la misma tarea; sin lectura de
GitHub no se escribe estado y se avisa; la lectura de PRs pagina y avisa si
queda incompleta. Sin cambios de superficie. Evidencia contra un proyecto
de prueba de Linear.
