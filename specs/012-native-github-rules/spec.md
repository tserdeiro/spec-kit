# Feature Specification: Verify native GitHub delivery guarantees

**Feature directory**: `specs/012-native-github-rules`
**Status**: Draft
**Input**: Complete reliability entry 11, `docs/reliability/11-native-github-rules.md`, with the common reliability decisions supplied by the user.

## Problem and affected users

Developers and maintainers cannot rely on a local guard to protect shared
branches from another client. GitHub settings may permit rewriting shared
history, prevent merge commits, or keep integrated branches from being deleted.
The current doctor checks only two repository settings and cannot establish
whether effective branch rules support the delivery workflow.

## Desired outcome

The existing doctor explains whether observable GitHub protections support the
stack: shared history is protected, merge commits are allowed, and integrated
delivery branches can be cleaned up. Each gap identifies its evidence, cause,
and a concrete native remediation while preserving the team's policy.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Diagnose delivery guarantees (Priority: P1)

A developer runs the doctor before sharing a stack and sees which branches and
settings are compatible, incompatible, or still unverified.

**Why this priority**: It exposes remote delivery blockers before work depends on them.

**Independent test**: Diagnose compatible and conflicting fixture repositories;
each finding names the affected branch, guarantee, and observed setting or rule.

**Acceptance scenarios**:

1. **Given** enforced protection against force-push, allowed merge commits, and
   compatible cleanup rules, **When** diagnosis completes, **Then** the observed
   scope is compatible and the report names any authorized bypass exceptions.
2. **Given** an absent force-push protection or an active rule that prevents merge
   commits, **When** diagnosed, **Then** the affected shared branch is incompatible.
3. **Given** automatic deletion is enabled but an effective rule prevents deleting
   an integrated feature or task branch, **When** diagnosed, **Then** cleanup is
   incompatible even though the repository setting alone appears correct.
4. **Given** inherited rules, disabled/evaluation rules, and existing review/check
   requirements, **When** diagnosed, **Then** enforcement and applicability decide
   the result, with the source and exceptions visible.

### User Story 2 - Act on an honest diagnosis (Priority: P2)

A maintainer gets a specific next action without a read failure being presented
as missing configuration or an unsupported capability as a settings mistake.

**Why this priority**: Correct remediation depends on knowing what was actually read.

**Independent test**: Run permission, unsupported-capability, and failed-read
fixtures; check distinct causes, actionable remediation, and zero remote writes.

**Acceptance scenarios**:

1. **Given** evidence that the consumer's plan cannot enforce a protection,
   **When** diagnosed, **Then** the report names the unavailable capability and
   the native administrative action needed to obtain it.
2. **Given** insufficient permissions, inaccessible rules, a rate limit, or an
   incomplete read, **When** diagnosed, **Then** the affected guarantee remains
   unverified with its cause and retry/access action; verified results remain visible.
3. **Given** an incompatible native setting or rule, **When** diagnosed, including
   during `doctor --fix`, **Then** the report provides a concrete proposed change
   for the owning administrator to review and authorize, with zero remote writes.

### Edge cases

- A successful empty rules read differs from a failed or truncated read.
- Overlapping repository and inherited rules can jointly restrict a branch;
  disabled/evaluation rules alone do not prove enforcement.
- Privileged bypass does not prove ordinary developers are unprotected, and an
  actor-specific exception does not prove merge or cleanup works for everyone.
- Trunk deletion protection is compatible with retaining trunk; the same rule
  on integrated feature/task branches can block cleanup.
- Missing authentication, a missing delivery-base branch, malformed responses,
  and disappearing branches leave affected observations unverified.
- The report states its observed branch scope and does not certify future branches.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: The doctor MUST identify the configured delivery base and existing
  remote branches following the repository's feature/task conventions, and state
  the inspected scope. A failed inventory MUST leave coverage unverified.
