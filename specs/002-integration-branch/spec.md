# Feature Specification: Integration branch

**Feature directory**: `specs/002-integration-branch`
**Status**: Draft — Stage 7 of `docs/plan.md`
**Input**: "Task PRs merge into the feature branch upstream already creates; one draft feature PR opens at the end of the product phase as the spec-review gate and closes the feature into the default branch with a merge commit; Linear links natively via branch names and magic words"

## Problem and affected users

Every task PR targets the default branch directly. Four consequences:
half-finished features reach the default branch task by task; stacked
tasks juggle a moving base against it; the reviewer never sees the whole
feature in one place before it lands; and the feature branch upstream
creates at `specify` is vestigial — a recorded friction nobody knew what
to do with. Separately, Linear only moves when someone remembers to run
`push`.

## Desired outcome

The feature branch is the integration unit (the vision's "Integración por
feature"): the product phase commits its artifacts there and closes by
opening one draft feature PR — the spec-review gate. Each task branches
from and merges into the feature branch. With every task checked, that
same PR — composed of already-reviewed task PRs — receives the final
human review and enters the default branch as one merge commit; the
branch is deleted. Linear reflects PR events in real time through its
native GitHub integration; `push` stays the idempotent reconciler.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Tasks deliver into the feature branch (Priority: P1)

A developer starts a task: the branch forks from the up-to-date feature
branch, the draft PR targets the feature branch, and every derived state
(*In Progress*, *In Review*, *Done*) behaves exactly as before.

**Why this priority**: the retargeted task loop is the model; everything
else composes around it.

**Independent test**: a task PR based on the feature branch derives the
same states as one based on the default branch used to.

**Acceptance scenarios**:

1. **Given** a task started with the loop, **When** the draft PR opens,
   **Then** its base is the feature branch and the task derives
   *In Progress*.
2. **Given** a task PR merged into the feature branch, **When** `push`
   runs, **Then** the task derives *Done* — no default-branch merge
   required.

### User Story 2 - The feature PR is the gate (Priority: P2)

The product phase ends by opening the draft feature PR
(`NNN-slug → default`). The team reviews the spec and plan there before
implementation starts, and nothing half-done can reach the default branch
because tasks never target it.

**Independent test**: after the product phase, the draft feature PR
exists and contains only `specs/<feature>/` artifacts (plus
`.specify/feature.json`).

**Acceptance scenarios**:

1. **Given** a completed product phase, **When** the phase closes,
   **Then** the draft feature PR is open with the artifacts as its diff.

### User Story 3 - Closing the feature shows the whole movie (Priority: P2)

With every task checked, the developer marks the feature PR ready. The
reviewer sees the composed feature — built from PRs already reviewed one
by one — approves, and a human merges with a **merge commit**; the
feature branch is deleted.

**Independent test**: dogfooded by this very feature's delivery.

**Acceptance scenarios**:

1. **Given** all tasks checked, **When** the feature PR turns ready,
   **Then** its diff equals the union of the merged task PRs.
2. **Given** the human merge, **Then** the default branch gains one merge
   commit preserving task history, and the feature branch is deleted.

### User Story 4 - Linear moves in real time (Priority: P3)

Task PRs carry the closing magic word (`Fixes WOR-###`); work-item
branches already match Linear's branch format. With the team's GitHub
integration enabled, states transition on PR events — `push` remains the
reconciliation that rules.

**Independent test**: a PR carrying the magic word transitions its issue
without anyone running `push`.

### Edge cases

- Default-branch drift: `implement` brings the default branch into the
  feature branch before the first task; later refreshes are the
  developer's duty.
- A task PR mistakenly targeting the default branch: the PR command must
  target the feature branch for feature tasks and say so.
- Work items (bugs/chores) are not features: their branches and PRs keep
  targeting the default branch.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Task branches MUST fork from the feature branch and their
  PRs MUST target it; work-item PRs keep the default branch.
- **FR-002**: The implement loop MUST first bring the default branch into
  the feature branch, then start tasks from it.
- **FR-003**: The product phase MUST close by opening the draft feature
  PR against the default branch.
- **FR-004**: Feature closure MUST be: every task checked → feature PR
  ready → final human review → **merge commit** → feature branch deleted.
  Approval and merge stay human-only.
- **FR-005**: Task PRs MUST carry the Linear closing magic word; state
  derivation and `push` idempotency MUST remain unchanged.
- **FR-006**: The README MUST document the model and the per-team Linear
  GitHub integration settings.

### Constraints and boundaries

- **C-001**: Composition only — preset commands/templates and README. No
  CLI code, no extension code, no upstream asset changes.
- **C-002**: Enabling Linear's GitHub integration is a human, per-team
  setting; the harness documents it, never configures it.

## Success criteria *(mandatory)*

- **SC-001**: A feature delivers end-to-end with zero task merges into
  the default branch before the single final merge commit.
- **SC-002**: Every state derivation over feature-branch-based task PRs
  matches today's behavior; a repeated `push` is still 0 operations.
- **SC-003**: The final feature PR diff equals the union of its reviewed
  task PRs — nothing lands unreviewed.
- **SC-004**: A linked PR event moves its Linear issue without `push`.

## Assumptions and dependencies

- **A-001**: One repository per feature; the feature branch lives until
  its final merge.
- **A-002**: A workspace admin enables Linear's GitHub integration; until
  then, `push` alone keeps projecting states (degraded freshness only).

## Source references

- **SRC-001**: `docs/vision.md` — "Integración por feature" (authority).
- **SRC-002**: `docs/plan.md` — Stage 7.
- **SRC-003**: https://linear.app/docs/github — linking and per-team
  transition settings.
