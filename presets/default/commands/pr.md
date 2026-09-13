---
name: speckit.pr
description: Guarantee the task branch and open the canonical draft pull request from the feature artifacts.
---

# Spec Kit PR

This command resolves, observes, and publishes one delivery. `gh` must be
authenticated (`gh auth status`). If authentication or an observation fails,
stop with the exact failure; a failed lookup is never evidence that a resource
is absent.

## 1. Resolve what is being delivered

- If the user named a task (`T###`) or an issue key (`WOR-123`-style), use it.
- Otherwise derive it from the current branch: `NNN-T###-*` is a feature task;
  `<team>-<n>-*` is a work item; the feature branch itself (`NNN-slug`) with
  its selected feature is the **feature PR**, whether its artifacts are local
  drafts or already published.
- Otherwise take the first unchecked task in the active feature's `tasks.md`
  (the active feature comes from `.specify/feature.json`) and report it.
- A named task is also `pr_create.py`'s second argument; without one, that
  script verifies the ledger's first unchecked task.

## 2. Guarantee the branch invariant

The branch must exist and follow its convention before a PR opens. A feature
task targets the open task PR it stacks on, otherwise its feature branch. A
work item resolves the delivery base (explicit `trunk:`, otherwise the
GitHub default). The feature PR resolves that same delivery base at creation.

- A correctly named checked-out branch continues.
- On a base or misnamed branch with committed work, create the correctly named
  branch at the current commit (`git switch -c NNN-T###-short-slug`). Never
  rename a branch that has an open PR.
- **Feature publication requires product approval.** Before any feature commit
  or push, confirm clean analysis, present the exact spec, plan, tasks,
  analysis result, and unresolved handoff prerequisites, and receive explicit
  human approval of that exact set. Publication permission is separate from
  technical approval of the plan and tasks. If a material artifact changes,
  stop for fresh analysis and approval. Completion checkboxes and completion
  evidence alone preserve the approved handoff; task IDs and task intent stay
  stable. In a fresh session, an observed OPEN PR whose branch, base, and
  artifacts still match that published handoff reuses the existing approval;
  it does not ask for approval again. A missing gate or unpublished/materially
  changed artifact requires the approval flow before any publication write.

Task and work-item branches retain their existing commit flow.

Run exactly one delivery route: a feature branch follows steps 3–5; a task or
work-item branch follows step 6. Do not run both routes for one invocation.

## 3. Observe before every feature mutation

The feature variant uses the existing branch, Git, GitHub PR, and Linear
projection as its handoff record. Before a commit, push, PR create, or PR body
update, capture all of this state:

```bash
git status --short
git rev-parse HEAD
git diff --name-only
git diff --cached --name-only
git ls-remote --heads origin <branch>
gh pr view <branch> --json number,url,state,isDraft,headRefName,baseRefName,headRefOid,body
```

Classify each command separately:

- A successful PR read is the resource. Only `state: OPEN` is reusable; an
  `isDraft` value is reported and preserved. `CLOSED` or `MERGED` is a closed
  gate and stops for a human decision; never reopen it or create a second gate.
- A PR read that exits nonzero with the exact `no pull requests found for
  branch ...` result is confirmed absence. Any other nonzero result,
  authentication error, timeout, malformed JSON, or repository/head mismatch
  is **publication lookup failed**. Stop without a create, edit, commit, or
  push.
- `git ls-remote` with no matching ref is confirmed remote-branch absence. A
  failed remote lookup is **publication lookup failed**, not absence.

Do not treat an existing local commit or a lost command response as proof that
the operation needs repeating. After an interrupted or ambiguous write,
observe the affected resource first and retry only the missing operation while
the observed branch/head/PR is unchanged:

- If the feature files are already in `HEAD`, do not make a second commit. If
  the feature diff is empty, do not commit.
- If the remote branch OID equals `HEAD`, do not push. After a lost push
  response, reread `git ls-remote`; retry only when it confirms the old remote
  OID and the local head is unchanged.
- If PR creation has a lost or ambiguous response, rerun `gh pr view` first.
  Reuse an observed OPEN PR; create only after confirmed absence. A failed
  lookup never authorizes a retry.
- If an edit has a lost or ambiguous response, reread the OPEN PR body. Update
  only when the body still differs; stop if the reread is ambiguous.

## 4. Prepare the canonical body from the final publication snapshot

Use `.github/PULL_REQUEST_TEMPLATE.md` in its exact section order:

1. **Work item** — the Linear Project and Issue range from the final
   `/speckit.linear.status` result, or `N/A` when that result confirms no
   projection; `specs/<feature>/`; all feature requirements; and all task IDs.
2. **Outcome** — state that this is the spec-review gate for the exact
   artifacts presented and explicitly product-approved before publication.
3. **Changes** — the approved feature diff, including its local draft, index,
   and worktree paths, against the delivery base. The effective committed diff
   is recalculated after publication before any PR mutation.
4. **Verification evidence** — clean analysis and the actual final Linear
   preview, apply, and status results, including any failed or incomplete
   prerequisite.
5. **Risk and delivery** — honest risks, human merge ownership, and
   `feature PR; task PRs stack into this branch`.
6. **Review focus** — whether the tasks cover the approved spec completely.

