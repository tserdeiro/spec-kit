# Feature Specification: Guided flow

**Feature directory**: `specs/001-guided-flow`
**Status**: Approved — Stage 6 of `docs/plan.md`
**Input**: "The flow tells and does the next step: branch-at-task-start instruction, /speckit.pr draft-PR command, NEXT column in status, /speckit.doctor, one-step maintainer release"

## Problem and affected users

The middle of the delivery workflow (steps 4–5) runs on tribal knowledge:
naming the task branch, opening the draft PR, filling the canonical body,
and knowing what to do next are all manual and undocumented at the moment
of action. Experienced developers absorb the conventions; inexperienced
ones stall exactly there. Diagnosing a broken setup requires knowing that
two separate doctors exist. Maintainers release through six manual steps.

## Desired outcome

At every point of the flow, the developer can ask what comes next and get
the answer derived from reality — and the two most error-prone manual
steps (the task branch and the draft PR) are guaranteed by the tooling
rather than by memory.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - The flow tells me what's next (Priority: P1)

A developer, junior or not, asks the agent where they stand. The status
table answers with the derived state of each task and work item **and the
suggested next action** ("open the draft PR", "self-review, then mark
ready", "waiting for the final review", "ask for the merge").

**Why this priority**: orientation is the cheapest fix for the biggest
junior friction; it needs no new surface.

**Independent test**: a task with a branch and no PR shows NEXT = open the
draft PR; a merged task shows no pending action.

**Acceptance scenarios**:

1. **Given** a task whose branch exists and has no PR, **When** the
   developer runs `status`, **Then** the row suggests opening the draft PR.
2. **Given** a task whose PR is ready and reviewed, **When** the developer
   runs `status`, **Then** the row suggests asking for the human merge.
3. **Given** no `gh` available, **When** the developer runs `status`,
   **Then** PR-derived suggestions degrade with the existing warning and
   branch-derived ones still appear.

### User Story 2 - The PR opens itself, correctly (Priority: P1)

When a task's implementation is done, the developer invokes one agent
command. It guarantees the branch invariant (right name; created if
missing), fills the canonical PR body from the feature artifacts, and
opens the draft PR.

**Why this priority**: the draft PR with the canonical body is the point
of no return where conventions must hold; today nothing guarantees them.

**Independent test**: from a finished task with no branch and no PR, one
command produces a correctly named branch and a draft PR whose body
carries tracker, evidence, and Stack line.

**Acceptance scenarios**:

1. **Given** a finished task on a misnamed or missing branch, **When** the
   developer runs the PR command, **Then** the branch exists with the
   `NNN-T###-slug` name before the PR opens.
2. **Given** the PR already exists, **When** the command runs again,
   **Then** nothing is duplicated and the developer is told where the PR is.

### User Story 3 - One health check (Priority: P2)

Anything broken, one command: it runs both extensions' doctors and
summarizes a single result with each remediation.

**Independent test**: with a healthy setup the summary is a single pass;
with the engine missing it surfaces the code-review remediation.

**Acceptance scenarios**:

1. **Given** a healthy consumer, **When** the developer runs the health
   command, **Then** one summary reports both extensions passing.

### User Story 4 - One-step release (Priority: P3)

The maintainer releases with one script run: tags, reproducible builds,
lock digests, push, GitHub releases.

**Independent test**: one invocation from a clean tree produces the tags,
artifacts, lock commit, and published releases for the requested versions.

**Acceptance scenarios**:

1. **Given** a clean tree and a version bump, **When** the maintainer runs
   the release script, **Then** the lock records the new digests and the
   releases exist with their artifacts.

### Edge cases

- A task with several PRs (stacked): NEXT reflects the most advanced one,
  like state derivation already does.
- The PR command on a work item (issue-key branch) uses the issue key as
  tracker and skips task-only fields.
- The release script must refuse a dirty tree and stop on the first
  failing build, leaving no tag pushed for an unbuilt artifact.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: `status` MUST show, per task and work item, the suggested
  next action derived from the same observable state as the projection.
- **FR-002**: The tasks template MUST instruct the implementing agent to
  create the task branch (`NNN-T###-slug`) when it starts a task.
- **FR-003**: A preset agent command (`/speckit.pr`) MUST validate or
  create the task branch, fill the canonical PR body from the feature
  artifacts, and open the PR as draft; re-running MUST be idempotent.
- **FR-004**: A preset agent command (`/speckit.doctor`) MUST run both
  extensions' doctors and summarize one result with remediations.
- **FR-005**: A maintainer script MUST perform the whole release —
  tags, builds, lock digests, push, GitHub releases — in one invocation,
  failing closed on a dirty tree or a failed build.

### Constraints and boundaries

- **C-001**: No new CLI commands or flags in either extension; FR-001 is
  output only, FR-003/FR-004 are preset agent commands, FR-005 is repo
  tooling.
- **C-002**: NEXT suggestions never mutate anything; approval and merge
  remain human.
- **C-003**: Everything composes existing mechanisms (preset commands,
  existing status output, existing build scripts).

## Success criteria *(mandatory)*

- **SC-001**: A developer can drive a task from start to merged without
  consulting a human or the README for the next step.
- **SC-002**: A draft PR opened by the command always satisfies the branch
  convention and the canonical body sections.
- **SC-003**: One command answers "is my setup healthy?" for both
  extensions.
- **SC-004**: A release requires exactly one maintainer invocation plus
  the human review of its output.

## Assumptions and dependencies

- **A-001**: `gh` remains the PR mechanism; without it, FR-003 degrades
  with a clear message and FR-001 keeps branch-derived suggestions.
- **A-002**: Point 6.1 (template instruction) makes the branch exist in
  the common case; FR-003 is the guarantee, not the norm.

## Source references

- **SRC-001**: `docs/plan.md` — Stage 6, Guided flow.
- **SRC-002**: `docs/vision.md` — DX principles and workflow steps 4–7.
- **SRC-003**: Stage 3/5 acceptance runs (`validation/`), where the manual
  friction this feature removes was recorded first-hand.
