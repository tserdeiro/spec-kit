# Tasks: Verify native GitHub delivery guarantees

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: T001 after technical approval and individual task assignment.

## Delivery strategy

- `012-native-github-rules` is the integration branch. Its draft feature PR
  targets `main`; reviewing it supplies the technical gate. Human merge commits
  integrate task PRs, then the completed feature.
- One task branch and draft PR per task, named `012-T###-short-slug`. Deliver
  sequentially; stack on the previous ready, open task PR, otherwise on the
  feature branch. Dependencies describe order, not a separate base selector.
- Each task includes its implementation, tests, manifest/caller changes, and
  completion evidence. Forecasts cover the whole deliverable; the existing
  400-line budget and 2× forecast stop apply. New IDs append without renumbering.
- Every task starts unchecked with pending evidence. Linear projects observed
  reality; publication does not mark implementation complete or grant approval.

## Phase 1: User Story 1 - Diagnose delivery guarantees (P1)

**Goal**: Show settings and effective shared-branch protection with explicit coverage.
**Independent evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q`

- [x] T001 [US1] Replace the settings-only doctor check with a runnable GitHub report in presets/default/scripts/python/github_delivery.py
  - **Traces**: FR-002, FR-008, FR-009, C-001, C-004, SC-001, SC-003; outcome: the existing doctor reports observed merge/deletion settings and explicitly unverified branch guarantees.
  - **Depends on**: none
  - **Boundaries**: Add the helper and `presets/default/tests/test_github_delivery.py`; register it in `presets/default/preset.yml` and update steps 4/5 in `presets/default/commands/doctor.md` atomically. Reuse the existing interpreter/repository conventions and read helpers where suitable. Establish the four-state result contract, safe GET-only execution, missing-field handling, deterministic rendering, and 0/1 exit status from plan D1/D4. Keep other doctor categories' local repairs unchanged. Until branch checks land, the aggregate remains unverified.
  - **Evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py -q` -> true/false/missing settings, absent gh, and failed reads produce scoped results without false overall compatibility; fake argv rejects writes; consumer files stay unchanged. `git diff --check` -> clean.
  - **Delivery**: single PR (~280 authored lines)
  - **Completion evidence**: PR #151; 8 focused tests and 79 preset tests passed; budget 282/400; diff check clean. Independent native review of 1a215c1 returned no-blocking-findings. Current-head review and CI gate readiness.

- [x] T002 [US1] Diagnose active rules on the complete shared-branch inventory in presets/default/scripts/python/github_delivery_rules.py
  - **Traces**: FR-001, FR-003, FR-004, FR-008, FR-009, C-004, SC-001, SC-002; outcome: trunk and remote canonical feature/task branches have explicit active-rules evidence and honest scope coverage.
  - **Depends on**: T001
  - **Boundaries**: Extend `github_delivery.py`, add the pure evaluator and `presets/default/tests/test_github_delivery_rules.py`, and register the evaluator in the preset manifest. Use `_common.delivery_base()` for trunk; fully paginate branch inventory and effective branch rules with explicit GET and validated page shapes. Encode path segments and deduplicate branch/ruleset identities. Render force-push evidence from `non_fast_forward`; mark classic-protection and exception coverage unverified until T003. GitHub performs pattern matching and inherited enforcement; the helper preserves its sources.
  - **Evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q` -> configured/default trunk, canonical versus unrelated branches, inherited active rules, disabled/evaluation absence, successful empty reads, malformed pages, second-page failure, and missing/disappearing branches are distinguished. Shell-shaped branch names remain literal argv. `git diff --check` -> clean.
  - **Delivery**: single PR (~370 authored lines)
  - **Completion evidence**: PR #153; 13 focused and 84 preset tests passed; budget 397/400; diff check clean. Trunk stderr leakage fixed and covered by a regression test. Independent native review of 6c9e400 returned no-blocking-findings. Current-head review and CI gate readiness.

- [x] T003 [US1] Combine classic protection and bypass visibility in presets/default/scripts/python/github_delivery_rules.py
  - **Traces**: FR-003, FR-004, FR-006, FR-008, FR-009, C-002, SC-001, SC-002; outcome: force-push protection reflects all observed layers and names exceptions without relying on privilege.
  - **Depends on**: T002
  - **Boundaries**: Extend both helpers and their focused tests. Read classic protection and each relevant ruleset detail once per run, including parent scope. Implement plan D2/D3's distinction between documented absence of classic protection and ambiguous 404; combine enforced restrictions, `enforce_admins`, visible bypass modes, and hidden fields. An omitted `bypass_actors` is unknown; a visible empty list is known. Broader bypass is an explicit exception, and PR-only bypass does not allow direct force-push/deletion. Preserve review/check policy.
  - **Evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q` -> classic-only protection, overlapping layers, admin exceptions, inherited detail, PR/always/exempt bypass, absent versus empty fields, and inaccessible protection retain correct force-push results and read-only argv. `git diff --check` -> clean.
  - **Delivery**: single PR (~340 authored lines)
  - **Completion evidence**: PR #155; 25 focused and 96 preset tests passed; budget 389/400; diff check clean. Independent native review of eba6fa4 returned no-blocking-findings. Current-head review and CI gate readiness.

