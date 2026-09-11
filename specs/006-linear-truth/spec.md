# Feature Specification: Linear state from complete observations

**Feature directory**: `specs/006-linear-truth`
**Status**: Draft
**Input**: [Reliability entry 01](../../docs/reliability/01-linear-truth.md), with the [round's common decisions](../../docs/reliability.md).

## Problem and affected users

Developers and reviewers cannot trust Linear when a failed or truncated
GitHub read looks like an empty PR list. Checked tasks or previously merged
PRs can then mark ongoing work complete. A ready PR can also hide another
draft for the same work item, and the current 200-PR limit loses evidence.

## Desired outcome

Linear reflects all relevant observed work. Open development takes precedence
over review or past merges. Uncertainty preserves existing remote states and
is explained; a verified empty result remains usable evidence.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Trust the state of ongoing work (Priority: P1)

A developer or reviewer sees whether the whole task, bug, or chore is still
in development, ready for review, or complete.

**Why this priority**: False completion and premature review hide unfinished work.

**Independent test**: Reconcile each work-item type against complete PR
observations and compare its state with the precedence table in FR-003.

**Acceptance scenarios**:

1. **Given** a merged PR and an open draft for one item, **When** reconciled,
   **Then** the item is In Progress, including when its task checkbox is checked.
2. **Given** a merged PR and an open ready PR, **When** reconciled, **Then**
   the item is In Review rather than Done.
3. **Given** several open PRs, **When** reconciled, **Then** any draft keeps
   the item In Progress; only an entirely ready open set yields In Review.
4. **Given** a complete observation with no open PRs, **When** reconciled,
   **Then** a merged PR permits Done; without one, the local evidence rules apply.

### User Story 2 - Preserve truth through incomplete observations (Priority: P1)

A developer can continue delivery during a service failure without silently
replacing Linear states with guesses.

**Why this priority**: Correct precedence is ineffective when missing evidence
is treated as proof of absence.

**Independent test**: Exercise failed reads, interrupted pagination, recovery,
and issue creation; inspect state changes and visible diagnostics.

**Acceptance scenarios**:

1. **Given** an existing Issue and an unavailable or unreadable GitHub result,
   **When** reconciled, **Then** its remote state is preserved and the affected
   work and reason are reported, even with a checked task or observed branch.
2. **Given** some PRs were read before pagination failed, **When** reconciled,
   **Then** affected states remain unchanged, even if the partial result
   contains merged or ready PRs.
3. **Given** a task Issue must be created while observation is uncertain,
   **When** created, **Then** Linear chooses its configured initial state;
   the report identifies that default separately from an unverified work state.
4. **Given** observation recovers, **When** reconciled again, **Then** current
   complete evidence determines the state; a further unchanged run writes nothing.
5. **Given** Linear rejects a reconciliation operation, **When** delivery
   continues, **Then** the failure and affected work remain visible, success is
   not claimed for that operation, and a retry converges without duplicates.

### User Story 3 - Keep all relevant work visible at scale (Priority: P2)

A team with a long PR history receives the same correct states as a small team.

**Why this priority**: Repository growth must not silently remove evidence.

**Independent test**: Use a repository fixture with more than 200 PRs and
relevant draft, ready, and merged PRs beyond the former limit.

**Acceptance scenarios**:

1. **Given** relevant PRs on later pages, **When** observation finishes,
   **Then** all contribute to state derivation, irrespective of listing order.
2. **Given** a complete empty PR result, **When** reconciled, **Then** checked
   tasks are Done, unchecked tasks with a branch are In Progress, and unchecked
   tasks without a branch are unstarted; bugs and chores follow FR-004.

### Edge cases

- Closed, unmerged PRs do not establish completion or readiness (FR-004).
- An already Done Issue returns to In Progress or In Review when a complete
  observation finds relevant open work (FR-003).
- Reordering or repeating PR observations does not alter the derived state.
- Failure to establish completeness preserves every state depending on that
  observation, including items absent from the partial result (FR-005).
- Similar task numbers in other features or repositories cannot affect the
  selected item's state (C-001).

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Observation MUST distinguish complete results, including verified
  absence of PRs, from failed or incomplete results. Missing access, malformed
  evidence, and interrupted reads MUST remain explicit uncertainty.
- **FR-002**: Observation MUST exhaust all pages needed to include every relevant
  PR. A fixed result ceiling or a successful first page MUST NOT establish
  completeness; relevant PRs beyond 200 MUST participate.
- **FR-003**: With complete observation, tasks, bugs, and chores MUST use the
  following precedence, independent of PR order or task checkbox:

  | Relevant PR evidence, first matching row | Derived state |
  | --- | --- |
  | Any open draft, including a mix with ready or merged PRs | In Progress |
  | Open PRs exist and all are ready | In Review |
  | No open PRs and at least one merged PR | Done |
  | No open or merged PRs | Local evidence rules in FR-004 |

- **FR-004**: After complete observation finds no open or merged PRs, a checked
  task MUST be Done; otherwise a task branch means In Progress and no branch
  means unstarted. A bug or chore with a branch MUST be In Progress; without
  a branch its existing state MUST remain untouched. Closed, unmerged PRs
  MUST be ignored for this derivation.
- **FR-005**: Failed or incomplete observation MUST preserve affected existing
  Linear states. Checkboxes, branches, and partial PR evidence MUST NOT supply
  replacement states. Reports MUST identify the uncertainty, affected scope,
  and reason instead of presenting a derived state as verified.
- **FR-006**: Creating a task Issue during uncertainty MUST omit any derived
  workflow state and leave its initial state to Linear's configured default.
  Reports MUST distinguish that remote default from a verified derived state.
- **FR-007**: Read-only status and reconciliation MUST apply the same evidence
  and precedence rules. Recovery MUST use fresh complete observations.
- **FR-008**: Repeating reconciliation with unchanged evidence and an already
  matching remote projection MUST produce zero remote mutations. Retrying
  after partial success MUST converge without duplicate Issues.
- **FR-009**: Linear failures MUST identify unsuccessful operations and affected
  work visibly, preserve truthful results for successful operations, and allow
  the surrounding delivery workflow to continue.

### Constraints and boundaries

- **C-001**: Preserve feature `NNN-slug` and task `NNN-T###-slug` naming, with
  feature numbers unique within a repository and one bound Linear team.
  Existing bug/chore branch identities and task PR links remain the boundary
  for associating evidence; this feature changes state derivation.
- **C-002**: Repository artifacts remain durable truth and Linear remains a
  projection. Bugs and chores originate as human-created Issues; reconciliation
  changes only their workflow state and preserves human-owned content.
- **C-003**: Deliver reliability entry 01 with local fixture-based acceptance.
  Published-distribution and live remote acceptance belong to entry 23;
  subsequent reliability entries retain their own scope and sequence.

### Key entities

- **Work item**: A feature task, bug, or chore associated with its repository,
  Linear Issue, branches, and relevant PRs; only feature tasks have checkboxes.
- **PR observation**: The relevant PR evidence and whether its coverage is
  complete, failed, or incomplete, with a reason for uncertainty.
- **State projection**: A verified desired workflow state, or an explicit
  decision to preserve the existing state because evidence is uncertain.

## Success criteria *(mandatory)*

- **SC-001**: Across all three work-item types, 100% of complete-observation
  acceptance cases match FR-003/FR-004; zero items with open PRs appear Done,
  and zero items with an open draft appear entirely ready for review.
- **SC-002**: Every failed or incomplete-observation case preserves affected
  existing states and explains why. Every creation-under-uncertainty case
  leaves the initial state to the remote default without claiming verification.
- **SC-003**: In a fixture exceeding 200 PRs, 100% of relevant PRs affect the
  result, including those on later pages; interrupted pagination yields no
  unsupported state transitions.
- **SC-004**: Every unchanged second reconciliation produces zero mutations;
  recovery and partial-success retries converge without duplicate Issues.
- **SC-005**: Every simulated Linear failure is visible with affected work and
  unsuccessful operations identified, while the surrounding delivery continues.

## Assumptions and dependencies

- **A-001**: Existing lifecycle configuration maps logical states to team
  states. This feature uses that mapping and its existing explicit diagnostics.
- **A-002**: A task checkbox remains valid completion evidence only after a
  complete observation excludes open PRs; closed, unmerged PRs remain neutral.
- **A-003**: Linear's configured initial Issue state is a remote-owned default,
  not evidence of progress. Uncertainty can therefore coexist with Issue
  creation, provided no derived state is supplied or claimed.
- **A-004**: Fixtures demonstrate this specification's behavior. Live agent,
  GitHub, and Linear acceptance remains separately pending under entry 23.

## Source references

- **SRC-001**: [Reliability entry 01](../../docs/reliability/01-linear-truth.md).
- **SRC-002**: [Common decisions and execution order](../../docs/reliability.md).
- **SRC-003**: [Product vision](../../docs/vision.md) and [delivery plan](../../docs/plan.md).
- **SRC-004**: Current [task derivation](../../packages/spec-kit-linear/src/spec_kit_linear/work_state.py), [PR observation](../../packages/spec-kit-linear/src/spec_kit_linear/github.py), and [bug/chore derivation](../../packages/spec-kit-linear/src/spec_kit_linear/work_items.py).
