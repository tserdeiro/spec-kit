# tserdeiro/spec-kit Constitution

## Core Principles

### I. Compose a pinned upstream

The distribution MUST compose an exact reviewed `github/spec-kit` release and
MUST NOT fork, privately patch, or reimplement Specify CLI, core commands, or
agent integrations. Every upstream upgrade changes `versions.lock.yml`, its
integrity evidence, and the clean-consumer baselines in one reviewed change.

### II. Preserve the native surface

Daily work MUST use native `specify` and `speckit` commands. Reusable behavior
MUST use the smallest public Spec Kit primitive that fits it. A parallel CLI,
renamed lifecycle, or private workflow engine requires a demonstrated gap and
an amendment to the product contract.

### III. Keep integrations consumer-selected

Consumer repositories choose any integration supported by the pinned Spec Kit
release. Distribution bundles and workflows MUST remain integration-agnostic.
Conformance matrices are minimum evidence sets, never allowlists, and generated
asset validation MUST NOT be reported as actual agent runtime execution.

### IV. Make repository artifacts durable truth

Constitution, specifications, plans, tasks, checklists, feature selection, Git
state, and verification evidence MUST make work resumable without chat history.
`.specify/feature.json` selects the active feature independently from the Git
branch; neither mechanism may silently substitute for the other.

### V. Protect source and consumer boundaries

This repository owns distribution policy, exact dependency locks, conformance,
and versioned composition assets. A consumer owns its project constitution,
feature artifacts, selected integration files, and Git history. Consumers MUST
NOT require this source checkout at runtime, and this source MUST NOT own or
overwrite consumer product decisions.

### VI. Make delivery units traceable and reviewable

Specifications MUST use stable requirement and success-criterion identifiers.
Every executable task MUST record its outcome and traces, dependencies, changed
or protected boundaries, reproducible evidence, `single` or `feature-chain`
delivery strategy, and forecast agent-reviewed executable-code lines. A checked
task means its completion evidence is present. Work above the 400-line internal
agent-review budget MUST be split into dependency-ordered units whose individual
forecasts fit that budget.

## Delivery and safety constraints

- `spec.md` is the authoritative staged product contract.
- Stages execute sequentially; later-stage artifacts are not introduced early.
- Upstream-managed generated assets remain unchanged except during an explicit
  pinned upgrade. Project-owned policy uses documented customization surfaces.
- Deterministic checks and human review are authoritative over agent claims.
- Credentials, tokens, operator identity, and global agent configuration never
  belong in repository artifacts.
- Branch-changing and destructive conformance runs use isolated temporary
  repositories and preserve the source checkout.
- Pull requests use the canonical `.github/PULL_REQUEST_TEMPLATE.md` sections;
  agent guidance does not duplicate machine-verifiable checks as attestations.
- `ready-for-development` requires clean cross-artifact analysis, independent
  human technical approval, reviewed Linear synchronization, and explicit
  assignment of every executable task. Until Stage 3 validates the remote
  integration, Stage 2 artifacts MUST keep those remote gates pending.

## Development workflow

Each change identifies its active stage, updates repository evidence together
with behavior, and runs the relevant conformance plus `git diff --check`.
Feature continuity relies on `.specify/feature.json`, feature artifacts, and Git
state. Humans approve planning boundaries, commits, publication, final review,
and merge. Findings that change product intent return to the product contract
instead of being hidden in implementation.

## Governance

This constitution governs implementation decisions in this repository.
`spec.md` defines product scope and stage acceptance; when the documents appear
to conflict, work stops until the conflict is resolved explicitly. Amendments
require rationale, migration impact, updated conformance where applicable, and
human review. Version changes follow semantic versioning: MAJOR for principle
removal or incompatible governance, MINOR for a new principle or material
expansion, and PATCH for clarifications.

**Version**: 1.1.0 | **Ratified**: 2026-07-22 | **Last Amended**: 2026-07-22
