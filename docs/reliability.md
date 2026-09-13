# Confiabilidad del workflow: specs en orden de ejecución

Diseño acordado el 2026-09-11. Esta ronda deriva de [vision.md](vision.md)
y está registrada en [plan.md](plan.md). Los documentos describen trabajo
por implementar; no son evidencia de entrega. Reemplazan las propuestas
por fases y conservan la trazabilidad a sus puntos originales.

## Cómo ejecutarla con Spec Kit

Cada archivo numerado de [reliability/](reliability/) es la entrada de
**una única spec**, con un resultado acotado, alcance, aceptación y referencias.
Usar el archivo completo en `/speckit.specify`, por ejemplo:

```text
/speckit.specify Implementar lo definido en docs/reliability/01-linear-truth.md.
Leer también las decisiones comunes de docs/reliability.md.
```

Ejecutar las specs secuencialmente. Estos números ordenan la ronda; Spec Kit
asigna el número real bajo `specs/` mediante su mecanismo nativo.
Cada spec recorre clarify, plan, tasks, analyze y entrega por tareas.
La aprobación y publicación de producto siguen el contrato vigente hasta
que la entrada 06 entregue el nuevo comportamiento; este índice no lo
implementa por sí mismo.

Cada tarea conserva su rama y PR; el merge es humano. Mantener cada spec
centrada en su resultado: los detalles de las entradas siguientes no se
incorporan por anticipado. Si el plan revela una feature demasiado grande,
dividirla en resultados utilizables y reordenar este índice **antes** de
generar las tareas; evitar dividir un cambio que necesita ser atómico para
que el producto siga funcionando.

Los tests apropiados acompañan a cada entrega. La validación real integral
queda pendiente en 23 y no bloquea la primera spec. La revisión de Markdown
se resolvió en el PR #179, fuera de esta ronda.

## Orden aprobado

| Orden | Entrada para generar la spec | Resultado |
| --- | --- | --- |
| 01 | [Estados de Linear basados en una observación completa](reliability/01-linear-truth.md) | Estados sin falsos completados. |
| 02 | [Contexto de revisión suficiente con ledgers grandes](reliability/02-review-context.md) | Contexto suficiente sin cargar todo el ledger. |
| 04 | [Corregir categorías inválidas sin perder hallazgos](reliability/04-review-findings.md) | Corrección de formato con hallazgos íntegros. |
| 05 | [Iniciar bugs y chores con el nombre nativo de Linear](reliability/05-work-item-branches.md) | Datos y ramas de bugs/chores desde Linear. |
| 06 | [Publicar el plan después de la aprobación de producto](reliability/06-product-approval.md) | Publicación posterior a aprobación explícita. |
| 07 | [Retomar la tarea interrumpida sin duplicar trabajo](reliability/07-resumable-loop.md) | La misma rama y PR después de una interrupción. |
| 08 | [Cerrar la tarea con revisión y checks vigentes](reliability/08-task-close.md) | Ready respaldado por el candidato actual. |
| 09 | [Cerrar la feature desde el estado real de sus PRs](reliability/09-feature-close.md) | Gate final basado en entregas integradas. |
| 10 | [Validar mensajes de commit desde Git](reliability/10-native-commit-check.md) | Convenciones comprobadas por Git. |
| 11 | [Verificar las garantías de entrega en GitHub](reliability/11-native-github-rules.md) | Protecciones compatibles con el stack. |
| 12 | [Crear y actualizar PRs con una rutina idempotente](reliability/12-pr-delivery.md) | Template y publicación de PRs idempotentes. |
| 13 | [Solicitar revisión y mostrar el siguiente paso al revisor](reliability/13-review-routing.md) | Revisor solicitado y siguiente paso pertinente. |
| 14 | [Completar la configuración necesaria de Linear](reliability/14-linear-onboarding.md) | Team configurado con operaciones autorizadas. |
| 15 | [Incorporar assess al recorrido de producto](reliability/15-native-discovery.md) | Assess oficial para ideas por madurar. |
| 16 | [Mostrar y ejecutar el siguiente paso de producto](reliability/16-guided-journey.md) | Contexto y continuidad desde las primeras fases. |
| 17 | [Ejecutar el diagnóstico de instalación sin agente](reliability/17-executable-doctor.md) | Diagnóstico reproducible sin agente. |
| 18 | [Diagnosticar y reparar el cableado de eventos](reliability/18-event-wiring.md) | Cableado reparable y observabilidad veraz. |
| 19 | [Comprobar nombres, frontmatter y renders de comandos](reliability/19-command-conformance.md) | Nombres y renders comprobados automáticamente. |
| 20 | [Publicar un payload limpio con cambios identificables](reliability/20-distribution-payload.md) | Assets limpios, versiones y changelog coherentes. |
| 21 | [Coordinar la asignación y el relevo de una feature](reliability/21-developer-handoff.md) | Asignación y relevo explícitos. |
| 23 | [Validar el workflow estable desde la distribución publicada](reliability/23-live-acceptance.md) | Evidencia real del workflow publicado. |

## Decisiones comunes

- **Convención de ramas:** feature `NNN-slug`; tarea `NNN-T###-slug`.
  Bugs y chores usan el `branchName` nativo de su Issue. Sin Linear
  configurado, conservan el formato predeterminado por clave de Issue.
  Un fallo de conexión no equivale a ausencia de configuración. Adoptar
  siempre el trabajo existente antes de crear otra rama.
