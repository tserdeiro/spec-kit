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
   the sixteen optional `git.commit` hooks a composite `condition`: the
   enabled per-event key when present; the shared `auto_commit.default`
   applies only when the whole event section is absent (T022) — the same fallback
   `auto_commit.py`'s `_parse_auto_commit_config` already implements by
   hand. Expressing that needs disjunction, so
   `HookExecutor._evaluate_condition` now composes its five atom forms
   (`config.<path>`/`env.<VAR>` with `is set`, `is not set`, `==`, `!=`)
   with `and`, `or`, `not`, and parentheses. All ten
   `templates/commands/*.md` files (twenty `before_`/`after_` hook
   blocks) evaluate a hook's `condition` the same way, replacing the old
   instruction to skip any hook that has one, and
   `docs/reference/extensions.md` documents the same rule. The two
   mandatory hooks (`git.initialize`, `git.feature`) are untouched; they
   carry no `auto_commit` key to gate on. Tests cover the grammar
   (composition, precedence, malformed shapes) and prove
   `should_execute_hook` agrees with `_parse_auto_commit_config` across
   default true/false and explicit per-event overrides. For standalone 0003, malformed conditions still evaluate false. Patch 0004
   rejects malformed conditions in the requested event before evaluation. It closes the
   no-op prompt dogfooding entry 25 names, now with a live
   per-event-or-default prompt through the stock templates.

## Additional dogfooding fixes

| Patch | Outcome | Dogfooding |
| --- | --- | --- |
| `0004-execute-hooks-deterministically.patch` | Resolve lifecycle hooks through the native CLI; return invocation metadata for the agent to execute. Requires 0003. | 22, 23, 84 |
| `0005-clarify-feature-branch-output.patch` | Remove obsolete persistence hints from core and Git-extension branch creators; document `.specify/feature.json`. | 18, 36 |
| `0006-use-native-template-resolver.patch` | Name the installed resolver and consume its composed `TEMPLATE_CONTENT`. | 38 |
| `0007-preserve-command-examples.patch` | Preserve illustrative data fences during command path rewriting. | 66 |
| `0008-preserve-rendered-script-modes.patch` | Repair POSIX shebang `.sh` execute bits in the shared preset installer, including bundles. | 73 |
| `0009-clarify-agentless-integration-install.patch` | Document and test native installation without the agent binary; no new flag. | 95 |

FR-016 now matches 0001: preserve installed integrations and their settings,
while retaining upstream's active-only command registration. The distribution's
doctor owns the other integrations' skill mirrors.

The patches target the exact pinned commit, not the installed CLI. The
revised 0003 uses narrower unchanged context and also applies on upstream
`main` at `c173bf19a6654e3b05386ec3599349a55282b897`. For that base, replace
0004 with [the rebased variant](main/0004-execute-hooks-deterministically.patch);
apply the remaining numbered patches normally. This rebase preserves upstream
changes outside the hook blocks and removes its newer obsolete Cline note tests.

0004 still requires Specify during lifecycle-hook resolution. Its runtime
installation contract remains an open decision; the distribution promises
that cloning a configured consumer supplies the installed workflow. The
current patch must not be treated as a completed portability fix. Apply 0003
before 0004; the remaining patches target the pin independently. The complete
series is checked in numerical order. Patch 0003's test-helper insertion was
moved so it also applies after 0002.

See [verification](verification.md) for the combined results and limitations,
[manual tests](manual-tests.md) for the agent-run evidence upstream's
contributing guide requires (2026-09-11: 0001, 0002 and 0005–0009 pass on
Claude Code; Codex and PowerShell not run), and
[proposed PR bodies](submissions.md) for the reviewable submission text.
The [portable hook runtime proposal](hooks-runtime-design.md) defines the
replacement for 0003/0004, its two-step delivery and acceptance evidence.
It is not implemented by the current patches.

## Opening a patch upstream

A human, credentialed step — outside any task's scope:

```bash
gh repo fork github/spec-kit --fork-name <fork-name> --clone
cd <fork-name>
git checkout -b <branch> v1.0.4
git am /path/to/docs/upstream/0001-....patch
gh pr create --repo github/spec-kit --body-file <reviewed-pr-body.md>
```

Record the resulting PR URL in `specs/005-developer-experience/tasks.md`,
the task's Completion evidence.

Use `git apply` for the complete numbered series (it accepts both mail patches
and plain diffs). Review
the result, then create the human-controlled commit. Rebase submissions onto
upstream's current default branch and rerun the relevant checks before opening
PRs. Preparing and testing a patch does not complete upstream publication or
consumer runtime acceptance.

Use a separate fork name: `tserdeiro/spec-kit` is this independent distribution.
The PR drafts retain this distribution's six canonical sections and include
upstream's Description, Testing and AI Disclosure content as subsections.
AI assistance is disclosed without co-author attribution; the submitting
maintainer must perform and attest their own final review.
