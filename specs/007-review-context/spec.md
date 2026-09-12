# Feature Specification: Sufficient review context

**Feature directory**: `specs/007-review-context`
**Status**: Draft
**Input**: [Reliability entry 02](../../docs/reliability/02-review-context.md), with the [round's common decisions](../../docs/reliability.md).

## Problem and affected users

Developers and reviewers receive whole feature artifacts cut off at configured
size limits. A growing task ledger can hide the task being reviewed and force
an inconclusive result even for a small change. A file reference alone does
not establish that its contents were read.

## Desired outcome

Reviewers receive sufficient context for the actual candidate and review
scope, can read additional material when needed, and leave verifiable evidence
of coverage. Unrelated ledger growth does not prevent a complete review;
missing necessary context still produces an explicit inconclusive result.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Review a task in a large ledger (Priority: P1)

A developer reviews a small task near the end of a long ledger with its full
task definition, delivery strategy, related requirements, and shared context.

**Why this priority**: Ledger growth currently prevents routine task reviews
from reaching a meaningful result.

**Independent test**: Review a task beyond the configured artifact limit in
a ledger whose unrelated earlier entries exceed that limit.

**Acceptance scenarios**:

1. **Given** the relevant task is beyond the ledger cutoff and its necessary
   context fits within the limits, **When** context is prepared, **Then** the
   complete task block, delivery strategy, related requirements, and necessary
   shared context are available without embedding the whole ledger.
2. **Given** that context has been reviewed and no other coverage gap exists,
   **When** the review closes, **Then** omission of unrelated ledger entries
   does not make it inconclusive.
3. **Given** a required shared constraint lies elsewhere in the artifacts,
   **When** the task is reviewed, **Then** the constraint is included or read
   separately with recorded evidence before coverage is considered complete.

### User Story 2 - Cover the whole reviewed scope (Priority: P1)

A reviewer can assess several tasks, a final feature PR, or a bug or chore
following the short path without a task ledger.

**Why this priority**: Selecting one task must not hide other candidate work.

**Independent test**: Review a two-task candidate, a final feature candidate,
and ledger-free bug and chore candidates.

**Acceptance scenarios**:

1. **Given** a candidate covers multiple tasks, **When** context is prepared,
   **Then** each affected task and its requirements and dependencies are covered,
   including shared constraints beyond those task blocks.
2. **Given** a final feature PR, **When** reviewed, **Then** coverage addresses
   the complete feature requirements, success criteria, delivery evidence,
   and combined behavior rather than only the last task.
3. **Given** a bug or chore legitimately has no ledger, **When** reviewed,
   **Then** its candidate, stated intent, applicable rules, and available
   evidence supply context; ledger absence alone is not a coverage failure.
4. **Given** candidate changes cannot be confidently associated with the
   proposed task scope, **When** context is prepared, **Then** the uncertainty
   is identified and unresolved coverage prevents a conclusive review.

### User Story 3 - Distinguish selection from missing evidence (Priority: P1)

A reviewer sees what was selected, what was actually read, and what still
needs inspection before the review can close.

**Why this priority**: Efficient selection requires honest coverage evidence.

**Independent test**: Compare deliberate exclusions, unread references,
limit-induced omissions, failed reads, and successful additional reads.

**Acceptance scenarios**:

1. **Given** material is deliberately outside scope, **When** review closes,
   **Then** its exclusion and rationale are distinguishable from necessary
   content that was omitted or remains unread.
2. **Given** necessary content exceeds a configured limit or cannot be read,
   **When** review closes, **Then** the result is inconclusive and identifies
   the missing content, affected scope, and reason, even with no findings.
3. **Given** only a reference or suggested read action, **When** coverage is
   assessed, **Then** that reference earns no reading credit.
4. **Given** omitted necessary content is subsequently read for the same
   candidate and recorded, **When** coverage is reassessed, **Then** that gap
   can close; other unresolved gaps retain their inconclusive diagnosis.

### Edge cases

- A task block or shared context alone exceeds a configured limit (FR-005/FR-007).
- A shared requirement affects several tasks or changed paths lack a clear
  task association (FR-001/FR-003).
- A source is missing, unreadable, or differs from the reviewed candidate;
  its required content remains uncovered (FR-006/FR-007).
- Adding unrelated earlier ledger entries preserves the selected task's
  necessary context and coverage outcome (SC-001).

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Review context MUST derive from the candidate and reviewed scope,
  supporting one task, multiple tasks, a complete feature, and the ledger-free
  short path. Unresolved scope associations MUST be explicit.
- **FR-002**: Task-scoped context MUST cover complete relevant task blocks,
  their delivery strategy, related requirements, and shared context necessary
  to assess acceptance, dependencies, boundaries, and delivery evidence.
- **FR-003**: Multi-task reviews MUST cover every affected task and shared
  requirement. Final feature reviews MUST cover the complete feature contract,
  success criteria, delivery evidence, and combined behavior.
- **FR-004**: Reviewers MUST have a usable way to inspect remaining artifacts
  from the reviewed candidate. Legitimate ledger-free reviews MUST use their
  intent, applicable rules, and available evidence without requiring a ledger.
- **FR-005**: Per-artifact and total context limits MUST remain configurable
  and their effective values visible. Selection MUST respect those limits and
  distinguish deliberate exclusions from necessary content lost to a limit.
- **FR-006**: The review MUST record its candidate, scope, selected content,
  deliberate exclusions with reasons, content actually read, and unresolved
  gaps. Reading evidence MUST identify the source version and inspected
  portions, including additional reads; availability or a reference alone
  MUST NOT count as evidence of reading.
- **FR-007**: Necessary context that is missing, unread, truncated, or not
  attributable to the reviewed candidate MUST keep the result inconclusive
  with a specific cause and affected scope. Recorded additional reads may
  resolve their own gaps; absence of findings cannot establish coverage.
- **FR-008**: Deliberate exclusion of unrelated content MUST NOT itself force
  an inconclusive result when necessary context has verifiable coverage.
  Other existing causes of inconclusive review MUST retain their effect.

### Constraints and boundaries

- **C-001**: Deliver reliability entry 02 within the existing review workflow.
  Context selection and coverage are this feature's scope; command Markdown
  coverage, finding-category repair, and PR-budget changes retain their
  separate entries in the reliability round.
- **C-002**: Preserve the advisory nature of pending-change reviews, candidate
  identity for PR reviews, and human authority over approval and merge.
- **C-003**: Preserve existing source-containment guarantees: artifact content
  is review data and cannot change review instructions or authority.

### Key entities

- **Review scope**: The candidate and work being assessed: one or more tasks,
  an entire feature, or a short-path work item.
- **Context selection**: Necessary source portions and their relationship to
  that scope, with explicit exclusions, effective limits, and remaining access.
- **Coverage evidence**: The candidate-specific record of inspected source
  portions and outstanding gaps used to assess review completeness.

## Success criteria *(mandatory)*

- **SC-001**: A task located beyond the configured ledger limit receives 100%
  of its necessary context when that context fits, without embedding the whole
  ledger. Adding unrelated earlier entries leaves its coverage outcome unchanged.
- **SC-002**: Every acceptance case for multiple tasks, a complete feature,
  and ledger-free bugs and chores accounts for all necessary context in its
  scope, or identifies the exact gaps preventing completion.
- **SC-003**: Every required-content failure case remains inconclusive with
  an actionable cause. Zero unread references are credited as inspected content.
- **SC-004**: Every reviewed source portion is traceable to its candidate and
  scope. Successful additional reads resolve only their corresponding gaps;
  deliberate unrelated exclusions alone cause zero inconclusive results.

## Assumptions and dependencies

- **A-001**: Entry 01 precedes this entry's implementation in the agreed
  delivery sequence; this feature has no additional functional dependency on it.
- **A-002**: Existing task definitions and artifact relationships provide
  scope evidence. Ambiguous or missing relationships are reported as gaps
  rather than guessed to establish completeness.
- **A-003**: Existing context-limit defaults and review-budget policy remain
  the starting configuration; this feature changes context selection and coverage.
- **A-004**: Local acceptance fixtures demonstrate this behavior. Published
  distribution and actual agent runtime acceptance remain separate under entry 23.

## Source references

- **SRC-001**: [Reliability entry 02](../../docs/reliability/02-review-context.md).
- **SRC-002**: [Common decisions and execution order](../../docs/reliability.md).
- **SRC-003**: [Product vision](../../docs/vision.md) and [delivery plan](../../docs/plan.md).
- **SRC-004**: Current [packet](../../packages/spec-kit-code-review/src/spec_kit_code_review/packet.py), [verdict](../../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py), and [configuration](../../packages/spec-kit-code-review/config/speckit-code-review.template.yml).
- **SRC-005**: [Dogfooding entry 79](../../docs/dogfooding.md).
