# Implementation Plan: Linear state from complete observations

**Feature directory**: `specs/006-linear-truth`
**Spec**: [spec.md](spec.md)

## Summary

Make observation completeness explicit through the existing Linear package:
scan every PR page, derive draft → ready → merged precedence, and suppress
workflow-state writes when evidence is uncertain. Preserve remote defaults
on Issue creation and expose reconciliation failures without blocking runtime
handlers. This template keeps research, data contracts, and validation in
this plan; implementation and task generation follow separately.

## Technical context

- **Language/runtime**: Python 3.11+, standard library; existing Bash and
  PowerShell launchers. [Manifest](../../packages/spec-kit-linear/pyproject.toml).
- **Primary dependencies**: no runtime packages; Git and authenticated `gh`.
  Installed `gh` 2.97.0 supports the required pagination flags. Development
  uses `pytest>=8`, locked at 9.1.1 in the package's
  [lockfile](../../packages/spec-kit-linear/uv.lock). No new dependency.
- **Storage/state**: consumer artifacts and Git remain authoritative; Linear
  owns its initial Issue default and human fields. Observations are ephemeral.
- **Verification**: pytest with existing fake transports and temporary repos;
  package installed-artifact conformance; `git diff --check`.
- **Target environment**: existing consumer platforms and all upstream-selected
  integrations; the common Python runtime carries the behavior.
