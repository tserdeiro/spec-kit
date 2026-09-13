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
- Otherwise derive it from the final path segment of the current branch:
  `NNN-T###-*` is a feature task; `<team>-<n>-*` is a work item; the feature
  branch itself (`NNN-slug`) with its selected feature is the **feature PR**,
  whether its artifacts are local drafts or already published. A configured
  namespace remains in the full branch name and does not change this final
  segment classification.
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

Before either route reads or mutates a PR, anchor GitHub to every push
destination of `origin` with native repository resolution. Do not parse remote
URLs or infer a target from an upstream alias:

```bash
origin_url="$(git remote get-url origin)"
test -n "$origin_url" || { echo "gate-consistency: origin is unavailable" >&2; exit 1; }
push_urls="$(git remote get-url --push --all origin)" || { echo "gate-consistency: cannot read origin push URLs" >&2; exit 1; }
target_url="$(gh repo view "$origin_url" --json url --jq .url)" || { echo "gate-consistency: cannot resolve origin repository" >&2; exit 1; }
test -n "$target_url" || { echo "gate-consistency: GitHub target URL is empty" >&2; exit 1; }
while IFS= read -r push_url; do
  test -n "$push_url" || continue
  push_target="$(gh repo view "$push_url" --json url --jq .url)" || { echo "gate-consistency: cannot resolve an origin push URL" >&2; exit 1; }
  test "$push_target" = "$target_url" || { echo "gate-consistency: origin push URL targets another repository" >&2; exit 1; }
done <<<"$push_urls"
expected_repo="$(gh repo view "$origin_url" --json nameWithOwner --jq .nameWithOwner)" || { echo "gate-consistency: cannot resolve GitHub repository identity" >&2; exit 1; }
test -n "$expected_repo" || { echo "gate-consistency: GitHub repository identity is empty" >&2; exit 1; }
expected_head="$(git branch --show-current)"
```

Every PR read must request `isCrossRepository`, `headRepository`,
`headRepositoryOwner`, `headRefName`, and `baseRefName`. A reusable task or
work-item PR requires `isCrossRepository: false`,
`headRepository.nameWithOwner == expected_repo`, and
`headRefName == expected_head`; its observed base is preserved. A mismatch is
a gate-consistency failure before reuse or push.

Run exactly one delivery route: a feature branch follows steps 3–5; a task or
work-item branch follows step 6. Do not run both routes for one invocation.

## 3. Observe before every feature mutation

The feature variant uses the existing branch, Git, GitHub PR, and Linear
projection as its handoff record. Before a commit, push, PR create, or PR body
update, resolve the expected delivery base and target repository before
adopting any existing PR gate, then capture all of this state:

```bash
paths="$(bash .specify/scripts/bash/check-prerequisites.sh --paths-only)"
feature_dir="$(printf '%s\n' "$paths" | sed -n 's/^FEATURE_DIR: //p')"
selected_feature="$(basename "$feature_dir")"
expected_head="$(git branch --show-current)"
expected_segment="${expected_head##*/}"
test "$expected_segment" = "$selected_feature" || { echo "gate-consistency: current branch segment does not match selected feature" >&2; exit 1; }
pr_python="python3"
test -x .venv/bin/python && pr_python=".venv/bin/python"
base_line="$(GH_REPO="$origin_url" "$pr_python" .specify/presets/default/scripts/python/pr_create.py feature)"
case "$base_line" in
  base=*) base="${base_line#base=}" ;;
  *) echo "gate-consistency: pr_create.py did not resolve a base" >&2; exit 1 ;;
esac
expected_base="$base"
```

Keep the complete `git branch --show-current` value as `expected_head` for Git
and PR operations, and compare only its final path segment with the selected
feature directory basename. Thus `jdoe/web/008-guided-tour` matches
`specs/008-guided-tour`, while `jdoe/web/009-guided-tour` is a
gate-consistency failure. Record `base=<name>` as `expected_base`. The `gh pr
view` query below is against `expected_repo`, the target repository for the
delivery. Its `headRepository.nameWithOwner` must also equal `expected_repo`; a
cross-repo head is never silently adopted as this delivery's gate.

```bash
git status --short
git rev-parse HEAD
git diff --name-only
git diff --cached --name-only
git ls-remote --heads origin <branch>
gh pr view <branch> --repo "$origin_url" --json number,url,state,isDraft,isCrossRepository,headRepository,headRepositoryOwner,headRefName,baseRefName,headRefOid,body
```

