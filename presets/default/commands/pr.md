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
- A task named this way also fills the `named_task` literal in step 5's
  `pr-create` block, which then verifies the branch against it; without a
  named task, the block verifies against the ledger's first unchecked
  task instead.

## 2. Guarantee the branch invariant

The branch is what projects the task to *In Progress*; it must exist and
follow the convention before the PR opens. The PR's **base** follows from
what is delivered: a feature task targets the open task PR it stacks on,
else its **feature branch** (`NNN-slug`, resolved from the active
feature); a work item queries the **GitHub default**; the feature PR
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
  task, the GitHub default for a work item), not the plan.
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
# pr-create:start
set -e
delivery_kind="<feature|task|work-item>"
case "$delivery_kind" in
  feature)
    trunk=$(sed -nE '/^trunk:/{s/^trunk:[[:space:]]*["'"'"']?([^"'"'"'#[:space:]]*)["'"'"']?.*$/\1/p;q;}' \
      .specify/extensions/git/git-config.yml 2>/dev/null || true)
    base=${trunk:-$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)}
    git check-ref-format --branch "$base" >/dev/null
    ;;
  task)
    paths=$(bash .specify/scripts/bash/check-prerequisites.sh --paths-only)
    feature_branch=$(printf '%s\n' "$paths" | sed -n 's/^BRANCH: //p')
    feature_number=${feature_branch##*/}
    feature_number=${feature_number%%-*}
    named_task="<T### or empty>"
    current=$(git branch --show-current)
    branch_task=$(printf '%s\n' "${current##*/}" | sed -nE 's/^[0-9]+-(T[0-9]{3})-.*/\1/p')
    tasks_file=$(printf '%s\n' "$paths" | sed -n 's/^FEATURE_DIR: //p')/tasks.md
    if [ ! -f "$tasks_file" ]; then
      printf 'error: task ledger not found: %s\n' "$tasks_file" >&2
      exit 2
    fi
    ledger_task=$(awk '
      in_fence {
        i=0; while (substr($0,i+1,1)==" ") i++
        c=substr($0,i+1); sub(/[ \t]+$/, "", c)
        ok=(i<=3 && length(c)>=mlen)
        if (ok) for (j=1;j<=length(c);j++) if (substr(c,j,1)!=marker) { ok=0; break }
        if (ok) in_fence=0
        next
      }
      {
        i=0; while (substr($0,i+1,1)==" ") i++
        r=substr($0,i+1); ch=substr(r,1,1)
        if (i<=3 && (ch=="`" || ch=="~")) {
          n=0; while (substr(r,n+1,1)==ch) n++
          if (n>=3 && (ch!="`" || !index(substr(r,n+1),"`"))) { in_fence=1; marker=ch; mlen=n; next }
        }
        if ($0 ~ /^[ \t]*- \[ \] T[0-9][0-9][0-9]/) {
          match($0, /T[0-9][0-9][0-9]/)
          print substr($0, RSTART, RLENGTH)
          exit
        }
      }
    ' "$tasks_file")
    expected_task=${named_task:-$ledger_task}
    if [ -z "$expected_task" ]; then
      printf 'error: no unchecked task found in %s\n' "$tasks_file" >&2
      exit 2
    fi
    if [ "$branch_task" != "$expected_task" ]; then
      printf 'error: branch %s delivers %s but the task to deliver is %s\n' \
        "$current" "$branch_task" "$expected_task" >&2
      exit 2
    fi
    prs=$(mktemp)
    gh pr list --state open --limit 100 --json headRefName,baseRefName,isDraft \
      --jq ".[] | select(.headRefName | startswith(\"$feature_number-T\")) | \"\(.headRefName) \(.baseRefName) \(.isDraft)\"" \
      > "$prs"
    base="$feature_branch"
    git fetch origin
    for head in $(awk '$3 == "false" { print $1 }' "$prs"); do
      git merge-base --is-ancestor "origin/$head" HEAD || continue
      if [ "$base" = "$feature_branch" ] ||
        git merge-base --is-ancestor "origin/$base" "origin/$head"; then
        base="$head"
      fi
    done
    ;;
  work-item) base=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name) ;;
  *) printf 'error: unknown delivery kind: %s\n' "$delivery_kind" >&2; exit 2 ;;
esac
gh pr create --draft --base "$base" --title "<type(scope): subject>" --body "<the body>"
# pr-create:end
```

Replace only the delivery-kind and named-task literals. Repository-derived
branch names stay runtime data and reach `gh` only through the quoted
`base` argument. No Python, no JSON parsing beyond `gh --jq`.

The feature PR's **delivery base**: an explicit non-empty `trunk:` key in
the consumer's `.specify/extensions/git/git-config.yml` wins (quotes
optional); absent or empty falls back to the GitHub default branch;
either way the name must pass `git check-ref-format --branch`, or the
command stops. `implement-append.md`'s first-task refresh resolves the
delivery base the same way. The feature PR's title is
`feat(<area>): <feature outcome>`.

Title in English, `type(scope): subject`, matching the branch's commit.
Report the PR URL, then remind the flow: the next steps are the
self-review (`/speckit.code-review`) and `ready for review` — Linear's
native integration transitions the issue on that event, and
`/speckit.linear.push --apply` reconciles anything it missed.
