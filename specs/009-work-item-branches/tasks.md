# Tasks: Start work items with native Linear branches

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: First unchecked task, delivered by a fresh Luna Extra High agent.

## Delivery strategy

- `009-work-item-branches` is the integration branch. Open its draft feature PR
  against the configured delivery base. Each task has one `009-T###-short-slug`
  branch and one draft PR stacked on the preceding ready task PR, otherwise on
  the feature branch. Derive bases with the existing delivery scripts.
- Run one task at a time in dependency order; independently review its delivery,
  record completion evidence, and mark its PR ready before starting the next.
  Final review and merge remain human. The user authorized commits, push, PRs,
  and Linear synchronization on 2026-09-12.
- Forecasts include implementation, tests, fixtures, and conformance. Respect
  400 authored executable lines and the existing 2× forecast stop. Protected
  spec/constitution and unrelated dirty documentation remain untouched.
- MVP: T001–T004 demonstrate configured/unconfigured start and safe adoption.
  Full delivery includes cross-surface behavior, installed evidence, an Astra
  Extra High whole-feature audit, Luna fixes, and final extension review.

## Phase 1: User Story 1 - Start from the Issue (P1)

**Goal**: Obtain native Issue context and branch without asking for known data.
**Independent evidence**: Key-only configured start and explicit failure behavior;
missing configuration alone enables supplied key/title fallback.

- [x] T001 [US1] Read Issue context and native branch resolution in packages/spec-kit-linear/src/spec_kit_linear/linear_client.py
  - **Traces**: FR-001, FR-002, FR-004, FR-006, SC-001, SC-003; outcome: validated read-only native results include exact suggested branch and context.
  - **Depends on**: none
  - **Boundaries**: Extend client value types/queries and focused `packages/spec-kit-linear/tests` fixtures. Read canonical Issue context and batch distinct native branch lookups within existing query limits; handle null/malformed results and retain transport/credential redaction. Validate team/result identity at the resolver boundary supplied by T002. Preserve mutation allowlist and runtime dependencies.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` -> native context, exact branch bytes, lookup null/malformed responses, batching, and existing transport regressions pass.
  - **Delivery**: single PR (~340 authored lines)
  - **Completion evidence**: PR #144; package suite 509 passed / 286 subtests; `git diff --check` passed; budget 181/400. Fresh extension review of `028fd1812c90c6d78d8171c208e7487b5288fa84`: `no-blocking-findings`, 0 findings, 6 covered ranges / 0 gaps, session closed. Independent read-only live probe: api_key credentials, context present, exact Git-valid native branch, duplicate inputs resolved once to the same Issue; observed prefix is literal in the configured template, without viewer-prefix inference.

- [ ] T002 [US1] Expose stateless configured resolution through packages/spec-kit-linear/scripts/python/resolve_work_item.py
  - **Traces**: FR-001, FR-004, FR-006, FR-007, C-001, C-002, SC-003; outcome: installed consumers resolve an Issue or branches with explicit absent/error/conflict outcomes.
  - **Depends on**: T001
  - **Boundaries**: Add `work_item_resolution.py`, the internal launcher, and focused package tests. Use existing config/credential/client loaders; canonical keys and explicit PR/native evidence must agree with the bound team. Treat multiple explicit keys as ambiguity and native null without canonical explicit identity as unresolved, following plan D1. Return JSON context without secrets; avoid new public commands or persistent mappings. Keep feature/task observations outside work-item resolution.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` -> bridge covers no config, invalid config, missing credentials, network/permission failure, wrong team, conflicting keys, valid native result, and feature/task exclusion.
  - **Delivery**: single PR (~320 authored lines)
  - **Completion evidence**: Pending

- [ ] T003 [US1] Start configured and unconfigured work items in presets/default/scripts/python/work_item_start.py
  - **Traces**: FR-001–004, FR-008, C-004, SC-001, SC-003, SC-005; outcome: start takes an Issue key and uses exact native branch/context or asks only for absent fallback data.
  - **Depends on**: T002
  - **Boundaries**: Add start helper; update `task_base.py`, `commands/bugfix.md`, `commands/chore.md`, and preset tests together. Replace caller-built branch input. Call only the installed resolver; validate refs with Git before mutations, use argument arrays, preserve dirty files, and reconcile only after success. Without configuration, derive the default key/title slug. Bugs retain triage; chores remain direct. T004 extends this first-start slice with adoption.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest presets/default/tests -q` -> configured exact-name creation, context return, default fallback, missing title, invalid name, reserved full feature/task-name collision, and configured failures pass in isolated repositories.
  - **Delivery**: single PR (~340 authored lines)
  - **Completion evidence**: Pending

## Phase 2: User Story 2 - Resume the same work (P1)

**Goal**: Adopt existing work before creating a branch.
**Independent evidence**: Repeated start after title/format/assignee changes keeps
one branch/PR and preserves commits; conflicting evidence prevents mutation.

- [ ] T004 [US2] Adopt existing branch or PR work in presets/default/scripts/python/work_item_start.py
  - **Traces**: FR-005, FR-006, C-004, SC-002, SC-003; outcome: uniquely identified local/remote work wins over the current suggested name.
  - **Depends on**: T003
  - **Boundaries**: Extend start helper and tests with complete remote-head/PR observation, canonical Tracker linkage, native head resolution, local/remote deduplication, unique-open-PR precedence, and tracking adoption. Cover changed title/format/assignee, multiple candidates, fork heads, closed unmerged PRs, unavailable refs, dirty work, and another worktree. Preserve history and stop before speculative switches/creation on failed evidence.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest presets/default/tests -q` -> repeated starts adopt exact existing heads, including an old title-only PR head with canonical Tracker identity and null native branch lookup; preserve history/files and report conflicts/failures without duplicate work.
  - **Delivery**: single PR (~370 authored lines)
  - **Completion evidence**: Pending

