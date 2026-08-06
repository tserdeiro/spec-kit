# tserdeiro/spec-kit

Un harness de desarrollo ultra-liviano para trabajar con agentes de código
(Claude Code, Codex, etc.) que cubre el ciclo completo de entrega: de una
necesidad de negocio a un PR revisado y mergeado, con
[Linear](https://linear.app) siempre al día **sin que nadie lo actualice a
mano**. Está construido sobre [GitHub Spec Kit](https://github.com/github/spec-kit),
sin fork: solo composición.

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

**Spec-Driven Development (SDD)** significa que antes de escribir código se
escriben artefactos durables en el repo — especificación, plan y tareas — y
el agente de código trabaja a partir de ellos. La verdad vive en archivos
versionados, nunca en la memoria de un chat.

Esta distribución le suma a Spec Kit tres cosas:

1. **Linear como espejo automático.** Los Projects, Issues y estados se
   *derivan* de la realidad observable (checkboxes de tareas, branches,
   PRs). Tú nunca mueves una tarjeta: haces tu trabajo en git y GitHub, y
   la sincronización reconcilia Linear.
2. **Un comando de revisión de código** (`/speckit.code-review`) que usas
   antes de pedir revisión y que el revisor vuelve a usar al final.
   Nunca aprueba ni mergea: eso siempre lo hace una persona.
3. **Instalación por rol en un paso**, para que no tengas que saber nada de
   lo anterior para empezar.

Tres términos que verás seguido:

- **Extensión**: agrega comandos nuevos (p. ej. la de Linear).
- **Preset**: personaliza los templates de spec/plan/tareas.
- **Bundle**: un paquete instalable que trae el preset y las extensiones de
  tu rol, todo junto y en versiones exactas.

## ⚡ Primeros pasos

Al terminar estos 5 pasos tendrás tu repositorio conectado a tu agente, a
Linear y al motor de revisión. Necesitas tener instalados: `git`,
[`uv`](https://docs.astral.sh/uv/) (gestor de Python), `gh`
([GitHub CLI](https://cli.github.com/), autenticado con `gh auth login`) y
`node`/`npm` (los usa el motor de revisión). Para el paso 4 pide una API key
de Linear (Linear → Settings → API → Personal API keys).

### 1. Instala el CLI de Spec Kit (versión exacta)

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.13.0
uv tool update-shell
```

Reinicia la terminal y comprueba: `specify version` debe decir `0.13.0`.

### 2. Inicializa tu repositorio

Dentro del repo donde vas a trabajar, con el agente que uses (Claude Code,
Codex, etc. — cualquiera soportado sirve igual de bien):

```bash
specify init --here --integration <agente>
```

### 3. Instala el bundle de tu rol

Primero registra los catálogos de esta distribución (una sola vez por
repositorio), luego instala tu rol — si no sabes cuál eres, mira
[¿Qué rol soy?](#-qué-rol-soy):

```bash
specify extension catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/extensions.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify preset catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/presets.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify bundle catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/bundles.json --id tserdeiro-spec-kit --priority 1
specify bundle install developer   # o: product | reviewer
```

### 4. Conecta Linear

`onboard` resuelve todo solo y escribe `speckit-linear.yml` (se commitea:
no contiene secretos; tu API key vive en `.speckit-linear.env`, que queda
gitignoreado). Desde tu agente, `/speckit.linear.onboard`, o desde la
terminal:

```bash
LINEAR_API_KEY=... bash .specify/extensions/linear/scripts/bash/run.sh onboard --team-key <EQUIPO> --repository <slug>
```

El equipo de Linear debe tener los estados `In Progress` e `In Review`; si
falta alguno, todo funciona igual pero ese paso no se refleja (verás un
aviso).

### 5. Prepara el motor de revisión

`doctor --fix` crea la configuración e instala el motor de revisión
verificando su firma. Desde tu agente, `/speckit.code-review.doctor`, o:

```bash
bash .specify/extensions/code-review/scripts/bash/run.sh doctor --fix
```

Listo. Si algo falla más adelante, los dos `doctor --fix` (Linear y review)
son siempre el primer auxilio.

## 👥 ¿Qué rol soy?

| Bundle | Eres tú si... | Instala |
| --- | --- | --- |
| `product` | Conviertes necesidades de negocio en specs, planes y tareas | preset + `linear` |
| `developer` | Implementas tareas, abres PRs y corriges bugs | preset + `git` + `bug` + `linear` + `code-review` |
| `reviewer` | Haces la revisión final antes de aprobar | preset + `code-review` |

Quitar un bundle nunca rompe lo que otro necesita.

## 📆 El día a día: features

Los comandos `/speckit.*` se escriben en el chat de tu agente de código.
El flujo completo, con el estado que Linear refleja solo:

| Paso | Qué haces | Linear |
| --- | --- | --- |
| 1. Especificar | `/speckit.specify` | — |
| 2. Planificar | `/speckit.plan` | se crea el Project |
| 3. Tareas | `/speckit.tasks` | se crean los Issues (*Todo*) |
| 4. Implementar | un branch por tarea: `NNN-T###-slug` (ej. `002-T004-parser-fix`) | *In Progress* |
| 5. Pull request | PR en **draft** por tarea terminada | *In Progress* |
| 6. Auto-revisión | `/speckit.code-review`, corriges, y marcas `ready for review` | *In Review* |
| 7. Revisión final | el revisor usa el mismo comando con `--publish`; una persona mergea | *Done* |

Reglas de oro:

- **La rama base es la default branch del repositorio** (aquí `main`; en
  otros proyectos puede ser `dev`): los branches de tarea salen de ella
  actualizada y los PRs vuelven a ella. No hay nada que configurar — `gh`
  apunta solo a la default branch que el repo tiene en GitHub, y los
  comandos la resuelven en vez de asumir un nombre.
- **Nunca actualices Linear a mano.** Cada sincronización (automática tras
  los comandos, o `push --apply` a mano) deriva los estados de tus
  checkboxes, branches y PRs. Si no cambió nada, no escribe nada.
- **PRs chicos**: máximo ~400 líneas ejecutables escritas por ti. Si la
  tarea es más grande, se parte en
  [Stacked PRs](https://docs.github.com/en/pull-requests/get-started/stacked-prs-quickstart)
  (cada PR dice sobre cuál se apila, en la línea `Stack:` del template).
  El comando de revisión te avisa si te pasas.
- La revisión **nunca aprueba ni mergea** — eso es siempre humano. Exit 1
  del comando significa "hay hallazgos que corregir", no que algo falló.
- El body del PR usa el template canónico
  [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).

## 🐛 Bugs y chores

El camino corto — sin spec ni plan:

1. El bug o chore **nace como Issue en Linear** (lo crea una persona), p.
   ej. `WOR-123`.
2. Un branch con la clave del issue: `wor-123-slug-corto`. Los estados se
   derivan igual que en features: branch o PR draft → *In Progress*, PR
   ready → *In Review*, merge → *Done*.
3. Si es un **bug**, usa el trío de triage: `/speckit.bug.assess` (pégale
   el reporte o la URL) → `/speckit.bug.fix` → `/speckit.bug.test`. Los
   tres reportes quedan en `.specify/bugs/<slug>/` y viajan en el PR como
   evidencia. Si es un **chore**, saltas el trío: cambio directo.
4. PR draft → auto-revisión → `ready for review` → revisión final → merge
   humano.

## 🧰 Comandos

Nativos de Spec Kit: `/speckit.constitution`, `.specify`, `.clarify`,
`.plan`, `.checklist`, `.tasks`, `.analyze`, `.implement`, `.converge`, y el
trío `/speckit.bug.*`.

| Extensión | Comandos |
| --- | --- |
| `linear` | `onboard`, `push` (`--dry-run` / `--apply`), `status`, `doctor --fix`, `completions` |
| `code-review` | `speckit.code-review` (`--publish`), `doctor --fix`, `completions` |

No hay más superficie que esta: cada comando expone solo lo que su paso
necesita (y hay tests que lo fijan).

## 🧬 ¿Cómo funciona por dentro?

Una duda razonable: si el paso 1 instala el CLI de `github/spec-kit`, ¿de
dónde salen las extensiones y comandos de esta distribución?

**El CLI de upstream es la maquinaria, no el contenido** — como instalar
`npm`: te da la *capacidad* de instalar cosas, no las cosas. Trae los
comandos core, las integraciones de agentes y un sistema de instalación
con catálogos. Esta distribución publica el contenido donde esa maquinaria
sabe consumirlo:

- Los [catálogos](catalog/) son nuestro "registry": tres JSON estáticos
  servidos desde este repo que mapean `id + versión → URL de descarga`.
  El paso 3 los registra en tu repo (`.specify/*-catalogs.yml`) y desde
  entonces `specify` conoce nuestro índice además del oficial.
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
                         comandos (/speckit.pr, /speckit.doctor) como
                         skills de TU agente
```

**Después de instalar, todo es local**: comandos, templates y extensiones
viven en tu repo; los catálogos solo se consultan al instalar o al correr
`bundle update`. Este repositorio nunca participa en tu runtime.

## 🏢 Rollout en tu equipo

**Instalar es un evento por-repositorio, no por-dev**: todo lo que el
paso 3 instala queda dentro del repo y se commitea. Quien clona después
recibe el producto ya instalado.

| Una vez por repositorio (se commitea) | Cada dev, en su máquina |
| --- | --- |
| `specify init` + los 3 `catalog add` | `gh auth login` |
| `specify bundle install developer` | su `.speckit-linear.env` con **su** API key (gitignoreado) |
| `onboard` (el binding de Linear, sin secretos) | `doctor --fix` una vez (instala el motor de revisión localmente) |

- **Con el bundle `developer` alcanza para todos**: es el superconjunto de
  `product` y `reviewer`. Los roles definen qué comandos *usa* cada quien,
  no qué instala.
- **Agentes distintos conviven**: instala las integraciones que tu equipo
  usa hoy; cuando aparezca un dev con otro agente, cualquiera corre
  `specify integration install <agente>` + `specify bundle update --all`
  (re-registra los comandos del preset en el agente nuevo) y lo commitea.
  No hace falta predecir.

**¿Cómo sabe el sistema quién está en qué?** No lo sabe — lo *deriva*,
por pregunta, de la realidad observable:

| Pregunta | De dónde sale la respuesta |
| --- | --- |
| ¿En qué tarea estaba mi dev? | El branch en el que está parado (`002-T003-slug` codifica feature y tarea) + `tasks.md` + `/speckit.linear.status --all` |
| ¿A qué tarea le hago review? | A un PR explícito, siempre — nunca a "lo que alguien estaba haciendo" |
| ¿Cómo no se pisan dos devs? | Cada tarea vive en su branch; cualquier `push` ve todos los branches y PRs del repo y reconcilia idempotente |
| ¿Quién tiene asignado qué? | Linear (producto asigna); la columna `ASSIGNEE` del status lo muestra |

- **`push` reconcilia lo que su alcance cubre**: tu feature seleccionada
  (más los bugs/chores, que van en todo push). Las tareas de otro plan las
  deriva un push que las incluya (`--all`, o el de quien trabaja ese
  plan) — y como todo es idempotente, repetir da "0 operaciones".
- **`implement` no elige entre planes**: opera sobre la feature activa
  (`.specify/feature.json`, u `export SPECIFY_FEATURE=...` por terminal) y
  toma su primera tarea sin marcar. Elegir *qué* plan trabaja cada quien
  es decisión humana (la asignación en Linear); el primer movimiento tras
  un pull es siempre `/speckit.linear.status --all`.

Dos fricciones conocidas, con su mitigación:

1. **`.specify/feature.json` es compartido**: dos personas creando
   features *a la vez* se lo disputan — creación secuencial, o
   `SPECIFY_FEATURE` por terminal (la implementación no depende de él: manda
   el branch).
2. **Una tarea = un assignee**: dos devs en la misma tarea colisionarían en
   el branch; la asignación en Linear es el semáforo.

## 🔄 Actualizar

Nada se actualiza solo; las versiones son siempre explícitas:

```bash
uv tool install specify-cli --force --from git+https://github.com/github/spec-kit.git@<tag-nuevo>
specify bundle update --all
```

Después vuelve a correr los dos `doctor`.

## ❓ Problemas frecuentes

- **"is from a discovery-only catalog"** al instalar → al registrar los
  catálogos faltó `--install-allowed` (paso 3). Quita el catálogo y vuelve
  a agregarlo con la flag.
- **El motor de revisión no aparece** → `doctor --fix` de code-review lo
  instala y verifica; necesita `npm` disponible.
- **Un paso no se refleja en Linear** → corre `status` para ver el estado
  derivado y su fuente; revisa que el branch siga la convención
  (`NNN-T###-slug` o `wor-123-slug`) y que `gh auth status` esté OK (sin
  `gh`, los estados que dependen de PRs no se calculan y lo verás avisado).
- **Falta `In Review` en el equipo** → créalo en Linear (Settings → Teams →
  Workflow, tipo *started*) y re-corre `onboard`.
- Ante la duda: `doctor --fix` de cada extensión, y sus mensajes traen la
  remediación exacta.

## 🔐 Integridad

[`versions.lock.yml`](versions.lock.yml) pinnea el upstream y cada extensión
por tag, commit y digest — incluidos los digests por plataforma del motor de
revisión, que viajan dentro de la propia extensión para que cualquier
consumidor verifique lo que `doctor --fix` instala. Las releases se
construyen reproduciblemente desde tags por paquete
([`scripts/release/`](scripts/release/)), y cada etapa de entrega se aceptó
contra los artefactos publicados, con la evidencia en
[`validation/`](validation/). El pin de upstream puede reproducirse desde un
clon independiente:

```bash
git clone --branch v0.13.0 --depth 1 \
  https://github.com/github/spec-kit.git /tmp/spec-kit-v0.13.0
git -C /tmp/spec-kit-v0.13.0 rev-parse 'v0.13.0^{commit}'
git -C /tmp/spec-kit-v0.13.0 rev-parse 'v0.13.0^{tree}'
git -C /tmp/spec-kit-v0.13.0 archive --format=tar v0.13.0 | shasum -a 256
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

La conformance por paquete vive en `packages/*/scripts/conformance/`; la de
los bundles en [`scripts/conformance/bundles.sh`](scripts/conformance/bundles.sh).
La CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) corre ambas
suites. Commits, releases y publicación son siempre decisiones humanas.
