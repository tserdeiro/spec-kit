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
  feature task; `<team>-<n>-*` names a work item (bug or chore).
- Otherwise take the first unchecked task in the active feature's
  `tasks.md` (the active feature comes from `.specify/feature.json`), and
  say which one you picked.

## 2. Guarantee the branch invariant

The branch is what projects the task to *In Progress*; it must exist and
follow the convention before the PR opens. The PR's **base** follows from
what is delivered: a feature task targets its **feature branch**
(`NNN-slug`); a work item targets the **repository's default branch**
(`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).

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
  task, the repository's default branch for a work item), not the plan.
- **Verification evidence** — the task's **Evidence** commands with their
  actual, truthful results; run them if you have not.
- **Risk and delivery** — honest risks; `Stack: standalone`, or
  `PR N of M, stacked on #<PR>` when this task stacks.
- **Review focus** — the one question the human reviewer should answer.

## 5. Open the draft

```bash
gh pr create --draft --base <base> --title "<type(scope): subject>" --body "<the body>"
```

`<base>` is the feature branch for a feature task, the repository's
default branch for a work item.

Title in English, `type(scope): subject`, matching the branch's commit.
Report the PR URL, then remind the flow: the next steps are the
self-review (`/speckit.code-review`), `ready for review`, and the state
projection (`/speckit.linear.push` or its lifecycle hook).
