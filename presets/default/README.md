# `default` preset

The workflow templates for this distribution: `spec`, `plan`, `tasks`, and
`checklist`, plus the workflow commands (`speckit.pr`, `speckit.bugfix`,
`speckit.chore`, `speckit.doctor`, and the `speckit.specify`,
`speckit.plan`, `speckit.tasks`, `speckit.analyze`, and
`speckit.implement` appends). The `tasks` template carries the
integration-branch delivery conventions — one task in flight per
developer, no parallel tasks; the rest trim the upstream core templates
to what the flow needs.

Phase close: product-phase commands (`specify`, `plan`, `tasks`,
`analyze`) never announce optional hooks — enabled ones run silently,
the rest are skipped — and end by committing the feature's artifacts,
staging `specs/<feature-directory>/` only (unrelated dirty files stay
untouched) and skipping silently when nothing changed.

## Install

```bash
specify preset add --from https://github.com/tserdeiro/spec-kit/releases/download/bundles%2Fv0.15.0/default-0.9.0.zip
```

Local development:

```bash
specify preset add --dev presets/default
specify preset resolve tasks-template
```

The three role bundles (`product`, `developer`, `reviewer`) install this preset
for you; add it directly only when you want the templates without a role.

## Delivery base

Set `trunk: <branch>` in `.specify/extensions/git/git-config.yml` when a
feature targets a branch other than GitHub's default. The feature-PR path
in `speckit.pr` and the first-task refresh in `speckit.implement` use that
explicit value first and fall back to the GitHub default when it is absent
or empty; either way the name must pass `git check-ref-format --branch`.
Task PRs target the open task PR they stack on, else the feature branch;
work-item branches and PRs (`speckit.chore`, `speckit.bugfix`,
`speckit.pr`) use the delivery base too.

## One stack

Delivery keeps one linear stack per feature: `speckit.implement` and
`speckit.pr` derive each task's base from the feature's open, ready task
PRs, never a second stack.

## Budget stop

A task stops before its PR opens — and again before `ready for review`
if the branch grew — when its authored executable lines (the added
lines of the files the review budget counts) pass the smaller of twice
its `Delivery` forecast and 400. A breached forecast or budget is
amended only by a human in the ledger, never inside the PR that
exceeded it.

## Closing the run

The loop never merges: a run ends with every task PR `ready for review`
and its fresh review closed. The human merges root-first; only on an
explicit request does the agent act — `git worktree prune`, then, for
each PR root-first, retargets its base to the feature branch by API
(`gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -f base=<feature-branch>`)
and merges it with `gh pr merge <n> --merge`. Never `--delete-branch`:
it closes the PR stacked above before GitHub retargets it, and the
repository's auto-delete of merged branches does the cleanup instead. A
revert travels through the same loop as any task, its commit subject
`revert(scope): <subject>`, never `git revert`'s default.

## Doctor

`speckit.doctor` mirrors extension and preset skills whole across every
installed integration and appends each core command's preset layer to
its own render, never another's; it also adds the installer's cache and
`.venv` directories to `.gitignore` when not already covered. Both
passes are read-only until `--fix`.

## Scripts

`scripts/python/task_base.py` (Python 3.11+, standard library only) sets
up a task's branch in three modes: `refresh` (once per feature, merges
the delivery base into the feature branch), `task <NNN-T###-slug>`
(branches from the open task stack's top, else the feature branch), and
`work-item <branch-name>` (branches from the delivery base — the mode
`speckit.chore` and `speckit.bugfix` both call, one script for both).
Every mode that creates a branch ends by reconciling Linear
(`push --hook`) when the extension is installed; a failing reconcile is
a warning, never a script failure. Run it with the consumer's
`.venv/bin/python` when it exists, else `python3` on PATH — the rule
upstream's own `py` scripts follow.

`scripts/python/pr_create.py <feature|task|work-item> [named-task]`
resolves and prints the PR's base only — the same delivery-base rule as
`task_base.py`, plus, for a task, the open task-PR stack's head and the
branch-identity check against the named task or the ledger's first
unchecked one. It never runs `gh pr create` itself; `speckit.pr` composes
that call's title and body and runs it with the printed base. Same
interpreter rule as `task_base.py`.

`scripts/python/budget_stop.py <task_id> <base>` stops a task before its
authored executable lines pass the review budget — same rules as the
`budget-stop` block it will replace: the forecast comes from the task's
`Delivery` line (fence-aware; absent or without a `~N` marker defaults to
400), the sum is `git diff --numstat --no-renames <base>...HEAD` excluding
binary rows, the four lockfiles, and eleven doc/asset suffixes, and the
stop is the smaller of twice the forecast and 400. Same interpreter rule
as `task_base.py`.

`scripts/python/stack_propagate.py <fixed_branch>` carries a fix landed
on `fixed_branch` through every open task PR stacked above it — the
same chain `task_base.py`'s `task` mode reads — merging each in stack
order as a `--no-ff` commit (`merge(task): carry the <T### of
fixed_branch> fix into <T### of that branch>`) and pushing it to
`origin`. A merge conflict aborts, names the branch, and exits 2
without touching the branches above it; an empty chain is reported and
exits 0. Same interpreter rule as `task_base.py`.

`scripts/python/merge_root_first.py` (no argument) is the mechanical
half of a human's explicit "yes, merge" on an open task-PR stack: self-
derives the feature branch, runs `git worktree prune`, then walks the
open task PRs root-first, retargeting each to the feature branch by API
(`gh api -X PATCH .../pulls/<n> -f base=<feature-branch>`) before merging
it (`gh pr merge <n> --merge`, never `--delete-branch` — the repository's
auto-delete of merged branches does that cleanup instead). It prints one
`merged #<n> <head>` line per PR, stops naming the PR number on a failing
`gh` call, and reports `nothing to merge on <feature-branch>` on an empty
stack. Same interpreter rule as `task_base.py`.

`scripts/python/ledger_check.py <task_id>` verifies a task's ledger entry
before its PR is marked `ready for review`: the checkbox must be `[x]`
and its `Completion evidence` filled — not empty, not `Pending`
(case-insensitive), and not the template's bracketed sample text — else
it exits 2 naming exactly what is missing. Same interpreter rule as
`task_base.py`.

## Executable blocks

Every marked block in the preset's commands — `first-task-refresh`,
`task-base`, `stack-propagate`, `budget-stop`, `skill-mirror`,
`ignore-entries` — is POSIX shell: `set -e`, no pipeline
that needs `pipefail`, no arrays or other bash-isms. Conformance
extracts and runs each one with `sh` (`dash` on Ubuntu CI); the agent
replaces only the named literals inside it.
