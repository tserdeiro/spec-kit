# 02. Contexto de revisión suficiente con ledgers grandes

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 6 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El packet incorpora artefactos completos y trunca cada uno a un máximo
configurable de 60.000 bytes. Un ledger grande puede omitir la tarea
relevante y obliga a declarar la revisión inconclusa.

## Resultado y alcance

Construir el contexto desde el candidato y el alcance revisado: bloque de
tarea, estrategia de entrega, requisitos relacionados y contexto compartido
necesario. Ofrecer acceso al resto de los artefactos y registrar qué contenido
se revisó. Cubrir también una revisión de feature completa, varias tareas y
el camino corto sin ledger; no asumir siempre una única tarea.

Mantener explícitos los límites configurables. Una selección deliberada de
contexto suficiente se distingue de una omisión accidental. La referencia
a un archivo no demuestra que se haya leído.

## Aceptación

Una tarea pequeña al final de un ledger mayor que el límite obtiene contexto
completo sin cargar todo el ledger. Se conserva el diagnóstico inconcluso
cuando falta contenido necesario. Los requisitos compartidos, los cambios
de varias tareas y el PR final de feature tienen cobertura verificable.

## Referencias

[Packet](../../packages/spec-kit-code-review/src/spec_kit_code_review/packet.py),
[veredicto](../../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py),
[configuración](../../packages/spec-kit-code-review/config/speckit-code-review.template.yml),
[dogfooding, entrada 79](../dogfooding.md).