- **FR-002**: The doctor MUST diagnose repository merge-commit and automatic
  merged-branch-deletion settings using observed values.
- **FR-003**: The doctor MUST combine applicable enforced GitHub rulesets,
  inherited rules, and classic branch protections, accounting for visible bypass
  exceptions; uncertain evidence MUST remain unverified.
- **FR-004**: The doctor MUST identify shared branches without enforced
  force-push protection and report the source of verified protection.
- **FR-005**: The doctor MUST identify effective restrictions that prohibit merge
  commits or deletion of integrated feature/task branches, retaining trunk.
- **FR-006**: Each diagnosis MUST distinguish compatible, incompatible,
  capability unavailable, and unverified outcomes. Permission failures and read
  failures MUST retain distinct causes; ambiguous failures MUST NOT prove a plan
  limitation or missing configuration.
- **FR-007**: Every gap MUST provide an affected scope, evidence, and concrete
  native next action. Configuration changes MUST name the setting/rule and its
  intended value or scope; inherited changes MUST identify their owner.
- **FR-008**: GitHub diagnosis MUST make zero remote writes on all doctor paths,
  including `--fix`, and MUST preserve existing checks, reviews, and bypass policy.
- **FR-009**: The doctor summary MUST retain verified subresults, mark incomplete
  evidence explicitly, and declare overall compatibility only when every
  required guarantee is verified within the stated scope.

### Constraints and boundaries

- **C-001**: Use the existing native doctor and project-owned customization
  surfaces; preserve the upstream-managed baseline and consumer-selected integrations.
- **C-002**: Remote repair requires applicable human authorization for a concrete,
  reviewable configuration. Required checks, human reviews, and exceptions belong
  to the team; diagnosis grants no approval or bypass authority.
- **C-003**: This feature delivers fixture-backed diagnosis. Live force-push
  rejection and ordered stack-merge acceptance belong to reliability entry 23;
  release/promotion repair remains in its separate round.
- **C-004**: Diagnosis MUST avoid credentials and raw authentication material in
  output and MUST leave Git state and consumer configuration unchanged.

## Success criteria *(mandatory)*

- **SC-001**: Every compatible, missing-protection, blocked-merge, and blocked-cleanup
  fixture yields the expected per-guarantee result, including inherited conflicts.
- **SC-002**: Every unavailable-capability, insufficient-permission, failed-read,
  and incomplete-read fixture retains its correct cause; none yields a false pass.
- **SC-003**: Every diagnosed gap includes its scope and an actionable native
  remediation; every fixture invocation records zero remote writes and local changes.
- **SC-004**: Installed-consumer checks reproduce the diagnostic contract independently
  of this source checkout; their evidence explicitly identifies synthetic coverage.

## Assumptions and dependencies

- **A-001**: Shared delivery branches are the resolved trunk plus existing remote
  `NNN-slug` feature and `NNN-T###-slug` task branches. Other team-specific branch
  families are outside this bounded observation; no new branch registry is introduced.
- **A-002**: The user's 2026-09-12 request authorizes planning entry 11 from `main`
  alongside other agents and publishing its draft PR and Linear projection.
  It does not record technical approval, task assignment, implementation, or merge.
- **A-003**: No functional dependency on entry 10 is required. Consumer plan and
  credentials determine which remote evidence can be read.

## Source references

- **SRC-001**: User-supplied `docs/reliability/11-native-github-rules.md` and common
  `docs/reliability.md` decisions, read on 2026-09-12. The numbered input is local
  uncommitted roadmap work in the source checkout; its scope is captured here.
- **SRC-002**: [Doctor](../../presets/default/commands/doctor.md) and
  [ordered merge](../../presets/default/scripts/python/merge_root_first.py).
- **SRC-003**: [Vision](../../docs/vision.md), [delivery plan](../../docs/plan.md),
  [release boundary](../../docs/releases.md), and [constitution](../../.specify/memory/constitution.md).
