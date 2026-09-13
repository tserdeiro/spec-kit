# Feature Specification: Start work items with native Linear branches

**Feature directory**: `specs/009-work-item-branches`
**Status**: Draft
**Input**: [Reliability entry 05](../../docs/reliability/05-work-item-branches.md), in full.

## Problem and affected users

Developers starting bugs and chores must repeat an Issue title already held by
Linear. Different parts of delivery recognize different branch formats. A title,
format, or assignee change can hide existing work and cause a duplicate branch.

## Desired outcome

Start or resume an Issue using its existing work first, otherwise its native
Linear branch name. Resolve the same Issue throughout delivery, asking only for
missing information and preserving the short bug/chore workflow.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Start from the Issue (Priority: P1)

A developer supplies an Issue key or link and receives its title, context, and
native branch without repeating information already available in Linear.

**Why this priority**: This removes the first interruption in the short path.

**Independent test**: Start a bug and a chore from a key with configured Linear,
then repeat with no configuration and with a configured integration failure.

**Acceptance scenarios**:

1. **Given** a linked Issue and working configuration, **When** work starts,
   **Then** its title and context are read and its valid native branch name is
   used exactly, including any user prefix returned with the active credentials.
2. **Given** no Linear configuration, **When** a key and title are supplied,
   **Then** the default `team-number-slug` branch starts; only missing information
   is requested. Bugs continue through triage and chores directly to their change.
3. **Given** configured Linear fails, the Issue is unavailable, or its proposed
   name is invalid, **When** work starts, **Then** a precise diagnosis prevents
   branch creation; the unconfigured path is not substituted.

### User Story 2 - Resume the same work (Priority: P1)

A developer resumes the existing branch or PR even after the Issue's title,
branch format, or responsible person changes.

**Why this priority**: Avoiding duplicate work protects continuity.

**Independent test**: Create existing local and remote work, change the Issue's
proposed branch, and repeat start without creating a second branch or PR.

**Acceptance scenarios**:

1. **Given** one existing branch or open PR linked to the Issue, **When** start is
   repeated after a metadata change, **Then** that work is adopted before the
   current proposed branch is considered.
2. **Given** conflicting existing candidates or incomplete integration evidence,
   **When** start is attempted, **Then** it reports the conflict or failure and
   leaves Git work and Issue state unchanged.
3. **Given** an existing remote branch, **When** adopted, **Then** its history is
   retained locally and any existing PR remains the delivery PR.

### User Story 3 - Keep identity consistent through delivery (Priority: P2)

Developers use any native Linear branch format throughout PR creation, review,
guards, and state projection without requiring feature artifacts for a work item.

**Why this priority**: A valid start must remain valid in downstream commands.

**Independent test**: Run the same branch-format cases through every affected
surface and verify the same Issue; run feature and stack regressions alongside.

**Acceptance scenarios**:

1. **Given** a uniquely resolvable native work-item branch, **When** PR creation,
   review, or projection inspect it, **Then** they identify the same Issue and
   follow the short path even with stale feature selection present; guards
   classify it as a work item without applying feature-task-only restrictions.
2. **Given** an unresolvable or ambiguous branch, **When** identity is needed,
   **Then** no unrelated Issue is selected or updated.
3. **Given** a feature or feature-task branch, **When** the same surfaces run,
   **Then** `NNN-slug` and `NNN-T###-slug` keep their existing behavior and task
   links remain in the PR body.

### Edge cases

- User prefixes, key-only names, nested path segments, and title-based names are
  accepted when Linear resolves them uniquely; Git remains the name validator.
- A branch containing several Issue-like keys is not an excuse to guess identity.
- A native suggestion colliding exactly with a reserved feature/task convention
  is an identity conflict; diagnose it before creation instead of renaming it.
- A matching open PR is authoritative existing work; multiple open PR heads for
  the same Issue require disambiguation. Closed unmerged PRs alone do not restart
  work or prove completion; existing lifecycle precedence remains intact.