- **Identidad:** números de feature únicos por repositorio y un team de
  Linear. Se conserva la convención anterior, sin un registro paralelo de
  identidades ni ampliar en esta ronda los prefijos de features/tareas.
  Las tareas se enlazan a Linear mediante el cuerpo del PR.
- **Discovery:** usar `assess` oficial cuando haya una idea por madurar.
  Sus notas pueden compartirse por Git; su `go` habilita especificar, no
  aprueba un plan técnico. Un fix definido entra directamente a su recorrido.
- **Cierre de producto:** refinar spec, plan y tareas localmente; analizar;
  obtener aprobación humana explícita; entonces commitear, publicar y abrir
  el gate. `implement` exige ese gate y deja de crearlo automáticamente.
  Un cambio de alcance vuelve a producto antes de publicar.
- **Cierre de tarea:** cambios y evidencia de tests → commit final → push →
  revisión del candidato → checks → ready. La revisión cubre HEAD y
  merge-base; su resultado vive en la sesión y el PR. Inicialmente todo
  cambio posterior exige revisión vigente, también en el ledger.
- **Autonomía:** automatizar la mecánica dentro de la autorización otorgada;
  aprobación de producto, revisión final y merge son humanos. Los cambios
  de contrato necesarios son parte de 06, no permisos concedidos por leer
  una propuesta.
- **Stacks y coordinación:** sin tope de PRs listos; mostrar carga y
  antigüedad. Un ejecutor activo por feature, con relevo explícito.
  Mostrar divergencia respecto del trunk, sin merge automático.
- **Doctor:** lectura por defecto; reparación con `--fix` dentro de sus
  permisos. Preservar configuraciones humanas y usar mecanismos nativos.
  Las escrituras remotas conservan su autorización específica.
- **Eventos:** diferenciar assets, cableado, prueba sintética del
  dispatcher/handler y evento observado desde el agente. Solo el último
  acredita ejecución real del agente; handlers sin secretos en sus logs.
- **Nombre de revisión:** sigue pendiente elegir la superficie pública,
  distinguiendo nombre lógico de representación por integración. Resolver
  en 19; no bloquea las entradas anteriores.

## Estado de partida y trabajo separado

El consumidor de este repositorio fue actualizado con el PR #116 y los
commits pendientes ya fueron enviados, según confirmó el usuario.
No queda una fase 0 que exija repetir esas operaciones.

La [reconciliación observada](../validation/linear-observed-reconciliation.md)
ya ejercitó operaciones reales de Linear y handlers invocados por el
dispatcher. Su propia tabla distingue lo observado de lo pendiente: PRs
GitHub, In Review, Codex y disparo desde el agente no quedan acreditados
por esa prueba. Conservar esta evidencia y completar lo pendiente en 23
contra las versiones que se publiquen.

Los [parches upstream](upstream/README.md) y sus
[pruebas manuales](upstream/manual-tests.md) tienen un circuito independiente;
abrir sus PRs no es requisito para empezar esta ronda. 0003/0004 permanecen
aparcados detrás del [resolver portátil](upstream/hooks-runtime-design.md).
[Releases](releases.md) sigue siendo una ronda propia: esta reorganización
no incorpora promociones ni su automatización de settings.

## Cobertura de la propuesta y del dogfooding

| Tema original | Entradas de esta ronda |
| --- | --- |
| 1: verdad de Linear | 01 |
| 2: recuperación y cierres | 07–09 |
| 3 y 4: recorrido de producto y datos de Issues | 05, 06, 16 |
| 5: divergencia respecto del trunk | 09 |
| 6: contexto y categorías | 02, 04 (Markdown: PR #179) |
| 7: evidencia vigente antes de ready | 08 |
| 9: garantías nativas | 10, 11 |
| 10: template y mecánica de PRs | 12 |
| 11: aprobación de producto | 06, 15 |
| 12: revisión solicitada | 13 |
| 13: onboarding de Linear | 05, 14 |
| 14–16: instalación, observabilidad y payload | 17–20 |
| 17: varios desarrolladores | 21 |
| 18: nombres y teams | 05, 21; convención anterior conservada |
| 19: carga de revisión sin tope | 09, 21 |
| Aceptación pendiente de 005 y de esta ronda | 23 |

El frontmatter inválido de la entrada 72 del dogfooding queda asignado a
19 para validación en la distribución; cualquier corrección del parser
nativo va a upstream. La higiene de versiones y etiquetas históricas
queda en 20. Las entradas 31/96 (renders), 40 (slug repetido), 87 (contexto)
y 89/102/103 (eventos) quedan cubiertas por 19, 05, 16 y 18 respectivamente.

La segunda parte de la entrada 55 (AVAILABLE_DOCS y ejemplo de categorías
de analyze) sigue en el backlog upstream; no autoriza editar el baseline.
La política de excepciones de checklist de la entrada 39 sigue vigente:
esta ronda no la cambia implícitamente.

## Cómo evaluar la mejora

En la aceptación final registrar intervenciones mecánicas por tarea,
tiempo de recuperación, exactitud de Linear, cobertura y causas de revisión
inconclusa, tiempo de instalación y espera
de revisión. Los tests por spec demuestran sus contratos; la validación
publicada acredita el recorrido real.
