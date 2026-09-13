# 13. Solicitar revisión y mostrar el siguiente paso al revisor

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 12 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [08](08-task-close.md), [12](12-pr-delivery.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Marcar un PR listo no garantiza que se solicite revisión. El contexto actual
está pensado para quien implementa y puede decir al revisor que espere el merge.

## Resultado y alcance

Usar CODEOWNERS existente cuando corresponda o solicitar revisores configurados
mediante GitHub después de verificar el cierre de tarea. Detectar solicitudes
existentes y evitar duplicarlas. La elección de responsables pertenece al
equipo; no inferirla simplemente de quién no es el autor.

Adaptar el siguiente paso a identidad, asignación y revisión solicitada.
Si no hay revisor configurado o faltan permisos, mostrar la acción humana
concreta. La solicitud de revisión no sustituye la revisión humana ni
autoriza el merge.

## Aceptación

Repetir el cierre no duplica solicitudes. Autor, revisor solicitado y tercero
reciben instrucciones coherentes. Un único maintainer recibe un diagnóstico
útil sin intentar aprobar su propio PR. La prueba de notificaciones reales
se registra en la entrada 23.

## Referencias

[Reporting](../../packages/spec-kit-linear/src/spec_kit_linear/reporting.py),
[next action](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py),
[implement](../../presets/default/commands/implement.md).