Classify each command separately:

- A successful PR read is the resource. Before considering it reusable,
  require `isCrossRepository: false` and
  `headRepository.nameWithOwner == expected_repo`, then compare `headRefName`
  with `expected_head` and `baseRefName` with `expected_base`. Any fork,
  retarget, wrong branch, or other mismatch is a
  **gate-consistency failure**; stop and report it. Never adopt an observed `baseRefName`
  as the expected base. Only `state: OPEN` is reusable when its
  identity matches; its `isDraft` value is reported and preserved. `CLOSED` or `MERGED`
  is a closed gate and stops for a human decision; never reopen it or create a
  second gate.
- A PR read that exits nonzero with the exact `no pull requests found for
  branch ...` result is confirmed absence. Any other nonzero result,
  authentication error, timeout, or malformed JSON is **publication lookup
  failed**. Stop without a create, edit, commit, or push.
- `git ls-remote` with no matching ref is confirmed remote-branch absence. A
  failed remote lookup is **publication lookup failed**, not absence.
- A known commit or push failure with a deterministic rejection, permission,
  authentication, validation, or network diagnostic stops publication. Do not
  run a later push, PR, Linear, or body write; report the failed operation and
  its recovery action.
- A lost response or timeout after a possible write is uncertain, not a known
  failure. Read back the affected resource and continue only after an
  unambiguous expected result: `HEAD` and the feature diff for commit, the
  remote OID for push, and the PR identity/body for create or edit. Otherwise
  stop without another mutation.

Do not treat an existing local commit or a lost command response as proof that
the operation needs repeating. After an interrupted or ambiguous write,
observe the affected resource first and retry only the missing operation while
the observed branch/head/PR is unchanged:

- If the feature files are already in `HEAD`, do not make a second commit. If
  the feature diff is empty, do not commit.
- If the remote branch OID equals `HEAD`, do not push. After a lost push
  response, reread `git ls-remote`; retry only when it confirms the old remote
  OID and the local head is unchanged.