- Dirty files, a branch checked out elsewhere, unavailable remote refs, and
  foreign-repository PRs must not be overwritten or silently substituted.
- Missing configuration differs from invalid configuration, missing credentials,
  permission denial, network failure, and incomplete GitHub observation.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Configured start MUST retrieve the Issue's canonical identity,
  title, context, and native branch name without requesting known information.
- **FR-002**: New configured branches MUST use the returned name exactly after
  Git validation, including the credential-dependent prefix; template rebuilding
  and automatic renaming are prohibited.
- **FR-003**: Unconfigured start MUST use a supplied Issue key and the default
  `team-number-slug` convention, requesting only missing context.
- **FR-004**: Configured integration failures and invalid Issue/name results
  MUST produce actionable diagnostics before creating or switching work.
- **FR-005**: Start MUST adopt uniquely identified existing branch/PR work before
  creating new work, despite changed Issue title, format, or assignee.
- **FR-006**: Ambiguous identity, conflicting candidates, and incomplete required
  observation MUST prevent speculative branch creation or Issue state changes.
- **FR-007**: Start, PR creation, review, guards, and projection MUST use one
  consistent identity contract, consulting native resolution where required.
- **FR-008**: Work-item delivery MUST remain independent of spec/plan artifacts;
  bugs retain their triage sequence and chores their direct path.
- **FR-009**: Features and their tasks MUST retain their current branch conventions,
  stack behavior, and task links through the existing PR body.
- **FR-010**: Projection MUST preserve existing lifecycle precedence and uncertain
  observation behavior while resolving native work-item branches uniquely.

### Constraints and boundaries

- **C-001**: Use native Linear/Git capabilities and existing extension boundaries;
  introduce no parallel identity registry, runtime dependency, or template engine.
- **C-002**: Preserve upstream-managed assets and consumer independence. This
  feature changes authored extensions/preset behavior within the delivered stages.
- **C-003**: Issue content, assignment, and ownership remain human-controlled;
  this path writes only the already-authorized lifecycle projection.
- **C-004**: Preserve unrelated working files and history. Keep credentials and
  operator identity out of committed artifacts and diagnostics.

### Key entities

- **Work item**: A human-created Issue with canonical identifier, title, context,
  and current suggested branch; identity survives metadata changes.
- **Existing work**: Observed local/remote branches and repository PRs associated
  with that Issue; derived from native systems, never a separate registry.

## Success criteria *(mandatory)*

- **SC-001**: Configured starts require zero repeated title/context questions and
  create names identical to Linear's valid results across the observed formats.
- **SC-002**: Repeated starts after title, format, or assignee changes create zero
  duplicate branches/PRs and preserve the existing work's history.
- **SC-003**: Every tested integration failure, invalid name, and ambiguous
  identity produces zero speculative branch creations or unrelated Issue updates.
- **SC-004**: Start, PR creation, review, and projection agree on the Issue in the
  native-format matrix; guards apply work-item restrictions consistently, and
  feature/task-stack fixtures keep their existing results.
- **SC-005**: Bug and chore scenarios pass with and without configuration without
  requiring a spec/plan; live read-only evidence records native prefix behavior
  for the configured credential type separately from fixture acceptance.

## Assumptions and dependencies

- **A-001**: Reliability entry 01 and the preceding executed entry 04 are already
  merged. Entry 03 was omitted by the earlier human decision recorded in feature
  008. This request explicitly selects entry 05.
- **A-002**: Existing PR links and native Issue resolution provide identity when
  the current suggested branch has changed. Conflicting evidence requires a
  decision rather than a new registry or heuristic guess.
- **A-003**: Live verification is read-only against existing Issues; synthetic
  fixtures cover mutations and alternative credential/format configurations.

## Source references

- **SRC-001**: [Reliability entry 05](../../docs/reliability/05-work-item-branches.md).
- **SRC-002**: [Round contract](../../docs/reliability.md), [vision](../../docs/vision.md),
  and [delivery plan](../../docs/plan.md).
- **SRC-003**: [Linear's official schema](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql).
