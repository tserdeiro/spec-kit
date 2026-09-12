# Feature Specification: Correct review finding categories

**Feature directory**: `specs/008-review-findings`
**Status**: Draft
**Input**: [Reliability entry 04](../../docs/reliability/04-review-findings.md), in full.

## Problem and affected users

Reviewers can finish a code review but fail to submit its findings because
they used an unsupported category. Instructions repeat the category list,
and correcting the file currently leaves no record of the original result
or proof that only categories changed. Developers need to recover that
review without losing findings or repeating the code analysis.

## Desired outcome

Give the reviewer the validator's actual category catalog and a precise
diagnosis. Let the reviewer correct categories in the current review session,
preserving the original submission and evidence of each correction. Accept
the result only when the complete submission passes the existing checks.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - Use the accepted categories (Priority: P1)

A reviewer reads the accepted categories and can identify the exact finding
that prevents submission.

**Why this priority**: One authoritative catalog prevents contradictory guidance.

**Independent test**: Compare the categories in the review instructions with
the accepted catalog, then submit one unsupported category.

**Acceptance scenarios**:

1. **Given** a new review, **When** its instructions are prepared, **Then**
   their category catalog is exactly the one the validator accepts.
2. **Given** an unsupported category, **When** the reviewer submits findings,
   **Then** the diagnostic names the original finding's one-based index,
   invalid value, accepted values, and how to retry the current session.

### User Story 2 - Correct a category without losing review work (Priority: P1)

A reviewer chooses a supported category using the finding's existing meaning
and resubmits the same result. The original and correction remain inspectable.

**Why this priority**: Safe recovery is the feature's primary deliverable.

**Independent test**: Submit an otherwise valid result with one unsupported
category and a blocking finding, correct that category, and close the same
session with every finding and its severity preserved.

**Acceptance scenarios**:

1. **Given** a category rejection, **When** the reviewer edits only the invalid
   category and resubmits, **Then** the complete result is validated in the same
   session and the code analysis is reused while its candidate remains current.
2. **Given** a corrected result, **When** an operator inspects its evidence,
   **Then** the original submission, changed indices and values, and validation
   outcome can be traced to that session.
3. **Given** several invalid categories, **When** a partial correction is
   submitted, **Then** remaining errors keep the session open; a subsequent
   complete correction can succeed without replacing the original evidence.
4. **Given** an ambiguous category or a correction that deletes, reorders,
   adds, or changes a finding's other fields, **When** closure is attempted,
   **Then** it is rejected with an explicit reason and the review stays open.

### Edge cases

- A non-string or missing category remains invalid and requires an explicit
  supported replacement; the system never guesses one from a similar name.
- Changing an already valid category, severity, location, content, optional
  field, or reading evidence is not a category correction.
- Malformed documents and other validation failures retain strict diagnostics.
  A category correction does not waive unrelated errors.
- Changed review inputs invalidate reuse under the existing session checks.
- Unavailable, incomplete, or altered correction evidence prevents closure.
- Repeating the same rejected submission preserves the same original and does
  not create duplicate correction records. An initially valid empty result
  follows the existing review workflow.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Reviewer instructions MUST derive their accepted categories from
  the validator's catalog.
- **FR-002**: Category failures MUST report the finding's one-based input index,
  invalid or missing value, accepted values, and the current-session retry action.
- **FR-003**: The reviewer MUST be able to correct invalid categories and
  resubmit within the open session without repeating unchanged code analysis.
- **FR-004**: Before enabling correction, the system MUST preserve the original
  submission unchanged and record each distinct correction attempt, its changed
  categories, validation outcome, and session association.
- **FR-005**: A category correction MUST preserve the number and order of
  findings, every other field, already valid categories, and the rest of the
  submitted document. The system MUST reject any additional change.
- **FR-006**: A corrected submission MUST pass the complete existing validation
  before closure. Invalid, partial, or unresolved corrections, including checks
  that would discard or truncate a submitted finding, MUST retain an explicit
  diagnostic and leave the session open without publication.
- **FR-007**: Correction MUST retain existing candidate and review-evidence
  freshness checks. Changed inputs or unverifiable correction history MUST
  prevent reuse of the review result.

### Constraints and boundaries

- **C-001**: Category selection belongs to the reviewer. Validation remains
  strict; dropping findings or lowering severity cannot make a correction pass.
- **C-002**: This feature extends category recovery in the existing review
  workflow. Review scope, verdict policy, budgets, publication authority, and
  human approval remain governed by their current contracts.
- **C-003**: Review evidence stays in the consumer's private evidence location.
  The preserved original is local evidence; ordinary rendered outputs retain
  existing redaction and untrusted-content protections.

### Key entities *(include only when data or durable state is involved)*

- **Category catalog**: The single set of classifications accepted by validation.
- **Finding submission**: Ordered findings and their accompanying review evidence.
- **Correction record**: Session association, original and attempted submission
  identities, changed category indices/values, and validation outcome.

## Success criteria *(mandatory)*

- **SC-001**: Every accepted category appears in reviewer guidance, and guidance
  names zero categories that validation rejects.
- **SC-002**: An otherwise valid submission with one invalid category can close
  after one correction and resubmission, with zero repeated code-analysis passes
  and 100% of findings and their non-category information preserved.
- **SC-003**: Every distinct category-correction attempt has inspectable evidence
  linking the unchanged original, proposed changes, and validation outcome.
- **SC-004**: Every tested invalid, ambiguous, destructive, stale, or unverifiable
  correction fails to close or publish the review. Preserved blocking findings
  continue to require changes after a valid correction.

## Assumptions and dependencies

- **A-001**: Reliability entry 04 follows entry 03 in delivery order and has no
  additional functional dependency. Feature numbers are assigned independently.
- **A-002**: A correction changes classification only. If understanding a finding
  requires substantive changes or fresh code analysis, the reviewer starts a new
  review under the existing lifecycle and preserves the previous evidence.
- **A-003**: Document whitespace and object-key order may change; field values,
  field presence, and finding-array order define preservation. The saved original
  itself remains byte-for-byte unchanged.

## Source references

- **SRC-001**: [Reliability entry 04](../../docs/reliability/04-review-findings.md).
- **SRC-002**: [Round contract](../../docs/reliability.md), [vision](../../docs/vision.md),
  and [delivery plan](../../docs/plan.md).
- **SRC-003**: [Dogfooding entry 90](../../docs/dogfooding.md), resolved here by
  explicit reviewer correction rather than category coercion or finding removal.
