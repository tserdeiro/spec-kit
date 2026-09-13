# Implementation Plan: Start work items with native Linear branches

**Feature directory**: `specs/009-work-item-branches`
**Spec**: [spec.md](spec.md)

## Summary

Centralize native Issue reads and branch resolution in Linear. The preset calls
an installed internal JSON bridge to start or adopt work. Review consumes the
canonical PR linkage and exact feature/task conventions without requiring Linear.
One behavioral matrix enforces the contract across independent packages. T002
delivers explicit Issue lookup; T009 adds observation batches before T003. T001
owns all native client reads and their transport tests; T009 owns observation
resolution. This keeps the existing task identities, order, and review limits.
Research, data contracts, and validation remain here, following the resolved template.

## Technical context

- **Language/runtime**: Python 3.11+; existing Bash/PowerShell launchers.
- **Primary dependencies**: stdlib, Git, `gh`, existing pytest. Both extension
  manifests declare zero runtime dependencies: [Linear](../../packages/spec-kit-linear/pyproject.toml),
  [review](../../packages/spec-kit-code-review/pyproject.toml).
- **Storage/state**: Git refs, PR body links, Linear Issues; transient resolutions.
- **Verification**: isolated Git fixtures, fake APIs, installed-artifact conformance,
  and read-only live credential evidence.
- **Target environment**: current consumer platforms and selected integrations;
  reviewer-only installations remain independent of Linear.
