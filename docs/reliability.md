# Confiabilidad del workflow: propuesta para la próxima ronda

Propuesta para revisión, reescrita el 2026-09-11 en lenguaje llano. Fusiona
la auditoría de Codex sobre la 005, la revisión de Claude y los ajustes de
`dx-proposals.md`, que este documento reemplaza. Todo lo que afirma sobre el
código está verificado contra la versión publicada el 2026-09-10 (linear
0.13.0, code-review 0.5.0, preset 0.10.0, bundles 0.16.0) y contra
[`dogfooding.md`](dogfooding.md). Deriva de [`vision.md`](vision.md); la spec
de la ronda se escribe a partir de aquí. Releases ([`releases.md`](releases.md))
sigue siendo una ronda aparte.

## Cómo leer este documento

Cada punto tiene cuatro partes: **Hoy** cuenta qué le pasa a un dev con la
versión actual; **Propuesta** dice qué cambiaría, sin tecnicismos;
**Detalle** deja las referencias al código y a las entradas del dogfooding
para quien implemente; **Decisión** aparece solo cuando hace falta una
respuesta humana antes de codear. Al final hay un orden recomendado, una
lista de decisiones y qué no vamos a hacer.

Términos que se repiten:

- **Rama de feature** (`003-checkout`): donde se integra una feature entera.
  **Rama de tarea** (`003-T004-parser`): una por tarea, sale de la anterior.
- **Stack**: la cadena de PRs de tarea, cada uno apilado sobre el anterior.
  Se mergean de abajo hacia arriba, "raíz primero".
- **Gate**: el PR draft de la feature. Ahí un humano aprueba spec y plan
  antes de implementar; al final, ese mismo PR cierra la feature.
- **Ledger**: el archivo `tasks.md`, la lista de tareas con sus casillas.
- **Derivar y reconciliar**: Linear no se actualiza a mano. Cada estado se
  calcula desde lo observable (casilla, rama, PR) y se escribe; repetirlo
  sin cambios no hace nada.
- **Packet**: el paquete de archivos que lee el motor de revisión.
- **Presupuesto y forecast**: cada tarea estima cuántas líneas va a agregar;
  el loop frena al doble de la estimación o a 400 líneas.
- **Guard**: un chequeo que bloquea una acción peligrosa antes de que
  ocurra. Solo funciona en agentes con eventos (Claude, Codex, Cursor).
- **Doctor**: el chequeo de salud del setup.
- **Trunk**: la rama donde aterrizan las features (`main` o `dev`).
- **Ruleset**: reglas que GitHub aplica del lado del servidor, para todos.
- **CODEOWNERS**: un archivo de GitHub que asigna revisores por carpeta y
  pide la revisión solo.

## De dónde partimos

- La 005 dejó la mecánica en scripts y eventos, pero el flujo todavía no es
  confiable cuando se interrumpe, se retoma o falla a medias. Los ocho
  hallazgos de Codex siguen vigentes; solo cambió dónde vive la evidencia.
