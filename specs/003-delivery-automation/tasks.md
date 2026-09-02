---
description: "Dependency-ordered, traceable delivery units for feature implementation"
---

# Tasks: Unattended delivery automation

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- **The feature branch (`003-delivery-automation`) is the integration
  branch**: every task merges into it; the feature enters the default
  branch once, through the feature PR, as a merge commit.
- **One branch per task** (`003-T###-short-slug`), draft PR against the
  feature branch; one task in flight, dependency order, stacking when the
  predecessor is unmerged; ~400 authored-line budget per reviewed PR.
- Task states project to Linear from observable reality: checkbox, task
  branch, PR draft/ready/merged.
- Note (plan D11): this file intentionally omits the template's
  instructive "Task block format" section — the installed linear 0.10.0
  parser reads its fenced example as a real task. T009 removes the need
  for this workaround.

## Phase 1: Setup

**Purpose**: Make this repository its own consumer so the projection half
of the flow is dogfooded here (plan D11, spec A-002).

- [x] T001 Install published spec-kit-linear 0.10.0 and spec-kit-code-review 0.2.1 into this repository and onboard Linear to the TDS team
  - **Traces**: A-002, FR-004 (evidence path), SC-002; outcome: distribution catalogs added, `specify extension add` vendors both published extensions (the loop's self-review needs code-review installed — scope widened during delivery), `onboard --team-key TDS --repository spec-kit` binds Linear, doctor green, `push --current --apply` projects this feature's Project + Issues
  - **Depends on**: none
  - **Boundaries**: `.specify/extensions/{linear,code-review}/**`, `.specify/extensions.yml` + `.registry`, catalog config files, generated `.agents/skills/`, `.gitignore` (extension cache; stale binding comment); root `speckit-linear.yml` and `.speckit-linear.env` stay gitignored by this repo's standing policy; no package/preset source changes
  - **Evidence**: `bash .specify/extensions/linear/scripts/bash/run.sh doctor` → green; `... run.sh push --current --apply` → 15 operations applied (1 Project + 14 Issues in TDS)
  - **Delivery**: single PR into 003-delivery-automation (vendored payloads + config; mechanical diff)
  - **Completion evidence**: PR #44 (draft→ready 2026-08-31); doctor online green; push applied 15 operations (Project + TDS-14..TDS-27); vendored linear/src verified byte-identical to tag spec-kit-linear/v0.10.0; no credentials tracked; self-review no-blocking-findings (session e4f7885d)

## Phase 2: User Story 1 — The flow acts instead of reminding (P1)

**Goal**: product-phase commands end committed and silent.
**Independent test**: run any product-phase command; no hook block, artifacts committed, clean `git status`.

- [ ] T002 Phase-close append: silence optional hooks and commit feature artifacts in presets/default
  - **Traces**: FR-001, FR-002, SC-001; outcome: new `commands/phase-close-append.md` registered (append) for `speckit.specify`, `speckit.plan`, `speckit.analyze`; same rule folded into `tasks-append.md`; optional hooks never announced (enabled→execute silently), each phase ends committing `specs/<feature>/` only, skipping when clean
  - **Depends on**: none
  - **Boundaries**: `presets/default/commands/`, `presets/default/preset.yml`, `presets/default/README.md`; core templates untouched (C-001)
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; append text present in regenerated skills; this feature's later phases run silent and committed
  - **Delivery**: single PR into 003-delivery-automation (~80 authored lines)
  - **Completion evidence**: Pending

## Phase 3: User Story 2 — Linear mirrors the unattended run (P2)

**Goal**: the loop itself reconciles Linear and reviews with a fresh context.
**Independent test**: drive one task; its issue moves with no human push; findings live in their session.

- [ ] T003 Loop reconciliation: `push --hook` at loop start and after each transition in implement-append.md
  - **Traces**: FR-004, SC-002; outcome: loop step 0 and the transitions it causes (task branch created, PR ready) invoke `speckit.linear.push --hook`; unconfigured repos no-op silently; failures report once and never block delivery
  - **Depends on**: none
  - **Boundaries**: `presets/default/commands/implement-append.md` only; no lifecycle hook registrations (plan Alternatives)
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; during this feature's own loop, TDS issues read In Progress/In Review with no human push
  - **Delivery**: single PR into 003-delivery-automation (~40 authored lines)
  - **Completion evidence**: Pending

- [ ] T004 Fresh-context self-review in the loop (implement-append.md)
  - **Traces**: FR-011, US2.4; outcome: the loop delegates packet reading and findings to a fresh sub-agent (hosts without sub-agents run it themselves), findings written inside the review session directory, never reused
  - **Depends on**: T003
  - **Boundaries**: `presets/default/commands/implement-append.md`; enforcement half lands in T010
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; this loop's own reviews delegate and write per-session findings
  - **Delivery**: single PR into 003-delivery-automation (~30 authored lines)
  - **Completion evidence**: Pending

## Phase 4: User Story 3 — One command to implement (P3)

**Goal**: `implement` verifies/opens the feature gate itself.
**Independent test**: run implement with no feature PR; the draft gate opens, then T-first starts.

- [ ] T005 Loop step 0: verify or open the draft feature PR in implement-append.md
  - **Traces**: FR-003, SC-005; outcome: before the first task the loop checks the feature branch's PR and, when missing, executes the `speckit.pr` feature-variant routine (idempotent; existing PR reported, never duplicated)
  - **Depends on**: T004
  - **Boundaries**: `presets/default/commands/implement-append.md`; `pr.md` stays the routine's single owner
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; loop text names the gate as step 0 and delegates to `speckit.pr`
  - **Delivery**: single PR into 003-delivery-automation (~30 authored lines)
  - **Completion evidence**: Pending

## Phase 5: User Story 4 — Setup diagnoses itself (P4)

**Goal**: gaps name their remediation; native coverage stated honestly.
**Independent test**: unlink/misconfigure a fixture repo; read the named fixes.

- [ ] T006 Unlinked-repo guard in spec-kit-linear: name `onboard`, never a raw API error
  - **Traces**: FR-005, SC-003; outcome: `push` and `status` short-circuit before any network call when root `speckit-linear.yml` is missing or still placeholder, with a `configuration` diagnostic naming `onboard`; credential failures keep naming their source
  - **Depends on**: none
  - **Boundaries**: `packages/spec-kit-linear/src/spec_kit_linear/{cli,config}.py`, tests; no behavior change for linked repos
  - **Evidence**: `uv run --project packages/spec-kit-linear pytest` green incl. new guard cases; fixture run shows the onboard message
  - **Delivery**: single PR into 003-delivery-automation (~80 authored lines)
  - **Completion evidence**: Pending

- [ ] T007 Platform checks in the preset doctor (doctor.md)
  - **Traces**: FR-006, SC-003; outcome: doctor additionally reports `deleteBranchOnMerge` and `mergeCommitAllowed` via read-only `gh repo view`, each with the exact setting to change; degrades to "cannot verify" without `gh`
  - **Depends on**: T006
  - **Boundaries**: `presets/default/commands/doctor.md` only; never mutates settings
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; doctor run in this repo names both settings' states
  - **Delivery**: single PR into 003-delivery-automation (~30 authored lines)
  - **Completion evidence**: Pending

- [ ] T008 Document native Linear automation coverage (spec-kit-linear README + root README note)
  - **Traces**: FR-007, US4.3; outcome: docs state PR automations are team-level, a target-branch rule (`^\d{3}-`) is required for task-PR merges into feature branches, linking rides the PR-body magic word (branches carry no issue key), and `push` reconciles regardless
  - **Depends on**: T007
  - **Boundaries**: `packages/spec-kit-linear/README.md`, root `README.md` (Spanish consumer note); no code
  - **Evidence**: doc sections present; `git diff --check` clean
  - **Delivery**: single PR into 003-delivery-automation (~50 authored lines)
  - **Completion evidence**: Pending

## Phase 6: User Story 5 — The flow never breaks its own tools (P5)

**Goal**: generated artifacts parse; docs match validators; trunk configurable.
**Independent test**: template-section fixture parses; documented findings close first try; `trunk:` respected.

- [x] T009 Tasks parser ignores fenced blocks in spec-kit-linear
  - **Traces**: FR-008, SC-004; outcome: ``` and ~~~ fences skipped for title/phase/task matching; the tasks template's instructive section parses without manual deletion; existing files parse identically
  - **Depends on**: none
  - **Boundaries**: `packages/spec-kit-linear/src/spec_kit_linear/parser.py`, tests (template-section fixture)
  - **Evidence**: `uv run --project packages/spec-kit-linear pytest` green incl. fixture built from `presets/default/templates/tasks-template.md`
  - **Delivery**: single PR into 003-delivery-automation (~60 authored lines)
  - **Completion evidence**: PR #52 (ready 2026-09-01, stacked on #44 for loop tooling); 13 parser tests and full 402-test linear suite passed; template fixture preserves its fenced instructional section while parsing the real task; `git diff --check` passed; fresh review no-blocking-findings (session b12bd7ea, per-session findings)

- [x] T010 Findings format: correct the docs and bind the findings path to its session (spec-kit-code-review)
  - **Traces**: FR-009, FR-011, SC-004; outcome: `commands/code-review.md` + README show `{"findings": [...]}` exactly as validated; `--findings` outside the session directory it closes is a usage error with a message naming the expected location
  - **Depends on**: T009
  - **Boundaries**: `packages/spec-kit-code-review/{commands/code-review.md,README.md}`, `src/spec_kit_code_review/cli.py`, tests; validator schema unchanged
  - **Evidence**: `uv run --project packages/spec-kit-code-review pytest` green incl. path-bind cases; doc example passes the validator verbatim
  - **Delivery**: single PR into 003-delivery-automation (~70 authored lines)
  - **Completion evidence**: PR #53 (ready 2026-09-01, stacked on #52); documented envelope validated; outside and escaping-symlink paths rejected; reopening discards stale close artifacts; partial publication retries require the same normalized findings plan; 786 tests and 493 subtests passed; two fresh reviews found stale findings and stale partial-publication reuse, both corrected; final fresh review no-blocking-findings (session 0919ffd0)

- [x] T011 Deterministic trunk resolver and product Git composition
  - **Traces**: FR-010, SC-006; outcome: the product bundle installs Git and its preset helper reuses the pinned Specify PyYAML runtime (no new consumer dependency) to resolve and Git-validate a non-empty string `trunk:` in `.specify/extensions/git/git-config.yml`; absent/null/empty uses the GitHub default; invalid forms fail closed
  - **Depends on**: T010
  - **Boundaries**: product bundle Git composition; `presets/default/scripts/resolve-delivery-base.py`; helper conformance in `scripts/conformance/bundles.sh`; upstream Git template untouched (C-001)
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; temporary consumers exercise real YAML, configured/fallback/invalid values, inert argv, `python3 -S` bootstrap into Specify's runtime, and command failures
  - **Delivery**: single PR into 003-delivery-automation (≤400 authored executable lines; split from the unsafe ~50-line forecast)
  - **Completion evidence**: PR #55 (ready 2026-09-01, stacked on #53); product bundle installs the pinned Git extension; resolver reuses `pyyaml>=6.0` declared by `specify-cli` 1.0.1, rejects duplicate/invalid YAML and non-string trunks, falls back only for absent/null/empty, and validates literal Git branch argv; `python3 -S` bootstrap, configured/fallback/failure/Unicode cases, `bash scripts/conformance/bundles.sh`, syntax checks, and `git diff --check` passed; effective executable budget 368/400; fresh reviews exposed the unsafe hand parser and the final PyYAML candidate had no findings

- [ ] T015 Wire runtime trunk resolution into feature delivery commands
  - **Traces**: FR-010, SC-006; outcome: feature PR and first-task refresh invoke T011's helper; task/work-item PR bases derive at runtime; all repository-derived branch names remain inert argv; behavior is documented and this repo sets `trunk: main`
  - **Depends on**: T011
  - **Boundaries**: `presets/default/commands/{pr.md,implement-append.md}`; preset/root READMEs; this repo's consumer `git-config.yml`; command conformance in `scripts/conformance/bundles.sh`; `spec.md`/`plan.md` clarifications
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; temporary consumers execute feature/task/work-item creation and first-task refresh with configured/fallback/metacharacter/failure cases
  - **Delivery**: single PR into 003-delivery-automation (≤400 authored executable lines), stacked on T011
  - **Completion evidence**: Pending

## Phase 7: Polish and release

**Purpose**: coherent versions, plan extended, transversal evidence.

- [ ] T012 Extend docs/plan.md with this round and groom docs/dogfooding.md
  - **Traces**: A-004, A-001; outcome: `docs/plan.md` gains the delivered-round entry for this feature; `docs/dogfooding.md` entries met during delivery are appended and the graduated ones marked
  - **Depends on**: T015
  - **Boundaries**: `docs/` only
  - **Evidence**: `git diff --check` clean; round entry cites the feature directory
  - **Delivery**: single PR into 003-delivery-automation (~40 authored lines)
  - **Completion evidence**: Pending

- [ ] T013 Release preparation: coherent version bump (preset 0.8.0, linear 0.11.0, code-review 0.3.0, bundles)
  - **Traces**: plan Rollout; outcome: `scripts/release/publish.sh --bump` produces manifests, bundle pins, conformance pin, and changelog entries; publication itself stays human
  - **Depends on**: T012
  - **Boundaries**: manifests, changelogs, `versions.lock.yml` pins; no behavior changes
  - **Evidence**: `bash scripts/conformance/bundles.sh` green on the bumped tree; `git diff --check` clean
  - **Delivery**: single PR into 003-delivery-automation (generated bump; mechanical)
  - **Completion evidence**: Pending

- [ ] T014 Transversal verification: SC-001…SC-006 evidence on the integrated feature branch
  - **Traces**: SC-001..SC-006; outcome: consolidated evidence — silent committed phases (this delivery's transcript/git log), TDS states with no human push, gate opened by implement, parser/findings first-try passes (0.11.0 suites), trunk resolution exercised; installed linear upgraded to 0.11.0 when its release is published
  - **Depends on**: T013; needs the task chain merged by a human and, for the upgrade check, the published 0.11.0 release
  - **Boundaries**: evidence recording in this file and `docs/dogfooding.md`; no source changes
  - **Evidence**: each SC's command or artifact recorded in Completion evidence
  - **Delivery**: single PR into 003-delivery-automation (evidence only)
  - **Completion evidence**: Pending

## Dependencies

```text
T001 (setup, independent)
T002 (US1, independent)
T003 → T004 → T005 (implement-append chain)
T006 → T007 → T008 (diagnosis chain)
T009 → T010 → T011 → T015 (tools chain)
T012 → T013 → T014 (closing chain, after all above)
```

One task in flight: delivery follows file order (T001…T011, T015,
T012…T014); chains above state which earlier task each one stacks on when
unmerged.

## Implementation strategy

**MVP**: T002 — the daily surface every developer touches (US1). Each
later phase lands an independently testable story; T014 closes the
feature only after human merges, per the loop's contract.
