# Changelog

## 0.8.0

- The managed blocks carry the prose a PM needs: each task Issue leads
  with its `tasks.md` body, and the spec's Problem/Desired-outcome
  sections project onto `Project.content` — `Project.description` caps
  at 255 characters, so only the `Source:`/`Plan:` lines stay there.
  The task block's `Status:` line is gone: the workflow state already
  travels natively via `stateId`.
- Prose blocks reconcile by an embedded `body-hash` comment, never by
  bytes: Linear rewrites stored markdown (bullets, blank lines), so a
  byte compare would replan the same write on every push. Trade-off,
  documented in the planner: a human edit inside a managed block
  persists until its source artifact changes. Prose can no longer forge
  the block markers, and a removal that empties `Project.content` sends
  `" "` (a `""` write is a Linear no-op).

## 0.7.1

- The `after_plan`/`after_tasks` lifecycle hooks ship `optional: false`:
  a consumer install registers the Linear projection as automatic, so
  the mirror needs no per-repo registry edit (which every bundle update
  overwrote). A test pins the intent.

## 0.7.0

- Projected titles now respect Linear's limits: Project names clip at 80
  characters and Issue titles at 255 — deterministically, so
  reconciliation stays idempotent, and with a warning naming the artifact
  line to shorten. An over-long spec H1 previously surfaced as a bare
  INVALID_INPUT.
- Linear's own error messages now travel in the diagnostics (redacted),
  and client errors no longer claim to be "read" operations when a
  mutation failed.

## 0.6.4

- `onboard` persists an inline `LINEAR_API_KEY` to `.speckit-linear.env`
  (gitignored, mode `0600`) so the key it just used keeps authenticating
  later commands — only when no env file already defines a credential,
  never touching an existing file, and saying so in its output.

## 0.6.3

- Credentials get a paved path: `doctor --fix` writes the
  `.speckit-linear.env` template when no credential is defined anywhere,
  the missing-credential message names the exact file, a defined
  credential reports its source (file path or process environment —
  never the value), and an authentication failure names the source to
  renew.

## 0.6.2

- The doctor's lifecycle-hook comparison derives its expected events from
  `extension.yml` instead of a hardcoded list that still named the four
  hooks pruned in 0.4.0 (it warned about them on every healthy setup).

## 0.6.1

- The conformance harness derives the pinned CLI version from the
  source checkout's `versions.lock.yml` instead of hardcoding it.

## 0.6.0

- The distribution's upstream pin moved from `github/spec-kit` v0.13.0 to
  v1.0.1: the extension now requires specify-cli `>=1.0.1,<1.1.0` and its
  conformance harness gates on 1.0.1.

## 0.5.1

- `push.md` and the README document the derivation priority the code
  applies since 0.5.0: an observable pull request speaks first; the
  checkbox decides only once no live PR remains.

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
