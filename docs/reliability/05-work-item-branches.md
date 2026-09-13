# 05. Iniciar bugs y chores con el nombre nativo de Linear

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 4, 13, 18 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [01](01-linear-truth.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El agente pide el título de una Issue que Linear ya conoce. El reconocimiento
actual acepta solo algunos de los formatos de rama que Linear ofrece.

## Resultado y decisiones

- Con una Issue vinculada, obtener título, contexto y `branchName` mediante
  la API nativa. Validar el nombre con Git y usarlo sin reconstruir el template.
- Conservar `NNN-slug` para features y `NNN-T###-slug` para sus tareas.
  Las tareas se enlazan a Linear mediante el cuerpo del PR existente.
- Sin Linear configurado, conservar el camino por clave de Issue aportada
  por el usuario y la convención predeterminada `team-numero-slug`; pedir
  solo los datos que no estén disponibles.
- Adoptar primero la rama/PR existente de esa Issue, aunque cambie el título,
  formato o responsable. Una caída de una integración configurada no se
  confunde con ausencia de configuración ni genera otra rama.
- Resolver una única Issue inequívoca desde el nombre, usando las capacidades
  nativas cuando corresponda. Aplicar el contrato conjuntamente en inicio,
  PRs, revisión, guards y proyección; no crear un registro paralelo de identidades.

## Aceptación

Cubrir los formatos de Linear mostrados por su API, ausencia de configuración,
error de red, rama existente y título cambiado. Comprobar el comportamiento
del prefijo de usuario con las credenciales usadas. Los fixtures de features
y stacks conservan la convención anterior; bugs y chores siguen el camino
corto sin exigir spec ni plan.

## Referencias

[Bugfix](../../presets/default/commands/bugfix.md),
[chore](../../presets/default/commands/chore.md),
[work items](../../packages/spec-kit-linear/src/spec_kit_linear/work_items.py),
[cliente Linear](../../packages/spec-kit-linear/src/spec_kit_linear/linear_client.py),
[esquema oficial](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql).
