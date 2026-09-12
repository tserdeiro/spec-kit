# Feature Specification: Native commit message validation

**Feature directory**: `specs/011-native-commit-check`
**Status**: Draft
**Input**: Reliability entry 10, `docs/reliability/10-native-commit-check.md`, supplied from the author's working tree on 2026-09-12.

## Problem and affected users

Developers committing from a terminal or an agent without runtime events bypass
the existing commit-message guard. This repository's convention checks do not
travel to consumers. Installing validation must preserve the consumer's hooks
and hook manager.

## Desired outcome

The existing doctor diagnoses native commit-message validation and its `--fix`
path installs it where composition is safe. Git applies the guard's current
message rule regardless of the agent used; existing hooks keep working.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Validate commits outside agent events (Priority: P1)

A developer diagnoses the repository, installs the offered local repair, and
receives an actionable rejection for an invalid commit message from Git.

**Why this priority**: This closes the terminal and unwired-agent coverage gap.

**Independent test**: In an isolated consumer, diagnose without writes, install
the repair, and compare real Git commit outcomes with the guard for the same
valid and invalid subjects.

**Acceptance scenarios**:

1. **Given** absent validation, **When** doctor runs without `--fix`, **Then** it
   names the missing check, effective hook location, and repair without writes.
2. **Given** a safely installable consumer, **When** doctor runs with `--fix`,
   **Then** valid commits succeed and invalid subjects fail before a commit is
   created, including messages supplied by an editor or a file.
3. **Given** a subject the guard can resolve, **When** that same subject reaches
   Git's validator, **Then** both accept or reject it by the existing rule.
4. **Given** installed validation, **When** its runtime or message file cannot
   be read, **Then** the commit fails with the exact recovery action.

### User Story 2 - Preserve the consumer's hook workflow (Priority: P1)

A developer enables validation in a repository using a custom hooks directory,
existing hooks, or a hook manager, without losing its previous behavior.

**Why this priority**: Adoption must preserve existing local tooling.

**Independent test**: Exercise default and custom hook paths, existing success
and failure hooks, Husky, and Lefthook; repeat installation and count executions.

**Acceptance scenarios**:

1. **Given** a supported hook composition, **When** repair runs twice, **Then**
   Spec Kit validates exactly once and previous hooks retain their content,
   arguments, relative order, and rejection effect when execution reaches them.
2. **Given** a custom hooks path or linked worktree, **When** doctor resolves
   validation, **Then** it reports Git's effective arrangement and preserves
   the configured path.
3. **Given** a supported hook manager, **When** repair is safe, **Then**
   validation composes through native supported mechanisms and the manager's
   generated dispatcher remains intact.
4. **Given** ambiguous ownership, unsupported composition, or unsafe writes,
   **When** doctor runs with `--fix`, **Then** hook/configuration content stays
   intact and the result names a concrete manual integration action.

### Edge cases

- Empty subjects, missing scope, uppercase type/scope, breaking-change syntax,
  multiline bodies, spaces in paths, and non-ASCII subject text retain the
  current rule's outcome.
- A previous hook rejects, exits early, or changes the message. Doctor must
  describe execution order and any limitation rather than promise final-message
  enforcement it cannot observe.
- Shared/global paths, symlinks, disabled validation, concurrent edits, partial
  installation, and duplicate registrations require explicit diagnosis.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Doctor MUST diagnose effective native validation, its location and
  composition owner, and the precise next action without writes.
- **FR-002**: `doctor --fix` MUST install validation in safely supported local
  hook arrangements through the existing installation workflow.
- **FR-003**: Git and the guard MUST apply the same existing subject rule to every
  subject both observe; valid subjects pass and invalid subjects fail.
- **FR-004**: Native validation MUST inspect and preserve the message file Git
  provides, including terminal, editor, and unwired-agent commits.
- **FR-005**: Discovery and repair MUST honor effective `core.hooksPath` and
  linked-worktree layout without replacing the configured hooks path.
- **FR-006**: Repair MUST preserve existing hook content, arguments, relative
  order, and rejection effect through supported native composition.
- **FR-007**: Integration with Husky and Lefthook MUST preserve their dispatchers
  and use supported native composition, including the manager's own mechanism
  when changing its entries is necessary.
- **FR-008**: Repeating successful repair MUST leave one effective validation
  invocation, with no duplicate registrations or unrelated changes.
- **FR-009**: Unsafe, unsupported, ambiguous, or concurrently changed arrangements
  MUST remain intact and receive an exact manual recovery action.
- **FR-010**: Invalid subjects and unavailable validator prerequisites MUST reject
  the commit with actionable diagnostics; doctor MUST distinguish installed,
  missing, disabled, and unverifiable validation.

### Constraints and boundaries

- **C-001**: This is reliability entry 10. The current extension doctor owns
  installation; entry 17 owns an executable aggregate doctor.
- **C-002**: A local hook is bypassable and is not server enforcement. GitHub
  rules, CI distribution, additional guard rules, and release automation retain
  their separate scope and authority.
- **C-003**: Preserve native commands, the current subject policy, pinned upstream
  baseline, consumer-selected integrations, and human approval/review/merge
  authority. Build on existing dependencies.
- **C-004**: Consumer-installed validation MUST work without this source checkout,
  credentials, remote calls, or a review-engine invocation during a commit.

### Key entities

- **Commit subject**: First line of the observed message and its validation result.
- **Hook arrangement**: Effective location, composition owner, existing entries,
  and evidence of safe repair or required manual action.
- **Owned validation entry**: Identifiable Spec Kit invocation whose repeatable
  installation and removal preserve consumer tooling.

## Success criteria *(mandatory)*

- **SC-001**: Every subject in the agreed acceptance corpus has identical guard
  and native-validator results; invalid real commits create no commit, and valid
  ones succeed when other hooks pass.
- **SC-002**: Each supported arrangement survives two repair runs with exactly
  one validation invocation per commit and preserved previous hooks.
- **SC-003**: All read-only and unsafe-repair cases preserve hook/configuration
  bytes and modes and report the affected path and actionable next step.
- **SC-004**: A separately installed consumer validates commits without agent
  events or source-checkout access, observing both success and rejection.

## Assumptions and dependencies

- **A-001**: The user requested planning this entry from `main` independently of
  preceding roadmap entries; the input declares no additional functional
  dependency. Feature numbering is independent of roadmap numbering.
- **A-002**: Existing rule means lowercase type, required lowercase/digit/hyphen
  scope, colon and space, and a nonempty subject. Editor input unobservable by
  the pre-tool guard is covered by Git; parity concerns an identical subject.
- **A-003**: Planning assumes Git 2.54+ for automatic installation through native
  composition; older versions receive an upgrade action. This recommendation
  was presented to the user and remains part of the pending technical approval.
  Git's native bypasses remain consumer decisions.

## Source references

- **SRC-001**: Full user-supplied reliability entry 10, untracked in the source
  checkout at intake. Its problem, doctor/`--fix`, `commit-msg`, safe composition,
  parity, idempotency, and manual recovery contract are captured above.
- **SRC-002**: [Vision](../../docs/vision.md), [delivery plan](../../docs/plan.md),
  and [constitution](../../.specify/memory/constitution.md).
- **SRC-003**: [Guard](../../packages/spec-kit-code-review/src/spec_kit_code_review/cli.py),
  [extension doctor](../../packages/spec-kit-code-review/src/spec_kit_code_review/doctor.py),
  [preset doctor](../../presets/default/commands/doctor.md), and
  [repository conventions](../../.github/workflows/conventions.yml).
