---
description: 'Dependency-ordered delivery units for sufficient review context'
---

# Tasks: Sufficient review context

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- Feature branch `007-review-context` integrates task PRs and reaches the
  delivery base through its feature PR, with human review and merge. Resolve
  the base from non-empty `trunk:`, otherwise the GitHub default branch.
- Product closes with committed artifacts and an authorized draft feature PR
  through `/speckit.pr`; implementation starts after the plan's handoff gates
  and reliability entry 01 delivery. Publication retains human authorization.
- Start each task on `007-T###-short-slug`, based on the open ready task PR at
  the stack's top, otherwise the feature branch. Use the installed task-base
  routine before editing. `Depends on` defines execution order; the delivery
  loop resolves branch topology. One task runs at a time; ready permits the next.
- Each task delivers one PR. Forecasts include changed callers, tests, fixtures,
  and documentation. Keep each PR under the existing ~400 authored executable
  lines and apply the 2× forecast stop. Re-slice oversized work through product
  before execution; committed IDs remain stable.
- Completion evidence travels in the task PR's final commit. Review scope and
  Linear state continue to derive from their respective observable evidence.

## Task block format

Every task has a checkbox, stable ID, story marker where applicable, Traces,
Depends on, Boundaries, Evidence, Delivery forecast, and Completion evidence.
Commands run from the repository root. Each slice updates its callers and
regression fixtures so the existing review workflow remains executable.

## Phase 1: User Story 1 - Review a task in a large ledger (P1)

**Goal**: Expose complete task definitions before narrowing the packet.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_sdd_context.py packages/spec-kit-code-review/tests/unit/test_packet.py -q` -> full real blocks and delivery fields survive parsing; fenced examples are not tasks.

- [x] T001 [US1] Expose complete task blocks in packages/spec-kit-code-review/src/spec_kit_code_review/sdd_context.py
  - **Traces**: FR-002, SC-001; outcome: context and the existing packet task summary expose complete blocks, traces, dependencies, delivery, and completion evidence with exact source ranges.
  - **Depends on**: none
  - **Boundaries**: Change `sdd_context.py`, its packet summary caller in `packet.py`, and `tests/unit/test_sdd_context.py`/`test_packet.py`. Preserve source text, existing reader ownership, constitution, and upstream assets. Follow plan D1; distinguish changed-path hints from protected paths and evidence commands.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_sdd_context.py packages/spec-kit-code-review/tests/unit/test_packet.py -q` -> indented fields, fenced samples/evidence, repeated IDs, malformed blocks, and the final block are covered; existing context output still works.
  - **Delivery**: single PR (~280 authored lines)
  - **Completion evidence**: PR #127; full package suite: 855 tests and 423 subtests passed; diff check passed. Independent review found nested checklist misclassification; fixed in `38d0ece` with regression coverage. Review evidence: https://github.com/tserdeiro/spec-kit/pull/127#issuecomment-5642251766. Independent reviews also found duplicate-ID, missing-dependency, and required-field gaps; all corrected with regression tests. Complete reached blocks now render after artifact truncation; final focused run: 72 tests and 5 subtests passed, golden passed. Protected, negated, and ambiguous path claims have regression coverage. Independent review https://github.com/tserdeiro/spec-kit/pull/127#issuecomment-5642498231 reported no blocking findings and one major false-gap issue, now corrected and root-reviewed. CI is recorded in the PR.

## Phase 2: User Story 2 - Cover the whole reviewed scope (P1)

