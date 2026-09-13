# 14. Completar la configuración necesaria de Linear

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 13 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Un team sin estado de revisión requiere configuración manual y no puede
representar el recorrido completo. El onboarding debe explicar qué falta
y aplicar solo lo autorizado.

## Resultado y alcance

Extender el onboarding nativo existente para previsualizar y, con autorización
del administrador, crear el estado de revisión ausente y completar su mapeo.
Reutilizar estados equivalentes ya configurados; preservar nombres,
automatizaciones y recursos existentes distintos de lo solicitado.

Acotar las operaciones a la configuración que el flujo necesita: estados,
binding y mapeo PR→estado. Reusar los mecanismos existentes para labels y
vistas. Mantener un team por repositorio; explicar una selección incompatible.
El doctor diagnostica o remite al onboarding cuando falta autorización.

## Aceptación

Team sin estado de revisión: preview exacto, apply autorizado y segunda pasada
sin operaciones. Team ya configurado: conservación del estado y mapeo.
Permisos insuficientes: diagnóstico y cero escrituras fuera de alcance.
La aceptación real sobre Linear queda para la entrada 23.

## Referencias

[Cliente Linear](../../packages/spec-kit-linear/src/spec_kit_linear/linear_client.py),
[CLI](../../packages/spec-kit-linear/src/spec_kit_linear/cli.py),
[README de Linear](../../packages/spec-kit-linear/README.md),
[reconciliación observada](../../validation/linear-observed-reconciliation.md).
