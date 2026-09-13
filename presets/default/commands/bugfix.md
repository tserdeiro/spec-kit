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
- Start from the key with the preset helper. It queries the installed Linear
  resolver and returns the canonical title, context, and exact native branch.

## 2. Create the branch

Resolve the repository's up-to-date delivery base and branch from it by
running `task_base.py`'s `work-item` mode — with the consumer's
`.venv/bin/python` when it exists, else `python3` on PATH, the rule
upstream's own `py` scripts follow:

```bash
python3 .specify/presets/default/scripts/python/task_base.py work-item WOR-123
```

- If Linear is genuinely unconfigured, provide the title as the second
  argument so the helper derives `wor-123-title-slug`. A configured resolver
  failure stops the command with its diagnosis; it never switches to the
  fallback.
- The JSON result is the context for triage. Use its returned title and
  description instead of asking the user to repeat Issue information.
- The branch is what projects the issue to *In Progress*; the script
  reconciles Linear only after the branch setup succeeds. Report the state.

## 3. Triage, then deliver

- Run the triage trio in order: `/speckit.bug.assess` (paste the user's
  report or reproduction) → `/speckit.bug.fix` → `/speckit.bug.test`.
  The three reports under `.specify/bugs/<slug>/` travel in the PR as
  evidence.
- **The stack is derived, never invented**: the issue author describes
  the symptom, not the technology — read the real manifests and the
  neighboring code, reuse what is installed, never add a dependency or
  reimplement what an installed library covers (human decisions), and
  verify any unfamiliar API against official documentation before use.
- Then the flow ends as always: `/speckit.pr` opens the canonical draft
  PR, self-review with `/speckit.code-review`, fix, mark
  `ready for review`, human review and merge.
