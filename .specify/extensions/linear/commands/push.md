---
name: speckit.linear.push
description: Project the current feature state into Linear.
---

# Spec Kit Linear push

`push` renders the difference between the repository's feature artifacts and
Linear, then either previews it or applies it:

```bash
bash .specify/extensions/linear/scripts/bash/run.sh push --current
bash .specify/extensions/linear/scripts/bash/run.sh push --current --apply
```

The projection is Feature Project → `Txxx` Issues. Titles clip at
Linear's limits — Project names at 80 characters, Issue titles at 255 —
deterministically, with a warning naming the artifact line to shorten. A Project appears when the
feature is planned and an Issue per task when tasks are generated.

Each Issue's workflow state is re-derived on every push from a fresh
observation. The paginated pull-request scan is `complete`, `failed`, or
`incomplete`; only `complete` permits lifecycle derivation, including verified
empty. Failed or incomplete scans preserve existing remote states, including
items absent from partial output, and report the uncertainty.

Complete evidence uses open draft → open ready → merged precedence, yielding
*In Progress* → *In Review* → *Done*. The lowest PR number is the witness
within a rank; closed unmerged PRs are ignored. Checkbox and branch rules apply
only when no open or merged PR exists. States are written only where the
`lifecycle` config section has an ID.

Preview is the default; `--apply` writes. Both are idempotent: the plan is the
difference, so applying it twice is a no-op and every mutation is preceded by
a fresh read of the exact resources it touches. A task created during
uncertainty omits `stateId`, leaving its workflow state to Linear's configured
default. The repository is the sole
authority — `push` never changes assignees after creation, project leads,
members, human comments, or any local file.

Bugs and chores take the short path: the Issue is created in Linear by a
person, and `push` only projects its workflow state. A branch named after the
Issue key — `<team key>-<number>` with an optional `-suffix`, case-insensitive,
e.g. `wor-123-fix-crash` — is the convention; the same PR rules then apply,
minus the checkbox (nothing observed means the Issue is left untouched). No
Issue is ever created, retitled, re-described, labelled, or assigned here.
Every `push` reconciles every observed work item, whatever feature is
selected and even when the repository has no feature at all; all keys are
resolved in one batched query, and a branch naming an Issue that does not
exist is a warning, never an operation.

Select the feature with `--feature NNN`, `--current`, or `--all`; with none of
them a single feature directory is used. `--feature`/`--current` always
resolve or fail; every other selection projects no feature at all in a
repository that has no `specs/NNN-*` directory.

`--hook` marks a lifecycle-hook invocation. It is not meant for manual use: a
missing configuration or `hooks.lifecycle_enabled: false` makes it a clean
no-op (exit `0`) instead of an error, and it applies what it renders unless
`hooks.auto_apply: false`. The extension's runtime-event handlers — `session_start` and
`post_tool_use` — run `push --hook` this way, in-process, with no
`run.sh`/`uv run` indirection (`--current` added on a feature/task branch,
the bare selector on a work-item branch).
