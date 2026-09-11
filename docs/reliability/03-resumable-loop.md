# Fase 3: retomar una tarea y marcarla lista con respaldo

Parte de la [propuesta de confiabilidad](../reliability.md). Puntos 2, 7 y 5.
Depende de las fases 1 y 2 y de dos decisiones de la fase 0 (tope de PRs en
espera; refresh desde el trunk).

## Problemática

- `implement` siempre intenta crear una rama nueva. Si la rama ya existe o
  hay un PR draft de la misma tarea, se frena o falla. Cambiar de agente a
  mitad de tarea obliga a reconstruir a mano lo que ya estaba hecho.
- Después de corregir lo que encontró la revisión, el loop agrega el commit
  final y marca el PR listo, sin volver a revisar lo cambiado ni comprobar
  que los checks pasen.
- Mantener la rama de feature al día con el trunk es "deber del developer":
  algo que hay que acordarse de hacer.

## Solución recomendada

- Al entrar, el comando mira qué existe (rama, cambios sin commitear, PR,
  sesión de revisión) y ejecuta solo el paso que falta. Reconoce su propio
  draft y lo continúa; un draft de otra tarea sigue frenando, con
  explicación. El mismo camino vale para bugs y chores. El template deja de
  decir `git switch -c` desde la feature: la regla vive en el script.
- Dos transiciones que hoy siguen en prosa pasan a scripts. Cerrar la tarea:
  presupuesto, ledger, revisión cerrada sobre el commit actual sin hallazgos
  bloqueantes, checks de CI en verde cuando el repo los tiene, y recién
  entonces `ready`. Cerrar la feature: todo marcado y ningún PR de tarea
  abierto antes de marcar el gate listo. Un cambio que solo toca el ledger
  tiene tratamiento liviano; un cambio de código renueva la evidencia,
  también en los PRs apilados encima.
- La línea de contexto y `status` muestran "la feature está N commits
  detrás del trunk", después de refrescar. No se mergea solo.
- Opción a evaluar: worktrees de Git para atender otro trabajo sin
  abandonar el checkout actual.

## Decisiones que necesitan respuesta

Decididas el 2026-09-11: sin tope de PRs en espera, mostrando carga y
antigüedad; el refresh desde el trunk solo se muestra, sin merge
automático.

## Anexo

- Evidencia:
  [`task_base.py:43`](../../presets/default/scripts/python/task_base.py:43),
  [`task_base.py:51`](../../presets/default/scripts/python/task_base.py:51),
  [`implement.md:59`](../../presets/default/commands/implement.md:59),
  [`implement.md:66`](../../presets/default/commands/implement.md:66),
  [`implement.md:94`](../../presets/default/commands/implement.md:94),
  [`implement.md:104`](../../presets/default/commands/implement.md:104),
  [`implement.md:110`](../../presets/default/commands/implement.md:110),
  [`implement.md:124`](../../presets/default/commands/implement.md:124),
  [`tasks-template.md:33`](../../presets/default/templates/tasks-template.md:33).
- Aceptación: cortar la sesión después de crear la rama, del commit, del
  push, del draft o de la revisión, y repetir `implement`, continúa sin
  duplicados ni pérdida; un relevo encuentra el mismo paso pendiente; una
  revisión anterior no habilita cambios posteriores sin verificar; la
  feature no se cierra con un PR de tarea abierto.

## Entrada para /speckit.specify

Hacer reanudable el loop de entrega: `implement` detecta rama, cambios, PR y
revisión existentes y ejecuta solo el paso faltante, adoptando su propio
draft; scripts de cierre de tarea (presupuesto, ledger, revisión vigente,
checks, ready) y de cierre de feature; la divergencia respecto del trunk se
muestra en la línea de contexto y en `status`.
