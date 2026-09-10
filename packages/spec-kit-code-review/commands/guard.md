---
name: guard
description: Internal pre_tool_use event handler; not a user command.
scripts:
  py: scripts/python/guard.py
---

# Spec Kit Code Review guard (internal)

This is the extension's `pre_tool_use` runtime-event handler, declared in
`extension.yml` with matcher `Bash|Edit|Write` and resolved by the
dispatcher's on-disk file-stem fallback — its name is deliberately undotted
and equal to this file's stem. Never invoke it directly.

It reads the native payload from stdin and blocks, before it takes effect
(exit 2, a one-line message on stderr naming the fix): a `git commit -m`
whose subject does not follow `type(scope): subject`; a `git push` carrying
any form of `--force`; and a `gh pr merge` carrying `--delete-branch`. It
also blocks an `Edit`/`Write` to a `protected_paths` glob while on a task
branch (`NNN-T###-...`). Every other tool, command, or branch — and any
malformed payload or internal failure — is a silent no-op, exit 0.
