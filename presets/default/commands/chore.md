---
name: speckit.chore
description: Start a maintenance chore from its Linear issue key, on its issue-key branch.
---

# Spec Kit Chore

One command from the Linear issue to working on its branch, for minimal
maintenance work — no spec, no plan, no triage. For a bug, use
`/speckit.bugfix` instead. Work items are born in Linear by a human; this
command never creates or edits issue content — it only starts the
repository side. You (the agent) execute these steps in order and report
each outcome.

## 1. Resolve the issue

- The user must name the issue key (`WOR-123`-style), alone or inside a
  pasted Linear URL or title. Without one, stop and ask for it — the
  issue is created by a human in Linear first, never by you.
- Normalize the key to lowercase for the branch (`wor-123`).

## 2. Create the branch

Resolve the repository's up-to-date **delivery base** and branch from it:

```bash
set -e
trunk=$(sed -nE '/^trunk:/{s/^trunk:[[:space:]]*["'"'"']?([^"'"'"'#[:space:]]*)["'"'"']?.*$/\1/p;q;}' \
  .specify/extensions/git/git-config.yml 2>/dev/null || true)
base=${trunk:-$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)}
git check-ref-format --branch "$base" >/dev/null
git fetch origin
git switch -c wor-123-short-slug "origin/$base"
```

- The slug is 2–4 words from the issue's title. If the user gave only the
  key and the title is not in the conversation, ask for the title — do
  not invent a slug.
- If a branch for this key already exists (`git branch --all --list
  '*wor-123-*'`), switch to it instead and say so. Re-running this
  command must never create a duplicate.
- The branch is what projects the issue to *In Progress*: run
  `/speckit.linear.push --apply` — a branch alone is not a PR event, so
  Linear's native integration has nothing to move yet — and report the
  state.

## 3. Hand off to the delivery flow

Make the change directly — **with the stack derived, never invented**:
if the issue links stack or documentation, that rules; otherwise read
the real manifests and neighboring code and reuse what is installed.
Never add a dependency or reimplement what an installed library covers
(human decisions); verify any unfamiliar API against official
documentation before use. Then the flow ends as always: `/speckit.pr`
opens the canonical draft PR, self-review with `/speckit.code-review`,
fix, mark `ready for review`, human review and merge.
