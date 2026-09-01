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

## 2. Guarantee the branch invariant

The branch is what projects the task to *In Progress*; it must exist and
follow the convention before the PR opens. Resolve the repository's
**delivery base** once:

```bash
# delivery-base-resolution:start
delivery_base=$(awk '$1 == "trunk:" && $2 !~ /^#/ { value=$2; gsub(/^"|"$/, "", value); print value; exit }' \
  .specify/extensions/git/git-config.yml 2>/dev/null || true)
if [ -z "$delivery_base" ]; then
  delivery_base=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
fi
# delivery-base-resolution:end
```

An explicit non-empty `trunk:` value wins; otherwise the GitHub default
applies. The PR's **base** follows from what is delivered: a feature task
targets its **feature branch** (`NNN-slug`); a work item — and the feature
PR itself — targets `<delivery-base>`.

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
exists, report its URL and state, change nothing, and stop. Re-running
this command must never duplicate.

## 4. Fill the canonical body

Use `.github/PULL_REQUEST_TEMPLATE.md` — every section, in its order:

- **Work item** — Tracker: the Linear identifier for the task (from
  `/speckit.linear.status`; `N/A` if the feature is not projected) or the
  issue key itself for a work item — written as **`Fixes WOR-123`** so
  Linear's GitHub integration links the PR and transitions the issue
  natively. Spec Kit evidence: `specs/<feature>/` for a task;
  `.specify/bugs/<slug>/` for a bug; `N/A (chore)` otherwise.
  Requirements: the task's **Traces** line. Tasks: the `T###`, or
  `N/A (short path)`.
- **Outcome** — the task's outcome line, phrased as the delivered result.
- **Changes** — summarize the real diff against the PR's base branch
  (`git diff <base>...HEAD --stat` — the feature branch for a feature
  task, `<delivery-base>` for a work item), not the plan.
- **Verification evidence** — the task's **Evidence** commands with their
  actual, truthful results; run them if you have not.
- **Risk and delivery** — honest risks; `Stack: standalone`, or
  `PR N of M, stacked on #<PR>` when this task stacks.
- **Review focus** — the one question the human reviewer should answer.

**Feature-PR variant** — when step 1 resolved the feature PR, the same
sections carry the feature, not a task: Work item — the Linear Project
(from `/speckit.linear.status`) and its Issue range (`T001–T###`); Spec
Kit evidence — `specs/<feature>/`; Requirements — the spec's FR range;
Tasks — all of them. Outcome — state that this is the **spec-review
gate**: draft while tasks deliver into the feature branch, ready when
every task is checked, closed by a human **merge commit**; reviewing it
now approves the spec and plan. Changes — the committed artifacts.
Verification evidence — the Linear projection result. Risk — implementation
lands task by task into this branch, each PR reviewed before merge; Stack —
`feature PR; task PRs stack into this branch`. Review focus — do the tasks
cover the spec with nothing missing and nothing extra?

## 5. Open the draft

```bash
gh pr create --draft --base <base> --title "<type(scope): subject>" --body "<the body>"
```

`<base>` is the feature branch for a feature task; the repository's
`<delivery-base>` for a work item **and for the feature PR itself**.
The feature PR's title is `feat(<area>): <feature outcome>`.

Title in English, `type(scope): subject`, matching the branch's commit.
Report the PR URL, then remind the flow: the next steps are the
self-review (`/speckit.code-review`) and `ready for review` — Linear's
native integration transitions the issue on that event, and
`/speckit.linear.push --apply` reconciles anything it missed.
