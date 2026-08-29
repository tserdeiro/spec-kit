# Changelog

## 0.5.0

- An observable pull request now outranks the checkbox in task-state
  derivation. The delivery flow checks the box inside the task PR before
  `ready for review`, so an open PR projects review/started — never a
  premature done — and the checkbox is the durable truth once the PR is
  merged or gone.

## 0.4.0

- The custom assignee path is gone: no `[@alias]` markers, no
  `team.members` configuration, no user lookup. Assignment is native
  Linear (the UI or the official Linear MCP acting as the human);
  `assigneeId` is now unconditionally a preserved field on every
  mutation kind.
- Four of the six lifecycle hooks are gone (`after_specify`,
  `after_clarify`, `after_analyze`, `after_implement`): they projected
  nothing, or projected what Linear's native GitHub integration now does.
  `after_plan` and `after_tasks` stay — creation is what nothing native
  can do.
- Work-item branches accept Linear's native "Copy git branch name"
  format (`<username>/wor-123-slug`): the native button is a first-class
  way to start a bug or chore.
- `onboard` creates the missing repository bindings — the `Repository`
  label group, the `<slug>` child label, and both shared views — in
  dependency order, additively; ambiguity still aborts and workflow
  states remain a human decision. Live-fired against a real workspace,
  idempotent on the second run.

## 0.3.0

- `onboard` completes the team's PR-automation mapping for Linear's native
  GitHub integration (`draft` → In Progress, `start` → In Review, `merge`
  → Done): creates the missing mappings, warns about — never overwrites —
  a different human mapping, never touches branch-scoped rules, and warns
  when the workspace has no GitHub integration connected. Its one remote
  write, additive-only, behind the mutation allowlist; `--dry-run` plans
  without writing.

## 0.2.0

- `status` shows a `NEXT` column: the suggested next action per task and
  work item, derived from the same observable state as the projection
  (open the draft PR, self-review then mark ready, await the final review,
  record completion evidence). Output only — no new command, no new flag.

## 0.1.0

First release of the fresh repository. Five commands — `onboard`, `push`
(`--dry-run`/`--apply`), `status`, `doctor --fix`, `completions` — that
project feature tasks and Issue-key work items into Linear by deriving every
state from observable reality (checkboxes, `NNN-T###` and `<team>-<n>`
branches, pull requests via `gh`), idempotently and with graceful, warned
degradation. Zero runtime dependencies.
