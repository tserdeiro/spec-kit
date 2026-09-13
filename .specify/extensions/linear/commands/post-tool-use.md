---
name: post-tool-use
description: Internal post_tool_use event handler; not a user command.
scripts:
  py: scripts/python/post_tool_use.py
---

# Spec Kit Linear post-tool-use (internal)

This is the extension's `post_tool_use` runtime-event handler, declared in
`extension.yml` with matcher `Bash` and resolved by the dispatcher's on-disk
file-stem fallback — its name is deliberately undotted and equal to this
file's stem. Never invoke it directly.

It reads the native payload from stdin; when the Bash command it carries
matches `git push` or `gh pr create`/`ready`/`merge`, it reconciles Linear
(`push --hook`, the same branch-shape-dependent selector `session-start`
uses). Every other command, a non-Bash payload, or malformed or empty stdin
is a silent no-op. It prints nothing for successful, missing, disabled,
irrelevant, or malformed invocations. Configured reconciliation or partial
application failures emit sanitized stderr warnings, and the handler always
exits `0`.
