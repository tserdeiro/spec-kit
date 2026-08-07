# spec-kit — Visión de producto

Documento de visión y autoridad de producto. [`plan.md`](plan.md) deriva de este documento; ante un conflicto, manda esta visión. Implementada por completo (Etapas 0–7) el 2026-08-06, verificada contra artefactos publicados.

## Qué es

Un harness de desarrollo ultra-liviano y portable basado en
[github/spec-kit](https://github.com/github/spec-kit), que cubre el ciclo de
entrega completo del día a día: necesidad de negocio → especificación → plan →
tareas → implementación → revisión → merge.

Cubre todo el trabajo diario —features, bugs y chores— con caminos
proporcionales al tamaño del trabajo: una feature recorre el flujo completo;
un bug o chore toma un camino más corto.

## Principios

### Ultra-liviano

- Se construye por capas: lo mínimo que funciona de punta a punta, y cada
  capa nueva se agrega sobre un producto que ya funciona.
- Nada "por las dudas": ni funcionalidades especulativas ni soluciones
  overkill. Un comando expone solo lo que su paso necesita.
- Pasos pequeños, seguros y bien definidos; soluciones simples a problemas
  complejos.

### La realidad observable manda

- Los artefactos del repositorio son la verdad durable; Linear es una
  proyección y nunca escribe artefactos.
- Los estados **se derivan, no se avisan**: cada `push` reconcilia Linear
  desde lo observable (checkbox, branches, PRs) de forma idempotente — sin
  eventos, sin actualizaciones manuales, sin estado fantasma. Una segunda
  pasada sin cambios son cero operaciones.
- Hecho significa **funcionando de punta a punta y verificado contra los
  artefactos publicados**, no especificado ni probado solo con fixtures.
- Cuando falta una pieza (sin `gh`, sin un estado en el team), se degrada
  explícitamente con un aviso; nunca se falla en silencio ni se inventa.

### Portabilidad

Debe funcionar por completo con **todos** los agentes soportados por upstream
([Supported AI Coding Agent Integrations](https://github.com/github/spec-kit/blob/main/README.md#-supported-ai-coding-agent-integrations)).
Ningún agente es de segunda clase: los comandos viajan como `.md` +
launchers, sin lógica por agente, y las extensiones no tienen dependencias de
runtime.

### Developer Experience

El proyecto es usado por desarrolladores de distintos niveles y en distintos
proyectos: **la DX es prioridad**.

- **Un solo camino de instalación**: registrar los catálogos de la
  distribución e instalar el bundle del rol. `doctor --fix` cierra los
  huecos que queden — incluida la instalación verificada del motor de
  revisión pinneado.
- Toda fricción se pule; lo automatizable se automatiza. Autocompletado de
  comandos y mensajes con remediación exacta, especialmente para juniors.

## Roles

Tres roles, cubiertos por personas distintas del equipo, cada uno con su
bundle instalable (compuestos con los mecanismos nativos de upstream:
preset + extensiones pinneadas, servidos por catálogos estáticos):

- `product`: convierte necesidades de negocio en especificaciones y tareas.
- `developer`: implementa por tarea, abre PRs draft y se auto-revisa; lleva
  además el trío de triage de bugs.
- `reviewer`: desarrollador senior que hace la revisión final y aprueba.

## Workflow de features

SDD (Spec-Driven Development) + code review, con Linear como seguimiento:

1. **Especificación** — producto convierte la necesidad de negocio en
   especificación técnica (`/speckit.specify`).
2. **Planificación** — producto planifica el trabajo (`/speckit.plan`) → se
   crea un Project en Linear.
3. **Tareas** — producto crea y asigna tareas accionables
   (`/speckit.tasks`) → se crean Issues en Linear dentro del Project.
4. **Implementación** — el desarrollador completa las tareas de a una
   (`/speckit.implement`), **un branch por tarea** (`NNN-T###-slug`) →
   *In Progress*.
5. **Pull Request** — un PR en `draft` por tarea terminada. Un PR revisado
   se mantiene bajo ~400 líneas ejecutables autoradas; una tarea mayor se
   parte en [Stacked PRs](https://docs.github.com/en/pull-requests/get-started/stacked-prs-quickstart),
   cada uno nombrando sobre cuál se apila.
6. **Auto-revisión** — el desarrollador ejecuta `/speckit.code-review` y
   corrige antes de marcar `ready for review` → *In Review*.
7. **Revisión final** — el revisor ejecuta el mismo comando con `--publish`
   y suma su revisión humana → merge humano → *Done*.

**Integración por feature**: el branch que `/speckit.specify` crea
(`NNN-slug`, desde el branch default) es la unidad de integración. La fase
de producto commitea sus artefactos ahí y cierra abriendo su PR draft hacia
el default — el gate de revisión del spec. Cada tarea sale de ese branch y
mergea hacia él; completadas todas las tareas, ese mismo PR — ya compuesto
de PRs revisados — recibe la revisión final y entra al default por merge
commit, y el branch de feature se borra. Nada a medias llega al branch
default.

Un único comando de revisión que detecta su contexto: sin candidato revisa
el diff pendiente (consultivo); con PR revisa el candidato anclado a su
commit. Solo publica con `--publish`, `changes-requested` sale con exit 1, y
aprobar o mergear es **inalcanzable por construcción**: siempre humano.

## Workflow de bugs y chores

Camino corto, sin spec ni plan:

1. El bug o chore **nace como Issue en Linear** (lo crea un humano); el
   harness nunca crea ni edita su contenido, solo proyecta su estado.
2. Un branch por issue-key (`wor-123-slug`) → los estados se derivan igual
   que en features: branch o PR draft → *In Progress*, PR ready →
   *In Review*, merge → *Done*.
3. **Bugs**: el trío oficial `/speckit.bug.assess` → `.fix` → `.test`
   (evaluar sin tocar, tocar acotado, verificar sin sobre-reclamar); sus
   reportes en `.specify/bugs/<slug>/` viajan en el PR como evidencia.
   **Chores**: mismo camino sin el trío.
4. PR draft → auto-revisión → ready → revisión final → merge humano.

## Extensiones

Dos extensiones first-party, más las oficiales de upstream (`git`, `bug`):

- **Linear**: `onboard` (alta one-shot que resuelve todos los IDs), `push`
  (`--dry-run`/`--apply`, la reconciliación), `status`, `doctor --fix`,
  `completions`. Núcleo del flujo, no un opcional. Requiere en el team los
  estados *In Progress* e *In Review* (los resuelve por nombre; sin
  *In Review*, degrada con aviso). Convive con la integración nativa
  GitHub↔Linear (links por branch o magic words, transiciones en tiempo
  real, configurada por equipo): esa integración adelanta estados; `push`
  sigue siendo la reconciliación idempotente que manda.
- **Code review**: `/speckit.code-review` (el comando único) + `doctor
  --fix` + `completions`. Envuelve [Open Code Review](https://github.com/alibaba/open-code-review)
  en modo delegación, fail-closed, con el pin del motor viajando dentro de
  la propia extensión para que cualquier consumidor lo verifique.

## Notas

- El proyecto no arrastra retro-compatibilidad: los caminos obsoletos se
  eliminan, no se deprecian.
- Todo lo publicado se pinnea por versión exacta y digest en
  `versions.lock.yml`; las subidas de versión son explícitas y revisadas.