**Goal**: Identify all affected work before selecting excerpts.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_review_context.py packages/spec-kit-code-review/tests/unit/test_candidate.py -q` -> single/multiple task, full-feature, explicit-ref, and ledger-free scope follow plan D2; conflicts remain explicit.

- [x] T002 [US2] Resolve candidate scope in packages/spec-kit-code-review/src/spec_kit_code_review/review_context.py
  - **Traces**: FR-001, FR-003, FR-004, FR-007, SC-002; outcome: the packet identifies task, multi-task, feature, or short-path scope with supporting evidence and unresolved associations.
  - **Depends on**: T001
  - **Boundaries**: Add `review_context.py` and `tests/unit/test_review_context.py`; update `github.py`, `cli.py`, context output in `packet.py`, and affected `test_candidate.py`/`test_phase_two.py`/`tests/support/fake_gh.py` fixtures. Preserve candidate identity and feature selection state. Add the existing `headRefName` read and follow D2's decision table; carry unresolved scope into inconclusive causes immediately.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_review_context.py packages/spec-kit-code-review/tests/unit/test_candidate.py packages/spec-kit-code-review/tests/unit/test_phase_two.py -q` -> task identity cannot hide other changes; full-feature and explicit-ref reviews widen appropriately; unrelated active features do not impose a ledger on bugs/chores.
  - **Delivery**: single PR (~340 authored lines)
  - **Completion evidence**: PR #128; T002 suite: 93 tests and 37 subtests passed; final resolver/SDD: 35 tests and 5 subtests passed; affected golden checks passed; diff check clean. Independent review https://github.com/tserdeiro/spec-kit/pull/128#issuecomment-5642706671 found omitted contradictory PR intent; corrected with regression coverage and orchestrator review. CI is recorded in the PR.

## Phase 3: User Story 1 - Select sufficient bounded context (P1)

**Goal**: Review a late task with shared requirements without injecting unrelated ledger history.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_review_context.py packages/spec-kit-code-review/tests/unit/test_packet.py -q` -> a task beyond 60,000 bytes retains all necessary context; unrelated ledger growth leaves its required selection unchanged.

- [x] T003 [US1] Select required source ranges in packages/spec-kit-code-review/src/spec_kit_code_review/review_context.py
  - **Traces**: FR-002, FR-003, FR-004, FR-008, SC-001, SC-002; outcome: packets contain full relevant task blocks, related requirements, shared context, and dependency evidence; deliberate exclusions carry reasons and remaining-source access.
  - **Depends on**: T002
  - **Boundaries**: Change `review_context.py`, `sdd_context.py`, selection wiring in `cli.py`/`packet.py`, and `test_review_context.py`/`test_sdd_context.py`/`test_packet.py`. Implement D3 with complete source sections; preserve containment and budget policy. Direct dependency evidence does not recursively inject unrelated history. Unknown relevance widens selection; missing traces/dependency cycles remain gaps.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_review_context.py packages/spec-kit-code-review/tests/unit/test_sdd_context.py packages/spec-kit-code-review/tests/unit/test_packet.py -q` -> large-ledger late task, shared requirements, missing references, dependency cycles, overlapping task paths, and whole-feature selection are covered.
  - **Delivery**: single PR (~360 authored lines)
  - **Completion evidence**: PR #129; focused/golden suites: 97 tests and 10 subtests passed; persisted-session golden updated and CI passed. Independent review https://github.com/tserdeiro/spec-kit/pull/129#issuecomment-5642878196 found no findings. Human explicitly authorized the 533/400-line exception on 2026-09-12: 368 implementation/test lines plus 165 golden fixture lines.