- **Constraints**: reliability entry 01 only; preserve branch names and the
  pinned upstream 1.0.4. Retain the existing 400-line review limit and 2×
  forecast stop. Task generation must split delivery into working increments.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| Python | 3.11+ | [subprocess](https://docs.python.org/3.11/library/subprocess.html), [dataclasses](https://docs.python.org/3.11/library/dataclasses.html) |
| GitHub CLI | installed 2.97.0 | [`gh api`](https://cli.github.com/manual/gh_api), including `--paginate`, `--slurp`, and repository placeholders |
| GitHub REST | version 2022-11-28 | [List pull requests](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests) |
| Linear GraphQL | existing public schema | [Issue defaults and errors](https://linear.app/developers/graphql), [pagination](https://linear.app/developers/pagination) |
| pytest | locked 9.1.1 | [Invocation and exit codes](https://docs.pytest.org/en/stable/how-to/usage.html) |

An interface not covered here must be checked against its official source
before implementation. Linear documents that omitting `stateId` selects the
team's first Backlog state, or Triage when enabled; this is not a derived state.

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose pinned upstream | PASS | PASS | Changes stay in the authored Linear package; baseline and pin unchanged. |
| II. Preserve native surface | PASS | PASS | Existing `push`, `status`, and event handlers; no command or flag added. |
| III. Consumer-selected integrations | PASS | PASS | Common Python implementation; installed-asset evidence remains distinct from live agent acceptance. |
| IV. Durable repository truth | PASS | PASS | Explicit uncertainty; no remembered state or replacement for feature selection. |
| V. Source/consumer boundary | PASS | PASS | Shipped package owns runtime; fixtures use isolated consumers. |
| VI. Traceable delivery units | PASS | PASS | FR/SC mapping below; tasks must carry forecasts, boundaries, and evidence under the current budget. |
| Sequential delivery and human gates | PASS | PASS | Entry 01; product handoff below remains pending, with remote publication separately authorized. |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| GitHub reads | `github.py` | Complete paginated observation with strict response validation | Git fetch, credential handling, new public flags |
| Task and work-item state | `work_state.py`, `work_items.py` | Shared precedence and explicit unknown state | Branch renaming or new identity registry |
| Remote plan | `planner.py` | Omit unverified lifecycle updates and creation state | Human fields, new mutation kinds |
| Application evidence | `reconciler.py`, `errors.py`, `cli.py` | Preserve successful/failed operation context | Automatic mutation replay or rollback |
| Status and handlers | `reporting.py`, `cli.py` | Explain uncertainty and visible non-blocking failures | Event wiring, discovery, or feature-close redesign |

## Technical decisions

### D1. Let GitHub CLI exhaust the repository listing

- **Decision**: Replace `gh pr list --limit 200` with `gh api --method GET
  repos/{owner}/{repo}/pulls -f state=all -F per_page=100 --paginate --slurp`,
  using the documented REST version header. Keep one repository-wide scan per
  observation and the current subprocess timeout. Validate the exit status
  before parsing the outer page array. Normalize `number`, `head.ref`,
  `draft`, `state`, and `merged_at` into the existing PR representation.
- **Rationale**: `gh` already owns authentication, repository resolution, and
  Link pagination. It can emit a valid partial array before a later failure;
  JSON validity alone cannot prove a complete scan.
- **Trade-off**: Large repositories cost more reads and can exceed the timeout.
  Such runs preserve states with a diagnostic, rather than truncate history.
  This is a completed traversal, not an atomic snapshot of concurrent PR edits.

Reject empty/malformed envelopes, unsupported states, missing required fields,
and contradictory duplicate PR records. A successful `[[]]` is verified empty.
Deduplicate identical PR records by number. Read only the bound repository's
listing; repository scope means the PR target repository, preserving existing
association of incoming PRs. Retain exact task and issue-key matching. No per-task query,
new repository registry, or arbitrary maximum replaces the old ceiling.

### D2. Carry completeness, not an empty-list substitute

- **Decision**: Replace `PullRequestScan.available` with a required outcome
  (`complete`, `failed`, `incomplete`) plus the existing PR tuple and safe
  diagnostics. Missing CLI, process errors, timeouts, and nonzero exits are
  `failed`, even if output contains some pages. Exit-zero data that fails
  validation is `incomplete`. Only `complete` permits state derivation.
- **Rationale**: `_observe()` currently discards `available` and forwards an
  empty tuple. Both task and bug/chore derivations must receive the scan
  explicitly; an omitted scan must never imply verified absence.
- **Trade-off**: Failure invalidates state derivation repository-wide. Selected
  tasks remain reportable; bugs/chores found through local branches remain
  reportable. A repository-level diagnostic also covers unseen work items.

Discard failed/incomplete PR payloads as state evidence. Emit a warning naming
all selected features and the bound repository's work-item scope, including
items that could be absent from partial output. Do not persist scan history.

### D3. Use one deterministic precedence rule

- **Decision**: Replace the furthest-progress ranking with open draft first,
  then open ready, then merged. Among equivalent candidates choose the lowest
  PR number for the existing `pr_number`/next-action witness. Ignore closed,
  unmerged PRs. Apply FR-004's local rules only after a complete scan.
- **Rationale**: A single remaining draft prevents the whole item appearing
  reviewable. Open work outranks old merges and checked task boxes.
- **Trade-off**: The existing one-PR next-action display represents one witness,
  not every PR. Aggregated state still considers all relevant PRs.

### D4. Make unknown state explicit at the planner boundary

- **Decision**: Allow `TaskWorkState.state` and `WorkItemState.state` to be
  `None` for uncertainty, with source `unknown` and diagnostic detail. Require
  the task-state mapping in `build_push_plan`; remove `_task_state()`'s
  checkbox fallback. A missing mapping entry is an internal error, not a
  local-only derivation. `_desired_state_id(None)` returns no target state.
- **Rationale**: The current fallback can reintroduce false completion even
  after the scanner is fixed. Both creation and lifecycle update already
  conditionally add `stateId`; use those existing seams.
- **Trade-off**: Internal callers and fixtures must supply explicit observations.
  There is no compatibility route for callers that silently omit evidence.

Content and identity reconciliation continue under the existing allowlist.
An uncertain task Issue is created without `stateId`; its remote default is
shown separately from `derived_state: null`. Existing Issues receive no
lifecycle operation. Bugs and chores remain update-only. Reuse the same
observation during apply verification; the next invocation takes a fresh scan.

### D5. Preserve truthful reports through failure

- **Decision**: `status` and `push` share observation diagnostics; unknown rows
  display unverified state and no progress-based next action. Human tables,
  JSON, and session context distinguish the remote state from derived state.
  Creation previews explicitly say the initial state will be chosen by Linear.
- **Rationale**: A correct mutation plan is insufficient if reports still claim
  completion or handlers discard failures.
- **Trade-off**: Configured runtime handlers now emit concise sanitized warnings
  on stderr while keeping exit 0. Missing/disabled configuration retains its
  existing quiet no-op. Event wiring itself stays unchanged.

Carry partial application evidence through `ApplyResult`/`AppError` and the
CLI error payload: confirmed applied and recovered operation IDs, the failing
operation's ID/kind/target, and operations not attempted. Distinguish an
unconfirmed update from a known rejection; neither counts as success. Preserve
results from earlier feature plans if a later plan fails. A post-verification
failure retains confirmed writes but does not claim convergence. Manual
commands keep their existing nonzero error contract; handlers surface the
same diagnostic and allow delivery to continue. Never serialize raw exceptions
or service responses into handler output.

## Data and migration behavior

| Data | Contract |
| --- | --- |
| `PullRequestScan` | Explicit outcome, normalized PR tuple, diagnostics; only complete observations supply state evidence. |
| `PullRequest` | Positive integer number, exact head branch, boolean draft, normalized OPEN/CLOSED/MERGED; MERGED comes from `merged_at`. |
| Task/work-item state | Existing logical states or `None`; unknown source/detail explain preservation. Task identities and Issue keys unchanged. |
| Status row | `derived_state: null`, `state_source: unknown`, `next: null` under uncertainty; `remote_state` remains separately observed. |
| Mutation plan | Existing allowlisted operations; uncertain creation omits `stateId`, uncertain existing state has no lifecycle update. |
| Apply evidence | Applied/recovered IDs plus failed and unattempted operations; uncertain outcomes are never counted as confirmed writes. |

No stored schema or configuration migration. Remove obsolete scan fields and
fallback paths and update all package callers together. Existing managed
markers, remote identity adoption, and lifecycle mappings remain authoritative.

## Failure, retry, rollout, and rollback

- **Failure behavior**: GitHub uncertainty suppresses lifecycle writes only;
  Linear errors stop unsafe application, retain partial evidence, and remain
  visible. Event handlers continue delivery after reporting the failure.
- **Retry/idempotency**: Keep fresh Linear preconditions before each mutation,
  UUID/marker-based create recovery, and post-apply verification. Do not replay
  ambiguous updates. A later invocation re-observes and plans only differences.
- **Rollout**: Deliver complete scanning and state preservation together (T001),
  then reports/defaults (T002), precedence (T003), large-repository evidence
  (T004), failure evidence (T005-T006), and documentation (T007). The first
  vertical slice joins completeness to its state/planner callers.
  Release and consumer installation use the existing human
  publication workflow; live acceptance remains entry 23.
- **Rollback**: Stop lifecycle auto-apply using the existing `hooks.auto_apply`
  gate before a human-directed package rollback. Retain Issues and artifacts;
  rerun a corrected dry-run before resuming writes. Rolling back code alone
  would restore the old false-completion risk, not repair remote states.

## Security and privacy

`gh` owns GitHub credentials; the existing Linear client owns its credentials
and destination. Reuse centralized redaction and authored diagnostic messages;
never print raw CLI stderr, environment values, or service payloads. PR fields
are untrusted evidence, validated before association or derivation. Planning
and tests use read-only inspection and fake services. Applying a remote plan
retains its specific authorization and per-operation preconditions.

## Verification strategy

Run from the repository root. Commands below are implementation acceptance;
they do not claim that the planned behavior already exists.

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001, FR-002, SC-003 | Scanner fixtures: >200 PRs; empty result; missing CLI; timeout; malformed and valid partial output; late-page failure; duplicate/order cases | `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_work_state.py -q` |
| FR-003, FR-004, SC-001 | Draft+ready+merged combinations, checked/unchecked tasks, closed PRs, branch-only bugs/chores, and identity isolation | Same command plus `packages/spec-kit-linear/tests/unit/test_work_items.py` |
| FR-005, FR-006, FR-007, SC-002 | Planner and CLI fixtures prove zero lifecycle writes under uncertainty, omitted creation state, default-state readback, status parity, recovery, and no invented next action | `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_projection_planner.py packages/spec-kit-linear/tests/unit/test_planner_apply.py packages/spec-kit-linear/tests/unit/test_reporting.py packages/spec-kit-linear/tests/unit/test_cli.py -q` |
| FR-008, FR-009, SC-004/005 | Fake Linear: second pass zero writes; partial-success retry without duplication; ambiguous create/update; post-verification failure; visible handler warning with exit 0 | `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_planner_apply.py packages/spec-kit-linear/tests/unit/test_cli.py -q` |
| Package regressions and secrets | Full package tests, including redaction and allowlist protections | `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` |
| Installed consumer boundary | Hermetic Linear endpoint and temporary consumer; generated/installed assets, not observed agent execution | `bash packages/spec-kit-linear/scripts/conformance/installed-artifact.sh` |
| Documentation and scope | Package docs match precedence, uncertainty, handler output, and unchanged names | `git diff --check`; review changed paths |

The creation fixture must model a real non-null default (including Triage),
not merely store `input.get("stateId")`; otherwise it cannot prove FR-006.
Tests must distinguish all-success from failure after successful writes.

Planning baseline on 2026-09-11: the six existing focal files above passed
**197 tests and 121 subtests in 6.53s**. This validates the starting suite,
not the new acceptance cases. No implementation or installed-artifact
conformance was run in this planning phase.

## Source layout

```text
packages/spec-kit-linear/
  src/spec_kit_linear/
    github.py                         # exhaustive scan and strict normalization
    work_state.py, work_items.py       # complete observation and shared precedence
    planner.py                        # explicit states; remove checkbox fallback
    reporting.py, cli.py               # uncertainty, next actions, visible handler failures
    reconciler.py, errors.py           # partial application evidence
  tests/unit/
    test_work_state.py, test_work_items.py
    test_projection_planner.py, test_planner_apply.py
    test_reporting.py, test_cli.py, test_remote_discovery.py
  commands/push.md, commands/status.md
  commands/session-start.md, commands/post-tool-use.md
  README.md, CHANGELOG.md
```

Update authored docs during implementation. Installed `.specify/extensions/`
and generated `.agents/skills/` are distribution outputs, not editing targets.
The package lockfile, allowlist, mutation adapter, and conformance launcher are
reused unchanged unless focused evidence shows a necessary correction.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Raise the PR limit | Moves the truncation point without proving completeness. |
| Write a pagination client or add a GitHub SDK | Existing `gh api` already owns the required traversal and authentication. |
| Preserve checkbox fallback when GitHub fails | Converts unavailable evidence into a false state. |
| Pick the most advanced PR | A merge or ready PR hides remaining development. |
| Skip Issue creation during uncertainty | Linear already owns a documented default; creation can omit derived state. |
| Return success or silence for all reconciliation failures | Hides partial writes and leaves users unable to distinguish failure from convergence. |

## Product handoff

`ready-for-development` requires all rows to be complete. Analysis consistency
is not technical approval.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | Analysis completed: 100% requirement coverage; the sole low-severity verification-command omission was corrected. | complete |
| Technical approval of plan and tasks | Human review after the task breakdown. | pending |
| Reviewed Linear dry-run and synchronization | Latest `push --current --dry-run --json` after task generation passed on 2026-09-11: one `project.create` and seven `issue.create` operations for feature 006 in team TDS, label `spec-kit`; zero existing-work-item mutations. Application awaits authorization. | pending |
| Every executable task individually assignable and assigned | `tasks.md` contains seven assignable units; Linear assignment remains pending. | pending |
