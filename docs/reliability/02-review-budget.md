# Fase 2: revisión y presupuesto confiables

Parte de la [propuesta de confiabilidad](../reliability.md). Puntos 6 y 8.
Depende de la fase 0 (decisión sobre la métrica del presupuesto). Es
requisito de la fase 3: sin una revisión que pueda cerrarse, no hay "listo
para revisión" verificable.

## Problemática

**La revisión automática hoy no puede cerrarse bien.**

- Cuando el ledger pasa de 55 KB no entra en el packet y toda revisión
  termina "inconclusa", sin distinguir "sin hallazgos" de "no revisado".
- El motor excluye los archivos Markdown, que en este producto son el
  comportamiento mismo: los comandos del preset y de las extensiones.
- Si el revisor escribe una categoría de hallazgo que no existe, se rechaza
  el archivo de hallazgos entero.

**Hay dos formas de contar el presupuesto y no coinciden.**

- Renombrar un archivo de 300 líneas cuenta 300 en el loop y 0 en la
  revisión. Ambos ignoran Markdown.
- El loop cuenta solo líneas agregadas, con blancos y comentarios, y solo lo
  ya commiteado: quien implementa no puede medirse antes de commitear.
- El ejemplo del template de tareas no lleva el forecast que el comando
  exige, y las cifras de evidencia se tipean a mano y se desfasan.

## Solución recomendada

- El packet lleva el bloque de la tarea revisada, la estrategia de entrega
  y los requisitos relacionados, con acceso al resto de los artefactos y
  registro de qué se leyó. Los `.md` que definen comandos entran a la
  revisión. Una categoría inválida se corrige sin perder el hallazgo; nunca
  se descarta un hallazgo para lograr un resultado verde.
- Una sola definición de la métrica (qué cuenta, cómo se tratan renames,
  blancos y Markdown), una sola implementación o dos probadas equivalentes
  sobre los mismos casos, y un modo que mida el trabajo sin commitear.
- El ejemplo del template lleva `(~N authored lines)`. El PR toma las cifras
  de la salida de los scripts, nunca tipeadas.

## Decisiones que necesitan respuesta

Decidido el 2026-09-11: unificar primero, medir después; no contar líneas
netas.

## Anexo

- Evidencia: entradas [74](../dogfooding.md:640), [79](../dogfooding.md:680)
  y [90](../dogfooding.md:809) del dogfooding;
  [`speckit-code-review.template.yml:14`](../../packages/spec-kit-code-review/config/speckit-code-review.template.yml:14);
  [`budget_stop.py:56`](../../presets/default/scripts/python/budget_stop.py:56),
  [`budget.py:92`](../../packages/spec-kit-code-review/src/spec_kit_code_review/budget.py:92);
  entradas [58](../dogfooding.md:491), [67](../dogfooding.md:576),
  [69](../dogfooding.md:595), [75](../dogfooding.md:649) y
  [78](../dogfooding.md:672);
  [`tasks-template.md:55`](../../presets/default/templates/tasks-template.md:55)
  contra [`tasks.md:42`](../../presets/default/commands/tasks.md:42).
- Aceptación: una tarea chica con un ledger grande obtiene veredicto
  concluyente; una omisión real sigue siendo inconclusa; un cambio en un
  comando Markdown se revisa; un error de categoría se corrige sin rehacer
  la revisión; un rename puro cuesta lo mismo en los dos caminos; los
  archivos nuevos se ven antes del commit; los números del PR coinciden con
  los capturados.

## Entrada para /speckit.specify

Hacer cerrable la revisión automática y unificar el presupuesto: packet
acotado al bloque de la tarea con acceso al resto, Markdown de comandos
incluido, categorías inválidas corregibles sin perder hallazgos; una sola
métrica de presupuesto compartida por el loop y la revisión, con modo de
working tree; el PR toma las cifras de los scripts.
