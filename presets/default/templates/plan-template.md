# Implementation Plan: [FEATURE]

**Feature directory**: `specs/[###-feature-name]`
**Spec**: [spec.md](spec.md)

## Summary

[Primary outcome and the smallest technical approach that delivers it.]

## Technical context

- **Language/runtime**: [version or NEEDS CLARIFICATION]
- **Primary dependencies**: [read from the real manifests
  (`package.json`, lockfiles, etc.) and cite them; a dependency that is
  not already installed is a human decision, never a plan default]
- **Storage/state**: [durable state and ownership, or none]
- **Verification**: [test framework and required repository checks]
- **Target environment**: [supported platform/runtime]
- **Constraints**: [compatibility, performance, safety, and review limits]

## Documentation

The documentation this feature's implementation consults — provided by
the task author when given, official sources otherwise. An API not
covered by these links is verified against its official documentation
before use, never guessed.

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| [dependency] | [from the manifest] | [link] |

## Constitution check

*GATE: Must pass before design and be re-checked after design.*

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| [principle from `.specify/memory/constitution.md`] | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |
| [one row per constitution principle] | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| [surface] | [owner] | [planned behavior] | [out-of-scope behavior] |

## Technical decisions

### [Decision title]

- **Decision**: [chosen approach]
- **Rationale**: [delivery-relevant reason]
- **Trade-off**: [meaningful cost or limitation]

## Data and migration behavior

[Describe data/state shape, validation, compatibility, and migration. Remove only when no state exists.]

## Failure, retry, rollout, and rollback

- **Failure behavior**: [safe failure and diagnostics]
- **Retry/idempotency**: [repeat behavior]
- **Rollout**: [adoption sequence]
- **Rollback**: [how to restore or stop without data loss]

## Security and privacy

[Describe trust boundaries, secrets, permissions, remote writes, and privacy impact.]

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| [FR/SC/risk] | [test, inspection, or artifact] | `[reproducible command]` |

## Source layout

```text
[Only the real paths affected by this feature]
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| [only material alternative] | [delivery-relevant trade-off] |

## Product handoff

`ready-for-development` requires all rows to be complete. Analysis consistency is not technical approval.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | [counts, coverage, and no blockers] | [pending/complete] |
| Technical approval of plan and tasks | [human approval record] | [pending/complete] |
| Reviewed Linear dry-run and synchronization | [remote plan and result] | [pending/complete] |
| Every executable task individually assignable and assigned | [mapping and assignees] | [pending/complete] |

