# 17. Ejecutar el diagnóstico de instalación sin agente

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 14 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [10](10-native-commit-check.md), [11](11-native-github-rules.md), [12](12-pr-delivery.md), [14](14-linear-onboarding.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El doctor agrega resultados mediante prosa. Su respuesta depende de que el
agente ejecute todos los pasos y clasifique correctamente los fallos.

## Resultado y alcance

Un doctor ejecutable en el preset compone los sub-doctors existentes y
produce diagnóstico estructurado más resumen legible, ejecutable también
desde la terminal. Conservar las seis categorías del producto y ubicar
explícitamente las comprobaciones añadidas en las entradas anteriores.

`doctor` solo lee. `--fix` aplica las reparaciones disponibles y autorizadas,
reutilizando las interfaces existentes. Las escrituras remotas conservan
su autorización específica; un flag no concede permisos de administrador.

Resolver y comprobar el intérprete realmente usado por cada script.
Distinguir componente ausente por rol, prerrequisito fallido y comprobación
no verificable. La salida saludable requiere evidencia, no solo ausencia
de un error. El script distribuido funciona sin este checkout fuente.

## Aceptación

El mismo setup produce el mismo resultado desde terminal y agente.
Un sub-doctor fallido o no verificable nunca queda oculto por otro que pasa.
`--fix` es idempotente y las reparaciones se vuelven a comprobar.
Cada rol valida solo sus componentes requeridos.

## Referencias

[Doctor actual](../../presets/default/commands/doctor.md),
[Linear CLI](../../packages/spec-kit-linear/src/spec_kit_linear/cli.py),
[code-review CLI](../../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py).
