---
name: speckit.bugfix
description: Start a bug fix from its Linear issue key — issue-key branch, then the triage trio.
---

# Spec Kit Bugfix

One command from the Linear issue to triaging the bug on its branch. For
minimal maintenance without triage, use `/speckit.chore` instead. Work
items are born in Linear by a human; this command never creates or edits
issue content — it only starts the repository side. You (the agent)
execute these steps in order and report each outcome.

## 1. Resolve the issue

- The user must name the issue key (`WOR-123`-style), alone or inside a
  pasted Linear URL or title. Without one, stop and ask for it — the
  issue is created by a human in Linear first, never by you.
- Normalize the key to lowercase for the branch (`wor-123`).

## 2. Create the branch

- From the repository's **up-to-date default branch** (resolve it with
  `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`;
  `git fetch` first): `git switch -c wor-123-short-slug`.
- The slug is 2–4 words from the issue's title. If the user gave only the
  key and the title is not in the conversation, ask for the title — do
  not invent a slug.
- If a branch for this key already exists (`git branch --all --list
  '*wor-123-*'`), switch to it instead and say so. Re-running this
  command must never create a duplicate.
- The branch is what projects the issue to *In Progress*: run
  `/speckit.linear.push --apply` (or let the lifecycle hook do it) and
  report the state.

## 3. Triage, then deliver

- Run the triage trio in order: `/speckit.bug.assess` (paste the user's
  report or reproduction) → `/speckit.bug.fix` → `/speckit.bug.test`.
  The three reports under `.specify/bugs/<slug>/` travel in the PR as
  evidence.
- Then the flow ends as always: `/speckit.pr` opens the canonical draft
  PR, self-review with `/speckit.code-review`, fix, mark
  `ready for review`, human review and merge.
