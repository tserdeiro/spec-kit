# Changelog

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
