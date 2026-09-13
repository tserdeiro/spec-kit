# 10. Validar mensajes de commit desde Git

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 9 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

El guard del agente no cubre commits desde una terminal o un agente sin
eventos. El CI de convenciones de este repositorio no está instalado en los
consumidores.

## Resultado y alcance

Ofrecer desde el doctor el hook nativo `commit-msg` con la misma regla del
guard. `doctor` diagnostica; `doctor --fix` instala la reparación local.
Respetar `core.hooksPath`, hooks existentes y gestores como husky o lefthook:
usar su mecanismo de composición y evitar sobrescrituras.

Compartir la regla entre guard y hook, o comprobar equivalencia sobre los
mismos casos. El hook es una validación local, no una garantía del servidor.
La instalación usa el doctor actual; el agregador ejecutable llega en la
entrada 17.

## Aceptación

El mismo mensaje válido o inválido recibe el mismo resultado desde Git y el
guard. Instalar dos veces no duplica ejecuciones. Los hooks previos siguen
funcionando. Una integración que no puede repararse de forma segura devuelve
una acción concreta.

## Referencias

[Guard y doctor](../../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py),
[doctor del preset](../../presets/default/commands/doctor.md),
[convenciones locales](../../.github/workflows/conventions.yml).
