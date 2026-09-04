---
description: "Dependency-ordered, traceable delivery units for feature implementation"
---

# Tasks: [FEATURE NAME]

**Inputs**: [spec.md](spec.md), [plan.md](plan.md), and applicable design artifacts
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- **The feature branch (`NNN-slug`) is the integration branch**: every
  task merges into it, and the feature enters the **delivery base** only
  once, through the feature PR, as a merge commit. The delivery base is
  the explicit non-empty `trunk:` value, or the GitHub default branch when
  `trunk:` is absent or empty.
- **Closing the product phase opens the gate**: with this file complete,
  commit the feature artifacts on the feature branch and open the
  **draft feature PR** (`NNN-slug` → delivery base) — `/speckit.pr` on
  the feature branch does it with the canonical body. Reviewing it is how
  the team approves the spec and plan before implementation; the same PR,
  ready once every task is checked, later closes the feature.
- **One branch per task**, named `NNN-T###-short-slug` (feature number, task
  id); its pull request opens as `draft` **against the open task PR it
  stacks on, else the feature branch**.
- **One task in flight per developer, never in parallel**: tasks deliver
  one at a time, in dependency order. Marking the current PR
  `ready for review` is what frees the developer to start the next task;
  each task stacks its branch on the previous task's ready, unmerged PR
  (declared in the PR's `Stack:` line), or on the feature branch when
  none is open.
- **Starting a task means creating its branch first**: before touching any
  code for `T###`, run `git switch -c NNN-T###-short-slug` from the
  up-to-date feature branch. If you are the implementing agent, do this as
  the first action of the task — the branch is what projects the task to
  *In Progress*.
- A reviewed PR stays under ~400 authored executable lines. A task that
  exceeds it splits into
  [stacked PRs](https://docs.github.com/en/pull-requests/get-started/stacked-prs-quickstart),
  each under the budget and each naming the PR it stacks on. The review
  command warns when a diff exceeds the budget.
- Task states project to Linear from observable reality: the checkbox, the
  task branch, and the PR's draft/ready/merged state.

## Task block format

Every task is one resumable delivery unit. Replace all sample values. Use `[US#]` in user-story phases. No parallel markers: tasks are ordered by their dependencies alone.

```markdown
- [ ] T001 [US?] Deliver a concrete outcome in exact/path.ext
  - **Traces**: FR-001, SC-001; outcome: [observable result]
  - **Depends on**: none | T###
  - **Boundaries**: [files or system surfaces changed and protected]
  - **Evidence**: `[command]` -> [expected result or required review]
  - **Delivery**: single PR | stacked PR [N] on [T###'s PR]
  - **Completion evidence**: [filled in the task PR's final commit, before ready for review; the merge lands it on the feature branch]
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

## Dependencies and stack order

- **Critical path**: [T### -> T### -> T###]
- **Stack order**: [PR 1 -> PR 2, or `Not applicable`]
