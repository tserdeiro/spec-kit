---
description: Generate an actionable, dependency-ordered tasks.md for the feature based on available design artifacts.
handoffs:
  - label: Analyze For Consistency
    agent: speckit.analyze
    prompt: Run a project analysis for consistency
    send: true
  - label: Implement Project
    agent: speckit.implement
    prompt: Start the implementation in phases
    send: true
scripts:
  sh: scripts/bash/setup-tasks.sh --json
  ps: scripts/powershell/setup-tasks.ps1 -Json
  py: scripts/python/setup_tasks.py --json
---

# Spec Kit Tasks

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Setup

1. Run `{SCRIPT}` from the repository root; parse `FEATURE_DIR`, `TASKS_TEMPLATE_CONTENT` (or `TASKS_TEMPLATE`, when an older setup script omits the content field), and `AVAILABLE_DOCS`. Every path is absolute.
2. **Load the artifacts** — `plan.md` and `spec.md` from `FEATURE_DIR` (required); `data-model.md`, `contracts/`, `research.md`, and `quickstart.md` when `AVAILABLE_DOCS` lists them; `.specify/memory/constitution.md` when present.
3. **Load the template** — `TASKS_TEMPLATE_CONTENT`, or the file `TASKS_TEMPLATE` names.
4. **Hooks, silently** — read `.specify/extensions.yml`'s `hooks.before_tasks` (skip entirely, silently, on a missing file, a missing key, or invalid YAML). Among entries whose `enabled` is not explicitly `false` and whose `condition` is empty (a non-empty `condition` is left to the HookExecutor): suppress every product-phase `git.commit` hook, including mandatory and default-enabled configurations; invoke other **mandatory** hooks (`optional: false`) as their own slash command — dots become hyphens, e.g. `speckit.linear.push` → `/speckit-linear-push` — and wait for them before continuing; skip every optional non-`git.commit` hook silently. Nothing about a hook is ever printed. The same rule governs `hooks.after_tasks` — see Completion below. Mandatory Linear hooks remain active.

## The ledger rules

Fill the template's task blocks — organized by user story, in priority order from `spec.md`, except where dependency order below takes precedence — under these rules:

- **One task at a time, no `[P]` marker, no parallel-execution example.** Order every task by its dependencies alone (`Depends on`), so the list reads as the sequence one developer follows; who takes which task is Linear assignment, never a marker here.
- **Dependency order wins over user-story priority when they conflict** — a task with no caller yet cannot be verified. Tasks form one chain in file order: `Depends on` documents that order and never chooses the base — delivery stacks the next task on the open, ready task PR, or starts from the feature branch when none is open.
- **The resolved template rules the sections and files this ledger produces** — only the sections `TASKS_TEMPLATE_CONTENT` defines, at the density of the previous feature's own ledger.
- **Every `Delivery` line carries its forecast as `(~N authored lines)`** — the review budget's count of added executable lines — sized to the task's whole deliverable (the change itself, its tests, its manifest entry, its conformance conversion), never only the size of what it replaces. A prose-only task forecasts its diff size the same way; the budget stop counts executable lines alone, so it stays moot for that task without excusing it from stating a forecast.
- **`single PR` means one PR for the task.** Stacking the next task's branch on this one's open PR is the loop's own topology, never a choice a task's `Delivery` line makes.
- **IDs are provisional during local refinement.** Freeze the task IDs when
  the exact analyzed artifacts receive their first approved publication. A
  later task addition uses the next unused ID and requires fresh analysis and
  product approval; completion checkboxes and evidence do not change the
  approved product intent.

## Completion

Run `.specify/extensions.yml`'s `hooks.after_tasks` by Setup step 4's own rule — silently, mandatory hooks awaited, eligible optional hooks run quietly, every other one skipped. Product-phase `git.commit` remains suppressed, including when configured as mandatory.

Leave the generated `tasks.md` local. Do not commit, push, or create a feature PR from this phase. After `/speckit.analyze` reports clean, present the exact product artifact set and handoff prerequisites; explicit human approval is required before the feature variant of `/speckit.pr` publishes it.

Report: the path to the generated `tasks.md`; that no publication occurred; the total task count and the count per user story; the independent-test criterion for each story; the suggested MVP scope; and confirmation every task follows the template's checklist format.
