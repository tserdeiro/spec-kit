# Fase 0: antes de empezar

Parte de la [propuesta de confiabilidad](../reliability.md). No es una
feature: son chores, verificaciones pendientes y decisiones. Se ejecuta sin
spec-kit: cada chore en su rama y su PR (como el #116), cada decisión
anotada aquí con fecha, cada verificación con su evidencia registrada.

## Problemática

- Este repositorio corría con payloads anteriores a la 005 y sin eventos.
  Resuelto con el PR #116 (mergeado el 2026-09-11); lo que dejó ver está en
  la [entrada 102](../dogfooding.md) del dogfooding.
- La 005 sigue sin dos evidencias de aceptación: la ejecución viva en Codex
  y una reconciliación observada en un proyecto de prueba de Linear
  ([entradas 88 y 97](../dogfooding.md:777)).
- Los parches a upstream están preparados y verificados, pero no abiertos.
  Upstream exige pruebas manuales con agente para cada comando afectado;
  0003 y 0004 quedaron aparcados detrás del
  [diseño del resolver portátil](../upstream/hooks-runtime-design.md).
- Cinco decisiones bloquean fases posteriores y una condición externa (el
  plan de GitHub de los consumidores) condiciona la fase 4.
- El árbol tiene trabajo sin commitear: la ronda de upstream, los documentos
  de esta propuesta y las entradas 100 a 102 del dogfooding.
- Tres etiquetas del dogfooding están desactualizadas (32, 34 y 92) y el
  `preset.yml` fuente sigue con el piso `>=1.0.1`.

## Qué hacer

1. **Commitear lo pendiente**, un concern por commit: la ronda de upstream
   (`docs(upstream): ...`), la propuesta (`docs(reliability): ...`) y el
   dogfooding (`docs(dogfooding): ...`). Decidir si `dx-proposals.md` se
   borra, porque `reliability.md` lo absorbió.
2. **Responder las decisiones** de la tabla de abajo y anotarlas con fecha.
   Hecho el 2026-09-11, salvo el nombre del comando de revisión.
   Verificar el plan de GitHub de los repos consumidores: los rulesets en
   repos privados exigen Pro o Team.
3. **Cerrar la aceptación de la 005**: correr los tres prompts de T023 en
   una máquina con Codex instalado (no está instalado en la máquina actual) y registrar los transcripts; hacer un
   `push --apply` contra un proyecto de prueba en Linear y verificar los
   estados en la interfaz. Evidencia en `validation/` o en el dogfooding.
4. **Abrir los PRs a upstream** que tengan sus pruebas de agente hechas:
   0001, 0002 y 0005 a 0009, con el mapa de pruebas de
   [`hooks-runtime-design.md`](../upstream/hooks-runtime-design.md) y los
   bodies de [`submissions.md`](../upstream/submissions.md). 0003 y 0004 no
   se abren.
5. **Higiene**, en un chore: marcar 32 y 34 como resueltas y cerrar 92 en
   el dogfooding; subir el piso del preset a `>=1.0.4`; sumar `reliability.md`
   y `reliability/` a las excepciones de idioma de `AGENTS.md`; asignar el
   número de ronda en `plan.md` (los números de ronda y los de `specs/` son
   independientes).

## Decisiones que necesitan respuesta

| Decisión | Fase que la necesita | Recomendación | Respuesta y fecha |
| --- | --- | --- | --- |
| Métrica del presupuesto y alcance del packet | 2 | unificar primero, medir después; no contar líneas netas | Sí, unificar primero y medir después (2026-09-11). |
| Qué cuenta como aprobación del plan y qué registro vale con un solo maintainer | 4 | revisión nativa del PR de feature más un registro explícito para el caso de una persona | La aprobación es el propio envío del plan al repositorio: producto commitea spec y plan cuando los termina y no hace falta otra aprobación (2026-09-11). |
| Nombre canónico del comando de revisión | 6 | elegir uno y que toda la documentación diga el real | Pendiente: falta elegir el nombre. |
| Prefijos de monorepo y teams por repositorio | 1 y 7 | soportar el prefijo con un contrato único; un team hasta que haya necesidad real | Se soporta `autor/app/003-slug`; un team por repositorio hasta que haya necesidad real (2026-09-11). |
| Tope de PRs en espera de revisión | 3 | sin tope, mostrando carga y antigüedad | Sin tope; se muestran carga y antigüedad (2026-09-11). |
| Plan de GitHub y gestor de hooks de los consumidores | 4 | verificar en el doctor antes de aplicar | Sí, verificar en el doctor antes de aplicar, hooks incluidos (2026-09-11). |
| Crear `In Review` desde `onboard` | 4 | ofrecerlo, con autorización del team | Sí: `onboard` crea `In Review` y lo que haga falta para que Linear quede bien configurado (2026-09-11). |
| Canal de depuración de los handlers | 6 | una línea en stderr bajo una variable | Sí, una línea en stderr bajo una variable (2026-09-11). |
| Refresh automático desde el trunk | 3 | solo mostrar, hasta acordar una política | Solo mostrar; sin merge automático (2026-09-11). |

## Criterio de salida

Todo commiteado; las nueve decisiones respondidas con fecha; las dos
evidencias de la 005 registradas; los siete PRs a upstream abiertos o con su
bloqueo anotado; el chore de higiene mergeado. Recién entonces se escribe la
spec de la fase 1.

## Anexo

- Evidencia del upgrade: PR #116 y la entrada 102 del dogfooding.
- Verificación de los parches: [`verification.md`](../upstream/verification.md).
- Regla de regeneración local tras un upgrade: `uv sync`, y
  `specify extension disable <id> && specify extension enable <id>` para
  volver a cablear `.claude/settings.json`, que no viaja en el commit.
