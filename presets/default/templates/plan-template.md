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

**Contract verification**: before tasks are generated, verify the few
uncertainties that change the architecture — identity selection,
endpoints, transport, field shapes, error forms. Fixtures stay sanitized
and name their provenance. An `assumed` row stays listed and is named in
the evidence of the first task that exercises that contract.

| Integration or guarantee | Uncertainty that changes the design | Verified how | Status |
| --- | --- | --- | --- |
| [integration] | [what would change the design] | [official documentation, small reproduction against the native client, or sanitized fixture path] | [verified/assumed] |

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
- **Guarantee boundaries**: for each hard guarantee (e.g. "preserve a
  concurrently modified configuration"), the supported scenarios, the
  rejected behaviors, the unavoidable limits, and the acceptance
  evidence. A transactional mechanism plans write, recovery, and cleanup
  from the start.

## Security and privacy

[Describe trust boundaries, secrets, permissions, remote writes, and privacy impact.]

## Verification strategy

| Surface | Suite or command | Verifies (FR/SC) | When (change / candidate close / CI) |
| --- | --- | --- | --- |
| [changed surface] | `[reproducible command]` | [FR/SC IDs] | [change / candidate close / CI] |

Each task's Evidence line points at rows of this table.

**Behavior families**: a cross-cutting requirement gets one row per path;
a defect in one row means the whole family is reviewed before the next
candidate.

| Requirement | Path | Implemented in | Evidence |
| --- | --- | --- | --- |
| [cross-cutting FR] | [normal/error/recovery/cleanup] | [file] | [test] |

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

