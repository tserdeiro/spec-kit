---
description: "Dependency-ordered delivery units for the guided flow"
---

# Tasks: Guided flow

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Phase 1: Orientation (US1)

- [x] T001 Instruct the task branch at task start in presets/default/templates/tasks-template.md
  - **Traces**: FR-002; outcome: the implementing agent is told to create `NNN-T###-slug` before touching code
  - **Depends on**: none
  - **Boundaries**: presets/default only; no CLI, no extension code
  - **Evidence**: template diff; conformance `scripts/conformance/bundles.sh` still green
  - **Delivery**: single PR
  - **Completion evidence**: PR #1 merged 2026-08-06; conformance passed; WOR-18 Done

- [x] T002 Add the NEXT column to status in packages/spec-kit-linear
  - **Traces**: FR-001, SC-001; outcome: every task/work-item row suggests its next action, in text and --json
  - **Depends on**: none
  - **Boundaries**: reporting/cli of spec-kit-linear; output only, no new command or flag
  - **Evidence**: `uv run pytest packages/spec-kit-linear/tests` -> green, with new NEXT tests
  - **Delivery**: single PR
  - **Completion evidence**: PR #3 merged 2026-08-06; 332 tests green; WOR-19 Done

## Phase 2: Execution (US2)

- [ ] T003 Create the /speckit.pr preset command in presets/default
  - **Traces**: FR-003, SC-002; outcome: one agent command guarantees the branch and opens the canonical draft PR, idempotently
  - **Depends on**: T001
  - **Boundaries**: presets/default/commands; gh is the only writer; no extension code
  - **Evidence**: dogfooded on T003's own PR; bundles conformance green with the grown preset
  - **Delivery**: single PR
  - **Completion evidence**: Pending

## Phase 3: Health and release (US3, US4)

- [ ] T004 Create the /speckit.doctor preset command in presets/default
  - **Traces**: FR-004, SC-003; outcome: one command, both doctors, one summary with remediations
  - **Depends on**: none
  - **Boundaries**: presets/default/commands
  - **Evidence**: run against this repo (healthy) and with the engine root emptied (remediation surfaced)
  - **Delivery**: single PR
  - **Completion evidence**: Pending

- [ ] T005 Create scripts/release/publish.sh
  - **Traces**: FR-005, SC-004; outcome: one invocation performs tags, builds, lock digests, push, releases; fails closed on dirty tree
  - **Depends on**: none
  - **Boundaries**: scripts/release; composes build-release.sh and build-bundles.sh
  - **Evidence**: dry exercise against a throwaway tag; used for this feature's own release
  - **Delivery**: single PR
  - **Completion evidence**: Pending

## Dependencies and parallel work

- **Critical path**: T001 -> T003
- **Parallel opportunities**: T002, T004, T005 (disjoint boundaries)
- **Stack order**: Not applicable