- If PR creation has a lost or ambiguous response, rerun the full-identity
  `gh pr view` first.
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
`headRepository`, `isCrossRepository`, `headRefName`, and `body`. An exact body
match schedules no write.

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
   git add -- specs/<feature-directory>/
   git diff --cached --name-only
   git commit --only -m "docs(specs): <feature>" -- specs/<feature-directory>/
   ```
   A known commit failure stops before any push, PR, Linear, or body write. A
   lost commit response requires the commit readback in step 3 before anything
   else continues.
3. Immediately before any push, reread and compare the mutation boundary:

   ```bash
   git rev-parse HEAD
   git ls-remote --heads origin <branch>
   gh pr view <branch> --repo "$origin_url" --json number,state,isCrossRepository,headRepository,headRepositoryOwner,headRefName,baseRefName,headRefOid
   ```

   Compare these results with step 1, the expected repository/branch/base, and
   the confirmed commit result. If the initial PR was absent, it must still be
   absent; if it was OPEN, the same number, state, head branch, base branch, and remote head OID
   must remain, with the same head repository. Any concurrent PR
   identity/state/repository/head/base change, failed lookup, or remote OID
   change stops before push as a gate-consistency failure. A confirmed own
   commit may change local `HEAD`; push only when the observed remote OID is
   absent or differs from that local `HEAD`:

   ```bash
   git push -u origin <branch>
   ```

   Read back the remote OID after a successful or ambiguous push. A known push
   failure stops before PR or Linear writes; an uncertain response continues
   only after that readback proves the expected remote OID.
4. Observe the PR again and recheck its full identity against
   `expected_repo`, `expected_head`, and `expected_base`. If absence is
   confirmed, use the base already resolved before the gate observation; if an
   OPEN PR is present, require the same matching identity and never adopt its observed `baseRefName`.
   For an OPEN PR after the push readback, require `headRefOid` to equal the
   confirmed remote OID (or the confirmed local `HEAD`); a different or
   uncertain OID leaves publication pending and stops before Linear or body
   writes. A mismatch is a gate-consistency failure. Recompute
   the Changes section from the effective commit and keep the candidate body
   local:

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
   decision. After either mutation, reread `headRefOid` and require it to
   equal the confirmed remote OID before reporting publication verified;
   otherwise preserve the pending state and stop. Use the canonical body file
   for either mutation:

   ```bash
   gh pr create --repo "$origin_url" --draft --base "$base" --title "feat(<area>): <feature outcome>" --body-file "$body_file"
   gh pr edit --repo "$origin_url" <number> --body-file "$body_file"
   ```

Two unchanged retries run the same observations and perform zero duplicate
commits, pushes, PR creates, PR body updates, Projects, or Issues. Report the
URL, state, head/base, skipped writes, Linear result, and every remaining
prerequisite. The feature PR stays draft while tasks land, becomes ready only
through the normal human review flow when all tasks are checked, and closes by
a human merge commit.

## 6. Open task or work-item delivery PRs

Use the common remote identity gate above before the first PR observation. Do
not resolve a base with `pr_create.py` while an existing PR could already
provide the approved base. Prepare the canonical body only after that
observation. If an OPEN PR exists,
use its observed base and preserve its body when the stable evidence is
unchanged; do not invoke `pr_create.py`. If absence is confirmed after the
push, resolve the base in step 3 immediately before composing a new body. On
that confirmed-absence path, the helper checks
the branch task against the named task or the first unchecked ledger task and
selects the open stack head, otherwise the feature branch. For a confirmed
absence on a feature or work-item route, it resolves and validates the
delivery base. Prepare the
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

   ```bash
   gh pr view <branch> --repo "$origin_url" --json number,url,state,isDraft,isCrossRepository,headRepository,headRepositoryOwner,headRefName,baseRefName,headRefOid,body
   ```

   Reuse an OPEN PR only when `isCrossRepository: false`,
   `headRepository.nameWithOwner == expected_repo`, and
   `headRefName == expected_head`; preserve its observed base and body. A fork,
   wrong repository, wrong branch, or failed lookup is a gate-consistency
   failure and stops before reuse or push.
2. Immediately before pushing, reread the PR identity/state/repository/head/base
   and remote OID and compare them with step 1 and the common expected
   repository/head. A confirmed initial PR absence must remain absent; an OPEN
   PR must retain the same number, repository, head, base, and remote OID. Any
   concurrent change or failed lookup stops before push. Then push the branch
   before opening a new PR, using the same observed remote OID rule as the
   feature flow:

   ```bash
   gh pr view <branch> --repo "$origin_url" --json number,state,isCrossRepository,headRepository,headRepositoryOwner,headRefName,baseRefName,headRefOid
   ```

   ```bash
   git push -u origin <branch>
   ```

   Read back the remote OID after a successful or ambiguous push. A known push
   failure stops before PR creation; an uncertain response continues only
   after readback proves the expected remote OID. If the PR is OPEN, its
   `headRefOid` must equal that confirmed remote OID before the delivery is
   treated as verified; a mismatch remains pending.
3. Observe the PR again with the same full identity fields. If absence is
   confirmed, resolve the base now, then compose the canonical body and create
   the draft. Use project
   `.venv/bin/python` when it exists, otherwise `python3`:

   ```bash
   gh pr view <branch> --repo "$origin_url" --json number,state,isCrossRepository,headRepository,headRepositoryOwner,headRefName,baseRefName,headRefOid,body
   ```

   ```bash
   pr_python="python3"
   test -x .venv/bin/python && pr_python=".venv/bin/python"
   base_line="$(GH_REPO="$origin_url" "$pr_python" .specify/presets/default/scripts/python/pr_create.py <feature|task|work-item> [T###])"
   case "$base_line" in
     base=*) base="${base_line#base=}" ;;
     *) echo "publication lookup failed: pr_create.py did not resolve a base" >&2; exit 1 ;;
   esac
   ```

   If an OPEN PR exists, require the same repository/head comparison before
   updating its body. Use its observed base and update its body only when
   stable evidence differs; do not invoke `pr_create.py` or replace its body
   merely to restyle it. After create or edit, reread `headRefOid` and require
   it to equal the confirmed remote OID before reporting publication verified;
   otherwise preserve the pending state and stop. Never inline the body:

   ```bash
   gh pr create --repo "$origin_url" --draft --base "$base" --title "<type(scope): subject>" --body-file "$body_file"
   gh pr edit --repo "$origin_url" <number> --body-file "$body_file"
   ```

   Report the PR URL, then continue with `/speckit.code-review` and the normal
   ready-for-review flow.
