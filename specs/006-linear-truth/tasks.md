---
description: 'Dependency-ordered delivery units for Linear observation truth'
---

# Tasks: Linear state from complete observations

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- Feature branch `006-linear-truth` integrates task PRs and reaches the delivery
  base through its feature PR, with human review and merge. Resolve the base
  from non-empty `trunk:`, otherwise the GitHub default branch.
- Product closes with committed artifacts and an authorized draft feature PR
  through `/speckit.pr`; implementation starts after the plan's handoff gates.
  Commit, remote synchronization, and publication retain human authorization.
- Start each task on `006-T###-short-slug`, based on the open ready task PR at
  the stack's top, otherwise the feature branch. Use the installed task-base
  routine before editing. `Depends on` defines execution order; the delivery
  loop resolves branch topology. One task runs at a time; ready permits the next.
- Every task delivers one PR. Forecasts include code, changed callers, tests,
  and documentation. Keep each PR under the existing ~400 authored executable
  lines and apply the existing 2× forecast stop. Re-slice oversized work through
  product before execution; preserve committed IDs.
- Reconciliation derives states from complete observations; task checkboxes
  carry completion evidence and PRs describe delivery progress.

## Task block format

Each task has a checkbox, stable ID, story marker where applicable, Traces,
Depends on, Boundaries, Evidence, Delivery forecast, and Completion evidence.
Commands run from the repository root. Focused tests accompany each change;
fill completion evidence in its final commit before ready for review.

## Phase 1: User Story 2 - Preserve truth through incomplete observations (P1)

**Goal**: Uncertain observation preserves existing states and lets new task
Issues use Linear's default. Complete scanning and preservation form one slice.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_work_state.py packages/spec-kit-linear/tests/unit/test_work_items.py packages/spec-kit-linear/tests/unit/test_planner_apply.py packages/spec-kit-linear/tests/unit/test_reporting.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> failed/partial reads produce zero lifecycle writes; creation omits state; recovery derives fresh state.

