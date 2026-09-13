# 15. Incorporar assess al recorrido de producto

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 11 y adopción de assess de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [06](06-product-approval.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Las ideas todavía abiertas necesitan un lugar para madurar antes de generar
artefactos de entrega. Upstream ya ofrece ese recorrido.

## Resultado y decisiones

Componer la extensión oficial `assess` en la distribución para el rol
product, con el pin y los mecanismos nativos de catálogo y bundle.
Está presente en el upstream fijado a v1.0.4; verificar sus assets contra ese
pin, no consumir directamente la rama main.

Usar sus artefactos en `.specify/assessments/<slug>/` para discovery.
Son notas editables que pueden compartirse por Git bajo la autorización
aplicable. `go` habilita pasar a `specify`; no equivale a aprobación humana
del plan técnico ni publica archivos automáticamente.

El recorrido es proporcional: `assess` se utiliza cuando hay una idea por
evaluar; un fix definido o una entrada de confiabilidad ya diagnosticada
puede ir directamente a su camino de entrega. Usar las etapas nativas
necesarias, sin imponer cinco comandos a todo trabajo.

## Aceptación

El bundle product entrega los comandos nativos de assess para las
integraciones seleccionadas. Una idea se refina y entrega a `specify`
con su evidencia. Su `go` no permite saltar la aprobación de producto.
El camino de un fix conocido conserva su entrada directa.

## Referencias

[Assess upstream](https://github.com/github/spec-kit/blob/v1.0.4/extensions/assess/README.md),
[pin](../../versions.lock.yml), [bundles](../../bundles),
[visión](../vision.md).
