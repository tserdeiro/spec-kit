# tserdeiro/spec-kit

Un harness de desarrollo ultra-liviano para trabajar con agentes de código
(Claude Code, Codex, etc.): cubre el ciclo completo de una necesidad de
negocio a un PR revisado y mergeado, con [Linear](https://linear.app)
siempre al día **sin que nadie lo actualice a mano**. Construido sobre
[GitHub Spec Kit](https://github.com/github/spec-kit), sin fork: solo
composición.

## 🎯 Tu día en cuatro comandos

Con una feature ya especificada, tu día se resume en cuatro comandos:

- **`/speckit.linear.status`** — dónde estás; la misma orientación que
  ya te imprime sola cada sesión, para pedirla vos cuando quieras.
- **`/speckit.implement <feature>`** — entrega la próxima tarea de punta
  a punta: rama, código, PR draft, auto-revisión y `ready for review`.
- **`/speckit.code-review <n> --publish`** — revisa el PR de otra
  persona.
- **`/speckit.doctor`** (`--fix` para lo mecánico) — cura el setup.

Mergear sigue siendo siempre una decisión humana — nunca un comando.

## Tabla de contenidos

- [🎯 Tu día en cuatro comandos](#-tu-día-en-cuatro-comandos)
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

Cuatro pasos y tu repo queda conectado a tu agente, a Linear y al motor de
revisión. Prerrequisitos: `git`, [`uv`](https://docs.astral.sh/uv/),
[Python 3.11+](https://www.python.org/downloads/) (el mismo que exige
Spec Kit; corre los scripts del preset y los hooks), `gh`
([GitHub CLI](https://cli.github.com/), autenticado con `gh auth login`) y
`node`/`npm` (los usa el motor de revisión). Para el paso 4, una API key
de Linear (Linear → Settings → API → Personal API keys).

### 1. Instala el CLI de Spec Kit (versión exacta)

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.0.4
uv tool update-shell
```

Reinicia la terminal; `specify version` debe decir `1.0.4`.

### 2. Inicializa tu repositorio

Dentro del repo donde vas a trabajar:

```bash
specify init --here --integration <agente>
```

`<agente>` es tu agente de código — `claude`, `codex`, `copilot`, `zed`, …
([lista completa](https://github.github.io/spec-kit/reference/integrations.html)).
Puedes usar cualquiera soportado; los guards y el contexto automático
requieren eventos nativos. `/speckit.doctor` informa si tu agente no los tiene.

### 3. Instala el bundle de tu rol

Registra los catálogos de esta distribución (una vez por repositorio) e
instala tu rol — si no sabes cuál eres: [¿Qué rol soy?](#-qué-rol-soy):

```bash
specify extension catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/extensions.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify preset catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/presets.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify bundle catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/bundles.json --id tserdeiro-spec-kit --priority 1
specify bundle install developer   # o: product | reviewer
```

### 4. Cierra el setup con el doctor

Con el bundle instalado, un solo comando termina de conectar Linear, el motor
de revisión y la validación nativa de commits: `/speckit.doctor`. Reporta lo que falta siempre en el
mismo orden — el intérprete de Python (el `.venv` del repo si existe, si
no `python3` en PATH), `gh auth`, la API key de Linear
(`.speckit-linear.env`, gitignoreada; `--fix` crea el template para
pegarla), el binding de `/speckit.linear.onboard`, la instalación del
motor de revisión, la validación nativa de commits, y los settings de entrega
de GitHub — nombrando el comando o la acción indicada para cada uno. `/speckit.doctor
--fix` aplica la parte mecánica; dos huecos quedan siempre solo reportados: el
intérprete (instalarlo o activarlo es decisión tuya) y los settings de GitHub
(aplicarlos es alcance de la ronda de releases).

Listo. Ante cualquier falla futura, `/speckit.doctor --fix` es el primer
auxilio.

### Validación nativa del mensaje de commit

La extensión `code-review` instala, con `/speckit.doctor --fix`, una única
entrada nativa `speckit-commit-message` para el evento `commit-msg`. Requiere
Git 2.54+ y `git hook list`; el mínimo de Git para el comando de revisión sigue
siendo 2.41. En Git anterior, el doctor informa que hay que actualizar Git y
volver a ejecutar `doctor --fix`, sin actualizarlo por su cuenta.

El doctor informa el `core.hooksPath` efectivo y el alcance elegido: usa el
archivo de configuración compartido que Git resuelve, que afecta a todos los
worktrees enlazados, salvo que `extensions.worktreeConfig` ya esté habilitado,
en cuyo caso usa el archivo `config.worktree` que Git resuelve para el worktree
actual. En alcance compartido, el payload instalado de la extensión debe
existir en cada worktree. Los hooks existentes y los
dispatchers de Husky y Lefthook conservan sus archivos, argumentos, orden,
modos y efecto de rechazo.

Los estados `missing`, `installed`, `disabled` y `unverifiable` (más fallas
parciales, duplicadas, ajenas o de payload, lock, permisos, concurrencia,
escritura y lectura posterior) se muestran con la ruta y el mensaje y la acción
disponibles. Un diagnóstico genérico `git_hooks_write_failed` (`native
registration was not completed ...; retry doctor`) puede significar un fallo al
escribir antes del reemplazo o un reemplazo seguido de un fallo al restaurar.
Inspecciona manualmente la ruta antes de reintentar; el diagnóstico no siempre
puede distinguir ambos resultados.
La reparación usa el lock cooperativo de Git y compara bytes, modo y estado
efectivo antes de preparar el archivo temporal. Los escritores que respetan el
lock no pueden editar a la vez; un escritor directo que lo ignore puede correr
después de esa comparación, sin garantía de comparación e intercambio atómico.
Luego edita con Git, reemplaza atómicamente y relee la configuración y la lista
de hooks. Si la lectura posterior falla, intenta restaurar los bytes y el modo
diagnosticados; si esa restauración falla, inspecciona manualmente la ruta y
usa el rollback de la sección propia. Para revertirla, usa solo el alcance que
el doctor informó: `git config --local --remove-section
hook.speckit-commit-message` o `git config --worktree --remove-section
hook.speckit-commit-message`; eso no toca los hooks de la aplicación.

El hook local se puede saltear con `git commit --no-verify` o una desactivación
por evento. Un hook tradicional posterior puede reescribir el mensaje después
de la validación; GitHub y CI siguen siendo controles separados.

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
| 3. Tareas | `/speckit.tasks` | se crean los Issues (*Todo*) |
| 4. Implementar | `/speckit.implement` verifica el gate — el **draft PR de feature** (`NNN-slug` → branch de entrega), donde el equipo aprueba spec y plan — y lo abre si falta, antes de la primera tarea; toma la primera tarea sin marcar y crea su branch `NNN-T###-slug` (ej. `002-T004-parser-fix`) **desde la punta del stack ready abierto**, o desde la feature si no hay stack | *In Progress* |
| 5. Pull request | `/speckit.pr` — abre el PR **draft** de la tarea con el body canónico y la **base derivada del stack**; la primera tarea apunta a la feature | *In Progress* |
| 6. Auto-revisión | `/speckit.code-review`, corriges, `[x]` + evidencia en el último commit, y marcas `ready for review` | *In Review* |
| 7. Revisión final | el revisor: `/speckit.code-review --publish` más su revisión humana; una persona mergea al branch de feature | *Done* |
| 8. Cierre | todas `[x]` en la feature y ningún PR de tarea abierto → marcas el PR de feature `ready` → revisión de la película completa → una persona mergea al branch de entrega con **merge commit**; GitHub borra el branch si tiene auto-borrado habilitado | — |

Los pasos 4–6 (abrir el PR, auto-revisarse, marcar `ready for review`)
los orquesta `/speckit.implement` solo, tarea por tarea; cada comando
también puede correrse suelto, y el detalle de cada paso en la tabla
sigue valiendo tal cual.

Reglas de oro. Lo que hacés vos:

- **Una tarea en vuelo, nunca en paralelo**: se entregan de a una, en
  orden de dependencias (las listas no llevan marcadores `[P]`);
  `ready for review` te libera para la siguiente.
- **El checkbox y la Completion evidence viajan en el último commit del
  PR de la tarea**: llegan al branch de feature únicamente vía el merge
  humano — ahí `[x]` = mergeado, por construcción; un comentario del
  reviewer se corrige en ese mismo PR, nunca tocando tareas pasadas.
- **Nunca actualices Linear a mano**: la proyección sigue al repositorio
  (branches, PRs, checkboxes); `push` es la reconciliación idempotente
  si algo no cuadra, y no escribe nada si no cambió nada.

<details>
<summary>Lo que garantiza el loop</summary>

- **El branch de feature (`NNN-slug`) es la integración**: las tareas
  se apilan sobre él y sus PRs se integran allí de raíz a hoja; la feature entra al
  branch de entrega una sola vez, con merge commit. Bugs y chores van
  directo al branch de entrega. `trunk: <branch>` en
  `.specify/extensions/git/git-config.yml` manda cuando el default de
  GitHub no es el real (este repo: `trunk: main`).
- **La base de cada PR se deriva del stack abierto, nunca se elige a
  mano**: la siguiente tarea se apila sobre el PR ready sin mergear de
  la anterior, o sale del branch de feature si no hay ninguno — un solo
  stack por feature.
- **El presupuesto frena solo**: al doble del forecast de la línea
  `Delivery`, o 400 líneas ejecutables, lo que llegue primero, nombrando
  lo que no entra; un forecast nunca se amplía en el PR que lo excede —
  lo cambia el humano en el ledger, o graba una excepción explícita en
  la conversación que queda en el PR.
- **La auto-revisión es siempre fresca**, con el body del PR ya armado
  desde el template canónico
  ([`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md));
  exit 1 del comando de revisión son hallazgos para corregir, no una
  falla — nunca aprueba ni mergea.
- **`ledger_check.py` frena el `ready for review`** hasta que el
  checkbox y la Completion evidence estén los dos.
- **El merge es raíz-primero y nunca pide borrar la rama**: a pedido
  tuyo en la conversación, un script prunea worktrees, consulta la base
  de cada PR y la cambia a la feature solo si hace falta. Si el cambio
  falla, continúa únicamente si una nueva lectura confirma esa base.
  Mergea de raíz hacia la hoja; el auto-borrado del repo limpia las ramas.
- **Cuatro guards bloquean antes del hecho**: un commit que no siga
  `type(scope): subject`, cualquier force-push, un merge con
  `--delete-branch`, o una escritura a un path protegido (`spec.md`, la
  constitución) desde una rama de tarea — cada uno nombra el arreglo;
  ninguno corre en un agente sin soporte de eventos (`/speckit.doctor`
  lo dice).
- **Linear se reconcilia solo**, por scripts y eventos, sin ningún
  reconcile manual; un PR abierto pesa más que el checkbox, así que una
  tarea en review nunca aparece como *Done*.
- **El stack técnico se deriva, nunca se inventa**: `/speckit.implement`
  lee la tarea y el plan primero, y si no alcanzan, los manifests reales
  y el código vecino; una dependencia nueva o reimplementar lo que una
  lib ya cubre siempre vuelve a vos como decisión.

</details>

**Linear en tiempo real** (opcional, recomendado): un admin conecta GitHub
en Linear (Settings → Integrations → GitHub), **una vez por workspace**;
con acceso "All repositories" los repos nuevos no piden nada. Las
automatizaciones de PR son **por equipo**: `onboard` completa el mapeo default
(draft → *In Progress*, ready → *In Review*, merged → *Done*), que aplica a
todo PR enlazado, sin pisar una elección distinta ni tocar reglas por branch.

Los PRs de tarea mergean a branches de feature y el mapeo default los cubre
una vez enlazados. El branch `NNN-T###-slug` no lleva la key de Linear:
`/speckit.pr` enlaza el Issue con `Fixes WOR-###` en el body canónico. Los
branches de bugs/chores sí llevan la key y se enlazan por nombre. Las reglas
por branch destino son overrides opcionales; usa una regex como `^\d{3}-`
solo si las features necesitan otro mapeo o ninguna acción. En todos los
casos, `push` vuelve a derivar el estado observable y reconcilia aunque la
automatización nativa no exista o no cubra el evento. Detalle: [integración GitHub de
Linear](https://linear.app/docs/github#branch-specific-rules).

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
   crea el branch (`wor-123-slug-corto`) desde el branch de entrega al día y
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
| preset `default` | `/speckit.pr`, `.bugfix`, `.chore`, `.doctor` (conduce el onboarding en siete categorías, verifica el cableado de eventos, espeja skills entre agentes y agrega al `.gitignore` las cachés del instalador) — más los reemplazos de `.implement` (el loop de entrega, sobre los scripts del preset) y `.tasks` (el ledger sin `[P]`), y los appends en `.specify`, `.plan` y `.analyze` (fases silenciosas y commiteadas) |
| extensión `linear` | `onboard`, `push` (`--dry-run` / `--apply`), `status`, `doctor --fix` |
| extensión `code-review` | `speckit.code-review` (`--publish`), `doctor --fix` — bloquea con un finding automático el PR de tarea que toque `spec.md` o la constitución (`protected_paths`) |

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
                         /speckit.chore y /speckit.doctor), reemplaza
                         tasks/implement y agrega capas a
                         specify/plan/analyze como skills de TU agente
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
| `onboard` (el binding de Linear, sin secretos) | `/speckit.doctor --fix` una vez (instala el motor de revisión y crea los templates que faltan) |

- **Con `developer` alcanza para todos**: es el superconjunto de
  `product` y `reviewer`; los roles definen qué comandos *usa* cada
  quien, no qué instala.
- **Agentes distintos conviven**: upstream registra los comandos de
  extensiones y preset solo en la integración **default** — y
  `/speckit.doctor --fix` copia enteros los skills de extensión y preset
  al resto de los agentes instalados y, en los comandos core, mantiene
  el render propio de cada agente y le suma las capas del preset, sin
  pisar nunca el render de un agente con el de otro. Sumar un agente:
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
`v1.0.4`): actualiza la herramienta, refresca los assets base del repo
(la constitución autorada se preserva) y re-aplica los bundles:

```bash
uv tool install specify-cli --force --from git+https://github.com/github/spec-kit.git@v1.0.4
specify init --here --force --integration <agente>
specify bundle update --all
```

(La primera vez tras subir a v1.0.1, destrackea el puntero local que el
CLI ahora gitignora: `git rm --cached .specify/feature.json`.)

Cuando una extensión suma wiring nuevo (eventos, comandos
reemplazados), ninguna de las dos vías de arriba re-renderiza sola los
hooks de tu agente: corre `specify integration upgrade <agente>` — una
integración ya instalada no cambia nada con `install ... --force`, el
comando es `upgrade` — y después `/speckit.doctor --fix`, cuyo espejo
restaura la capa del preset que `upgrade` acaba de pisar con el core de
upstream.

Tras cualquier actualización, re-corre `/speckit.doctor --fix`.

## ❓ Problemas frecuentes

- **"is from a discovery-only catalog"** al instalar → al registrar los
  catálogos faltó `--install-allowed` (paso 3). Quita el catálogo y
  vuelve a agregarlo con la flag.
- **El motor de revisión no aparece** → `/speckit.doctor --fix` lo
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
- **El doctor dice que tu agente no está cableado justo después de
  `bundle install`** → el instalador de bundles no refresca los eventos;
  corre `specify extension disable linear && specify extension enable
  linear` y vuelve a correr `/speckit.doctor` (entrada 103 del
  dogfooding).
- **Falta `In Review` en el equipo** → créalo en Linear (Settings → Teams
  → Workflow, tipo *started*) y re-corre `onboard`.
- Ante la duda: `/speckit.doctor --fix`; sus mensajes traen la
  remediación indicada.

## 🔐 Integridad

[`versions.lock.yml`](versions.lock.yml) pinnea el upstream y cada
extensión por tag, commit y digest — incluidos los digests por plataforma
del motor de revisión, que viajan dentro de la propia extensión para que
cualquier consumidor verifique lo que `doctor --fix` instala. Las releases
se construyen reproduciblemente desde tags por paquete
([`scripts/release/`](scripts/release/)), y cada etapa se aceptó contra
los artefactos publicados, con la evidencia en
[`validation/`](validation/). `bash scripts/conformance/bundles.sh
--published` recalcula el digest del archive del tag y del manifiesto de
cada extensión contra [`versions.lock.yml`](versions.lock.yml), y
descarga y verifica el zip publicado cuando ya existe; `publish.sh` lo
corre antes de publicar, cuando el zip todavía no existe, así que el
mantenedor lo vuelve a correr una vez publicado para verificar también
los zips subidos. El pin de upstream se reproduce desde un clon
independiente:

```bash
git clone --branch v1.0.4 --depth 1 \
  https://github.com/github/spec-kit.git /tmp/spec-kit-v1.0.4
git -C /tmp/spec-kit-v1.0.4 rev-parse 'v1.0.4^{commit}'
git -C /tmp/spec-kit-v1.0.4 rev-parse 'v1.0.4^{tree}'
git -C /tmp/spec-kit-v1.0.4 archive --format=tar v1.0.4 | shasum -a 256
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
uv run pytest presets/default/tests
```

La invocación de arriba —`uv run pytest packages/<paquete>/tests` desde
la raíz— es la documentada: `uv run --project <paquete> pytest`
recolecta ambos árboles de tests y choca en `tests.conftest`.

La conformance por paquete vive en `packages/*/scripts/conformance/`; la
de los bundles en
[`scripts/conformance/bundles.sh`](scripts/conformance/bundles.sh). La CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) corre las tres
suites. Commits, releases y publicación son siempre decisiones humanas.
