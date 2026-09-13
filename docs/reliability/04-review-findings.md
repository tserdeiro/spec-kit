# 04. Corregir categorías inválidas sin perder hallazgos

Entrada para una única spec de la [ronda de confiabilidad](../reliability.md).
Origen: puntos 6 de la propuesta anterior. Ejecutar después de la entrada
anterior del índice; sin dependencias funcionales adicionales.
Usar este archivo completo como entrada de `/speckit.specify`.

## Problema

Un error de categoría rechaza el archivo de hallazgos. Las categorías
admitidas ya están publicadas en el packet; repetir la lista en más prosa
no resuelve por sí mismo el fallo.

## Resultado y alcance

Usar el catálogo del validador como fuente para las instrucciones del
revisor. Si falla la categoría, devolver el índice, valor inválido y valores
admitidos, y permitir que el revisor corrija el mismo resultado dentro de la
sesión vigente. Conservar archivo original y evidencia de la corrección.

La validación sigue siendo estricta: nunca descartar un hallazgo ni cambiar
su severidad para obtener un resultado verde. Una corrección ambigua o que
sigue siendo inválida deja un diagnóstico explícito y no cierra la revisión.
La corrección de formato no exige repetir el análisis del código.

## Aceptación

Una categoría desconocida se corrige preservando contenido, ubicación y
severidad del hallazgo y el resto del archivo. Un archivo todavía inválido
no se acepta. Las instrucciones y el validador admiten las mismas categorías.

## Referencias

[Findings](../../packages/spec-kit-code-review/src/spec_kit_code_review/findings.py),
[sesiones](../../packages/spec-kit-code-review/src/spec_kit_code_review/session.py),
[dogfooding, entrada 90](../dogfooding.md).
