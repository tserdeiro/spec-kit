# tserdeiro/spec-kit

Un harness de desarrollo ultra-liviano para trabajar con agentes de código
(Claude Code, Codex, etc.): cubre el ciclo completo de una necesidad de
negocio a un PR revisado y mergeado, con [Linear](https://linear.app)
siempre al día **sin que nadie lo actualice a mano**. Construido sobre
[GitHub Spec Kit](https://github.com/github/spec-kit), sin fork: solo
composición.

## Tabla de contenidos

- [🤔 ¿Qué es esto?](#-qué-es-esto)
- [⚡ Primeros pasos](#-primeros-pasos)
- [👥 ¿Qué rol soy?](#-qué-rol-soy)
- [📆 El día a día: features](#-el-día-a-día-features)
- [🐛 Bugs y chores](#-bugs-y-chores)
- [🧰 Comandos](#-comandos)
- [🧬 ¿Cómo funciona por dentro?](#-cómo-funciona-por-dentro)
- [🏢 Rollout en tu equipo](#-rollout-en-tu-equipo)
- [🔄 Actualizar](#-actualizar)
- [❓ Problemas frecuentes](#-problemas-frecuentes)
- [🔐 Integridad](#-integridad)
- [🗺️ Mapa del repositorio](#%EF%B8%8F-mapa-del-repositorio)
- [🛠️ Desarrollo](#%EF%B8%8F-desarrollo)

## 🤔 ¿Qué es esto?

**Spec-Driven Development (SDD)**: antes de escribir código se escriben
artefactos durables en el repo — spec, plan y tareas — y el agente trabaja
a partir de ellos. La verdad vive en archivos versionados, nunca en la
memoria de un chat.

Esta distribución le suma a Spec Kit tres cosas:

1. **Linear como espejo automático**: Projects, Issues y estados se
   *derivan* de lo observable (checkboxes, branches, PRs). Tú nunca
   mueves una tarjeta.
2. **Un comando de revisión** (`/speckit.code-review`) para la
   auto-revisión y la revisión final. Nunca aprueba ni mergea: eso es
   siempre humano.
3. **Instalación por rol en un paso.**

Tres términos que verás seguido: una **extensión** agrega comandos (p. ej.
la de Linear), un **preset** personaliza los templates de spec/plan/tareas,
y un **bundle** instala el preset y las extensiones de tu rol, todo junto
y en versiones exactas.

## ⚡ Primeros pasos

Cinco pasos y tu repo queda conectado a tu agente, a Linear y al motor de
revisión. Prerrequisitos: `git`, [`uv`](https://docs.astral.sh/uv/), `gh`
([GitHub CLI](https://cli.github.com/), autenticado con `gh auth login`) y
`node`/`npm` (los usa el motor de revisión). Para el paso 4, una API key
de Linear (Linear → Settings → API → Personal API keys).

### 1. Instala el CLI de Spec Kit (versión exacta)

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.0.1
uv tool update-shell
```

Reinicia la terminal; `specify version` debe decir `1.0.1`.

### 2. Inicializa tu repositorio

Dentro del repo donde vas a trabajar:

```bash
specify init --here --integration <agente>
```

`<agente>` es tu agente de código — `claude`, `codex`, `copilot`, `zed`, …
([lista completa](https://github.github.io/spec-kit/reference/integrations.html)).
Cualquiera soportado sirve igual de bien.

### 3. Instala el bundle de tu rol

Registra los catálogos de esta distribución (una vez por repositorio) e
instala tu rol — si no sabes cuál eres: [¿Qué rol soy?](#-qué-rol-soy):

```bash
specify extension catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/extensions.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify preset catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/presets.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify bundle catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/bundles.json --id tserdeiro-spec-kit --priority 1
specify bundle install developer   # o: product | reviewer
```

### 4. Conecta Linear

`onboard` resuelve y **crea** solo todo lo vinculable — el label del
repositorio, sus dos vistas compartidas y el mapeo PR→estado del equipo —
y escribe `speckit-linear.yml` (se commitea: sin secretos). Tu API key
vive en `.speckit-linear.env`, gitignoreado — al pasarla inline, `onboard`
la persiste ahí solo; si aún no diste ninguna, `doctor --fix` crea el
template para pegarla. Desde tu agente,
`/speckit.linear.onboard`, o:

```bash
LINEAR_API_KEY=... bash .specify/extensions/linear/scripts/bash/run.sh onboard --team-key <EQUIPO> --repository <slug>
```

El equipo necesita los estados `In Progress` e `In Review`; si falta uno,
todo funciona igual pero ese paso no se refleja (verás un aviso).

### 5. Prepara el motor de revisión

`doctor --fix` crea la configuración e instala el motor verificando su
firma. Desde tu agente, `/speckit.code-review.doctor`, o:

```bash
bash .specify/extensions/code-review/scripts/bash/run.sh doctor --fix
```

Listo. Ante cualquier falla futura, los dos `doctor --fix` (Linear y
review) son el primer auxilio.

## 👥 ¿Qué rol soy?

| Bundle | Eres tú si... | Instala |
| --- | --- | --- |
| `product` | Conviertes necesidades de negocio en specs, planes y tareas | preset + `git` + `linear` |
| `developer` | Implementas tareas, abres PRs y corriges bugs | preset + `git` + `bug` + `linear` + `code-review` |
| `reviewer` | Haces la revisión final antes de aprobar | preset + `code-review` |

Los bundles conviven y quitar uno nunca rompe lo que otro necesita. Para
cambiar de rol:

```bash
specify bundle remove developer && specify bundle install reviewer
```

`specify bundle list` muestra lo instalado
([referencia completa](https://github.github.io/spec-kit/reference/bundles.html)).

## 📆 El día a día: features

Los comandos `/speckit.*` se escriben en el chat de tu agente. El flujo,
con el estado que Linear refleja solo:

| Paso | Qué haces | Linear |
| --- | --- | --- |
| 1. Especificar | `/speckit.specify` — nace el **branch de feature** `NNN-slug` | — |
| 2. Planificar | `/speckit.plan` | se crea el Project |
| 3. Tareas | `/speckit.tasks`, y `/speckit.pr` sobre el branch de feature abre su **draft PR** (`NNN-slug` → branch de entrega): el gate donde el equipo aprueba spec y plan | se crean los Issues (*Todo*) |
| 4. Implementar | `/speckit.implement` — toma la primera tarea sin marcar y crea su branch `NNN-T###-slug` (ej. `002-T004-parser-fix`) **desde el branch de feature** | *In Progress* |
| 5. Pull request | `/speckit.pr` — abre el PR **draft** de la tarea, **hacia el branch de feature**, con el body canónico | *In Progress* |
| 6. Auto-revisión | `/speckit.code-review`, corriges, `[x]` + evidencia en el último commit, y marcas `ready for review` | *In Review* |
| 7. Revisión final | el revisor: `/speckit.code-review --publish` más su revisión humana; una persona mergea al branch de feature | *Done* |
| 8. Cierre | todas `[x]` → marcas el PR de feature `ready` → revisión de la película completa → una persona mergea al branch de entrega con **merge commit** (el branch se borra); `/speckit.linear.push --apply` reconcilia | — |

Los pasos 4–6 los orquesta `/speckit.implement` solo, tarea por tarea;
cada comando también puede correrse suelto.

Reglas de oro:

- **Una tarea en vuelo por dev, nunca en paralelo**: se entregan de a
  una, en orden de dependencias (las listas no llevan marcadores `[P]`).
  `ready for review` te libera para la siguiente; si esa depende de una
  tarea sin mergear, su branch se apila sobre el de la anterior (línea
  `Stack:`) — no esperes el merge: al llegar, GitHub reapunta el PR
  apilado al branch de feature solo.
- **El checkbox viaja dentro del PR de la tarea**: tras la auto-revisión,
  el último commit del PR marca `[x]` y llena la **Completion evidence**
  (PR, verificación). Llega al branch de feature únicamente vía el merge
  humano — ahí `[x]` = mergeado, por construcción — y nadie vuelve a
  tocar tareas pasadas; comentarios del reviewer se corrigen en el mismo
  PR. En la proyección a Linear un PR abierto pesa más que el checkbox:
  una tarea en review nunca aparece como *Done*.
- **El branch de feature (`NNN-slug`) es la integración**: los branches
  de tarea salen de él actualizado y sus PRs vuelven a él; la feature
  entra al branch de entrega **una sola vez**, con merge commit — nada a
  medias llega antes. Bugs y chores siguen yendo al default de GitHub.
  Por defecto los comandos usan el default de GitHub; si el trunk real es
  otro, configura `trunk: <branch>` en
  `.specify/extensions/git/git-config.yml`. Debe cargar como string YAML y
  ser un nombre de branch válido para Git; nombres que parecen números o
  fechas deben ir entre comillas. Ese valor explícito tiene prioridad para el
  PR de feature y `/speckit.implement` (este repo declara `trunk: main`).
- **Nunca actualices Linear a mano**: el Project y los Issues nacen solos
  en plan/tareas, los estados los mueve la integración nativa por eventos
  de PR, y `push --apply` es la reconciliación idempotente que repara lo
  que falte. Si no cambió nada, no escribe nada.
- **PRs chicos**: máximo ~400 líneas ejecutables escritas por ti; una
  tarea mayor se parte en
  [Stacked PRs](https://docs.github.com/en/pull-requests/get-started/stacked-prs-quickstart)
  (cada uno nombra al anterior en su línea `Stack:`). El comando de
  revisión avisa si te pasas.
- **El body del PR usa el template canónico**
  [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md);
  `/speckit.pr` lo llena solo desde los artefactos.
- La revisión **nunca aprueba ni mergea** — siempre humano. Exit 1
  significa "hay hallazgos que corregir", no que algo falló.
- **El stack se deriva, no se inventa**: mandan la tarea y la sección
  `## Documentation` del plan; si no, el agente lee los manifests reales
  y el código vecino y reutiliza lo instalado. Una dependencia nueva o
  reimplementar lo que una lib cubre es **decisión humana**, y una API
  desconocida se verifica contra su doc oficial antes de usarse.
  Declara el principio en tu constitución (`/speckit.constitution`);
  tip opcional: el MCP de [Context7](https://context7.com) sirve docs
  actualizadas por versión.

**Linear en tiempo real** (opcional, recomendado): un admin conecta GitHub
en Linear (Settings → Integrations → GitHub), **una vez por workspace**;
con acceso "All repositories" los repos nuevos no piden nada. El mapeo por
equipo (draft → *In Progress*, ready → *In Review*, merged → *Done*) **lo
deja `onboard`** al vincular el repo: crea los que faltan, jamás pisa uno
elegido distinto. Los PRs de tarea llevan `Fixes WOR-###` y los branches
de bugs/chores ya usan el formato que Linear vincula, así que las tarjetas
se mueven solas; `push` sigue siendo la reconciliación que manda — sin la
integración, todo funciona igual con `push`.

**Asignación**: nativa de Linear — el harness nunca asigna a nadie, y la
columna `ASSIGNEE` del `status` refleja la verdad. O la UI de Linear, o el
MCP oficial desde tu agente (setup una vez por dev, auditado como vos):

```bash
claude mcp add --transport http linear-server https://mcp.linear.app/mcp
```

(Codex: `codex mcp add linear --url https://mcp.linear.app/mcp`.) Con eso
le pides *"asigna el plan 003 a Facu"* o *"este bug al dev con menos
tareas activas"* — consulta la carga real y asigna con tu ok. Regla fija:
**una tarea = un assignee** (el semáforo contra pisadas), y un `push`
jamás revierte una reasignación.

## 🐛 Bugs y chores

El camino corto — sin spec ni plan:

1. Nace como **Issue en Linear** (lo crea una persona), p. ej. `WOR-123`.
2. `/speckit.bugfix WOR-123` (bugs) o `/speckit.chore WOR-123` (chores)
   crea el branch (`wor-123-slug-corto`) desde la default al día y
   proyecta *In Progress*. Igual de válido: el botón **Copy git branch
   name** de la tarjeta (`usuario/wor-123-slug` — según tu config, al
   copiarlo Linear te asigna y arranca la tarjeta). Estados como en
   features: branch o PR draft → *In Progress*, ready → *In Review*,
   merge → *Done*.
3. `bugfix` sigue con el trío `/speckit.bug.assess` (pégale el reporte o
   la URL) → `/speckit.bug.fix` → `/speckit.bug.test`; los tres reportes
   quedan en `.specify/bugs/<slug>/` y viajan en el PR como evidencia.
   `chore` salta el trío: cambio directo.
4. PR draft → auto-revisión → `ready for review` → revisión final →
   merge humano.

## 🧰 Comandos

Nativos de Spec Kit: `/speckit.constitution`, `.specify`, `.clarify`,
`.plan`, `.checklist`, `.tasks`, `.analyze`, `.implement`, `.converge`, y
el trío `/speckit.bug.*`.

| Origen | Comandos |
| --- | --- |
| preset `default` | `/speckit.pr`, `.bugfix`, `.chore`, `.doctor` — más el workflow que inyecta dentro de `.tasks` y `.implement` |
| extensión `linear` | `onboard`, `push` (`--dry-run` / `--apply`), `status`, `doctor --fix`, `completions` |
| extensión `code-review` | `speckit.code-review` (`--publish`), `doctor --fix`, `completions` |

No hay más superficie que esta: cada comando expone solo lo que su paso
necesita (y hay tests que lo fijan).

## 🧬 ¿Cómo funciona por dentro?

Si el paso 1 instala el CLI de `github/spec-kit`, ¿de dónde salen los
comandos de esta distribución? **El CLI de upstream es la maquinaria, no
el contenido**: trae los comandos core, las integraciones de agentes y un
instalador con catálogos. Esta distribución publica el contenido donde esa
maquinaria sabe consumirlo:

- Los [catálogos](catalog/) son nuestro "registry": tres JSON estáticos
  servidos desde este repo que mapean `id + versión → URL de descarga`.
  El paso 3 los registra en tu repo (`.specify/*-catalogs.yml`).
- Las URLs apuntan a nuestras **GitHub Releases**: ZIPs construidos
  reproduciblemente y pinneados por versión y digest.

Qué pasa exactamente en `specify bundle install developer`:

```text
specify bundle install developer
  │
  ├─ busca "developer" en el stack de catálogos (el nuestro, prioridad 1)
  ├─ descarga developer-<versión>.zip de nuestras releases
  ├─ lee su bundle.yml: los componentes con versiones exactas
  │
  ├─ git, bug ........ vienen DENTRO del CLI de upstream (no descargan nada)
  ├─ linear .......... se resuelve en nuestro catálogo de extensiones
  │                    → ZIP de la release → .specify/extensions/linear/
  ├─ code-review ..... ídem → .specify/extensions/code-review/
  └─ preset default .. se resuelve en nuestro catálogo de presets
                       → templates a .specify/presets/ y registra los
                         comandos (/speckit.pr, /speckit.bugfix,
                         /speckit.chore, /speckit.doctor y los appends
                         de tasks/implement) como skills de TU agente
```

**Después de instalar, todo es local**: comandos, templates y extensiones
viven en tu repo; los catálogos solo se consultan al instalar o
actualizar. Este repositorio nunca participa en tu runtime.

## 🏢 Rollout en tu equipo

**Instalar es un evento por-repositorio, no por-dev**: todo lo del paso 3
queda en el repo y se commitea; quien clona recibe el producto instalado.

| Una vez por repositorio (se commitea) | Cada dev, en su máquina |
| --- | --- |
| `specify init` + los 3 `catalog add` | `gh auth login` |
| `specify bundle install developer` | su `.speckit-linear.env` con **su** API key (el template lo crea `doctor --fix`) |
| `onboard` (el binding de Linear, sin secretos) | `doctor --fix` una vez (instala el motor de revisión localmente) |

- **Con `developer` alcanza para todos**: es el superconjunto de
  `product` y `reviewer`; los roles definen qué comandos *usa* cada
  quien, no qué instala.
- **Agentes distintos conviven**: upstream registra los comandos de
  extensiones y preset solo en la integración **default** — y
  `/speckit.doctor --fix` espeja esos skills al resto de los agentes
  instalados, para que ninguno sea de segunda clase. Sumar un agente:
  `specify integration install <agente> --force`, `/speckit.doctor
  --fix`, y se commitea. Tras un `bundle update` o un `integration
  switch`, el mismo doctor re-espeja.

**¿Quién está en qué?** El sistema no lo sabe — lo *deriva* de lo
observable:

| Pregunta | De dónde sale la respuesta |
| --- | --- |
| ¿En qué tarea estaba mi dev? | El branch en el que está parado (`002-T003-slug` codifica feature y tarea) + `tasks.md` + `/speckit.linear.status --all` |
| ¿A qué tarea le hago review? | A un PR explícito, siempre — nunca a "lo que alguien estaba haciendo" |
| ¿Cómo no se pisan dos devs? | Cada tarea vive en su branch; cualquier `push` ve todos los branches y PRs y reconcilia idempotente |
| ¿Quién tiene asignado qué? | Linear (producto asigna); la columna `ASSIGNEE` del status |

- **`push` reconcilia su alcance**: tu feature seleccionada más todos los
  bugs/chores; las tareas de otro plan las deriva un push que las incluya
  (`--all`). Repetir sin cambios da "0 operaciones".
- **`implement` no elige entre planes**: opera sobre la feature que
  nombres (`/speckit.implement 003`) o la activa
  (`.specify/feature.json`), y toma su primera tarea sin marcar; ese
  cambio de feature activa nunca viaja en commits de tarea. Qué plan
  trabaja cada quien es la asignación en Linear, y el primer movimiento
  tras un pull es `/speckit.linear.status --all`.

**Settings de GitHub que enforcean las reglas** (una vez por repo):

```bash
gh api -X PATCH repos/<owner>/<repo> -f delete_branch_on_merge=true -F allow_squash_merge=false -F allow_rebase_merge=false
```

- **Solo merge commits**: la historia por tarea sobrevive; squash y
  rebase ni aparecen en el botón.
- **Auto-borrado de branches al mergear**: la limpieza remota es de
  GitHub, no tuya.
- **Protege la default branch** contra force-push y borrado:

```bash
gh api -X POST repos/<owner>/<repo>/rulesets --input - <<'EOF'
{"name":"protect-default-branch","target":"branch","enforcement":"active",
 "conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},
 "rules":[{"type":"deletion"},{"type":"non_fast_forward"}]}
EOF
```

  En repos consumidores suma `{"type":"pull_request"}` a `rules` para
  exigir PR hacia la default (recomendado; este repo fuente no lo usa
  porque su flujo de release commitea pins directo).

Dos fricciones conocidas, con su mitigación:

1. **`.specify/feature.json` es estado local por checkout** (el CLI lo
   gitignora desde v1.0.1): cada dev tiene su propia feature activa y el
   archivo ya no se disputa. Nombrar la feature en el comando
   (`/speckit.implement 003`) sigue siendo lo más explícito; manda el
   branch.
2. **Una tarea = un assignee**: dos devs en la misma tarea colisionarían
   en el branch; la asignación en Linear es el semáforo.

## 🔄 Actualizar

Nada se actualiza solo; las versiones son siempre explícitas.

**Releases de esta distribución** (bundles, extensiones, preset):

```bash
specify bundle update --all
```

**El CLI de upstream** (solo cuando esta distribución mueva su pin — hoy
`v1.0.1`): actualiza la herramienta, refresca los assets base del repo
(la constitución autorada se preserva) y re-aplica los bundles:

```bash
uv tool install specify-cli --force --from git+https://github.com/github/spec-kit.git@v1.0.1
specify init --here --force --integration <agente>
specify bundle update --all
```

(La primera vez tras subir a v1.0.1, destrackea el puntero local que el
CLI ahora gitignora: `git rm --cached .specify/feature.json`.)

Tras cualquier actualización, re-corre los dos `doctor --fix`.

## ❓ Problemas frecuentes

- **"is from a discovery-only catalog"** al instalar → al registrar los
  catálogos faltó `--install-allowed` (paso 3). Quita el catálogo y
  vuelve a agregarlo con la flag.
- **El motor de revisión no aparece** → `doctor --fix` de code-review lo
  instala y verifica; necesita `npm` disponible.
- **Un paso no se refleja en Linear** → corre `status` para ver el estado
  derivado y su fuente; revisa que el branch siga la convención
  (`NNN-T###-slug`, `wor-123-slug`, o el formato del botón de Linear
  `usuario/wor-123-slug`) y que `gh auth status` esté OK (sin `gh`, los
  estados que dependen de PRs no se calculan y lo verás avisado).
- **"pinned to X but the resolved version is Y" en un `bundle update`
  recién publicada una release** → los tres catálogos viajan por el CDN
  de raw.githubusercontent y pueden desfasarse unos minutos entre sí; el
  chequeo de pins aborta sin dejar nada a medias. Reintenta en ~5 min;
  si persiste, limpia el caché local
  (`rm -rf .specify/presets/.cache .specify/extensions/.cache`) y
  reintenta.
- **"was observed … but no such Issue exists" con un issue recién creado**
  → el índice de búsqueda de Linear tarda ~1–2 min en ver issues nuevos;
  el aviso no falla nada — reintenta el `push` y lo proyecta.
- **Falta `In Review` en el equipo** → créalo en Linear (Settings → Teams
  → Workflow, tipo *started*) y re-corre `onboard`.
- Ante la duda: `doctor --fix` de cada extensión; sus mensajes traen la
  remediación exacta.

## 🔐 Integridad

[`versions.lock.yml`](versions.lock.yml) pinnea el upstream y cada
extensión por tag, commit y digest — incluidos los digests por plataforma
del motor de revisión, que viajan dentro de la propia extensión para que
cualquier consumidor verifique lo que `doctor --fix` instala. Las releases
se construyen reproduciblemente desde tags por paquete
([`scripts/release/`](scripts/release/)), y cada etapa se aceptó contra
los artefactos publicados, con la evidencia en
[`validation/`](validation/). El pin de upstream se reproduce desde un
clon independiente:

```bash
git clone --branch v1.0.1 --depth 1 \
  https://github.com/github/spec-kit.git /tmp/spec-kit-v1.0.1
git -C /tmp/spec-kit-v1.0.1 rev-parse 'v1.0.1^{commit}'
git -C /tmp/spec-kit-v1.0.1 rev-parse 'v1.0.1^{tree}'
git -C /tmp/spec-kit-v1.0.1 archive --format=tar v1.0.1 | shasum -a 256
```

## 🗺️ Mapa del repositorio

| Ruta | Qué es |
| --- | --- |
| [`docs/vision.md`](docs/vision.md) | La visión de producto — la autoridad |
| [`docs/plan.md`](docs/plan.md) | El plan de entrega derivado de ella |
| [`packages/`](packages/) | Las extensiones `linear` y `code-review` (cero dependencias de runtime) |
| [`presets/default/`](presets/default/) | El preset con los templates del workflow |
| [`bundles/`](bundles/) | Los tres bundles de rol |
| [`catalog/`](catalog/) | Los catálogos estáticos servidos desde `main` |
| [`validation/`](validation/) | La evidencia de aceptación, etapa por etapa |
| [`specs/`](specs/) | Los artefactos de features de este propio repo |

Los repositorios consumidores son dueños de sus artefactos y su Git; nunca
dependen de este checkout en runtime.

## 🛠️ Desarrollo

Para trabajar en esta distribución (no hace falta para usarla):

```bash
uv sync
uv run pytest packages/spec-kit-linear/tests
uv run pytest packages/spec-kit-code-review/tests
```

La conformance por paquete vive en `packages/*/scripts/conformance/`; la
de los bundles en
[`scripts/conformance/bundles.sh`](scripts/conformance/bundles.sh). La CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) corre ambas
suites. Commits, releases y publicación son siempre decisiones humanas.