- [x] T004 [US1] Bound packet content and freeze its inventory in packages/spec-kit-code-review/src/spec_kit_code_review/packet.py
  - **Traces**: FR-005, FR-006, FR-007, SC-001, SC-003; outcome: effective limits constrain rendered content and every omitted required range remains visible and retrievable.
  - **Depends on**: T003
  - **Boundaries**: Change `packet.py`, `review_context.py`, preflight/evidence wiring in `cli.py`, limit comments in `config/speckit-code-review.template.yml`, and packet/containment/golden tests and fixtures. Reuse session atomic writers. Follow D4: per-source aggregate UTF-8 allowance, total rendered limit, complete external inventory bound by digest, and whole trusted envelope. Preserve default values and upstream assets.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_packet.py packages/spec-kit-code-review/tests/unit/test_packet_containment.py packages/spec-kit-code-review/tests/unit/test_golden_packet.py -q` -> per-source and total limits, non-ASCII text, escaping, exact boundaries, inventory digest, and preflight rejection of an impossible envelope all pass.
  - **Delivery**: single PR (~380 authored lines)
  - **Completion evidence**: PR #130; focused packet/advisory tests: 75 tests and 30 subtests passed; packet goldens: 8 tests and 3 subtests; full golden review: 11 tests and 4 subtests passed. Independent review https://github.com/tserdeiro/spec-kit/pull/130#issuecomment-5643229897 found no findings. CI exposed a nested golden-field assertion, corrected and orchestrator-reviewed; diff check passed.

## Phase 4: User Story 3 - Distinguish selection from missing evidence (P1)

**Goal**: Close review only with source-validated reading reports for all necessary context.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_coverage.py packages/spec-kit-code-review/tests/unit/test_phase_two.py -q` -> missing/reference-only/wrong-source receipts retain gaps; valid additional reads close only the ranges they cover.

- [x] T005 [US3] Validate reading receipts at closure in packages/spec-kit-code-review/src/spec_kit_code_review/coverage.py
  - **Traces**: FR-006, FR-007, SC-003, SC-004; outcome: the existing findings submission produces normalized, candidate-bound reading evidence; selected or referenced content alone receives no credit.
  - **Depends on**: T004
  - **Boundaries**: Add `coverage.py`/`tests/unit/test_coverage.py`; update `findings.py`, `cli.py`, packet instructions in `packet.py`, consumer submission schema in `commands/code-review.md`, and affected findings/phase-two fixtures. Follow D5's required coverage envelope and assessment rules, exact range hashing, overlap handling, frozen PR-intent snapshots, and candidate/packet/inventory/configuration guards. Preserve original findings input and existing atomic writers; old sessions require reopening.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_coverage.py packages/spec-kit-code-review/tests/unit/test_findings.py packages/spec-kit-code-review/tests/unit/test_phase_two.py -q` -> wrong hashes/versions, absent assessments, path escapes, duplicate/overlapping/partial reads, inventory tampering, and immutable findings are covered. Existing successful-close fixtures supply explicit receipts.
  - **Delivery**: single PR (~390 authored lines)
  - **Completion evidence**: PR #131; all four CI checks passed. Independent review https://github.com/tserdeiro/spec-kit/pull/131#issuecomment-5645387535 found inventory hashing before path redaction; corrected and orchestrator-reviewed. Regression: real temporary HOME with spaces opens, retrieves frozen intent, and closes; 4 snapshot tests passed. Final goldens: 19 tests and 7 subtests passed; packet/containment: 62 tests and 30 subtests passed; diff check clean. Human authorized the T005 budget exception on 2026-09-12 (496/400 before the required review fix).

- [x] T006 [US3] Report only unresolved coverage causes in packages/spec-kit-code-review/src/spec_kit_code_review/cli.py
  - **Traces**: FR-007, FR-008, SC-003, SC-004; outcome: reviewed selected/additional context can close, while missing necessary context remains inconclusive with actionable causes in JSON and human/publication summaries.
  - **Depends on**: T005
  - **Boundaries**: Change `cli.py`, `coverage.py`, packet instructions in `packet.py`, and `test_phase_two.py`/`test_golden_review.py` with their golden evidence. Follow D6; preserve all engine and non-SDD causes, blocking findings, publication authority, and close/reopen lifecycle. Update affected shared fixtures as part of this task.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_phase_two.py packages/spec-kit-code-review/tests/unit/test_golden_review.py -q` -> valid late-task coverage is conclusive, additional reads resolve only matching gaps, and unrelated exclusions do not suppress engine failures or blocking findings.
  - **Delivery**: single PR (~280 authored lines)
  - **Completion evidence**: PR #132; all four CI checks passed. Independent review https://github.com/tserdeiro/spec-kit/pull/132#issuecomment-5645549405 closed with no findings. Focused tests: 77 tests and 28 subtests passed; 4 frozen-intent regressions passed independently. Budget 224/400; diff check clean.

## Phase 5: User Story 2 - Preserve advisory and short-path workflows (P1)

**Goal**: Use the same scope selection in advisory review with honest host-reported evidence.
**Independent evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_working_tree.py -q` plus command-guidance review -> working-source hashes and inventory are available without a session or publishable verdict.

