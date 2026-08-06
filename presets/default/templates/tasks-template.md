---
description: "Dependency-ordered, traceable delivery units for feature implementation"
---

# Tasks: [FEATURE NAME]

**Inputs**: [spec.md](spec.md), [plan.md](plan.md), and applicable design artifacts
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- **One branch per task**, named `NNN-T###-short-slug` (feature number, task
  id); its pull request opens as `draft`.
- A reviewed PR stays under ~400 authored executable lines. A task that
  exceeds it splits into
  [stacked PRs](https://docs.github.com/en/pull-requests/get-started/stacked-prs-quickstart),
  each under the budget and each naming the PR it stacks on. The review
  command warns when a diff exceeds the budget.
- Task states project to Linear from observable reality: the checkbox, the
  task branch, and the PR's draft/ready/merged state.

## Task block format

Every task is one resumable delivery unit. Replace all sample values. Use `[P]` only when files do not overlap and dependencies are complete; use `[US#]` in user-story phases.

```markdown
- [ ] T001 [P?] [US?] Deliver a concrete outcome in exact/path.ext
  - **Traces**: FR-001, SC-001; outcome: [observable result]
  - **Depends on**: none | T###
  - **Boundaries**: [files or system surfaces changed and protected]
  - **Evidence**: `[command]` -> [expected result or required review]
  - **Delivery**: single PR | stacked PR [N] on [T###'s PR]
  - **Completion evidence**: [record only after completion; checked means evidence exists]
```

## Phase 1: Setup

**Purpose**: Establish only feature-specific prerequisites.

- [ ] T001 [Concrete setup outcome in exact/path.ext]
  - **Traces**: [FR/SC IDs]; outcome: [observable result]
  - **Depends on**: none
  - **Boundaries**: [changed and protected surfaces]
  - **Evidence**: `[command]` -> [expected result]
  - **Delivery**: [single PR | stacked PR N on T###]
  - **Completion evidence**: Pending

## Phase 2: Foundational

**Purpose**: Complete work that blocks every user story. Remove this phase if none exists.

- [ ] T002 [Foundational outcome in exact/path.ext]
  - **Traces**: [FR/SC IDs]; outcome: [observable result]
  - **Depends on**: T001
  - **Boundaries**: [changed and protected surfaces]
  - **Evidence**: `[command]` -> [expected result]
  - **Delivery**: [single PR | stacked PR N on T###]
  - **Completion evidence**: Pending

## Phase 3: User Story 1 - [Title] (P1)

**Goal**: [Observable story outcome]
**Independent evidence**: `[focused command or demonstration]`

- [ ] T003 [US1] [Implementation outcome in exact/path.ext]
  - **Traces**: [FR/SC IDs]; outcome: [observable result]
  - **Depends on**: [none or task IDs]
  - **Boundaries**: [changed and protected surfaces]
  - **Evidence**: `[command]` -> [expected result]
  - **Delivery**: [single PR | stacked PR N on T###]
  - **Completion evidence**: Pending

## Final phase: Cross-cutting verification

- [ ] T004 [Repository-level evidence or documentation outcome in exact/path.ext]
  - **Traces**: [FR/SC IDs]; outcome: [observable result]
  - **Depends on**: [task IDs]
  - **Boundaries**: [changed and protected surfaces]
  - **Evidence**: `[command]` -> [expected result]
  - **Delivery**: [single PR | stacked PR N on T###]
  - **Completion evidence**: Pending

## Dependencies and parallel work

- **Critical path**: [T### -> T### -> T###]
- **Parallel opportunities**: [task IDs and why their boundaries do not overlap]
- **Stack order**: [PR 1 -> PR 2, or `Not applicable`]

## Product handoff

- **Analysis**: [pending | clean with requirement/task counts and coverage]
- **Technical approval**: [pending | record]
- **Linear synchronization**: [pending | reviewed dry-run and applied mapping]
- **Assignment**: [pending | every executable task individually assigned]
- **Handoff state**: `not-ready-for-development` until every gate above is complete.

