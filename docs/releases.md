# Releases: diseño acordado

Decisiones del 2026-09-02 al 2026-09-05 para la ronda 005. Deriva de
[`vision.md`](vision.md); la spec se escribe a partir de este documento.

## Problema

En cada pase a staging y a producción, avisar a todo el equipo qué cambió y
qué probar, desde el harness, sin Slack, agnóstico al proyecto.

## Decisiones

- **Sin squash.** Solo merge commits, como hoy: cada PR deja su trailer
  `Merge pull request #N`, los stacked PRs siguen funcionando y el branch de
  entrega ya tiene un commit por PR.
- **Entornos por convención, sin config.** Producción = merge al default de
  GitHub. Staging = merge al branch `staging`, si existe en el remoto. Trunk
  = `trunk:` del git extension (`dev` en app-maker). Sin tags ni GitHub
  Releases.
- **Ledger nativo: Linear Releases.** Un pipeline continuo por repo y
  entorno (`<repo> · staging`, `<repo> · production` con `isProduction`),
  creados por `onboard`. Cada pase crea un release con `releaseSync` y la
  API key: `commitSha` más los PRs del rango; Linear resuelve los Issues
  desde los PRs. Requiere plan Business y la integración GitHub del
  workspace. Sin Business el comando para con la remediación de `doctor`;
  no hay camino alternativo.
- **Aviso: un Issue por release, con sub-issues.** Título
  `Release <entorno> <fecha>` (más el app cuando el pase toca uno solo);
  descripción con el resumen y el link al release; un sub-issue por ítem
  de prueba; suscriptos: los miembros del team. Sin Project, sin
  asignación, en Todo. Nunca se edita después de creado. El de producción
  enlaza el de staging y sus ítems son de repasada.
- **Contenido derivado, nunca inventado.** Por PR del rango: qué cambió
  (título y Outcome) y qué probar. Features: user stories y acceptance
  scenarios del spec, más Risks y Rollout del PR. Bugs: síntoma verificado
  en `.specify/bugs/<slug>/`. Chores: título. Agrupado por app según las
  rutas tocadas (`apps/<app>`; "compartido" para `packages/*`, nombrando
  qué apps lo consumen); `apps/native` marcado "requiere publicación en
  stores" con la versión del `app.json`. Idioma: el del README del repo.
- **Estados sin cambios.** `Todo → In Progress → In Review → Done`, Done =
  mergeado. El entorno es atributo del release, no de la tarea; la
  verificación vive en los Issues de release.
- **Sub-issues habilitados globalmente.** `issue.create` admite `parentId`
  y `subscriberIds`; regla: el harness crea jerarquía solo donde su fuente
  la declara. `push` sigue plano por construcción. Sin flags ni excepciones.
- **Setup desde el CLI.** `onboard` es el wizard: deriva lo derivable,
  pregunta en terminal lo que falta (key con entrada oculta), acepta flags
  para agentes y crea lo ausente de forma aditiva. `doctor --fix` aplica
  los settings de GitHub con `gh api` y repara drift. Dos pasos humanos:
  conectar GitHub en Linear (OAuth de admin) y contratar Business;
  `doctor` los verifica y remedia con instrucciones exactas.
- **Ledger durable en Linear.** Para releases, git guarda los commits y
  Linear qué salió. Excepción explícita al principio "los artefactos del
  repo son la verdad"; se declara en la visión.

## Workflow final

1. Un humano mergea el PR de promoción (`dev → staging`, `staging → main`
   o `dev → main`) y despliega como hoy.
2. `/speckit.release`, en cualquier checkout actualizado:
   - por cada entorno con merges sin release (HEAD del branch distinto del
     SHA del último release del pipeline) deriva el rango y sus PRs; sin
     release previo, el rango es el último merge de promoción;
   - el agente redacta los ítems desde los artefactos y los muestra;
   - con confirmación: `releaseSync`, luego el Issue con sus sub-issues y
     suscriptos.
3. Idempotente: release existente se salta; Issue con el marcador del
   release, cero operaciones. Un merge sin comando lo cubre la corrida
   siguiente.
4. El equipo prueba en staging desde los sub-issues y repasa producción
   desde el Issue de producción. Los bugs nacen como Issues, como hoy.

## Cambios a aplicar

Preset `default`:

- `speckit.release` (`.md`): la orquestación anterior; bloques POSIX, sin
  lógica por agente.
- Trunk: los PRs de bug y chore apuntan al trunk, no al default de GitHub
  (`pr.md`, `bugfix.md`, `chore.md`, README, template de tasks).

Extensión `linear`:

- Subcomando `release`: preview por defecto, `--apply` escribe; recibe el
  aviso redactado por archivo.
- Allowlist: `release.sync` y `release.pipeline.create` nuevos;
  `issue.create` suma `parentId` y `subscriberIds`; `subissue.create` sale
  de la lista de prohibidos.
- Lecturas: releases por pipeline, miembros del team,
  `organization.releasesEnabled`.
- `onboard`: prompts en TTY y flags equivalentes; crea los pipelines por
  entorno y persiste sus IDs en `speckit-linear.yml`.
- `doctor`: chequea plan, integración GitHub y pipelines; `--fix` aplica los
  settings de GitHub que hoy solo chequea.
- README del paquete: sección Releases, requisito Business, "what push
  will never do" actualizado.

Documentos:

- `vision.md`: sección Releases, tercer tipo de Issue creado por el harness,
  excepción del ledger.
- `README.md`: flujo de release, tabla de rollout (Business, integración
  GitHub), trunk para work items.
- `plan.md`: ronda 005.

## No se hace

GitHub Action de Linear (su access key no es legible por API; innecesaria),
tags y GitHub Releases (ledger duplicado), Slack o adaptadores de canal,
bots de CI con LLM, Project por release o Project "Releases" perpetuo,
Project Update, checklist en la descripción, estados `Staging` o `Merged`,
squash.

## Verificación previa a la spec

Requiere Business activo en Wortise (hoy `releasesEnabled: false`):

1. `releaseSync` por curl con la API key y un PR con `Fixes DRO-###`: el
   release debe listar ese Issue.
2. `issueCreate` con `subscriberIds`: los suscriptos deben recibir el aviso
   en su Inbox.