- [x] T001 [US2] Preserve states through complete observations in packages/spec-kit-linear/src/spec_kit_linear/github.py and its state/planner callers
  - **Traces**: FR-001, FR-002, FR-005, FR-006, FR-007, SC-002, SC-003; plan D1, D2, D4; outcome: replace the capped scan with one paginated/slurped `gh api` listing, normalize REST fields, and require complete/failed/incomplete outcome. Validate exit status before data and discard uncertain payloads. Pass the explicit scan through both derivations: unknown tasks and observed bug/chore branches yield null state. Creation omits `stateId`; existing states receive no lifecycle operation; a missing task-state mapping entry is an error. Complete-empty observations retain FR-004's local rules. Include basic multi-page, empty, malformed, missing-CLI, timeout, and valid-partial-output/nonzero cases; update existing fixture factories with callers.
  - **Depends on**: none
  - **Boundaries**: change `packages/spec-kit-linear/src/spec_kit_linear/{github,work_state,work_items,planner,cli}.py` and affected `packages/spec-kit-linear/tests/unit/{test_work_state,test_work_items,test_planner_apply,test_remote_discovery,test_cli}.py`; update every required scan/mapping caller. Preserve branch identity rules, mutation allowlisting, credentials, and existing PR precedence until T003. Deliver a working scanner-to-planner path.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` -> suite passes; uncertainty preserves checked-task and branch-only work-item states, uncertain creates omit `stateId`, and complete-empty differs from failure. Recorded `gh` argv proves repository-scoped pagination and the REST version header.
  - **Delivery**: single PR (~380 authored lines)
  - **Completion evidence**: PR [#119](https://github.com/tserdeiro/spec-kit/pull/119); full package suite: 452 passed, 252 subtests; strengthened lifecycle/default assertions: 34 planner tests passed; `git diff --check` clean. Independent review findings corrected; final candidate review required before ready.

- [x] T002 [US2] Explain unknown and default states in packages/spec-kit-linear/src/spec_kit_linear/reporting.py and cli.py
  - **Traces**: FR-005, FR-006, FR-007, FR-008, SC-002, SC-004; plan D4, D5; outcome: human tables, JSON, creation previews, and session context distinguish unverified derived state from remote state; unknown rows have no progress-based next action. Diagnostics name selected features and repository-wide work-item scope, including items absent from partial output. Model non-null Backlog and Triage defaults in the existing fake client; a checked task created under uncertainty adopts that default, reports null derived state, and reaches the correct state on recovery with zero operations on the subsequent unchanged run.
  - **Depends on**: T001
  - **Boundaries**: change `packages/spec-kit-linear/src/spec_kit_linear/{reporting,cli,work_state}.py` and `packages/spec-kit-linear/tests/unit/{test_reporting,test_cli,test_work_state}.py`; preserve T001's scan/mutation contracts and remote-owned defaults.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_reporting.py packages/spec-kit-linear/tests/unit/test_cli.py packages/spec-kit-linear/tests/unit/test_work_state.py -q` -> reports distinguish unknown from defaults, name affected scope, and recovery plus an unchanged repeat performs only the required transition.
  - **Delivery**: single PR (~200 authored lines)
  - **Completion evidence**: PR [#120](https://github.com/tserdeiro/spec-kit/pull/120); focused reporting/CLI/work-state suite: 145 passed, 104 subtests; configured Backlog/Triage creation and recovery converge with zero repeat operations; `git diff --check` clean. Final candidate review required before ready.

## Phase 2: User Story 1 - Trust the state of ongoing work (P1)

**Goal**: Open work outranks old merges; any draft keeps an item In Progress.
Equivalent inputs choose the same PR witness.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_work_state.py packages/spec-kit-linear/tests/unit/test_work_items.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> every FR-003/FR-004 combination matches for tasks, bugs, and chores.

- [x] T003 [US1] Make remaining open work determine state in packages/spec-kit-linear/src/spec_kit_linear/work_state.py
  - **Traces**: FR-003, FR-004, FR-007, SC-001, C-001; plan D3; outcome: shared selector ranks draft before ready before merged, chooses the lowest PR number within a rank, and ignores closed/unmerged PRs. Test reordered/repeated evidence, merged+draft, merged+ready, draft+ready, all-ready, and complete-empty cases; checked/unchecked tasks, branch-only bugs/chores, unrelated feature/task names, and a remotely Done item returning to In Progress or In Review. Assert the PR witness and next action alongside state.
  - **Depends on**: T002
  - **Boundaries**: change `packages/spec-kit-linear/src/spec_kit_linear/{work_state,work_items}.py` and `packages/spec-kit-linear/tests/unit/{test_work_state,test_work_items,test_cli}.py`; preserve complete-observation gating and exact branch associations.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_work_state.py packages/spec-kit-linear/tests/unit/test_work_items.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> no open item is Done, no draft item is entirely reviewable, and permutations yield identical state/witness.
  - **Delivery**: single PR (~170 authored lines)
  - **Completion evidence**: PR [#121](https://github.com/tserdeiro/spec-kit/pull/121); exact work-state/work-item/CLI suite: 153 passed, 141 subtests; historical merge plus open work yields correct state, witness and next action; `git diff --check` clean. Final candidate review required before ready.

## Phase 3: User Story 3 - Keep all relevant work visible at scale (P2)

**Goal**: Later pages participate in derivation; interrupted large observations
preserve all affected states.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_work_state.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> more than 200 PRs retain all relevant evidence, while failed traversal makes no unsupported transition.

- [x] T004 [US3] Prove large-repository derivation through the CLI in packages/spec-kit-linear/tests/unit/test_cli.py
  - **Traces**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-007, SC-001, SC-002, SC-003, C-001; plan D1-D3; outcome: exercise the real scanner-to-planner path with fake `gh` responses containing at least 301 PRs. Put relevant drafts, ready PRs, and merges beyond 200, including a late draft overturning an earlier merge. Check all work-item types, identical/contradictory duplicates, malformed later pages, timeout/truncation, and valid partial JSON with nonzero exit. Verify repository targeting and isolation of identical feature numbers in separate temporary repos; status and push agree.
  - **Depends on**: T003
  - **Boundaries**: extend `packages/spec-kit-linear/tests/unit/{test_work_state,test_cli}.py` with existing temporary-repo and fake-client facilities; assert T001-T003 behavior through production callers.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_work_state.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> later-page evidence controls state; every uncertain traversal preserves affected states, including items absent from the returned prefix.
  - **Delivery**: single PR (~190 authored lines)
  - **Completion evidence**: PR [#122](https://github.com/tserdeiro/spec-kit/pull/122); exact work-state/CLI suite: 141 passed, 124 subtests; real subprocess exercises 305 records, interruption/malformed preservation and distinct repository observations; `git diff --check` clean. Final candidate review required before ready.

## Phase 4: User Story 2 - Keep failures visible and recovery idempotent (P1)

**Goal**: Preserve confirmed application evidence after a later failure;
runtime handlers report failures and return control to delivery.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_planner_apply.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> partial failures retain precise outcomes, retries converge, and handler warnings remain visible with exit 0.

- [x] T005 [US2] Retain partial application evidence in packages/spec-kit-linear/src/spec_kit_linear/reconciler.py and cli.py
  - **Traces**: FR-008, FR-009, SC-004, SC-005; plan D5; outcome: extend existing apply/error results so failed mutation, precondition, or post-verification retains confirmed applied/recovered IDs, failed operation ID/kind/target when one exists, and unattempted operations. Carry earlier feature-plan successes through a later failure. Distinguish rejected and unconfirmed writes; retain manual nonzero exits. Test failure after success, ambiguous create recovery by identity, ambiguous update, failed readback, fresh preconditions, and retry followed by zero operations, preserving human fields.
  - **Depends on**: T004
  - **Boundaries**: change `packages/spec-kit-linear/src/spec_kit_linear/{reconciler,errors,cli}.py` and `packages/spec-kit-linear/tests/unit/{test_planner_apply,test_cli}.py`; preserve allowlisting, create UUID recovery, and fresh Linear snapshots. Evidence remains invocation-local.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_planner_apply.py packages/spec-kit-linear/tests/unit/test_cli.py -q` -> confirmed outcomes survive failures, uncertain writes are not counted as confirmed, and retries create no duplicate Issues.
  - **Delivery**: single PR (~290 authored lines)
  - **Completion evidence**: PR [#123](https://github.com/tserdeiro/spec-kit/pull/123); focused planner/CLI suite: 152 passed, 78 subtests; full package with loopback permitted: 488 passed, 280 subtests, no skips; rejection, ambiguity, preconditions, readback and postverification preserve partial evidence; `git diff --check` clean. Final candidate review required before ready.

- [ ] T006 [US2] Surface non-blocking reconciliation warnings in packages/spec-kit-linear/src/spec_kit_linear/cli.py
  - **Traces**: FR-005, FR-007, FR-009, SC-002, SC-005; plan D5; outcome: session-start and post-tool-use render authored, sanitized reconciliation warnings to stderr for configured invocations, including GitHub uncertainty and T005's partial Linear failures, while returning exit 0. Missing/disabled configuration retains its quiet no-op. Reuse manual diagnostic content so affected identity and unsuccessful operation remain visible. Test both handlers, successful quiet runs, and secret-shaped error payloads.
  - **Depends on**: T005
  - **Boundaries**: change `packages/spec-kit-linear/src/spec_kit_linear/cli.py` and `packages/spec-kit-linear/tests/unit/test_cli.py`; reuse `redaction.py` and event entrypoints. Preserve registration and manual error exits.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests/unit/test_cli.py packages/spec-kit-linear/tests/unit/test_credentials_redaction.py -q` -> configured failures emit useful sanitized stderr, handlers return 0, successful/disabled runs avoid failure warnings, and raw secrets never appear.
  - **Delivery**: single PR (~190 authored lines)
  - **Completion evidence**: Pending

## Phase 5: Cross-cutting verification

- [ ] T007 Document the implemented contract and local acceptance in packages/spec-kit-linear/README.md and this ledger
  - **Traces**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, SC-001, SC-002, SC-003, SC-004, SC-005, C-001, C-002, C-003; outcome: document precedence, complete/failed/incomplete observations, creation defaults, recovery, and visible handler failures; record full-suite and installed-artifact results, distinguishing local conformance from entry 23's pending live acceptance.
  - **Depends on**: T006
  - **Boundaries**: update `packages/spec-kit-linear/{README.md,CHANGELOG.md}`, `packages/spec-kit-linear/commands/{push,status,session-start,post-tool-use}.md`, and this task's completion evidence. Run existing conformance in a temporary consumer. Preserve distribution pins, generated assets, human fields, and the separate release workflow.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` -> all package tests pass; `bash packages/spec-kit-linear/scripts/conformance/installed-artifact.sh` -> installed-consumer checks pass; `git diff --check` -> clean. Review docs against the implemented state table and error output.
  - **Delivery**: single PR (~120 authored lines)
  - **Completion evidence**: Pending

## Dependencies and stack order

- **Critical path**: T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007.
- **Stack order**: PR T001 -> PR T002 -> PR T003 -> PR T004 -> PR T005 -> PR T006 -> PR T007 while predecessors remain open and ready; otherwise resume from the integrated feature branch.
- **MVP**: T001-T004 deliver complete observations, safe preservation/defaults,
  correct precedence, and large-repository evidence. T005-T007 complete failure
  visibility, retry acceptance, and documentation.
- **Story totals**: US1: 1; US2: 4; US3: 1; cross-cutting: 1. All seven tasks
  remain unchecked. Handoff, assignment, and live acceptance retain the gates
  recorded in `plan.md`.
