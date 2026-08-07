---
description: "Dependency-ordered delivery units for the integration branch"
---

# Tasks: Integration branch

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Phase 1: The retargeted loop (US1)

- [x] T001 Retarget the task delivery loop in presets/default/commands/implement-append.md
  - **Traces**: FR-001, FR-002; outcome: tasks branch from the feature branch after it absorbed the up-to-date default branch
  - **Depends on**: none
  - **Boundaries**: presets/default only; no CLI, no extension code
  - **Evidence**: `scripts/conformance/bundles.sh` green; loop text names the feature branch as base and the drift duty
  - **Delivery**: single PR into 002-integration-branch
  - **Completion evidence**: PR #18 merged into 002-integration-branch 2026-08-06; conformance passed; WOR-28 Done; states derived identically with the feature-branch base (SC-002)

- [x] T002 Retarget /speckit.pr and add the Linear magic word in presets/default/commands/pr.md
  - **Traces**: FR-001, FR-005, SC-004; outcome: feature-task PRs target the feature branch and carry `Fixes <ISSUE-KEY>`; work items keep the default branch
  - **Depends on**: T001
  - **Boundaries**: presets/default only; `gh` remains the only writer
  - **Evidence**: dogfooded on this feature's own task PRs; conformance green
  - **Delivery**: single PR into 002-integration-branch
  - **Completion evidence**: PR #19 merged into 002-integration-branch 2026-08-06, opened following the edited pr.md verbatim (base + magic word); conformance passed; WOR-29 Done

## Phase 2: Gate and closure (US2, US3)

- [x] T003 Instruct the product-phase gate in presets/default/templates/tasks-template.md
  - **Traces**: FR-003, SC-001; outcome: a completed product phase commits its artifacts on the feature branch and opens the draft feature PR
  - **Depends on**: none
  - **Boundaries**: presets/default templates only
  - **Evidence**: this feature's own draft PR opened at the close of this product phase; conformance green
  - **Delivery**: single PR into 002-integration-branch
  - **Completion evidence**: PR #20 merged into 002-integration-branch 2026-08-06; conformance passed; WOR-42 Done; gate itself dogfooded by PR #17

- [x] T004 Instruct the feature closure in presets/default/commands/implement-append.md
  - **Traces**: FR-004, SC-003; outcome: all tasks checked → feature PR ready → human review → merge commit → branch deleted → push reconciles
  - **Depends on**: T001
  - **Boundaries**: presets/default only; approval and merge stay human
  - **Evidence**: dogfooded by closing this very feature; conformance green
  - **Delivery**: single PR into 002-integration-branch
  - **Completion evidence**: PR #21 merged into 002-integration-branch 2026-08-06; conformance passed; WOR-43 Done; the ritual executes at this feature's own closure

## Phase 3: Documentation (US4)

- [ ] T005 Document the model and Linear's GitHub integration in README.md
  - **Traces**: FR-006, SC-004; outcome: the workflow section teaches the integration-branch flow; a block documents per-team GitHub integration and magic-word linking
  - **Depends on**: T001, T002, T003, T004
  - **Boundaries**: README (Spanish) and validation/ evidence only
  - **Evidence**: README sections; `validation/integration-branch-stage7-acceptance.md` with the dogfooded run
  - **Delivery**: single PR into 002-integration-branch

## Dependencies and parallel work

T001 → T002 and T001 → T004; T003 is independent; T005 closes after all.
One branch and one draft PR per task, every PR targeting
002-integration-branch; the feature PR itself (opened with this product
phase) closes into main with a merge commit when everything above is
checked.