## Phase 3: User Story 3 - Keep identity consistent through delivery (P2)

**Goal**: Resolve the same Issue through projection, PRs, review, and guards.
**Independent evidence**: Equivalent native-format cases agree across surfaces;
feature/task-stack behavior and reviewer-only portability remain intact.

- [ ] T005 [US3] Resolve native branch and PR observations before Linear projection in packages/spec-kit-linear/src/spec_kit_linear/work_items.py
  - **Traces**: FR-006, FR-007, FR-009, FR-010, SC-003, SC-004; outcome: canonical transient Issue identity drives existing lifecycle precedence.
  - **Depends on**: T004
  - **Boundaries**: Update `work_items.py`, `github.py`, `_observe` in `cli.py`, and focused tests to retain canonical PR linkage and native branch associations. Reuse T002 resolution; retire obsolete recognition. Keep exact feature/task refs outside work items even with task Issue links. Preserve complete/failed/incomplete scan semantics and affected Issue state on unresolved/conflicting identity. Preserve all existing mutation restrictions.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` -> key-only, nested/user/title-based native names and changed suggestions derive correctly; uncertain scans, conflicts, and feature/task fixtures preserve expected state.
  - **Delivery**: single PR (~360 authored lines)
  - **Completion evidence**: Pending

- [ ] T006 [US3] Reuse native identity for session and hook context in packages/spec-kit-linear/src/spec_kit_linear/cli.py
  - **Traces**: FR-004, FR-006, FR-007, FR-008, FR-010, SC-003, SC-004; outcome: hooks identify native work items without selecting an unrelated active feature.
  - **Depends on**: T005
  - **Boundaries**: Update `_reconcile_hook`, session-start/context callers and focused tests. Use the resolver consistently for current branches; configured failures remain explicit and preserve state, absent/disabled hooks remain quiet. Retire remaining caller-local work-item regex assumptions; retain existing event/reentrancy protections.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` -> native current-branch context, stale feature selection, absent/disabled configuration, and configured failure regressions pass.
  - **Delivery**: single PR (~260 authored lines)
  - **Completion evidence**: Pending

- [ ] T007 [US3] Resolve work-item review context and exact task guards in packages/spec-kit-code-review/src/spec_kit_code_review/sdd_context.py
  - **Traces**: FR-006–009, C-001, C-002, SC-003, SC-004; outcome: native work-item PRs stay on the short path and guards protect only actual feature tasks.
  - **Depends on**: T006
  - **Boundaries**: Update `sdd_context.py`, `review_context.py`, guard classification in `cli.py`, and unit/golden fixtures. Read canonical Work item/Tracker linkage, reject conflicting identities, and prefer work-item/bug evidence over stale feature selection. Classify complete feature/task conventions exactly; unsupported local identity stays explicit advisory. Preserve reviewer-only operation, anchored reads, coverage, and protected-path rules; execute no candidate bridge.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests -q` -> native prefixed/title-based PRs, ambiguous links, stale feature selection, full task names, and task-like native leaf guards pass without Linear installed.
  - **Delivery**: single PR (~350 authored lines)
  - **Completion evidence**: Pending

## Final phase: Cross-cutting verification

- [ ] T008 [US3] Complete PR routing and installed contract evidence in presets/default/commands/pr.md
  - **Traces**: FR-001–010, C-001–004, SC-001–005; outcome: all five surfaces follow the native identity contract in independently installed consumers.
  - **Depends on**: T007
  - **Boundaries**: Update PR guidance/helpers, package command/README references, preset tests, and the Linear installed-artifact and code-review review conformance scripts. Exercise the equivalent format/failure matrix across start, PRs, review, guards, and projection. Confirm packaged internal bridge and reviewer-only independence; regenerate authored-command skills in isolated consumers via supported dev install. Repeat read-only live prefix/native-resolution probe using implemented code and record redacted evidence in this task's completion. Preserve unrelated dirty docs and distinguish synthetic fixtures from actual agent runtime.
  - **Evidence**: Run both package pytest suites and preset tests; `bash packages/spec-kit-linear/scripts/conformance/installed-artifact.sh`; `bash packages/spec-kit-code-review/scripts/conformance/review.sh`; `git diff --check` -> pass. Live native probe returns the same Issue, exact valid branch and credential-prefix shape without remote mutation.
  - **Delivery**: single PR (~350 authored lines)
  - **Completion evidence**: Pending

## Dependencies and stack order

- **Critical path**: T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008.
- **Stack order**: one PR per task in that order, starting on the feature branch.
- **Execution assignment**: each task is assigned to a fresh Luna Extra High agent
  at dispatch; the orchestrator reviews delivery and preserves human Linear ownership.
