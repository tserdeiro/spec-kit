# Upstream patches

Patches against the pinned upstream tag (`v1.0.4`,
`cb610277fdea781fcfa83d20522c2db37c94068d` per `versions.lock.yml`), one
per upstream pull request. Each is prepared by this distribution's own
rounds, in a scratch clone outside this checkout, and opened by a human
from their own fork of `github/spec-kit` — this source checkout never
forks or vendors upstream (`AGENTS.md`). These files are the hand-off.

## Patches this round prepares

1. `0001-preserve-installed-integrations-on-force-reinit.patch` — preserve
   `installed_integrations` and each key's `integration_settings` across
   `specify init --here --force` (T020). Only the re-initialized
   integration is re-registered: a non-active one is left alone, the way
   upstream's `install`/`upgrade` already treat it (issue #2948), so this
   distribution's doctor mirror stays the answer for the second agent.
2. `0002-scope-auto-commit-git-add.patch` — replace `auto-commit.sh`'s (and
   its PowerShell and Python twins') blanket `git add .` with a scoped
   stage (T021): `.specify/memory/` for `after_constitution`; the whole
   working tree (`git add -A`, unchanged from before this scoping) for
   `before_implement`/`after_implement`, since implementation code lands
   wherever the project puts it, never only inside the feature directory;
   the active feature's directory (`specs/<feature>/`, resolved via
   `SPECIFY_FEATURE_DIRECTORY` or `.specify/feature.json`) for every other
   event; and a tracked-only `git add -u` fallback when no feature
   directory can be resolved — never an untracked file outside those
   paths.
3. `0003-gate-git-commit-hooks-on-auto-commit-config.patch` — give each of
   the sixteen optional `git.commit` hooks a `condition:
   "config.auto_commit.<event>.enabled == 'true'"` (T022), and make it
   matter: all ten `templates/commands/*.md` files (twenty `before_`/
   `after_` hook blocks) now evaluate a hook's `condition` the same way
   `HookExecutor._evaluate_condition` does, replacing the old instruction
   to skip any hook that has one, and `docs/reference/extensions.md`
   documents the same rule. The two mandatory hooks (`git.initialize`,
   `git.feature`) are untouched; they carry no `auto_commit` key to gate
   on. Tests pin the gated manifest, the live `should_execute_hook` gate,
   and that every template's evaluation wording is identical with the old
   skip sentence gone. The expression still honors only the per-event
   key, not `auto_commit.default`'s "enable for all" shorthand (the
   grammar has no disjunction), and a mistyped condition still degrades
   silently to never. It closes the no-op prompt dogfooding entry 25
   names, now with a live per-event prompt through the stock templates.

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
