# Changelog

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
