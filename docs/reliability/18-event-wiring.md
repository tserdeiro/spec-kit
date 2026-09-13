# 18. Diagnosticar y reparar el cableado de eventos

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 14, 15 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [17](17-executable-doctor.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Se observó un bundle instalado sin eventos cableados. Un handler silencioso
que falla se parece a uno que no tenía nada que hacer.

## Resultado y alcance

Comprobar cableado, launchers e intérprete real, y reparar mediante los
comandos nativos de Specify verificados contra el pin. Verificar después
de instalar, clonar y actualizar; preservar ajustes del consumidor y
espejar comandos en las integraciones instaladas mediante los mecanismos
existentes. No implementar otro registro de integraciones.

Separar resultados: assets generados; cableado presente; dispatcher/handler
probado sintéticamente; evento observado desde el agente real.
Una prueba sintética local sin efectos remotos no acredita el último nivel.

Añadir un canal de diagnóstico optativo, una línea en stderr bajo una
variable documentada, sin secretos. Distinguir no-op, error y ejecución;
un token inválido produce remediación, no falso éxito. La corrección nativa
de bundle install/update puede proponerse a upstream por separado.

## Aceptación

Fixtures de instalación limpia, cableado ausente, intérprete inexistente y
upgrade reparan o explican el bloqueo. La prueba sintética no escribe en
Linear ni GitHub. Agentes sin eventos reciben una limitación explícita.
El doctor nunca etiqueta como ejecución real una invocación manual del
dispatcher; esa evidencia se obtiene en la entrada 23.

## Referencias

[Doctor](../../presets/default/commands/doctor.md),
[event conformance](../../scripts/conformance/events-consumer.sh),
[skill mirror](../../presets/default/scripts/python/skill_mirror.py),
[dogfooding, entradas 89, 102 y 103](../dogfooding.md),
[reconciliación observada](../../validation/linear-observed-reconciliation.md).
