# 11. Verificar las garantías de entrega en GitHub

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 9 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Un guard local no protege las ramas compartidas frente a operaciones desde
otros clientes. Configurar reglas incompatibles puede impedir integrar y
limpiar un stack.

## Resultado y alcance

El doctor inspecciona rulesets y settings efectivos de GitHub: protección
contra force-push en ramas compartidas y compatibilidad con merge commits y
borrado de ramas integradas. Respetar las reglas existentes, los permisos y
las capacidades del plan del consumidor.

Presentar remediaciones concretas mediante mecanismos nativos. Las escrituras
remotas requieren la autorización aplicable y una configuración concreta
revisable; `doctor` siempre es de lectura. Checks exigidos y revisión humana
siguen la política del equipo. Las reparaciones de promociones y releases
permanecen en su ronda propia.

## Aceptación

Fixtures cubren configuración compatible, reglas que impiden la limpieza,
permisos insuficientes y lecturas fallidas. El diagnóstico distingue falta
de capacidad de falta de configuración. La prueba remota de rechazo de
force-push y merge ordenado queda para la entrada 23.

## Referencias

[Doctor](../../presets/default/commands/doctor.md),
[merge ordenado](../../presets/default/scripts/python/merge_root_first.py),
[visión](../vision.md), [releases](../releases.md).
