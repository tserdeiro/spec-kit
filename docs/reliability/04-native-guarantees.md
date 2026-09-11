# Fase 4: usar lo nativo de Git, GitHub y Linear

Parte de la [propuesta de confiabilidad](../reliability.md). Puntos 9, 10,
11, 12 y 13. Independiente del loop: casi todo es doctor y configuración.
Depende de tres decisiones de la fase 0 (aprobación del plan; plan de GitHub
y gestor de hooks de los consumidores; creación de `In Review`).

## Problemática

- Las cuatro reglas duras las bloquea un guard que solo corre en agentes
  con eventos. Zed y una persona en la terminal quedan afuera. El chequeo de
  formato de commits en CI existe solo en este repositorio.
- El comando `pr` y el motor de revisión asumen que existe
  `.github/PULL_REQUEST_TEMPLATE.md` en el consumidor; nadie lo instala ni
  lo verifica.
- `implement` considera aprobado el plan si existe un PR de feature abierto,
  y existir no es aprobar. El contrato del repo dice que los commits son
  humanos mientras el preset commitea solo.
- Marcar un PR listo no le pide revisión a nadie; el "qué sigue" al revisor
  le dice "esperá el merge".
- Si al equipo le falta el estado `In Review`, crearlo es un paso manual;
  el título de la Issue se le pregunta al dev.

## Solución recomendada

- El doctor instala un hook `commit-msg` de Git con la misma regla,
  respetando el gestor de hooks que el repo ya use. GitHub bloquea los
  force-push en las ramas compartidas con un ruleset; exigir PR, checks y
  revisión humana queda según el modelo del equipo. El guard sigue para los
  paths protegidos en ramas de tarea. Cuidado: sin reglas de borrado sobre
  las ramas de tarea, porque impedirían el auto-borrado al mergear.
- El doctor crea el template de PR si falta y verifica sus secciones si
  existe, sin pisar personalizaciones. Los pasos mecánicos de `pr` (commit
  acotado, push, crear o adoptar el draft, actualizar el cuerpo) pasan a
  script; el agente solo redacta.
- La aprobación del plan es el propio envío de spec y plan al repositorio
  por parte de producto; `implement` sigue exigiendo solo el PR de feature
  abierto. `AGENTS.md` y el README escriben la autorización acotada del
  agente: commits, pushes, drafts y reconciliación son suyos; producto,
  aprobación y merge son humanos.
- CODEOWNERS en el consumidor, o pedir revisor al marcar listo. El "qué
  sigue" tiene en cuenta asignación y pedidos de revisión.
- `onboard` ofrece crear `In Review`; título y slug salen de la clave de la
  Issue (con la fase 5).

## Decisiones que necesitan respuesta

Decididas el 2026-09-11: la aprobación del plan es su propio envío al
repositorio, sin gate adicional (queda escribir la autorización del agente);
el plan de GitHub y el gestor de hooks se verifican en el doctor antes de
aplicar; `onboard` crea `In Review` y lo que Linear necesite, con
autorización de quien administra el team.

## Anexo

- Evidencia:
  [`cli.py:2278`](../../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py:2278),
  [`conventions.yml:4`](../../.github/workflows/conventions.yml:4),
  [`vision.md:45`](../vision.md:45);
  [`pr.md:30`](../../presets/default/commands/pr.md:30),
  [`pr.md:60`](../../presets/default/commands/pr.md:60),
  [`pr.md:120`](../../presets/default/commands/pr.md:120),
  [`packet.py:1173`](../../packages/spec-kit-code-review/src/spec_kit_code_review/packet.py:1173);
  [`AGENTS.md:84`](../../AGENTS.md:84),
  [`plan-template.md:95`](../../presets/default/templates/plan-template.md:95),
  [`implement.md:42`](../../presets/default/commands/implement.md:42),
  [entrada 10](../dogfooding.md:87);
  [`reporting.py:194`](../../packages/spec-kit-linear/src/spec_kit_linear/reporting.py:194),
  [`work_state.py:190`](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:190);
  [`README.md:459`](../../README.md:459),
  [`README.md` de linear:79](../../packages/spec-kit-linear/README.md:79).
- Aceptación: el mismo commit inválido recibe diagnóstico desde el agente
  y desde una terminal; GitHub rechaza un force-push; un stack válido se
  integra raíz primero y sus ramas se limpian; un consumidor limpio obtiene
  un PR completo sin crear el template a mano; una aprobación vigente evita
  repetir preguntas; el revisor recibe el PR y su comando.

## Entrada para /speckit.specify

Llevar las garantías del flujo a mecanismos nativos: hook `commit-msg` y
rulesets instalados o verificados por el doctor, template de PR instalado,
pasos mecánicos de `pr` en script, la autorización del agente escrita en el
contrato, revisor solicitado por CODEOWNERS o al
marcar listo, y `onboard` ofreciendo el estado `In Review`.