Write the candidate body to a temporary file with its real newlines. Do not
inline a body string or use an alternate template. Prepare the approved scope
and effective `git diff <base>...HEAD` while keeping the body local; create or
edit a PR only after the final Linear snapshot in step 5. Compare an OPEN PR
only by approved scope, effective head/base, and semantic evidence: stable
Linear IDs, states, assignees, synchronization result, and prerequisite set.
When those values are unchanged, reuse its body **verbatim**, including
historical successful publication evidence. Do not recompose it for style or
replace it with retry counters, timestamps, or zero-operation text. Update it
only when a stable value changed, then reread `state`, `baseRefName`,
`headRefName`, and `body`. An exact body match schedules no write.

## 5. Publish the approved handoff once

For a feature branch, execute this sequence after approval and before reporting
success:

1. Observe branch, local head, remote head, and PR as in step 3. Stop on a
   closed gate or failed lookup.
2. Stage only the feature directory. Inspect the staged feature paths and any
   pre-existing unrelated staged paths. Recheck that the staged feature content
   is exactly the approved content and that no material edit occurred. Commit
   with the scoped operation below only when the feature has an uncommitted
   diff; unrelated staged content remains untouched:

   ```bash
   git diff --cached --name-only
   git commit --only -m "docs(specs): <feature>" -- specs/<feature-directory>/
   ```
3. Observe `HEAD` and the remote ref again. Push with
   `git push -u origin <branch>` only when the remote OID is absent or differs.
   Read back the remote OID after a successful or ambiguous push.
4. Observe the PR again. If it is absent, resolve the base with `pr_create.py`
   without creating the PR; if it is OPEN, use its observed `baseRefName`.
   Recompute the Changes section from the effective commit and keep the
   candidate body local:

   ```bash
   git diff "$base"...HEAD --stat
   ```

5. Run the existing Linear projection and capture one final snapshot for the
   body. Review the preview, apply it through its existing authorization, and
   read status after either success or failure:

   ```bash
   bash .specify/extensions/linear/scripts/bash/run.sh push --current
   bash .specify/extensions/linear/scripts/bash/run.sh push --current --apply
   bash .specify/extensions/linear/scripts/bash/run.sh status --current
   ```

   The final snapshot is the preview result, the apply result when attempted,
   and the post-apply status. Compare only stable IDs, states, assignees,
   synchronization result, and prerequisite set when deciding whether the body
   changed. A retry with zero operations, new counters, timestamps, or retry
   text does not replace historical successful publication evidence. A failed
   or incomplete preview/apply/status, unsynchronized projection, or
   unassigned executable task is recorded as a visible handoff prerequisite;
   it never becomes readiness by inference. Preserve the Git and PR publication
   when Linear requirements fail, and report the exact remaining action.
   Linear's assignment allowlist remains unchanged: this command does not
   assign users, rewrite ownership, or add mutations.
6. Observe the PR after the final Linear snapshot. Compose the body once from
   that snapshot. If absence is confirmed, create one draft PR and reread it.
   If an OPEN PR exists, reuse its body verbatim when scope, stable Linear
   evidence, and prerequisites are unchanged; update it only when a stable
   value differs, then reread it. If it is CLOSED or MERGED, stop for a human
   decision. Use the canonical body file for either mutation:

   ```bash
   gh pr create --draft --base "$base" --title "feat(<area>): <feature outcome>" --body-file "$body_file"
   gh pr edit <number> --body-file "$body_file"
   ```

Two unchanged retries run the same observations and perform zero duplicate
commits, pushes, PR creates, PR body updates, Projects, or Issues. Report the
URL, state, head/base, skipped writes, Linear result, and every remaining
prerequisite. The feature PR stays draft while tasks land, becomes ready only
through the normal human review flow when all tasks are checked, and closes by
a human merge commit.

## 6. Open task or work-item delivery PRs

Resolve the base with `pr_create.py`, using the consumer's `.venv/bin/python`
when it exists, otherwise `python3`:

```bash
python3 .specify/presets/default/scripts/python/pr_create.py <feature|task|work-item> [T###]
```

It prints `base=<name>` and never creates the PR. For task delivery, it checks
the branch task against the named task or the first unchecked ledger task and
selects the open stack head, otherwise the feature branch. For feature and
work-item delivery, it resolves and validates the delivery base. Prepare the
canonical body in a temporary file, using every section of
`.github/PULL_REQUEST_TEMPLATE.md` in its order. For a task, include the
Linear identifier from `/speckit.linear.status`; when present, write it as
`Fixes WOR-123`, otherwise use `N/A`. Include `specs/<feature>/`, the task's
FR/C/SC traces, its `T###`, outcome, real diff against the base, actual
Evidence results, and the stack line. For a bug, include its `Fixes WOR-123`
tracker link and `.specify/bugs/<slug>/` evidence; for a chore use `N/A
(chore)` evidence. Include outcome, actual verification, and delivery risk. Do
not create or edit the PR while preparing this body.

1. Observe the existing PR and remote head first. Reuse only an OPEN PR; a
   CLOSED or MERGED PR is a human decision, and a failed lookup stops without a
   create or push.
2. Push the branch before opening a new PR, using the same observed remote OID
   rule as the feature flow:

   ```bash
   git push -u origin <branch>
   ```

   Read back the remote OID after a successful or ambiguous push.
3. Observe the PR again. If absence is confirmed, create the draft with the
   canonical body file and reread it. If an OPEN PR exists, update its body
   only when the body differs, then reread it. Never inline the body:

   ```bash
   gh pr create --draft --base "$base" --title "<type(scope): subject>" --body-file "$body_file"
   gh pr edit <number> --body-file "$body_file"
   ```

   Report the PR URL, then continue with `/speckit.code-review` and the normal
   ready-for-review flow.
