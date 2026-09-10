---
name: speckit.pr
description: Guarantee the task branch and open the canonical draft pull request from the feature artifacts.
---

# Spec Kit PR

One command closes the gap between "the code is done" and "the draft PR is
open, correctly". You (the agent) execute these steps in order and report
each outcome. `gh` must be authenticated (`gh auth status`); without it,
stop and tell the user exactly that — nothing here works by hand-editing
GitHub.

## 1. Resolve what is being delivered

- If the user named a task (`T###`) or an issue key (`WOR-123`-style), use
  it.
- Otherwise derive it from the current branch: `NNN-T###-*` names a
  feature task; `<team>-<n>-*` names a work item (bug or chore); the
  **feature branch itself** (`NNN-slug`) with its artifacts committed
  names the **feature PR** — the spec-review gate that later closes the
  feature (see step 4's feature variant).
- Otherwise take the first unchecked task in the active feature's
  `tasks.md` (the active feature comes from `.specify/feature.json`), and
  say which one you picked.
- A task named this way is also step 5's `pr_create.py` second argument,
  which then verifies the branch against it; without a named task, the
  script verifies against the ledger's first unchecked task instead.

## 2. Guarantee the branch invariant

The branch is what projects the task to *In Progress*; it must exist and
follow the convention before the PR opens. The PR's **base** follows from
what is delivered: a feature task targets the open task PR it stacks on,
else its **feature branch** (`NNN-slug`, resolved from the active
feature); a work item resolves the **delivery base** (explicit `trunk:`,
else the GitHub default) exactly like the feature PR; the feature PR
resolves its **delivery base** at creation time (step 5).

- Correctly named branch checked out → continue.
- On the base branch or a misnamed branch with the work committed →
  create the correctly named branch **at the current commit**
  (`git switch -c NNN-T###-short-slug`) and continue there. Never rename
  a branch that already has an open PR.
- Uncommitted work → commit it on the correctly named branch first, with
  a `type(scope): subject` message in English.

Then push with upstream: `git push -u origin <branch>`.

## 3. Idempotency check

`gh pr view --json url,isDraft 2>/dev/null` on the branch: if a PR already
exists, report its URL and state, change nothing, and stop. `gh pr view`
exiting nonzero with "no pull requests found for branch ..." is the signal
that none exists — continue to step 4, it is not an error to fix.
Re-running this command must never duplicate.

## 4. Fill the canonical body

Use `.github/PULL_REQUEST_TEMPLATE.md` — every section, in its order:

- **Work item** — Tracker: the Linear identifier for the task (from
  `/speckit.linear.status`; `N/A` if the feature is not projected) or the
  issue key itself for a work item — written as **`Fixes WOR-123`** so
  Linear's GitHub integration links the PR and transitions the issue
  natively. Spec Kit evidence: `specs/<feature>/` for a task;
  `.specify/bugs/<slug>/` for a bug; `N/A (chore)` otherwise.
  Requirements: the FR, C, and SC ranges the task traces. Tasks: the
  `T###`, or `N/A (short path)`.
- **Outcome** — the task's outcome line, phrased as the delivered result.
- **Changes** — summarize the real diff against the PR's base branch
  (`git diff <base>...HEAD --stat` — the feature branch for a feature
  task, the delivery base for a work item), not the plan.
- **Verification evidence** — the task's **Evidence** commands with their
  actual, truthful results; run them if you have not.
- **Risk and delivery** — honest risks; `Stack: standalone`, or
  `PR N of M, stacked on #<PR>` when this task stacks.
- **Review focus** — the one question the human reviewer should answer.

**Feature-PR variant** — when step 1 resolved the feature PR, the same
sections carry the feature, not a task: Work item — the Linear Project
(from `/speckit.linear.status`) and its Issue range (`T001–T###`); Spec
Kit evidence — `specs/<feature>/`; Requirements — the spec's FR, C, and
SC ranges; Tasks — all of them. Outcome — state that this is the **spec-review
gate**: draft while tasks deliver into the feature branch, ready when
every task is checked, closed by a human **merge commit**; reviewing it
now approves the spec and plan. Changes — the committed artifacts.
Verification evidence — the Linear projection result. Risk — implementation
lands task by task into this branch, each PR reviewed before merge; Stack —
`feature PR; task PRs stack into this branch`. Review focus — do the tasks
cover the spec with nothing missing and nothing extra?

## 5. Open the draft

Resolve the base with `pr_create.py` — with the consumer's
`.venv/bin/python` when it exists, else `python3` on PATH, the rule
upstream's own `py` scripts follow. Its first argument is the delivery
kind step 1 resolved — `feature` for the feature branch itself
(`NNN-slug`), `task` for a task branch (`NNN-T###-slug`), or `work-item`
for a work-item branch (`<team>-<n>-slug`) — and its second, optional
argument is the task step 1 named, if any:

```bash
python3 .specify/presets/default/scripts/python/pr_create.py <feature|task|work-item> [T###]
```

It resolves the base for the kind. For `feature` and `work-item`, the
**delivery base**: an explicit non-empty `trunk:` key in the consumer's
`.specify/extensions/git/git-config.yml` wins (quotes optional), else the
GitHub default branch, validated with `git check-ref-format --branch`
(`task_base.py`'s `refresh` and `work-item` modes resolve it the same
way). For `task`, the open task-PR stack's head this branch stacks on,
else the feature branch — after checking that the branch's `T###` matches
the named task or the ledger's first unchecked task; a mismatch stops the
script naming both. It prints `base=<name>` only and never runs
`gh pr create` itself — compose and run that call yourself, with the
printed base:

```bash
gh pr create --draft --base "$base" --title "<type(scope): subject>" --body "<the body>"
```

Title in English, `type(scope): subject`, matching the branch's commit —
`feat(<area>): <feature outcome>` for the feature PR. Report the PR URL,
then remind the flow: the next steps are the self-review
(`/speckit.code-review`) and `ready for review` — Linear's native
integration transitions the issue on that event, and
`/speckit.linear.push --apply` reconciles anything it missed.
