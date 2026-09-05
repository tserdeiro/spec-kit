# Registro de dogfooding

Registro vivo de las fricciones del flujo de este repositorio, encontradas
usándolo sobre sí mismo. Cada problemática va seguida de su solución
pactada y de su estado: **resuelta** (entregada y publicada), **entregada**
(en el stack de la 004, pendiente de publicación; pasa a **resuelta**
cuando se publica), **ronda 004** (acordada, pendiente de implementar),
**regla** (sin código: se documenta en el loop o el README),
**documentada** (una regla ya enunciada en el loop o el README, con la
tarea que la escribió), **aceptada** (se convive con ella) o **upstream**
(vive en assets de upstream;
candidata a PR allá). Los commits de este archivo van separados de los
commits de fase.

Fuente de los hallazgos: la primera corrida real en un consumidor
(app-maker, 2026-08-31), la entrega de `003-delivery-automation` y su ronda
de corrección (2026-09-01 → 09-02).

## A. Stack de PRs

1. **El tooling instalado por una tarea desaparece en las ramas hermanas.**
   T001 instaló las extensiones dentro de la feature; toda rama que partió
   de la feature branch no las tenía, y el loop perdió su reconcile y su
   review. El modelo de dependencias ve código, no herramientas.
   *Resuelta (004, T001/#65; publicada 2026-09-05):* el loop no exige extensiones —
   detecta al iniciar qué tooling hay en la feature branch y usa ese
   conjunto en todas las tareas: sin `linear`, el reconcile se omite en
   silencio; sin `code-review`, un sub-agente fresco revisa el diff y deja
   los findings en el PR. Instalar o quitar extensiones es un chore en el
   trunk, nunca una tarea de feature.
2. **Un fix aguas arriba no llega a los PRs ya ramificados encima.** El fix
   POSIX de T017 dejó #62 en rojo hasta propagarlo a mano.
   *Resuelta (004, T003/#67; publicada 2026-09-05):* paso explícito en el loop — tras un fix
   en una rama con PRs encima, `git merge --no-ff -m "merge(task): …"` en
   cada rama de abajo, en orden, y push.
3. **Los ledgers divergen entre stacks paralelos.** Dos stacks checkearon
   tareas distintas; ningún branch tuvo el `tasks.md` completo hasta la
   integración humana. La preparación del release arrancó desde uno solo.
   *Resuelta (004, T002/#66; publicada 2026-09-05):* no hay stacks paralelos — el loop no
   arranca una tarea si hay otra ready sin mergear con distinta base.
4. **Integrar un stack relanza toda la CI en serie.** Colapsar de la hoja
   hacia abajo empuja commits al head de PRs abiertos (`synchronize`) y
   relanza todos los checks en cada paso.
   *Documentada (004, T005/#69; T012):* los stacks se mergean **raíz-primero**; el retarget
   de GitHub es un evento `edited`, que no dispara workflows. Se documenta
   en el paso de cierre del loop y en el README.
5. **La config de Linear no existe en worktrees y un worktree viejo bloquea
   el borrado de ramas.** `speckit-linear.yml` y `.speckit-linear.env` son
   locales al checkout principal; `gh pr merge --delete-branch` falló por un
   worktree en `/private/tmp`.
   *Resuelta (004, T009/#73 + T005/#69; publicada 2026-09-05):* resolver config y env
   desde `git rev-parse --git-common-dir` cuando no existen en el worktree;
   el cierre de feature corre `git worktree prune` antes de borrar ramas.
6. **Una rama con identidad de tarea equivocada (#54).** Se reusó una rama de
   T011 para T015; la validación chequea sintaxis, no que `T###` sea la
   tarea seleccionada.
   *Resuelta (004, T004/#68; publicada 2026-09-05):* `speckit.pr` compara el `T###` de la rama
   con la primera tarea sin checkear del ledger y para si no coincide.

## B. Proceso del agente

7. **Los desvíos de presupuesto se absorbieron en vez de frenar.** T011
   llegó a 7× su forecast; T013 amplió su propio presupuesto de 400 a 700
   líneas dentro del PR que lo rompía; la review "formal" quedó en 615/400.
   *Resuelta (004, T006/#70; publicada 2026-09-05):* pasado 2× del forecast la tarea **para**
   y vuelve al humano con diagnóstico ("el diseño no cabe"); un presupuesto
   nunca se amplía en el PR que lo excede.
8. **Las reviews empujaron complejidad en vez de cuestionarla.** Pidieron
   edge cases de YAML hasta que un resolver Python de 190 líneas con
   re-exec en el intérprete de Specify reemplazó tres líneas de shell.
   *Resuelta (004, T007/#71 + T001/#65; publicada 2026-09-05):* los principios de
   ingeniería viven donde los lee el review, que es el mismo para cualquier
   agente: `.opencodereview/rule.json` (sobre-ingeniería y abstracción
   especulativa = `major`; dependencia de runtime nueva = `blocking`); el
   preset shippea ese archivo base y `doctor --fix` lo escribe. Para los
   implementadores, una sola fuente: `AGENTS.md`, que `CLAUDE.md` importa.
   El brief del revisor fresco pregunta "¿hace falta el mecanismo?" antes
   de pedir un edge case.
9. **La implementación editó el contrato de producto.** T011 agregó C-006
   (un requisito de PyYAML) a `spec.md` para justificar su diseño.
   *Resuelta (004, T008/#72; publicada 2026-09-05):*
   `protected_paths` en `speckit-code-review.yml` (por defecto
   `specs/*/spec.md` y `.specify/memory/constitution.md`); si un PR de
   tarea (base `NNN-slug`) los toca, el comando emite un finding
   `blocking` automático y el veredicto es `changes-requested`. El feature
   PR (base = trunk) queda libre: ahí el spec cambia legítimamente.
10. **Se saltó el gate humano en dieciséis PRs.** El agente mergeó
    #44–#58 con la cuenta del maintainer y cero reviews; la revisión llegó
    después, sobre la feature branch.
    *Documentada (004, T005/#69; T012):* el loop **nunca decide** mergear: deja el stack con
    cada PR ready y su review fresca cerrada; el humano revisa por la
    mañana y mergea raíz-primero — o se lo pide al agente en la
    conversación, que entonces ejecuta `gh pr merge --merge
    --delete-branch` (comando corregido en el punto 32). Un ruleset
    de GitHub que exija aprobación en ramas
    `NNN-*` se activa solo cuando haya un segundo revisor o una identidad
    bot para el agente: en un repo de una sola persona bloquearía al
    maintainer, porque GitHub no cuenta la aprobación del autor del PR.
11. **Los revisores se cuelgan o divagan con packets grandes.** Una review
    de un packet de ~120 KB se colgó 10 minutos; otra gastó 20 minutos
    repitiendo verificaciones del implementador.
    *Resuelta (004, T001/#65; publicada 2026-09-05):* brief estándar del revisor en el loop —
    "verificá afirmaciones, no repitas experimentos"; packet mayor a
    100 KB → revisión por archivo.
12. **La conformance falló por diseño antes del release.** T013 hizo que el
    `bundles.sh` por defecto rechazara el árbol bumpeado y dejara `main` en
    rojo hasta publicar.
    *Resuelta (T019/#62):* el modo por defecto valida los manifests locales;
    `--published` exige paridad con el catálogo y lo corre `publish.sh`.

## C. Release y conformance

13. **Un `git revert` plano no cumple el check de naming del repo.** El
    subject por defecto no es `type(scope): subject`; lo atrapó la review
    fresca de T016 como bloqueante.
    *Resuelta (004, T005/#69; publicada 2026-09-05):* el loop gana un camino de revert con
    subject autorado (`revert(scope): …`).
14. **La conformance corre los bloques documentados bajo `sh`.** El
    `set -eo pipefail` de T017 pasó en macOS (`sh` es bash en modo POSIX) y
    falló en Ubuntu (`dash`); solo CI lo vio.
    *Documentada (004, T012):* todo bloque ejecutable de los comandos
    del preset es POSIX — `set -e`, sin pipelines que necesiten
    `pipefail`; la conformance ya los ejecuta con `sh`. Enunciado en el README del preset.
15. **La conformance de bundles no valida los hashes históricos del lock.**
    *Resuelta (004, T010/#75; publicada 2026-09-05):* `bundles.sh --published` recomputa el
    digest de cada asset publicado contra `versions.lock.yml`.
16. **La preparación del release desde un solo stack, el catálogo público
    que podía desviarse y el hardening sobredimensionado (#58).**
    *Resuelta:* #58 revertido por T016; T019 rehizo la preparación mínima
    (bump generado, `case` de flags, guard de rama, rollback de `uv lock`,
    build desde el tag); el punto 3 evita los stacks paralelos.

## D. Instalación y entorno

17. **Los skills existen solo para la integración elegida en `init`.** Este
    repo se inicializó con `ai: codex`; una sesión de Claude no tiene
    `/speckit.*` y el flujo se siguió leyendo los `SKILL.md` a mano.
    *Resuelta (004, T011/#76; publicada 2026-09-05):* el README documenta cómo instalar
    un segundo agente (`specify integration install <otro>`). Al hacerlo
    aquí con Claude (2026-09-03) apareció el límite del espejo del doctor:
    upstream renderiza los comandos core por integración y aplica los
    appends del preset solo a la default, así que copiar carpetas enteras
    sobreescribiría el render propio de Claude (`/speckit-…`,
    `argument-hint`) con el de codex (`$speckit-…`). El paso 5 del doctor
    debe copiar enteros solo los skills de extensiones/preset y, en los
    core, concatenar los appends del preset al render de cada integración.
18. **El hook de rama sugiere la persistencia equivocada.** `before_specify`
    imprime `To persist: export SPECIFY_FEATURE=…` cuando lo real es
    `.specify/feature.json`, que el comando escribe igual.
    *Upstream:* vive en el hook de la extensión git.
19. **El installer deja ruido no commiteable.** `specify extension add`
    escribe `.specify/extensions/.cache/` sin entrada de gitignore y
    construye `.venv` en el payload; en app-maker además está trackeado
    `.specify/presets/.cache/`.
    *Resuelta (004, T011/#76; publicada 2026-09-05):* `speckit.doctor --fix` agrega las
    entradas al `.gitignore` del consumidor.
20. **Los tests por paquete colisionan desde la raíz.** `uv run --project
    <paquete> pytest` recolecta ambos árboles y choca en `tests.conftest`.
    *Resuelta (docs):* el README documenta `uv run pytest
    packages/<paquete>/tests`.
21. **El skill de `implement` todavía anuncia hooks opcionales.** T002 los
    silenció en las fases de producto; la superficie de `implement` sigue
    mostrando los bloques (FR-002 más amplio que lo entregado).
    *Resuelta (004, T001/#65; publicada 2026-09-05):* el mismo append de silencio en
    `implement-append.md`.

## E. Upstream (fuera del control de la distribución)

Viven en assets gestionados por upstream (C-001); la distribución solo
neutraliza el comportamiento y espera un upgrade revisado o un PR allá.

22. **Las plantillas de comandos ordenan *imprimir* bloques "Optional Hook"**
    en vez de resolver los hooks de forma determinista. *Neutralizado* en
    fases de producto (T002); pendiente en `implement` (punto 21).
23. **La resolución de hooks es YAML interpretado por el LLM**, ~50 líneas
    repetidas dos veces en cada comando: costo de contexto y ejecución
    inconsistente. *Candidato a PR upstream.*
24. **`auto-commit.sh` hace `git add .`** y arrastra archivos ajenos.
    *Neutralizado:* los commits de fase están acotados a `specs/<feature>/`.
25. **La plantilla de config deshabilita `auto_commit` mientras el registro
    habilita los hooks que lo invocan:** el comando anunciado es un no-op.
    *Neutralizado* por el mismo cambio de T002.

## F. Resueltas en `003-delivery-automation`

- Linear estancado y gates manuales → el loop reconcilia al iniciar y en
  cada transición; `implement` verifica o abre el feature PR (T003, T005).
- Review con estado cruzado entre sesiones → review en contexto fresco;
  findings ligados a su sesión exacta, sin pisar el input (T004, T010,
  T018).
- Setup opaco → repositorio sin vincular nombra `onboard` antes de tocar la
  red; `doctor` verifica los settings de GitHub; cobertura de la
  automatización nativa documentada — la integración GitHub del workspace
  era la pieza que faltaba (T006, T007, T008).
- Tasks generadas que rompían el parser → los bloques de código se ignoran
  (T009).
- Rama vs feature independientes y plantilla con la default branch →
  `trunk:` resuelve la base de entrega en tres líneas de shell (T011/T015,
  reemplazado por T017).
- Proyección ausente en el repo fuente → este repo es su propio consumidor
  (T001), actualizado a lo que publica (T014).

## G. Hallazgos de la ronda 004

26. **El hook `after_plan` de Linear no puede crear el Project.** `push
    --current --hook` exige `tasks.md` (`artifact_missing`) y en `plan`
    todavía no existe: el hook registrado "Project at plan" falla en toda
    feature nueva y el Project nace recién en `after_tasks` (visto al
    planificar la 004, 2026-09-03).
    *Resuelta (004, T015/#74; publicada 2026-09-05):* `push` trata `tasks.md` como
    opcional: con `spec.md` y `plan.md` proyecta el Project sin Issues y
    avisa que el ledger es el próximo artefacto; los Issues llegan con
    `after_tasks`. Sumada al alcance en el gate (2026-09-03).
27. **`gh stack` nativo (preview) frente al apilado del loop.** Al
    planificar la 004 se evaluó la extensión oficial `github/gh-stack`
    (gh ≥ 2.90, preview pública): automatiza `init/add/push/submit/view`,
    pero no propaga fixes sin rebase, no llena el body canónico ni abre
    drafts, y guarda el tracking en el checkout local. La topología del
    loop ya es la de los Stacked PRs de GitHub (base = rama del PR
    anterior; GitHub reapunta al mergear la base).
    *Decisión (aceptada, 2026-09-03):* el loop deriva la base de los PRs
    abiertos y propaga con merges (puntos 2 y 3); `gh stack` se revisa
    cuando salga de preview, con `speckit.pr` como punto de adopción.

28. **El plan asumió mal el orden de `publish.sh`.** D13 daba por hecho
    que `--published` corre después de publicar; corre antes del push
    (`publish.sh:275`), así que la verificación del zip daría 404 en cada
    bump.
    *Resuelta (004, T010/#75; publicada 2026-09-05):* un 404 se reporta como pendiente y el
    mantenedor re-corre `--published` tras publicar; los digests de git
    se verifican siempre.
29. **El espejo a mano repitió el bug de la entrada 17.** El script del
    orquestador copió enteros cinco skills core sin append (`checklist`,
    `clarify`, `constitution`, `converge`, `taskstoissues`) entre
    integraciones en la primera regeneración; lo atrapó el diff antes del
    commit.
    *Resuelta (004, T011/#76; publicada 2026-09-05):* core = lo que lista el manifest de la
    integración; el doctor lo hace con un bloque ejecutable.
30. **La regla 2× se disparó dos veces en su propia ronda, por caminos
    distintos.** En T009 el bloque `budget-stop` corrió y frenó la tarea
    en 231/180, devolviéndola al humano; en T011 el implementador midió
    213/180 y paró antes del PR bajo la misma regla, y el orquestador
    aplicó el precedente de T009 —consolidar— antes de que el bloque
    llegara a correr.
    *Decisión (2026-09-04):* las dos entran tras consolidar scaffolding
    de tests duplicado (fixtures de worktree; un fixture entero para un
    caso), nunca ampliando el presupuesto — el forecast de tareas con
    fixtures de git suele quedarse corto; se estima con helper compartido
    desde el inicio.
31. **El preset instalado se etiquetaba 0.7.0 con contenido 0.8.0.**
    `specify preset resolve` leía el registro viejo hasta `preset remove
    default && preset add --dev presets/default`.
    *Regla:* regenerar tras cada edición del preset (el loop lo hace en
    cada tarea de preset).
32. **`--delete-branch` cierra el PR apilado antes del reapunte.** Al
    mergear la 004 a pedido, `gh pr merge 65 --merge --delete-branch`
    borró la rama antes de que GitHub reapuntara #66 y GitHub lo
    cerró; un PR cerrado no admite cambio de base, así que #66 quedó
    cerrado sin mergear y sus commits entraron por #67.
    *Entregada (chore #81):* el camino a pedido fija la base por
    API antes de cada merge y mergea sin `--delete-branch`; el
    auto-borrado del repo limpia.
33. **Una sesión de review abierta por una versión de la extensión no
    se cierra con otra.** Al revisar el PR del upgrade de este repo
    (#80), la sesión se abrió con code-review 0.4.0 (instalada en esa
    rama) y el cierre desde otra rama, con 0.3.0 instalada, falló con
    `config_sha256_mismatch`: la configuración congelada incluye los
    defaults del paquete, y 0.4.0 suma `protected_paths`. Es la
    guardia funcionando, no un bug.
    *Regla:* abrir y cerrar cada sesión con la misma versión
    instalada — en un chore de upgrade, cerrar desde la rama del
    chore o con el CLI del paquete a esa versión.
