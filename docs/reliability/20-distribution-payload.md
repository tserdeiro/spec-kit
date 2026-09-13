# 20. Publicar un payload limpio con cambios identificables

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 14, 15, 16 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; dependencias funcionales: [17](17-executable-doctor.md), [19](19-command-conformance.md).
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El preset distribuye herramientas de desarrollo innecesarias. Preset y
bundles no explican sus cambios y el doctor no distingue versión instalada,
pin fijado y actualización disponible.

## Resultado y alcance

Separar assets de runtime de tests y herramientas de desarrollo en el
empaquetado existente. Publicar changelog del preset y bundles dentro de
la publicación actual, con cambios y pasos de actualización comprobables.
Usar las fuentes canónicas de versión y los catálogos nativos.

El doctor informa instalado, fijado, disponible y no verificable. Una versión
nueva disponible no cambia automáticamente el pin. Alinear el requisito
mínimo del preset con las capacidades que usa y mantener publicación,
checksums y composición reproducibles.

Cerrar con evidencia las etiquetas históricas de dogfooding ya resueltas.
Esta spec mejora el empaquetado actual; promociones, detección de releases
pendientes y automatización de settings de esa ronda permanecen en releases.

## Aceptación

Un ZIP contiene los assets necesarios y excluye tests; un consumidor temporal
funciona desde ese ZIP. Versiones, manifests y changelog concuerdan.
Sin red, el doctor informa lo instalado y lo que no pudo consultar.
Una actualización disponible no se instala sola.

## Referencias

[Build](../../scripts/release/build-release.sh),
[bundles](../../scripts/release/build-bundles.sh),
[preset](../../presets/default/preset.yml),
[pin](../../versions.lock.yml),
[dogfooding, entradas 32, 34, 60, 65, 91 y 92](../dogfooding.md).