- [x] T007 [US2] Document and expose advisory reading evidence in packages/spec-kit-code-review/commands/code-review.md
  - **Traces**: FR-001, FR-004, FR-006, SC-002, SC-004; outcome: PR and advisory workflows tell reviewers how to inspect missing content and record exact reads; advisory results remain explicitly host-reported.
  - **Depends on**: T006
  - **Boundaries**: Change `commands/code-review.md`, package `README.md`, advisory wiring in `cli.py`/`packet.py`, and `test_working_tree.py` plus advisory golden fixtures. Follow D7: `coverage.json` beside the packet, created through host file tools, source comparison before reporting, fresh packet after source changes, no reuse for PR coverage. Protect native command names, sessionless advisory behavior, and repository files during review.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_working_tree.py packages/spec-kit-code-review/tests/unit/test_golden_packet.py -q` -> captured source hashes, selected ranges, short-path context, and advisory output remain consistent. Review the documented record schema and drift instructions against D7; record this as guidance validation, not live host execution.
  - **Delivery**: single PR (~280 authored lines)
  - **Completion evidence**: PR #133; all four CI checks passed. Independent review https://github.com/tserdeiro/spec-kit/pull/133#issuecomment-5645605186 closed with no findings. Working-tree, packet, findings, and review-golden tests: 135 tests and 30 subtests passed; two source-drift/schema regressions independently passed. Budget 118/400; diff check clean. Evidence validates guidance and generated assets, not live host execution.

## Final phase: Cross-cutting verification

- [x] T008 Prove installed context coverage in packages/spec-kit-code-review/scripts/conformance/review.sh
  - **Traces**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, SC-001, SC-002, SC-003, SC-004; outcome: an isolated consumer exercises sufficient late-task, shared multi-task, full-feature, and ledger-free context with verifiable closure behavior.
  - **Depends on**: T007
  - **Boundaries**: Change `scripts/conformance/review.sh`, affected consumer fixtures, shared fixture builders in `tests/conftest.py`/`tests/support/fake_gh.py`, and package README validation notes. Use temporary repositories and fake tools; installed payload must run independently of this checkout. Preserve release pins and all human remote actions.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit -q` and `bash packages/spec-kit-code-review/scripts/conformance/review.sh` and `git diff --check` -> unit regressions and installed-consumer scenarios pass. Assert valid additional reads, failed/reference-only reads, bounded UTF-8 packet size, unchanged operator checkout, and correct final causes. Label fake-tool evidence separately from entry 23 live acceptance.
  - **Delivery**: single PR (~300 authored lines)
  - **Completion evidence**: PR #134; all four CI checks passed. Independent review https://github.com/tserdeiro/spec-kit/pull/134#issuecomment-5645727507 closed with no findings and independently ran installed conformance. Full package suite: 908 tests and 428 subtests passed. Installed fake-tool conformance passed for late-task, multi-task, full-feature, short-path, partial/reference-only/invalid/full receipts, UTF-8 limits, and per-review checkout invariants. Budget 309/400; diff check clean. This is installed fake-tool evidence, not entry 23 live-host acceptance.

## Dependencies and stack order

- **Critical path**: T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008.
- **Stack order**: Each task stacks on the previous ready, unmerged task PR;
  when none is open it starts from `007-review-context`. Dependencies remain
  fixed; actual PR bases come from the delivery loop.
- **MVP**: T001–T006 deliver sufficient anchored review context and honest
  closure. T007 completes advisory guidance; T008 provides installed-consumer
  acceptance for the whole specification before release.