- [x] T004 [US1] Expose merge and cleanup conflicts in presets/default/scripts/python/github_delivery_rules.py
  - **Traces**: FR-002, FR-003, FR-005, FR-007, FR-008, FR-009, C-002, SC-001, SC-003; outcome: repository booleans cannot hide a rule that blocks stack integration or branch cleanup.
  - **Depends on**: T003
  - **Boundaries**: Extend the evaluator, report, and focused fixtures. Combine merge settings with linear history, allowed merge methods, locks, and merge-queue method/uncertainty. Combine automatic deletion with effective deletion restrictions, classic allow-deletions, locks, branch role, and known exceptions. Retain trunk while diagnosing feature/task cleanup. Add source/owner/rule-specific native remediation, concrete setting values or scope adjustments, and explicit uncertainty for unsupported semantics. Preserve confirmed conflicts alongside incomplete observations.
  - **Evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q` -> globally allowed but branch-blocked merge, linear history, method restrictions, queue uncertainty, auto-delete with deletion/lock conflicts, and retained-trunk fixtures match expected results. Proposed changes preserve team checks/reviews/bypass; no writes occur. `git diff --check` -> clean.
  - **Delivery**: single PR (~300 authored lines)
  - **Completion evidence**: PR #157; 34 focused and 105 preset tests passed; budget 397/400; diff check clean. Missing ruleset exception coverage fixed with a regression through diagnose. Independent native review of 6aec283 returned no-blocking-findings. Current-head review and CI gate readiness.

## Phase 2: User Story 2 - Act on an honest diagnosis (P2)

**Goal**: Distinguish configuration, capability, and access/read failures with a usable next action.
**Independent evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q`

- [ ] T005 [US2] Complete cause-specific remedies and safe failure reporting in presets/default/scripts/python/github_delivery.py
  - **Traces**: FR-006, FR-007, FR-008, FR-009, C-002, C-004, SC-002, SC-003; outcome: every gap carries evidence and the correct administrative or retry action without leaking secrets or misreporting capability.
  - **Depends on**: T004
  - **Boundaries**: Extend both helpers and focused tests with the complete cause matrix in plan D4. Distinguish explicit plan limits, denied permissions, hidden fields, rate limits, transient/partial reads, and unknown semantics; generic 403/404 or private visibility proves no plan limit. Sanitize bounded errors, retain independent verified/conflicting subresults, and give native owner/access/plan/retry guidance. Verify the existing doctor preserves these findings in category 6 on plain and `--fix` paths and never forwards mutation flags to the helper.
  - **Evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q` -> the complete SC-002 cause matrix, mixed success/failure, same-input repeatability, successful retry, hostile error text with synthetic credentials, zero mutation calls, and unchanged consumer configuration all pass. `git diff --check` -> clean.
  - **Delivery**: single PR (~280 authored lines)
  - **Completion evidence**: Pending

## Final phase: Cross-cutting verification

- [ ] T006 Prove installed-consumer behavior in presets/default/tests/test_github_delivery_install.py
  - **Traces**: FR-001, FR-008, FR-009, C-001, C-003, C-004, SC-001, SC-002, SC-003, SC-004; outcome: a consumer executes the packaged diagnosis independently of the source checkout, with accurately labelled synthetic evidence.
  - **Depends on**: T005
  - **Boundaries**: Add the installed test and only necessary shared fixture support in `presets/default/tests/conftest.py`; update `presets/default/README.md` with observed scope, outcomes, and native remediations. Use native preset installation into a temporary consumer and execute its installed helper with source paths absent from imports. Exercise compatible, cleanup-blocked, permission-denied, and failed-read cases; check manifest/script availability and the generated doctor's report-only GitHub caller, including `--fix` guidance. Run the existing bundle suite without adding a separate conformance runner. Preserve release pins, upstream renders, and live acceptance boundaries.
  - **Evidence**: `uv run --frozen --offline pytest presets/default/tests/test_github_delivery_install.py -q` -> installed synthetic matrix and generated caller pass; `uv run --frozen --offline pytest presets/default/tests -q` -> preset regressions pass; `bash scripts/conformance/bundles.sh` -> existing distribution lifecycle passes; `git diff --check` -> clean. Record generated-asset checks, installed synthetic execution, and pending entry-23 live acceptance separately.
  - **Delivery**: single PR (~260 authored lines)
  - **Completion evidence**: Pending

## Dependencies and stack order

- **Critical path**: T001 → T002 → T003 → T004 → T005 → T006.
- **Stack order**: One PR per task in that order; each targets the preceding
  ready, unmerged task PR or the feature branch when none is open.
