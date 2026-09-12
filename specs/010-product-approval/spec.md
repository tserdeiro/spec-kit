# Feature Specification: Publish after product approval

**Feature directory**: `specs/010-product-approval`
**Status**: Draft
**Input**: The complete user-supplied `docs/reliability/06-product-approval.md`.

## Problem and affected users

Product authors currently commit drafts at each phase, and implementation can
open its own feature gate. A published plan therefore does not reliably mean
that a human approved the product handoff. Developers need an agreed, durable
starting point that survives a new session.

## Desired outcome

Refine `specify → clarify → plan → tasks → analyze` locally. Present the
verified result for explicit human product approval, then execute its authorized
commit, publication, and canonical draft feature PR. Development consumes that
published handoff and reports missing prerequisites before starting a task.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Refine a local draft (Priority: P1)

A product author completes and revises the five product phases without
publishing an unapproved draft.

**Why this priority**: Approval must precede the first durable publication.

**Independent test**: Complete the product phases with auto-commit enabled;
compare feature history and remote branches/PRs before and after.

**Acceptance scenarios**:

1. **Given** unapproved product artifacts, **When** any product phase or its
   before/after hooks runs, **Then** the artifacts stay local and no automatic
   artifact commit, Git push, or feature PR creation occurs.
2. **Given** completed tasks and analysis, **When** the agent presents the
   result, **Then** it names unresolved findings and handoff prerequisites and
   waits for an explicit decision on the concrete artifacts.
3. **Given** an analysis failure or a human request for changes, **When** the
   author continues refining, **Then** the handoff remains unpublished.

### User Story 2 - Publish the approved handoff once (Priority: P1)

A human approves the verified spec, plan, and tasks. The agent performs the
 authorized publication and exposes the remaining development prerequisites.

**Why this priority**: An approved local result must become usable by another session.

**Independent test**: Approve one analyzed feature, publish it, and repeat the
closure in a fresh session; inspect its artifacts, PR, and Linear projection.

**Acceptance scenarios**:

1. **Given** clean analysis and explicit approval of the presented artifacts,
   **When** closure runs, **Then** only that feature's artifacts are committed
   and pushed and the existing PR routine opens or updates its one draft PR.
2. **Given** a completed or partially completed publication, **When** closure
   is retried, **Then** it reuses confirmed Git, PR, and Linear resources without
   duplicate commits, PRs, Projects, or Issues for unchanged artifacts.
3. **Given** publication succeeded but Linear synchronization or task assignment
   is incomplete, **When** handoff status is reported, **Then** development
   readiness remains pending with the specific outstanding action.
4. **Given** a published feature, **When** product scope changes, **Then** the
   changed artifacts require fresh analysis and human approval before publication.

### User Story 3 - Start from a coherent published gate (Priority: P1)

A developer starts or resumes work from repository and remote evidence without
needing the original product conversation.

**Why this priority**: Implementation must consume the handoff rather than manufacture it.

**Independent test**: Start implementation in fresh consumers with missing,
closed, stale, and valid feature gates; observe whether task work starts.

**Acceptance scenarios**:

1. **Given** no feature PR or a closed/merged feature PR, **When** implementation
   starts, **Then** it reports pending product closure and creates no gate,
   artifact commit, task branch, or task PR.
2. **Given** an open feature PR with unpublished product edits, mismatched
   feature/base, or unverified remote state, **When** implementation starts,
   **Then** it stops before mutating work and names the inconsistency.
3. **Given** an open coherent gate and complete development prerequisites,
   **When** a new session starts implementation, **Then** it can continue from
   the published artifacts without approving that unchanged handoff again.
4. **Given** normal task completion changes, **When** the next task starts,
   **Then** completion evidence and checkbox progress alone do not require new
   product approval; changes to task intent or delivery constraints do.

### Edge cases

- Approval applies to the artifact content presented. A subsequent edit before
  publication invalidates that decision for the changed content.
- A lost response after push or PR creation requires observation before retry.
  A permission or network failure never counts as successful publication.
- Existing unrelated dirty files remain untouched and outside the artifact commit.
- Rejected/closed feature gates remain human decisions, not automatic reopen requests.
- Linear projection can run during planning and task generation under the current
  contract; its existence is not product approval or development readiness.
- Optional discovery assessments remain separate from delivery artifacts.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: All five product phases MUST retain unapproved artifacts locally,
  including when configured hooks would otherwise auto-commit them.
