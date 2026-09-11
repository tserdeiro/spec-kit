# Fase 6: instalar y actualizar sin sorpresas

Parte de la [propuesta de confiabilidad](../reliability.md). Puntos 14, 15 y
16. Depende de dos decisiones de la fase 0 (nombre del comando de revisión;
canal de depuración de los handlers).

## Problemática

- Los pasos de instalación están repartidos entre instalación, onboarding,
  doctors de paquetes y el espejo de skills. Actualizar exige dos comandos
  extra porque `bundle update` no vuelve a cablear los hooks. El doctor son
  182 líneas de prosa que el agente ejecuta y resume.
- El doctor no compara lo instalado con lo publicado: este repositorio
  estuvo atrasado sin que nada lo dijera. Los handlers de eventos son
  silenciosos, así que una falla de tracking se ve igual que "no había
  nada que hacer".
- Lo que dejó ver el upgrade del PR #116 ([entrada 102](../dogfooding.md)):
  el cableado de Claude no viaja en el commit; los hooks fijan el
  intérprete encontrado al instalar y sin `uv sync` el guard no arranca y
  no avisa; `extension update` registra skills solo para la integración
  activa.
- La portada del README dice `/speckit.code-review` y el comando instalado
  se llama `/speckit-code-review-code-review`. El ZIP del preset viaja con
  sus tests. Ni el preset ni los bundles tienen changelog. Nada verifica
  que los comandos coincidan con sus renders instalados.

## Solución recomendada

- Un `doctor.py` en el preset que corra los sub-doctors y arme las seis
  categorías siempre igual, ejecutable sin agente. `--fix` corre
  `integration upgrade` cuando el cableado quedó viejo y regenera el
  cableado local que no viaja. Se adoptan el wizard de `onboard` y las
  reparaciones de GitHub del diseño de releases. Termina siempre en "listo
  para trabajar" o en una acción humana concreta.
- El doctor distingue instalado, versión fijada, actualización disponible,
  cableado y verificado. Verifica que el intérprete fijado en los archivos
  de hooks existe, no solo el marcador. Prueba el cableado de punta a punta
  con un evento sintético sin efectos remotos, con un canal observable para
  los handlers. Un token vencido produce una remediación, nunca un falso
  éxito.
- Proponer a upstream que `bundle update` refresque los eventos, después de
  confirmarlo en el CLI.
- Elegir el nombre canónico del comando de revisión y que toda la
  documentación diga el real. Separar el payload de las herramientas de
  desarrollo. Changelog del preset y de los bundles dentro de la
  publicación. Una aserción en CI que compare cada comando con sus renders.

## Decisiones que necesitan respuesta

Decidido el 2026-09-11: el canal de depuración de los handlers (una línea
en stderr bajo una variable). Pendiente: el nombre canónico del comando de
revisión.

## Anexo

- Evidencia: [`README.md:404`](../../README.md:404),
  [`README.md:429`](../../README.md:429),
  [`doctor.md:73`](../../presets/default/commands/doctor.md:73),
  [`doctor.md:126`](../../presets/default/commands/doctor.md:126),
  [`releases.md:48`](../releases.md:48),
  entradas [85](../dogfooding.md:743) y [89](../dogfooding.md:798),
  [`cli.py:1517`](../../packages/spec-kit-linear/src/spec_kit_linear/cli.py:1517);
  [`README.md:18`](../../README.md:18), entradas [60](../dogfooding.md:509),
  [64](../dogfooding.md:537), [65](../dogfooding.md:552),
  [91](../dogfooding.md:822) y [96](../dogfooding.md:907).
- Aceptación: actualizar un consumidor termina con comandos y eventos
  coherentes en un solo comando; un handler que nunca corrió no aparece
  como verificado; los comandos de la portada existen en la integración
  usada; un render desactualizado falla en CI; la versión publicada explica
  qué cambia y cómo actualizar.

## Entrada para /speckit.specify

Cerrar instalación y actualización con una sola verificación: doctor como
script con seis categorías, detección de versión atrasada y de cableado no
verificado, prueba sintética de los handlers, regeneración del cableado
local, nombre canónico del comando de revisión, payload sin tests,
changelog de preset y bundles, y chequeo de renders en CI.
