# 07. Retomar la tarea interrumpida sin duplicar trabajo

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 2 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [05](05-work-item-branches.md), [06](06-product-approval.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El inicio de tarea siempre crea una rama y rechaza cualquier draft abierto,
incluido el de la misma tarea. Una interrupción obliga a recuperar el estado
manualmente.

## Resultado y alcance

Derivar el próximo paso desde rama local/remota, cambios sin commitear, PR,
ledger y sesión de revisión. Adoptar el trabajo existente de la tarea antes
de buscar la primera casilla pendiente: una tarea marcada puede seguir
teniendo cierre pendiente en su draft.

Continuar después de crear rama, commit, push, PR o revisión; verificar cada
resultado remoto antes de repetir una operación de resultado incierto.
Explicar y detener discrepancias, drafts ajenos o stacks ambiguos. Conservar
cambios sin commitear y respetar un checkout ocupado por otro trabajo.
Aplicar el mismo principio al camino corto de bugs y chores.

La base sigue siendo la cabeza del stack ready o la rama de feature. Un
único trabajo en curso por ejecutor y stacks sin tope; no introducir un
orquestador nuevo ni automatizar la creación de worktrees en esta entrega.

## Aceptación

Interrumpir en cada paso y repetir produce la misma rama y PR, sin pérdida
de archivos ni nuevos commits vacíos. Una casilla marcada con draft pendiente
se retoma. Una rama solo remota se adopta. La ambigüedad deja diagnóstico
antes de mutar Git.

## Referencias

[Inicio de tarea](../../presets/default/scripts/python/task_base.py),
[PR](../../presets/default/scripts/python/pr_create.py),
[implement](../../presets/default/commands/implement.md).