- Este repositorio, que es su propio consumidor, corría al 2026-09-11 con
  payloads anteriores a la 005 y sin eventos cableados (linear 0.12.0 y
  code-review 0.4.0 instalados; sin `.specify/events.py`). La actualización
  se entregó como chore aparte (PR #116, mergeado el 2026-09-11); lo que
  dejó ver está en la entrada 102 del dogfooding.
- De la 005 quedan pendientes la ejecución viva en Codex y una
  reconciliación observada en un proyecto de prueba de Linear.
- Los parches a upstream están preparados y verificados en
  [`upstream/`](upstream/README.md). 0003 y 0004 se reemplazan por el diseño
  de un resolver de hooks portátil
  ([`hooks-runtime-design.md`](upstream/hooks-runtime-design.md)), que queda
  aparcado hasta terminar esta ronda. Los demás esperan las pruebas manuales
  con agente que exige upstream.

## Los puntos

### A. Que Linear no mienta

**1. Linear puede decir "hecho" cuando no lo está.** Codex, prioridad máxima.

- Hoy: si GitHub no responde, el sistema mira solo la casilla del ledger y
  marca la tarea como completada aunque su PR siga abierto. Si una tarea se
  partió en dos PRs y uno se mergeó, la marca completada aunque el otro siga
  abierto. Además lee como máximo 200 PRs y este repositorio ya tiene 115:
  en una o dos rondas más, dejaría de ver trabajo real.
- Propuesta: un PR abierto siempre gana, incluso sobre uno mergeado de la
  misma tarea (es lo que hace Linear nativamente cuando una Issue tiene
  varios PRs). Si no se pudo leer GitHub, no se toca el estado y se avisa.
  Se leen todos los PRs, y si la lectura queda incompleta se avisa en vez de
  actuar a medias. Una falla al hablar con Linear nunca frena el trabajo:
  la próxima reconciliación lo cubre, porque no guarda estado.
- Detalle:
  [`cli.py:945`](../packages/spec-kit-linear/src/spec_kit_linear/cli.py:945),
  [`work_state.py:96`](../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:96),
  [`work_state.py:131`](../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:131),
  [`github.py:27`](../packages/spec-kit-linear/src/spec_kit_linear/github.py:27),
  [`github.py:59`](../packages/spec-kit-linear/src/spec_kit_linear/github.py:59);
  los scripts del preset ya paginan y frenan al saturar
  ([`_common.py:137`](../presets/default/scripts/python/_common.py:137)).
  Validar contra un proyecto de prueba de Linear, no solo con fixtures.

### B. Que "seguí" funcione

**2. Retomar una tarea interrumpida.** Codex, prioridad máxima; Claude.

- Hoy: `implement` siempre intenta crear una rama nueva. Si la rama ya existe
  o hay un PR draft de la misma tarea, se frena o falla. Cambiar de agente a
  mitad de tarea obliga a reconstruir a mano lo que ya estaba hecho.
- Propuesta: al entrar, el comando mira qué existe (rama, cambios sin
  commitear, PR, sesión de revisión) y ejecuta solo el paso que falta.
  Reconoce su propio draft y lo continúa; un draft de otra tarea sigue
  frenando, con explicación. Las dos transiciones que hoy siguen en prosa
  pasan a scripts: cerrar la tarea (presupuesto, ledger y `ready`) y cerrar
  la feature (todo marcado y ningún PR de tarea abierto). El mismo camino de
  recuperación vale para bugs y chores. Opción a evaluar: worktrees de Git
  para atender otro trabajo sin abandonar el checkout actual.
- Detalle:
  [`task_base.py:43`](../presets/default/scripts/python/task_base.py:43),
  [`task_base.py:51`](../presets/default/scripts/python/task_base.py:51),
  [`implement.md:66`](../presets/default/commands/implement.md:66),
  [`implement.md:110`](../presets/default/commands/implement.md:110),
  [`implement.md:124`](../presets/default/commands/implement.md:124); el
  template todavía dice `git switch -c` desde la feature
  ([`tasks-template.md:33`](../presets/default/templates/tasks-template.md:33)).

**3. Producto también necesita saber qué sigue.** Claude.

- Hoy: la línea que orienta al empezar cada sesión solo existe desde que hay
  `plan.md`; antes desaparece sin explicar nada. Y aunque el template dice
  que cerrar la fase de producto abre el gate, ningún comando lo hace:
  producto tiene que acordarse de correr `/speckit.pr`.
- Propuesta: el "qué sigue" también cubre las fases previas: spec sin plan,
  plan sin tareas, tareas sin gate. El comando `tasks` abre el PR draft del
  gate al terminar y devuelve el link para aprobar.
- Detalle:
  [`parser.py:279`](../packages/spec-kit-linear/src/spec_kit_linear/parser.py:279),
  [`cli.py:1318`](../packages/spec-kit-linear/src/spec_kit_linear/cli.py:1318),
  [entrada 87](dogfooding.md:767),
  [`tasks-template.md:17`](../presets/default/templates/tasks-template.md:17).

**4. Pedir solo decisiones.** Codex; Claude.

- Hoy: para arrancar un bug hay que pegarle al agente el título de la Issue,
  aunque Linear ya lo tiene. El recorrido de producto se presenta como una
  lista de comandos para recordar.
- Propuesta: cada fase corre sus propias verificaciones y sigue sola cuando
  tiene lo que necesita; cuando necesita al humano, muestra la decisión
  concreta y su consecuencia. `bugfix` y `chore` toman título y contexto de
  la Issue a partir de su clave. Un junior recibe una línea explicando el
  próximo paso; alguien con experiencia, solo estado, resultado y bloqueo.
  Mismo workflow, sin perfiles ni flags.
- Detalle:
  [`README.md:142`](../README.md:142),
  [`bugfix.md:33`](../presets/default/commands/bugfix.md:33),
  [`chore.md:34`](../presets/default/commands/chore.md:34),
  [`linear_client.py:763`](../packages/spec-kit-linear/src/spec_kit_linear/linear_client.py:763).

**5. Ver si la feature quedó atrasada respecto del trunk.** Claude.

- Hoy: mantener la rama de feature al día con `main` es "deber del
  developer", o sea algo que hay que acordarse de hacer.
- Propuesta: la línea de contexto y `status` muestran "la feature está N
  commits detrás del trunk", después de refrescar. No se mergea solo.
- Detalle: [`implement.md:59`](../presets/default/commands/implement.md:59).
- Decisión (2026-09-11): solo mostrar; sin merge automático.

### C. Que la revisión automática sea confiable antes de exigirla

**6. Hoy la revisión no puede cerrarse bien.** Claude; requisito del punto 7.

- Hoy: cuando el ledger pasa de 55 KB no entra en el packet y toda revisión
  termina "inconclusa", sin distinguir "sin hallazgos" de "no revisado". El
  motor excluye los archivos Markdown, que en este producto son el
  comportamiento mismo. Y si el revisor escribe una categoría que no existe,
  se rechaza el archivo de hallazgos entero.
- Propuesta: el packet lleva el bloque de la tarea revisada, la estrategia
  de entrega y los requisitos relacionados, con acceso al resto de los
  artefactos y registro de qué se leyó. Los `.md` que definen comandos entran
  a la revisión. Una categoría inválida se corrige sin perder el hallazgo;
  nunca se descarta un hallazgo para lograr un resultado verde.
- Detalle: [entrada 79](dogfooding.md:680), [entrada 74](dogfooding.md:640),
  [entrada 90](dogfooding.md:809),
  [`speckit-code-review.template.yml:14`](../packages/spec-kit-code-review/config/speckit-code-review.template.yml:14).

**7. "Listo para revisión" tiene que estar respaldado.** Codex, prioridad máxima.

- Hoy: después de corregir lo que encontró la revisión, el loop agrega el
  commit final y marca el PR listo, sin volver a revisar lo cambiado ni
  comprobar que los checks pasen.
- Propuesta: el script de cierre de tarea exige una revisión cerrada sobre
  el commit actual, sin hallazgos bloqueantes, y los checks de CI en verde
  cuando el repo los tiene. Un cambio que solo toca el ledger tiene un
  tratamiento liviano; un cambio de código renueva la evidencia, también en
  los PRs apilados encima, porque su contenido cambió.
- Detalle:
  [`implement.md:94`](../presets/default/commands/implement.md:94),
  [`implement.md:104`](../presets/default/commands/implement.md:104).

**8. Una sola forma de contar el presupuesto.** Codex; Claude.

- Hoy: hay dos contadores que no coinciden. Renombrar un archivo de 300
  líneas cuenta 300 en el loop y 0 en la revisión. Ambos ignoran Markdown.
  El loop cuenta solo líneas agregadas, con blancos y comentarios, y solo lo
  ya commiteado, así que quien implementa no puede medirse antes de
  commitear. El ejemplo del template no lleva el forecast que el comando
  exige. Las cifras de evidencia se tipean a mano y se desfasan.
- Propuesta: una sola definición de la métrica (qué cuenta, cómo se tratan
  renames, blancos y Markdown), una sola implementación o dos probadas
  equivalentes, y un modo que mida el trabajo sin commitear. El ejemplo del
  template lleva `(~N authored lines)`. El PR toma las cifras de la salida de
  los scripts, nunca tipeadas.
- Detalle:
  [`budget_stop.py:56`](../presets/default/scripts/python/budget_stop.py:56),
  [`budget.py:92`](../packages/spec-kit-code-review/src/spec_kit_code_review/budget.py:92),
  entradas [58](dogfooding.md:491), [67](dogfooding.md:576),
  [69](dogfooding.md:595), [75](dogfooding.md:649), [78](dogfooding.md:672);
  [`tasks-template.md:55`](../presets/default/templates/tasks-template.md:55)
  contra [`tasks.md:42`](../presets/default/commands/tasks.md:42).
- Decisión (2026-09-11): unificar primero y medir después; no contar
  líneas netas, porque una eliminación grande también necesita revisión.

### D. Usar lo nativo de Git, GitHub y Linear

**9. Las reglas duras, en Git y GitHub; el guard como segunda línea.** Claude.

- Hoy: las cuatro reglas (mensaje de commit con formato, nada de
  force-push, nada de borrar ramas al mergear, nada de tocar el spec desde
  una rama de tarea) las bloquea un guard que solo corre en agentes con
  eventos. Zed y una persona en la terminal quedan afuera. El chequeo de
  formato de commits en CI existe solo en este repositorio, no en los
  consumidores.
- Propuesta: el doctor instala un hook `commit-msg` de Git con la misma
  regla, respetando el gestor de hooks que el repo ya use (husky, lefthook).
  GitHub bloquea los force-push en las ramas compartidas con un ruleset;
  exigir PR, checks y revisión humana queda según el modelo del equipo.
  El guard sigue para lo que no tiene equivalente nativo: los paths
  protegidos en ramas de tarea.
- Detalle:
  [`cli.py:2278`](../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py:2278),
  [`conventions.yml:4`](../.github/workflows/conventions.yml:4),
  [`vision.md:45`](vision.md:45).
- Cuidados: no poner reglas de borrado sobre las ramas de tarea, porque
  impedirían el auto-borrado de ramas al mergear, del que depende el flujo.
  Los rulesets en repos privados exigen plan Pro o Team; el doctor lo
  reporta. GitHub no deja que el autor apruebe su propio PR.

**10. El cuerpo del PR se instala, no se da por sentado.** Claude.

- Hoy: el comando `pr` y el motor de revisión asumen que existe
  `.github/PULL_REQUEST_TEMPLATE.md` en el consumidor. Nadie lo instala, el
  doctor no lo verifica y ningún test lo cubre.
- Propuesta: el doctor lo crea si falta y verifica sus secciones si existe,
  sin pisar personalizaciones. Los pasos mecánicos de `pr` (commit acotado,
  push, crear o adoptar el draft, actualizar el cuerpo) pasan a script; el
  agente solo redacta.
- Detalle: [`pr.md:60`](../presets/default/commands/pr.md:60),
  [`packet.py:1173`](../packages/spec-kit-code-review/src/spec_kit_code_review/packet.py:1173),
  [`pr.md:30`](../presets/default/commands/pr.md:30),
  [`pr.md:120`](../presets/default/commands/pr.md:120).

**11. Que la aprobación del plan sea observable y los permisos del agente
estén escritos.** Codex; Claude.

- Hoy: `implement` considera aprobado el plan si existe un PR de feature
  abierto, y existir no es aprobar. El contrato del repo dice que los
  commits son humanos mientras el preset commitea solo: dos textos que se
  contradicen.
- Propuesta (decidido el 2026-09-11): la aprobación es el propio envío del
  plan al repositorio. Producto commitea spec y plan cuando los termina; al
  llegar a Git ya están aprobados y no hace falta otra aprobación. El gate
  de `implement` sigue exigiendo solo el PR de feature abierto. Lo que sí
  falta es escribir en `AGENTS.md` y el README la autorización acotada del
  agente: commits, pushes, drafts y reconciliación son suyos; producto,
  aprobación y merge son humanos. El agente reconoce esa autorización sin
  volver a preguntar.
- Detalle: [`AGENTS.md:84`](../AGENTS.md:84),
  [`plan-template.md:95`](../presets/default/templates/plan-template.md:95),
  [`implement.md:42`](../presets/default/commands/implement.md:42),
  [entrada 10](dogfooding.md:87).
- Decisión: tomada; queda solo escribir la autorización.

**12. Que el revisor se entere por la plataforma.** Claude.

- Hoy: marcar un PR "listo" no le pide revisión a nadie. La columna "qué
  sigue" está pensada para quien implementa: al revisor le dice "esperá el
  merge".
- Propuesta: CODEOWNERS en el consumidor, o pedir revisor al marcar listo.
  El "qué sigue" tiene en cuenta asignación y pedidos de revisión: no
  alcanza con no ser el autor para ser revisor.
- Detalle:
  [`reporting.py:194`](../packages/spec-kit-linear/src/spec_kit_linear/reporting.py:194),
  [`work_state.py:190`](../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:190).

**13. Linear ya sabe lo que hoy pedimos a mano.** Claude; completa el 4.

- Hoy: si al equipo le falta el estado `In Review`, crearlo es un paso
  manual del rollout. El título de la Issue se le pregunta al dev.
- Propuesta: `onboard` ofrece crear `In Review`; título y slug salen de la
  clave de la Issue.
- Detalle: [`README.md:459`](../README.md:459),
  [`README.md` de linear:79](../packages/spec-kit-linear/README.md:79).
- Decisión (2026-09-11): sí. `onboard` crea `In Review` y lo que haga
  falta para que Linear quede bien configurado, con autorización de quien
  administra el team.

### E. Instalar y actualizar sin sorpresas

**14. Una sola verificación cierra instalación y actualización.** Codex; Claude.

- Hoy: los pasos están repartidos entre instalación, onboarding, doctors de
  paquetes y el espejo de skills. Actualizar exige dos comandos extra
  porque `bundle update` no vuelve a cablear los hooks. El doctor son 182
  líneas de prosa que el agente ejecuta y resume; el arreglo del cableado
  "nunca se corre aquí".
- Propuesta: un `doctor.py` en el preset que corra los sub-doctors y arme
  las seis categorías siempre igual, ejecutable sin agente. `--fix` corre
  `integration upgrade` cuando el cableado quedó viejo. Se adoptan el wizard
  de `onboard` y las reparaciones de GitHub del diseño de releases. Termina
  siempre en "listo para trabajar" o en una acción humana concreta.
  Proponer a upstream que `bundle install` y `bundle update` refresquen
  los eventos, después de confirmarlo en el CLI: un consumidor nuevo hoy
  queda sin cablear ([entrada 103](dogfooding.md)).
- Detalle: [`README.md:404`](../README.md:404),
  [`README.md:429`](../README.md:429),
  [`doctor.md:73`](../presets/default/commands/doctor.md:73),
  [`doctor.md:126`](../presets/default/commands/doctor.md:126),
  [`releases.md:48`](releases.md:48), [entrada 85](dogfooding.md:743).

**15. Que el doctor avise que estás atrasado y que los hooks corrieron.** Claude.

- Hoy: el doctor no compara lo instalado con lo publicado; este mismo
  repositorio estuvo atrasado sin que nada lo dijera. Los handlers de
  eventos son silenciosos por contrato, así que una falla de tracking se ve
  igual que "no había nada que hacer".
- Propuesta: el doctor distingue instalado, versión fijada, actualización
  disponible, cableado y verificado. Prueba el cableado de punta a punta con
  un evento sintético sin efectos remotos, con un canal observable para los
  handlers. Un token vencido produce una remediación, nunca un falso éxito.
- Detalle: [entrada 89](dogfooding.md:798),
  [`cli.py:1517`](../packages/spec-kit-linear/src/spec_kit_linear/cli.py:1517).

**16. Nombres, payload y notas de versión.** Claude.

- Hoy: la portada del README dice `/speckit.code-review` y el comando
  instalado se llama `/speckit-code-review-code-review`. El ZIP del preset
  viaja con sus tests. Ni el preset ni los bundles tienen changelog, así que
  `bundle update` no cuenta qué cambió. Nada verifica que los comandos del
  preset coincidan con sus renders instalados.
- Propuesta: elegir el nombre canónico del comando de revisión y que toda
  la documentación diga el real. Separar el payload de las herramientas de
  desarrollo. Changelog del preset y de los bundles dentro de la publicación.
  Una aserción en CI que compare cada comando con sus renders.
- Detalle: [`README.md:18`](../README.md:18), entradas
  [64](dogfooding.md:537), [60](dogfooding.md:509), [91](dogfooding.md:822),
  [96](dogfooding.md:907), [65](dogfooding.md:552).
- Decisión: pendiente, el nombre del comando, porque cambia la superficie
  de la extensión.

### F. Varios devs y monorepos

**17. Un ejecutor activo por feature, con relevos explícitos.** Codex.

- Hoy: el README presenta la asignación en Linear como el semáforo contra
  pisadas, pero `implement` toma la primera tarea sin marcar sin mirar a
  quién está asignada. Dos personas podrían arrancar la misma tarea.
- Propuesta: antes de implementar, comparar el assignee de la tarea con el
  usuario de Linear y con el trabajo abierto de la feature; una diferencia
  produce un diagnóstico útil, no un bloqueo mudo. Varios devs trabajan en
  features distintas; el relevo dentro de una feature es explícito:
  reasignar en Linear y adoptar el draft (punto 2).
- Detalle: [`README.md:239`](../README.md:239),
  [`README.md:401`](../README.md:401),
  [`task_base.py:43`](../presets/default/scripts/python/task_base.py:43).

**18. Monorepos: prefijos en las ramas y un team por repositorio.** Claude.

- Hoy: upstream permite ramas con prefijo (`autor/app/003-slug`) para
  monorepos. De nuestro lado, algunas rutas lo aceptan y otras no: el
  patrón de tarea, el listado del stack y la línea de sesión esperan que la
  rama empiece por `NNN-`. Un consumidor que use el prefijo dejaría de
  proyectar a Linear sin ningún aviso. Además `speckit-linear.yml` vincula
  un solo team de Linear por repositorio.
- Propuesta: un único contrato de nombres, aplicado en inicio, descubrimiento
  de PRs, propagación, merge, guards, revisión y Linear, con fixtures
  compartidas. Mientras no se necesite más de un team, declararlo y que el
  onboarding detecte la incompatibilidad.
- Detalle:
  [`git-config.yml:10`](../.specify/extensions/git/git-config.yml:10),
  [`discovery.py:13`](../packages/spec-kit-linear/src/spec_kit_linear/discovery.py:13),
  [`work_state.py:63`](../packages/spec-kit-linear/src/spec_kit_linear/work_state.py:63),
  [`_common.py:149`](../presets/default/scripts/python/_common.py:149).
- Decisión (2026-09-11): se soporta el prefijo de upstream
  (`autor/app/003-slug`); un solo team por repositorio hasta que haya una
  necesidad real.

### G. Decisiones de política

**19. Cuántos PRs pueden esperar revisión.** Claude.

- Hoy: la 005 dejó 28 PRs apilados para una sola persona revisando raíz
  primero.
- Opciones: un tope de PRs listos sin mergear por feature, tras el cual el
  loop espera; o sin tope, manteniendo el trabajo nocturno, pero mostrando
  carga y antigüedad para que el humano decida cuándo revisar.
- Decisión (2026-09-11): sin tope; se muestran carga y antigüedad.

**20. La regla del doble del forecast.** Claude.

- Hoy: la regla frenó tareas por estimaciones mal hechas por diseño (T026
  en 91 contra 80, T021 en 972 contra 10) y cuatro presupuestos quedaron
  excedidos tras correcciones, por decisión humana. En la 004 frenó dos veces.
- Propuesta: no tocarla todavía. Medir las interrupciones que produce y
  decidir con esa cifra si el forecast pasa a advertencia y solo frena el
  techo de 400.
- Detalle: entradas [70](dogfooding.md:604), [83](dogfooding.md:720),
  [94](dogfooding.md:869); [`plan.md:348`](plan.md:348).

## Orden recomendado

La lógica: primero lo que corrige estados y evidencia sin cambiar nada
visible; después lo que hace que "seguí" funcione sobre esos estados;
luego lo nativo y el recorrido completo; al final instalación, higiene y
coordinación. Las decisiones que cambian convenciones se toman antes,
porque la fase 1 depende de ellas.

| Fase | Puntos | Por qué en este lugar |
| --- | --- | --- |
| 0. Antes de empezar | actualizar y cablear este repositorio (chore en curso); pendientes de aceptación de la 005; PRs a upstream con sus pruebas de agente; decisiones de los puntos 8, 11, 16, 18 y 19; plan de GitHub para el 9 | sin la 18 no se toca la derivación; sin la 8 no se unifica el presupuesto; el repo tiene que correr con lo que va a probar |
| 1. Linear correcto | 1 | el mayor impacto, sin cambiar la superficie; base de todo lo demás |
| 2. Revisión y presupuesto | 6, 8 | sin una revisión que pueda cerrarse no hay "listo" verificable |
| 3. Loop reanudable y listo verificable | 2, 7, 5 | aquí nacen los scripts de cierre de tarea y de feature |
| 4. Nativo | 9, 10, 11, 12, 13 | independientes del loop; casi todo es doctor y configuración |
| 5. Recorrido completo | 3, 4 | usa el "qué sigue", el gate por aprobación y los títulos de Linear |
| 6. Instalación y actualización | 14, 15, 16 | cierra con una sola verificación y un repo que sabe decir que está atrasado |
| 7. Coordinación | 17 | depende de la identidad de Linear y del draft adoptable |
| Releases (ronda propia) | detectar promociones pendientes; `doctor --fix` aplicando los settings de GitHub | ya diseñado; espera el plan Business |

Cada fase tiene su propio archivo en [`reliability/`](reliability/), con
la problemática, la solución, sus decisiones y la entrada sugerida para
`/speckit.specify`; la fase 0 se ejecuta sin spec-kit.

Cada punto aterriza por el loop: una tarea, una rama, un PR, merge humano.
Lo de la fase 0 son chores. Las fases 4 y 5 pueden correr en paralelo con
la 3, porque no tocan los scripts del loop salvo el cierre de tarea en el 12.

## Cómo sabremos que mejoró

Por lo que se ve en el día a día, no por tests verdes:

- Intervenciones por tarea, separando decisiones de producto de
  recordatorios y reparaciones de Git.
- Recuperación: cuántas interrupciones se retoman con el mismo comando y
  cuánto tarda volver a trabajo útil.
- Exactitud de Linear: estados correctos sobre estados proyectados,
  incluyendo varios PRs y caídas de red.
- Revisión útil: cobertura de los archivos relevantes, causas de
  "inconcluso", hallazgos que solo necesitaban corregir el formato.
- Presupuesto: frecuencia y causa de las paradas y de las excepciones.
- Instalación: tiempo hasta el primer PR revisable, en instalación limpia y
  en actualización.
- Relevo humano: PRs listos, antigüedad y tiempo hasta la revisión.

El dogfooding de la ronda cubre instalación desde lo publicado, cambio de
agente a mitad de tarea, draft existente, GitHub caído, fix dentro de un
stack y relevo entre devs, y distingue ejecución real de agentes de
validación de archivos generados.

## Qué no vamos a hacer

Una extensión nueva; aprobar o mergear desde el harness; refrescar la rama
de feature sola sin una política acordada; cambiar la convención de ramas
salvo lo que decida el punto 18; tocar la regla del doble antes de medirla;
un script de bootstrap; adaptadores de canal; reimplementar lo que un
ruleset, un hook de Git, CODEOWNERS o la integración GitHub y Linear ya
hacen.

## Decisiones que necesitan respuesta

Respondidas el 2026-09-11; el detalle vive en
[`reliability/00-groundwork.md`](reliability/00-groundwork.md).

| Decisión | Punto | Respuesta |
| --- | --- | --- |
| Métrica del presupuesto y alcance del packet | 6, 8 | unificar primero, medir después; sin líneas netas |
| Aprobación del plan | 11 | el envío del plan al repositorio es la aprobación; no hay gate adicional |
| Nombre del comando de revisión | 16 | pendiente |
| Prefijos de monorepo y teams por repositorio | 18 | se soporta `autor/app/003-slug`; un team por repositorio por ahora |
| Tope de PRs en espera | 19 | sin tope, mostrando carga y antigüedad |
| Plan de GitHub y gestor de hooks | 9 | verificar en el doctor antes de aplicar |
| Crear `In Review` desde `onboard` | 13 | sí, y lo que Linear necesite para quedar bien configurado |
| Canal de depuración de los handlers | 15 | una línea en stderr bajo una variable |
| Refresh automático desde el trunk | 5 | solo mostrar |
| Número de ronda | | los números de ronda y de `specs/` son independientes; el plan registra la ronda por nombre |
| Idioma | | `AGENTS.md` suma `reliability.md` y `reliability/` a las excepciones |

## Anexo: qué queda abierto en el dogfooding

- Con decisión pendiente, cubiertas por este documento: 60 y 64 (16); 67,
  69 y 78 (8); 74, 79, 82 y 90 (6); 75 (8 y 10); 87 (3); 89 (15); 91 y
  96 (16).
- Sin cubrir todavía: 72, un frontmatter YAML inválido que falla en
  silencio; encaja en el doctor (14) o como parche a upstream.
- Etiquetas desactualizadas: 32 y 34 dicen "entregada" pero ya están
  publicadas; 92 dice pendiente pero la 94 la cerró, con el residuo del
  piso `>=1.0.1` en el `preset.yml` fuente.
- Reglas que dependen de que alguien se acuerde: 31 y 96 (renders), 35 (la
  receta de bump a mano, punto 14), 40 (el slug generado dos veces), 39 (la
  excepción de la checklist); 33 y 65 quedan aceptadas.
- Upstream: 18 y 36 los cubre el parche 0005; 22, 23 y 84 el diseño del
  resolver; 38 el 0006; 66 el 0007; 73 el 0008; 95 el 0009; 24 y 25 los
  parches 0002 y 0003. Siguen sin dueño 72 y la segunda mitad de la 55.
