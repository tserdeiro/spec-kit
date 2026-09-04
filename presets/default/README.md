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
specify preset add --from https://github.com/tserdeiro/spec-kit/releases/download/bundles%2Fv0.14.0/default-0.8.0.zip
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
work-item PRs target the GitHub default.

## One stack

Delivery keeps one linear stack per feature: `speckit.implement` and
`speckit.pr` derive each task's base from the feature's open, ready task
PRs, never a second stack. Merging stacked PRs root-first is the human's
step, not the loop's.

## Closing the run

The loop never merges: a run ends with every task PR `ready for review`
and its fresh review closed. The human merges root-first; only on an
explicit request does the agent act — `git worktree prune`, then
`gh pr merge <n> --merge --delete-branch` for each PR, root-first. A
revert travels through the same loop as any task, its commit subject
`revert(scope): subject`, never `git revert`'s default.
