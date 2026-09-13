# 16. Mostrar y ejecutar el siguiente paso de producto

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 3, 4 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [05](05-work-item-branches.md), [06](06-product-approval.md), [12](12-pr-delivery.md), [15](15-native-discovery.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

La línea de contexto aparece recién cuando existe plan.md. Antes no distingue
una feature recién especificada de una instalación incompleta. El recorrido
depende de recordar comandos.

## Resultado y alcance

Mostrar contexto para spec sin plan, plan sin tareas, tareas sin análisis y
producto pendiente de aprobación o publicación. Hacer opcional plan.md solo
en las rutas que pueden operar antes del plan; conservar los requisitos de
implementación y proyección que lo necesitan.

Cada fase ejecuta sus verificaciones y continúa cuando tiene los datos y
la autorización requeridos. Al terminar tasks/analyze, presentar el cierre
de producto de la entrada 06; publicar el gate solo después de aprobación.
Usar los handoffs nativos y el preset existente.

Ofrecer una instrucción concreta y breve, ampliable según lo que pida el
usuario, sin intentar adivinar su experiencia ni crear perfiles junior/senior.
Bugs y chores reutilizan los datos resueltos en la entrada 05.

## Aceptación

Una feature recién especificada muestra un siguiente paso útil. Faltan datos,
configuración o aprobación: cada caso produce un diagnóstico distinto.
Producto aprobado termina con el link del gate sin otro comando manual.
Producto no aprobado conserva sus borradores locales.

## Referencias

[Parser](../../packages/spec-kit-linear/src/spec_kit_linear/parser.py),
[CLI y contexto](../../packages/spec-kit-linear/src/spec_kit_linear/cli.py),
[tasks](../../presets/default/commands/tasks.md),
[plan template](../../presets/default/templates/plan-template.md).
