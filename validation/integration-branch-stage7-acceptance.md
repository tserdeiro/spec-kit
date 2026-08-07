# Stage 7 acceptance — Integration branch

Feature `002-integration-branch`, delivered 2026-08-06 through the model
it builds (dogfooding): every claim below is observable in this
repository's branches, PRs, and Linear projections.

## The dogfooded run

| Step | Evidence |
| --- | --- |
| Product phase on the feature branch | artifacts committed on `002-integration-branch`; `.specify/feature.json` updated there |
| Gate (FR-003) | draft feature PR #17 opened at the close of the product phase, before implementation |
| Task loop (FR-001, FR-002) | task branches `002-T001…T005-*` forked from the feature branch; PRs #18–#22 based on it |
| States over a feature-branch base (FR-005, SC-002) | each task derived *In Progress* (branch), *In Review* (ready PR), *Done* (merge into the feature branch) — identical to the default-branch behavior; repeated `push` = 0 operations |
| Magic word (FR-005, SC-004) | task PRs from T002 on carry `Fixes WOR-###`; native transitions activate when a workspace admin enables the team's GitHub integration (A-002) — until then `push` projects, degraded freshness only |
| Human boundary (FR-004) | every task PR and the feature PR reviewed and merged by a human; the harness never approved or merged |
| Nothing half-done on the default branch (SC-001) | zero task merges into `main` during the feature; `main` untouched between the product phase and the closure |

## Conformance

`scripts/conformance/bundles.sh` green on every task PR (#18–#22): the
preset with the retargeted loop, PR command, gate template, and closure
ritual installs in all three bundles.

## Closure (SC-003, FR-004)

The ritual of `implement-append.md` step 4 executed on this very feature:
feature PR #17 turned ready with every task checked and both CI suites
green, received the final human review, and a human merged it into `main`
with merge commit `b8659b4` on 2026-08-06 — task history preserved. The
feature branch was deleted (remote auto-deleted on merge) and the closing
`push --all --apply` reconciled with **0 operations**: every state had
already been derived during delivery.