- **FR-002**: Product closure MUST present the concrete spec, plan, tasks, and
  analysis result and require explicit human approval before their publication.
- **FR-003**: Authorized closure MUST commit only the active feature's artifacts,
  push them, and create or update its canonical draft feature PR.
- **FR-004**: Repeated or interrupted closure MUST observe completed operations
  and reuse the same feature PR and Linear projection for unchanged artifacts.
- **FR-005**: Development readiness MUST preserve clean analysis, independent
  human technical approval, reviewed Linear synchronization, and assignment of
  every executable task; incomplete prerequisites MUST remain visible and blocking.
- **FR-006**: Implementation MUST validate an open feature gate and coherent
  published product artifacts before any mutating hook or task operation; it
  MUST return pending product closure instead of creating a missing gate.
- **FR-007**: Changed scope, acceptance, plan decisions, or task definitions MUST
  receive fresh analysis and explicit approval before publication. Task completion
  checkboxes and completion evidence alone MUST preserve the accepted handoff.
- **FR-008**: Published repository and PR evidence MUST let a new session recover
  the unchanged handoff without a separate approval registry or chat history.
- **FR-009**: Failure diagnostics MUST distinguish approval, publication,
  gate-consistency, Linear, and assignment gaps and identify the next action;
  uncertain evidence MUST NOT authorize task work.
- **FR-010**: Vision, constitution, README, authored commands/templates, and
  authorization guidance MUST agree that agents execute authorized mechanics
  while product approval, final approval, and merge remain human decisions.

### Constraints and boundaries

- **C-001**: Use the pinned upstream and its documented preset/extension surfaces;
  preserve native command names, consumer ownership, and selectable integrations.
- **C-002**: Preserve feature/task identities, the current one-task delivery loop,
  canonical PR format, and human-controlled merge. This feature ends at product handoff.
- **C-003**: Reuse Git, the feature PR, and existing Linear projection as durable
  evidence. Keep credentials and operator identity outside repository artifacts.
- **C-004**: Deliver coordinated approval behavior through the default preset
  and project policy; preserve unrelated work and the upstream-managed baseline.

### Key entities

- **Product artifact set**: The active feature's specification, plan, task
  definitions, and applicable supporting design/checklist documents.
- **Published handoff**: Approved artifact content published on the feature
  branch and exposed through its canonical open PR.
- **Development prerequisites**: Analysis, human technical decision, reviewed
  Linear projection, and native task assignments required before development.

## Success criteria *(mandatory)*

- **SC-001**: Every product phase and applicable hook scenario produces zero
  automatic artifact commits, Git publications, or feature PRs before approval.
- **SC-002**: Successful closure and two unchanged retries produce one feature
  PR, one Project, one Issue per task, and zero additional artifact commits.
- **SC-003**: Every missing/closed/stale/uncertain gate or incomplete prerequisite
  scenario stops with a specific next action and zero task-start mutations.
- **SC-004**: A fresh session resumes the valid published handoff; each material
  product-edit scenario requires new approval, while completion-only progress does not.
- **SC-005**: All affected policy and generated command surfaces express the same
  approval boundary; installed-consumer evidence is separate from live execution.

## Assumptions and dependencies

- **A-001**: This is reliability entry 06; the round's order is independent of
  feature numbering. It has no functional dependency on entry 05's implementation.
- **A-002**: Authorization for mechanical publication does not by itself approve
  artifact content that has not yet been presented. Valid approval of the exact
  artifacts is reused within the authorized session.
- **A-003**: Linear's current plan/task projection remains active. Assignment uses
  native Linear; this feature adds no assignment owner or approval database.
- **A-004**: Implementation resumption, task/feature closure, discovery integration,
  generalized PR delivery, and budget policy follow their own round entries.

## Source references

- **SRC-001**: User-supplied `docs/reliability/06-product-approval.md`, complete
  local input dated 2026-09-12; its decisions are captured in this specification.
- **SRC-002**: [Vision](../../docs/vision.md), [delivery plan](../../docs/plan.md),
  [constitution](../../.specify/memory/constitution.md), [operating contract](../../AGENTS.md).
- **SRC-003**: [Product phase closure](../../presets/default/commands/phase-close-append.md),
  [tasks](../../presets/default/commands/tasks.md), [PR](../../presets/default/commands/pr.md),
  [implementation](../../presets/default/commands/implement.md).