- **Constraints**: delivered stages, one task in flight, whole-deliverable forecasts
  below 400 authored executable lines, unchanged upstream baseline and pins.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| Linear GraphQL | Schema checked 2026-09-12 | [Official schema](https://raw.githubusercontent.com/linear/linear/master/packages/sdk/src/schema.graphql), [API](https://linear.app/developers/graphql) |
| Git | Installed CLI | [check-ref-format](https://git-scm.com/docs/git-check-ref-format), [switch](https://git-scm.com/docs/git-switch) |
| GitHub CLI | Installed CLI | [gh api](https://cli.github.com/manual/gh_api) |
| Python | 3.11+ | [subprocess](https://docs.python.org/3.11/library/subprocess.html), [json](https://docs.python.org/3.11/library/json.html) |

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose pinned upstream | PASS | PASS | Authored preset/extensions only. |
| II. Preserve native surface | PASS | PASS | Existing slash commands; internal bridge only. |
| III. Consumer-selected integrations | PASS | PASS | Reviewer bundle needs no Linear; fixtures remain synthetic evidence. |
| IV. Durable repository truth | PASS | PASS | Derive from Git, native Issue lookup, and PR links. |
| V. Source/consumer boundary | PASS | PASS | Internal bridge ships inside its package; no source-root imports. |
| VI. Traceable delivery units | PASS | PASS | Sequential ledger with traces and complete forecasts. |
| Human gates and stage order | PASS | PASS | Full flow and remote actions authorized 2026-09-12; merge remains human. |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| Native reads | Linear client/resolver | Issue context, suggested branch, native lookup | Template reconstruction or identity registry |
| Start and PR routing | Default preset | Adopt existing work; native name or unconfigured key/title | Feature/task renaming or new slash command |
| Lifecycle observation | Linear | Resolve observed heads and PR linkage before derivation | New state precedence or Issue-content writes |
| Review and guard | Code-review | Canonical Work item identity; exact feature/task recognition | Linear dependency or executing candidate bridges |

## Technical decisions

### D1. Native resolution belongs to Linear

- **Decision**: Extend `LinearClient` with Issue context and batched
  `issueVcsBranchSearch(branchName: String!)` reads. Add stateless
  `work_item_resolution.py` and `scripts/python/resolve_work_item.py` inside the
  Linear package. Preserve existing transport, retries, redaction, query bounds,
  config, credentials, pagination, and team checks.
- **Rationale**: `Issue.branchName` is the suggested name; `gitBranchFormat` is a
  free template, not a format enum. Credential prefixes must not be reconstructed.
- **Trade-off**: Configured nonconventional names need online reads.

The internal JSON interface accepts an Issue key or observed branch names and
returns canonical identifier, Issue ID, title, description, URL, team, and exact
suggested branch. Separate absent configuration from invalid configuration,
missing runtime/credentials, denied access, transport failure, null lookup,
wrong-team response, and conflicting evidence. Add no public command or flags.

T004 extends observation results with `affected_issue_keys`, the union per exact
head of the leading strict identity, valid canonical Tracker identities, and
validated native identity. Retain valid identities when other Tracker evidence
is malformed. Exclude prefix/slug tokens and feature/task refs. Adoption and
projection consume this evidence to protect affected Issues without reparsing
identity. The user waived the 400-line limit and rejected T010; retain existing
forecasts, task order, actual size reporting, and independent reviews.

The native lookup returns one nullable Issue, not a candidate list. Accept its
native resolution only when team and explicit Issue/PR evidence agree; reject
multiple distinct explicit keys or contradictory results. Do not claim to detect
undocumented hidden API matches. Batch distinct names within existing request
bounds; exclude exact feature/task refs from work-item projection.

A unique canonical Tracker key (or strict default branch key) plus a successful
Issue read establishes identity even when a consulted native branch lookup is
null. A non-null native disagreement is a conflict; a name without explicit
identity and with null lookup stays unresolved. Native transport failure remains
failed evidence, distinct from a successful null result.

Only the leading strict default key and canonical Tracker fields are explicit
textual identities. Additional Issue-like tokens make a branch-only, native-null
fallback ambiguous; a native match or an agreeing canonical Tracker plus Issue
read resolves that ambiguity. Names outside the strict default layout require
native or canonical Tracker evidence.

### D2. Resolve and adopt before mutating Git

- **Decision**: Put setup in a small preset `work_item_start.py`, called by
  `task_base.py work-item`. Replace its old caller-built branch input with an
  Issue key plus title/context only when the unconfigured path needs them.
- **Rationale**: Today's helper blindly creates a supplied branch; adoption exists
  only in prose and misses changed metadata.
- **Trade-off**: Safe adoption needs complete branch and repository-PR observation.

Configured start calls the installed bridge before mutation. Unconfigured start
validates the supplied key and derives lowercase `team-number-slug` from the known
title; missing data returns an actionable input-needed diagnosis. Return Issue
context for bug triage. Use argument arrays and Git branch validation.
Reject a suggested full name that collides with the reserved `NNN-slug` or
`NNN-T###-slug` conventions before mutation; nested task-like leaves remain valid.

Observe local branches, remote heads, and paginated same-repository PRs. Prefer
the unique open PR linked through canonical `Tracker: Fixes TEAM-N`; otherwise
adopt the unique existing branch proven to belong to the Issue. Collapse local
and remote copies with the same name. Native resolution handles nonconventional
heads; PR linkage preserves identity after title/format/assignee changes.
Multiple PR heads, conflicting keys, or several unranked branches stop explicitly.
Closed unmerged PRs alone are not active work or proof of completion.

Adopt local branches without reset; track existing remote branches preserving
history. Validate target/base refs and fetch before switch/create. Preserve Git's
dirty-file/worktree checks; reject fork PRs and unavailable refs. Never force,
delete, rename, or overwrite. Reconcile lifecycle only after successful setup.
Repeat start re-observes and converges on existing work.

### D3. Resolve observations before deriving lifecycle

- **Decision**: Feed canonical transient Issue associations to `derive_work_items`
  and reuse resolution in status/push, session-start, and hook context.
- **Rationale**: Existing callers repeat an incomplete branch regex.
- **Trade-off**: Bounded additional native reads for observed work-item heads.

Retain canonical PR-body linkage in the existing GitHub model/parser. Exact
feature-task PRs remain tasks even when their bodies link Linear Issues. Preserve
`PullRequestScan` completeness and current precedence. Native null without
canonical explicit identity is unresolved, following D1;
transport/malformed responses never look complete. Conflicts and incomplete
required evidence preserve affected Issue state and produce sanitized diagnostics.
Only genuinely absent/disabled hook configuration is a quiet no-op.

### D4. Review uses anchored identity; guards remain local

- **Decision**: Review uses the canonical Work item/Tracker field, strict default
Issue keys, and bug evidence before stale feature selection. Classify numeric
feature/task refs by their complete convention, never an arbitrary leaf segment.
- **Rationale**: `bundles/reviewer` deliberately installs no Linear. Reviews must
not execute candidate-provided scripts or require its credentials.
- **Trade-off**: An unusual local name lacking PR identity remains an explicit
unresolved advisory context; it must not inherit unrelated SDD artifacts.

Parse the canonical field, not incidental Issue mentions. Reject contradictory
branch/body identities. Exact feature/task refs preserve their existing SDD
behavior and task PR links. Apply this in both `sdd_context.py` and
`review_context.py`. Guards protect exact full task refs only; native nested
paths ending in a task-like leaf do not inherit task-only protection. Ambiguous
review context remains advisory with truthful coverage.

### D5. Verify a common contract without coupling package releases

- **Decision**: Keep small owner-local adapters and run one equivalent case matrix
through start, PR routing, review, guards, and projection.
- **Rationale**: Packages/preset archive independently; root imports break consumers.
- **Trade-off**: Behavioral conformance detects drift instead of shared transport.

Use existing conformance entrypoints; add no vendored modules, dependency, registry,
or speculative general identity framework. Modify authored commands; regenerate
installed skills through supported dev-install tooling, never hand-edit them.

## Data and migration behavior

Issue resolutions and associations are transient. Existing PR Tracker fields,
Git ref names/history, and feature selection remain durable truth. No migration
or compatibility layer; replace obsolete parsing/callers together.

## Failure, retry, rollout, and rollback

- **Failure behavior**: Required reads/validation precede Git changes; diagnostics
identify absent, failed, conflicting, or invalid evidence without secrets.
- **Retry/idempotency**: Fresh observation adopts existing work; uncertain evidence
preserves state. Existing mutation-executor retries remain unchanged.
- **Rollout**: Sequential task PRs and installed-consumer verification; release
publication remains in the existing separate release workflow.
- **Rollback**: Reviewed revert chore, preserving all refs and Issue links.

## Security and privacy

Use existing fixed endpoints and credential loaders. Do not edit Issue content
or assignment. Names/context/PR bodies are untrusted data; use validated identifiers
and argument arrays. Review executes no candidate resolver. Live evidence retains
credential type and boolean/prefix shape observations, not operator names/secrets.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001–004, SC-001/003/005 | Native API/bridge and start fixtures | `uv run --frozen --offline --project packages/spec-kit-linear pytest packages/spec-kit-linear/tests -q` |
| FR-005–006, SC-002/003 | Adoption, changed metadata, conflicts, dirty preservation | `uv run --frozen --offline --project packages/spec-kit-code-review pytest presets/default/tests -q` |
| FR-007–010, SC-004 | Cross-surface formats, stale context, feature/task regressions | Both package suites plus preset suite |
| C-001–004, SC-005 | Packaged bridge and reviewer-only consumer | Linear `scripts/conformance/installed-artifact.sh`; review `scripts/conformance/review.sh` |
| Full candidate | Independent contract/code audit and extension review | `git diff --check`; anchored code-review sessions |

Live read-only evidence on 2026-09-12: configured `api_key`; one existing Issue's
branch had one prefix segment, passed Git validation, and native lookup returned
the same Issue. The organization's template uses a literal prefix, with only
Issue identifier/title placeholders. This verifies the configured prefix; it does
not establish credential-derived prefixes or OAuth behavior. T008
repeats the probe through the implementation. Fixtures cover key-only, user/nested
prefixes, title-only names, metadata changes, absence, failures, and conflicts.

## Source layout

```text
packages/spec-kit-linear/src/spec_kit_linear/{linear_client,work_item_resolution,work_items,github,cli}.py
packages/spec-kit-linear/scripts/python/resolve_work_item.py
packages/spec-kit-linear/tests/
packages/spec-kit-linear/scripts/conformance/installed-artifact.sh
presets/default/scripts/python/{work_item_start,task_base,pr_create,_common}.py
presets/default/commands/{bugfix,chore,pr}.md
presets/default/tests/
packages/spec-kit-code-review/src/spec_kit_code_review/{sdd_context,review_context,cli}.py
packages/spec-kit-code-review/tests/
packages/spec-kit-code-review/scripts/conformance/review.sh
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Rebuild branch templates or keep extending regexes | Native lookup covers configurable and credential-dependent formats. |
| Persistent alias map | Duplicates native identity and drifts. |
| Root shared import, vendored helper, or new dependency | Breaks independent archives or adds release coupling. |
| Execute candidate bridge in review | Violates reviewer trust and portability. |

## Product handoff

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | 2026-09-12: 15/15 FR+SC and 4/4 constraints covered, 9/9 tasks traced, zero outstanding findings; prerequisites and diff check pass. | complete |
| Technical approval of plan/tasks | Human explicitly requested implementation once artifacts are correct, 2026-09-12; clean analysis satisfies that condition. | authorized |
| Reviewed Linear dry-run and sync | Project and nine Issues verified: TDS-101–TDS-108 plus T009/TDS-109; bounded split synchronized without changing human assignees. | complete |
| Every executable task individually assignable and assigned | Nine separate delivery units; execution assigned to fresh Luna Extra High agents sequentially. Existing Linear human assignees remain unchanged. | execution assigned |
