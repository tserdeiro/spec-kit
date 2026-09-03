---
name: speckit-linear-doctor
description: Diagnose the Spec Kit Linear prerequisites. Never mutates Linear.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: linear:commands/doctor.md
---

# Spec Kit Linear doctor

```bash
bash .specify/extensions/linear/scripts/bash/run.sh doctor
bash .specify/extensions/linear/scripts/bash/run.sh doctor --offline --fix
```

Checks the Python/uv runtime, the Git worktree, `.gitignore`, the shared
configuration, the lifecycle section, the `gh` binary (present and
authenticated — a warning only, since pull-request states are optional),
Spec Kit's hook registry, and the local feature artifacts. `--offline` skips
the `gh` authentication check. Without `--offline` it additionally validates the
configured Workspace, Team, Project Label, and Shared Views with queries only;
set exactly one of `LINEAR_API_KEY` or `LINEAR_OAUTH_ACCESS_TOKEN`.

`--fix` applies the mechanical, local-only remediations doctor knows how to
make. It never issues a GraphQL mutation and never touches `specs/`.