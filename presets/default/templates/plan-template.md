# Implementation Plan: [FEATURE]

**Feature directory**: `specs/[###-feature-name]`
**Spec**: [spec.md](spec.md)

## Summary

[Primary outcome and the smallest technical approach that delivers it.]

## Technical context

- **Language/runtime**: [version or NEEDS CLARIFICATION]
- **Primary dependencies**: [dependencies or standard library only]
- **Storage/state**: [durable state and ownership, or none]
- **Verification**: [test framework and required repository checks]
- **Target environment**: [supported platform/runtime]
- **Constraints**: [compatibility, performance, safety, and review limits]

## Constitution check

*GATE: Must pass before design and be re-checked after design.*

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| Compose pinned upstream; no core patch | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |
| Preserve native command surface | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |
| Keep integrations consumer-selected | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |
| Repository artifacts remain durable truth | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |
| Preserve source/consumer boundaries and human control | [PASS/FAIL] | [PASS/FAIL] | [artifact or decision] |

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

<!-- Stage 2 defines this contract locally. Remote Linear validation begins in Stage 3. -->

