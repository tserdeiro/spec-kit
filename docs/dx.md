# Experiencia de desarrollo: ronda propuesta

Propuesta del 2026-09-08, para revisión. Deriva de
[`vision.md`](vision.md) ("toda fricción se pule; lo automatizable se
automatiza") y de las fricciones de [`dogfooding.md`](dogfooding.md). Acordada
el mismo día: es la **ronda 005** y la spec se escribe a partir de este
documento; releases ([`releases.md`](releases.md)) pasa a la 006 mientras
espera el plan Business.

## Problema

La capa de política está completa: un stack, presupuestos, gates, estados
derivados. La de mecanismo no. Vive en prosa que el agente tiene que
recordar y en bloques de shell que tiene que copiar y editar. Las
secciones D y G del dogfooding y el bump a v1.0.4 (cuatro reparaciones a
mano: el preset dev-instalado, viejo, re-renderizó `speckit-doctor`;
`init --force` dejó huérfana a la segunda integración; su reinstalación
perdió los appends del preset; faltaba una entrada de ignore; entrada 35)
muestran una sola falla: el agente se olvidó, lo rompió o lo espejó a
mano.

- `speckit-implement` renderea ~32 KB; la mitad es core de upstream que
  el append después contradice ("este loop gana").
- Linear se reconcilia solo cuando el agente ejecuta `push --hook` en
  tres puntos del loop; nada más lo dispara.
- Las reglas duras (subjects `type(scope)`, `--delete-branch`, `spec.md`
  en rama de tarea, force-push) las atrapa la CI o la review, después
  del hecho.
- Seis bloques awk/sh de 22 a 110 líneas viajan dentro del prompt y el
  agente "reemplaza solo el literal"; un agente más débil los rompe.
- Un junior lee unas setecientas palabras de reglas de oro para aprender
  un flujo que, de a una tarea, son cuatro comandos.

## La palanca

Upstream 1.0.x trae **eventos de runtime**. Una extensión declara
`events:` (`session_start`, `pre_tool_use`, `post_tool_use`,
`session_end`, `user_prompt_submit`, `stop`), cada handler un `command`
con `matcher` y `timeout` opcionales. `specify integration install`
genera `.specify/events.py` y lo cablea al archivo de hooks nativo de
cada agente: `.claude/settings.json`, `.codex/config.toml`,
`.cursor/hooks.json`, Copilot, Gemini, Devin, OpenCode, Qwen, Tabnine,
Vibe. El script del handler recibe el payload nativo por stdin y su exit
code se propaga, así que un handler de `pre_tool_use` puede bloquear una
llamada a herramienta. Verificado en el código del CLI instalado; las
páginas de referencia todavía no lo documentan. El cableado por agente
lo hace el CLI, así que la distribución no shippea lógica por agente,
como exige la visión. Los eventos se recolectan solo de manifests de
extensiones, nunca de presets. Zed no soporta eventos: ahí la prosa
sigue siendo la regla y el doctor lo dice.

## Decisiones (propuestas)

- **Pin v1.0.4.** Entregado: `chore/upstream-1.0.4`, PR #85. Los
  eventos necesitan ≥ 1.0.2 (fix del stdin de `event run`); los
  manifests de las extensiones pasan a exigir ≥ 1.0.4.
- - **El mecanismo se reparte entre lo que ya existe; no hay extensión
  nueva.** Los presets pueden shippear scripts (`provides` acepta `type:
  script`, en `scripts/`) y el payload del preset se commitea en el
  consumidor, así que el preset `default` shippea como scripts POSIX lo
  que hoy es shell inline en sus comandos: `task-base`, `budget-stop`,
  `stack-propagate`, `pr-create`, el merge a pedido raíz-primero, el
  check del ledger (checkbox más evidencia de completitud) y los dos
  bloques del doctor, `skill-mirror` e `ignore-entries`, que con 110 y
  22 líneas son los más grandes de todos; cada paso de un comando es una
  línea que ejecuta uno. La conformance ejecuta scripts, no bloques
  extraídos de prosa. Los eventos solo pueden declararlos extensiones, y
  las dos existentes ya son dueñas de esas dos preocupaciones: `linear`
  declara los de reconciliación y contexto (llaman a `push` y `status`),
  `code-review` los de guardas (`protected_paths` y las reglas de
  review, aplicadas antes de la acción en vez de después). Los handlers
  son comandos internos de cada extensión, fuera de la superficie de
  usuario como ya lo es `--hook`, sin puntos y con el mismo nombre que
  su archivo `.md`: el dispatcher los resuelve por nombre de archivo y
  falla abierto si no coinciden (entrada 46). `linear` y `code-review`
  siguen siendo opcionales, como ya lo es el tooling set del loop: sin
  `linear` no hay contexto ni reconcile, sin `code-review` no hay
  guardas, y la prosa sigue siendo la regla.

- **Tres registros de eventos, cuatro reglas.**
  - `session_start` (`linear`): `push --hook` (no-op limpio sin config)
    y una línea de contexto: rama, feature, primera tarea sin marcar, PRs
    de tarea abiertos, próximo comando. Agente y dev arrancan cada
    sesión sabiendo qué sigue. Solo lectura fuera de eso.
  - `post_tool_use` (`linear`), matcher `Bash`: tras `git push` o
    `gh pr create|ready|merge`, `push --hook`. Las tres frases de
    "reconciliá ahora" salen del loop.
  - `pre_tool_use` (`code-review`), matcher `Bash|Edit|Write`: un solo
    handler, porque el esquema admite uno por evento y por extensión
    (entrada 45), con dos guardas dentro según `tool_name`. En `Bash`
    bloquea `git commit -m` cuyo subject no cumpla `type(scope): subject`
    (una sola regex compartida con `conventions.yml`), `git push
    --force*` y `gh pr merge --delete-branch`; en `Edit|Write` bloquea
    `protected_paths` en una rama `NNN-T###-*`, que hoy la review atrapa
    un ciclo más tarde. Cada bloqueo nombra el arreglo.
- **`implement` se reemplaza, no se appendea.** Los presets soportan
  `replace` para comandos; el loop pasa a ser un comando compacto en vez
  de 15 KB de core más 17 KB de overrides. Lo mismo para `tasks` si su
  append contradice el core.
- **`NEXT` nombra comandos.** `status` sugiere `/speckit.implement 004`,
  `/speckit.pr`, `/speckit.code-review 12` o "esperar el merge humano",
  nunca un gesto manual como "crear la rama".
- **`/speckit.doctor` conduce el onboarding.** Tras `bundle install`, un
  solo comando lista lo que falta, en orden (`gh auth`, API key,
  `onboard`, motor, settings de GitHub), y `--fix` aplica la parte
  mecánica; los pasos 4 y 5 del README se funden en uno. El wizard de
  `onboard` de `releases.md` lo completa.
- **`completions` se retira.** El subcomando imprime un script de
  autocompletado bash/zsh para el CLI de cada extensión; solo sirve si
  ese CLI estuviera en el PATH con nombre corto, y en la práctica se
  invoca por el launcher `run.sh`, nada lo instala y el README no lo
  menciona. Sale de las dos extensiones; los slash commands los
  autocompleta cada agente por sí mismo, que es lo que la visión quería
  decir.
- **Portada del README.** Primero "tu día en cuatro comandos"; las
  reglas de oro separadas en lo que hace el dev (tres bullets) y lo que
  el loop garantiza (colapsado).

## Cambios a aplicar

Preset `default`:

- `scripts/bash/`: `task-base.sh`, `budget-stop.sh`,
  `stack-propagate.sh`, `pr-create.sh`, `merge-root-first.sh`,
  `ledger-check.sh`, `skill-mirror.sh`, `ignore-entries.sh`, declarados
  como `type: script` en `preset.yml`; `task-base.sh` termina con
  `push --hook` si `linear` está instalada, así ningún comando conserva
  una frase de reconcile;
  `sh` POSIX como hoy (los bloques nunca tuvieron gemelo PowerShell).
  La conformance corre cada script contra fixtures (los casos de
  `bundles.sh` se mudan con ellos).
- `implement` (y `tasks` si hace falta) con `strategy: replace`.
- La prosa de `pr`, `chore`, `bugfix`, `doctor` e `implement` reducida a
  pasos que llaman scripts.

Extensión `linear`:

- `events:` con `session_start` y `post_tool_use`, sus dos handlers
  como comandos internos (`scripts:` en el frontmatter, como exige el
  dispatcher) que llaman a `push --hook` y a `status`.
- `next_action` devuelve comandos. `completions` sale.
- `requires.speckit_version` pasa a `>=1.0.4,<1.1.0`.

Extensión `code-review`:

- `events:` con un `pre_tool_use` (matcher `Bash|Edit|Write`) y las dos
  guardas dentro; la regex de subjects compartida con `conventions.yml`.
- Sale el hook `after_implement` (una review advisory del working tree a
  la que el loop nunca llega). `completions` sale.
- `requires.speckit_version` pasa a `>=1.0.4,<1.1.0`.

Documentos:

- `vision.md`: los eventos como capa de mecanismo; Zed se degrada
  explícitamente; "autocompletado" pasa a ser el de cada agente.
- `README.md`: portada, onboarding vía doctor, receta de actualización
  (entrada 35).
- `plan.md`: la ronda. `dogfooding.md`: las entradas pasan a *resuelta*
  a medida que aterrizan.

Bundles: sin cambios de composición; versiones vía `publish.sh --bump`.

Pull requests a upstream (convierten neutralizaciones en borrados):

1. Registrar los comandos de extensiones y presets en todas las
   integraciones instaladas, no solo en la default (causa raíz de las
   entradas 17, 29 y de todo el bloque `skill-mirror`), y conservar
   `installed_integrations` a través de `init --force` (entrada 35).
2. `auto-commit.sh` sin `git add .` (entrada 24).
3. No registrar los dieciséis hooks `git.commit` cuando
   `auto_commit.default` es `false` (entrada 25).

## No se hace

Una extensión nueva para el mecanismo (los scripts caben en el preset y
los eventos en las extensiones que ya son dueñas de cada preocupación);
archivos de hooks autorados por agente (los genera el CLI); un handler
de `stop` en cada turno (costo sin señal); guardas más allá de las
cuatro reglas duras; `specify workflow` para el loop (gates
interactivos, corre comandos y no scripts); `gh stack` (entrada 27); un
script de bootstrap para la instalación (descartado antes; el README
sigue siendo la portada).

## Secuencia

1. Pin v1.0.4. Hecho.
2. Los scripts al preset, todavía sin eventos: los comandos los llaman,
   la conformance se muda. La tarea más grande; va sola.
3. Eventos, un handler por tarea (dos en `linear`, uno en
   `code-review`), verificados en Claude y Codex en un consumidor
   temporal (nunca dev-instalando sobre este checkout) y en Cursor en
   app-maker tras publicar.
4. `implement` por replace, comandos en `NEXT`, onboarding del doctor,
   README.
5. Higiene: el hook `after_implement`, `completions`, los PRs a
   upstream.

Cada punto aterriza por el loop: una tarea, una rama, un PR, merge
humano.

## Verificación previa a la spec

1. Un handler declarado por `linear` en un consumidor temporal aparece
   en `.claude/settings.json` y `.codex/config.toml` tras
   `specify integration install <key> --force`, se dispara en
   `session_start`, y un exit 2 en `pre_tool_use` bloquea la llamada en
   ambos agentes.
2. Lo mismo en Cursor en app-maker, más la degradación explícita de Zed.
3. `bundle install developer` en un consumidor limpio cablea los eventos
   sin ningún paso manual.

## Preguntas abiertas

- `AGENTS.md` nombra al README, `vision.md` y `dogfooding.md` como únicas
  excepciones en español; este documento y `releases.md` también lo
  están: enmendar la lista.
