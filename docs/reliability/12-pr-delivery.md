# 12. Crear y actualizar PRs con una rutina idempotente

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 10 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [05](05-work-item-branches.md), [06](06-product-approval.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

La rutina asume un template que el consumidor quizá no tiene, y deja commit,
push, creación y actualización del cuerpo en instrucciones al agente.

## Resultado y alcance

El doctor valida el template de PR y `--fix` lo crea cuando falta,
preservando personalizaciones existentes. Extraer la mecánica de `pr` a
scripts: resolver tipo y base, commit acotado autorizado, push, crear/adoptar
el draft y actualizar las secciones gestionadas del cuerpo.

Usar la plantilla canónica del consumidor y resultados capturados de
verificación. El agente redacta el contenido editorial. Preservar ediciones
humanas y describir qué secciones son gestionadas. Mantener separados
no-existe, cerrado/mergeado y consulta no verificable.

La variante de feature respeta la aprobación previa de la entrada 06.
Esta extracción consolida la rutina existente, no crea un segundo camino.

## Aceptación

Un consumidor limpio recibe un PR completo. Repetir tras commit, push o
respuesta incierta conserva el mismo PR. Un PR existente puede actualizarse
sin borrar contenido humano. Un fallo de consulta no crea un duplicado;
cambios ajenos no se incluyen en el commit.

## Referencias

[PR](../../presets/default/commands/pr.md),
[resolución de base](../../presets/default/scripts/python/pr_create.py),
[template](../../.github/PULL_REQUEST_TEMPLATE.md),
[packet](../../packages/spec-kit-code-review/src/spec_kit_code_review/packet.py).
