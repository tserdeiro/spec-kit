# 19. Comprobar nombres, frontmatter y renders de comandos

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 16 y frontmatter pendiente de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [17](17-executable-doctor.md), [18](18-event-wiring.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

La documentación puede anunciar un comando distinto del instalado; un render
viejo o frontmatter inválido deja instrucciones o launchers rotos.

## Resultado y alcance

Resolver el nombre canónico de revisión antes de implementar esta spec,
contrastando nombre lógico y forma nativa en cada integración. Conservar
los nombres nativos de Specify/Spec Kit y evitar alias propios.

Regenerar con el CLI pinneado, composición de preset y extensiones reales
en consumidores temporales. Comparar cada render con el esperado para esa
integración, normalizando solo valores de entorno identificados. La generación
se automatiza en el flujo de desarrollo; CI comprueba el resultado.

Validar frontmatter con un parser YAML mantenido y verificar placeholders
y launchers. La distribución detecta el defecto en sus assets antes de
publicarlos; una corrección del parser de upstream se tramita aparte.

## Aceptación

Un comando fuente cambiado, render obsoleto, YAML inválido o placeholder
sin resolver falla con archivo y diagnóstico. Las variantes legítimas de
integración no generan falsos positivos. La portada usa el comando realmente
disponible. La comprobación no modifica los assets baseline del checkout.

## Decisión pendiente

El nombre público de revisión sigue pendiente; resolverlo en clarify de esta
spec, sin bloquear las anteriores.

## Referencias

[Preset](../../presets/default/preset.yml),
[conformance](../../scripts/conformance),
[README](../../README.md),
[dogfooding, entradas 31, 64, 72 y 96](../dogfooding.md).
