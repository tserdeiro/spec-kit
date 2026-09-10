# Upstream patches

Patches against the pinned upstream tag (`v1.0.4`,
`cb610277fdea781fcfa83d20522c2db37c94068d` per `versions.lock.yml`), one
per upstream pull request. Each is prepared by this distribution's own
rounds, in a scratch clone outside this checkout, and opened by a human
from their own fork of `github/spec-kit` — this source checkout never
forks or vendors upstream (`AGENTS.md`). These files are the hand-off.

## Patches this round prepares

1. `0001-preserve-installed-integrations-on-force-reinit.patch` — register
   extension and preset commands for every previously installed
   integration, and preserve `installed_integrations` and each key's
   `integration_settings`, across `specify init --here --force` (T020).
2. Remove `git add .` from `auto-commit.sh` (T021). **Pending**: prepared
   once T021 lands.
3. Stop registering the sixteen `git.commit` hooks when the git
   extension's `auto_commit.default` is `false` (T022). **Pending**:
   prepared once T022 lands.

## Opening a patch upstream

A human, credentialed step — outside any task's scope:

```bash
gh repo fork github/spec-kit --clone
cd spec-kit
git checkout -b <branch> v1.0.4
git am /path/to/docs/upstream/0001-....patch
gh pr create --repo github/spec-kit --fill
```

Record the resulting PR URL in `specs/005-developer-experience/tasks.md`,
the task's Completion evidence.
