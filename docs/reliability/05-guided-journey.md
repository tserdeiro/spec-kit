# Fase 5: el recorrido completo, pidiendo solo decisiones

Parte de la [propuesta de confiabilidad](../reliability.md). Puntos 3 y 4.
Usa lo que dejan las fases 3 y 4: el "qué sigue", el gate por aprobación y
los títulos de Linear. Puede correr en paralelo con la fase 3.

## Problemática

- La línea que orienta al empezar cada sesión solo existe desde que hay
  `plan.md`; antes desaparece sin explicar nada, igual que si Linear no
  estuviera configurado.
- El template dice que cerrar la fase de producto abre el gate, pero ningún
  comando lo hace: producto tiene que acordarse de correr `/speckit.pr`.
- Para arrancar un bug hay que pegarle al agente el título de la Issue,
  aunque Linear ya lo tiene.
- El recorrido de producto se presenta como una lista de comandos para
  recordar; el flujo no distingue a quién le habla.

## Solución recomendada

- El "qué sigue" cubre también las fases previas: spec sin plan, plan sin
  tareas, tareas sin gate. `plan.md` pasa a opcional para la línea de
  contexto, como ya lo es `tasks.md`.
- El comando `tasks` abre el PR draft del gate al terminar y devuelve el
  link para aprobar.
- Cada fase corre sus propias verificaciones y sigue sola cuando tiene lo
  que necesita; cuando necesita al humano, muestra la decisión concreta y
  su consecuencia.
- `bugfix` y `chore` toman título y contexto de la Issue a partir de su
  clave.
- Un junior recibe una línea explicando el próximo paso; alguien con
  experiencia, solo estado, resultado y bloqueo. Mismo workflow, sin
  perfiles ni flags.

## Decisiones que necesitan respuesta

Ninguna.

## Anexo

- Evidencia:
  [`parser.py:279`](../../packages/spec-kit-linear/src/spec_kit_linear/parser.py:279),
  [`cli.py:1318`](../../packages/spec-kit-linear/src/spec_kit_linear/cli.py:1318),
  [entrada 87](../dogfooding.md:767),
  [`tasks-template.md:17`](../../presets/default/templates/tasks-template.md:17),
  [`README.md:142`](../../README.md:142),
  [`bugfix.md:33`](../../presets/default/commands/bugfix.md:33),
  [`chore.md:34`](../../presets/default/commands/chore.md:34),
  [`linear_client.py:763`](../../packages/spec-kit-linear/src/spec_kit_linear/linear_client.py:763).
- Aceptación: una feature recién especificada muestra el siguiente paso;
  producto termina con un link revisable; una clave de bug alcanza para
  arrancar; el mismo recorrido sirve para un junior y para alguien
  experimentado.

## Entrada para /speckit.specify

Completar el recorrido guiado: "qué sigue" para las fases de producto,
apertura automática del gate al cerrar `tasks`, título y contexto de bugs y
chores desde la clave de Linear, y cada fase que verifica y continúa sola,
pidiendo al humano solo decisiones.
