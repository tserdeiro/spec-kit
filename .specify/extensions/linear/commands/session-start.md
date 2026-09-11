---
name: session-start
description: Internal session_start event handler; not a user command.
scripts:
  py: scripts/python/session_start.py
---

# Spec Kit Linear session-start (internal)

This is the extension's `session_start` runtime-event handler, declared in
`extension.yml` and resolved by the dispatcher's on-disk file-stem fallback —
its name is deliberately undotted and equal to this file's stem. Never invoke
it directly.

It reconciles Linear (`push --hook`, with `--current` added on a feature/task
branch only -- a work item is feature-independent) and then prints one
context line naming the current branch's Linear state and the next command
to run — or nothing at all when the branch matches no recognized shape, or
the extension is unconfigured.
