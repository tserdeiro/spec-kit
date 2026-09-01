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

- [x] T002 Phase-close append: silence optional hooks and commit feature artifacts in presets/default
  - **Traces**: FR-001, FR-002, SC-001; outcome: new `commands/phase-close-append.md` registered (append) for `speckit.specify`, `speckit.plan`, `speckit.analyze`; same rule folded into `tasks-append.md`; optional hooks never announced (enabled→execute silently), each phase ends committing `specs/<feature>/` only, skipping when clean
  - **Depends on**: T001 (loop tooling — recorded during delivery; upstream resolves one append layer per command per preset, so the tasks rule was folded, not double-registered)
  - **Boundaries**: `presets/default/commands/`, `presets/default/preset.yml`, `presets/default/README.md`; core templates untouched (C-001)
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; append text present in regenerated skills; this feature's later phases run silent and committed
  - **Delivery**: single PR into 003-delivery-automation (~80 authored lines)
  - **Completion evidence**: PR #45 (ready 2026-08-31, stacked on #44); bundles conformance ok; phase-close section verified at EOF of the four regenerated skills; self-review no-blocking-findings (session 94c69ba1)

## Phase 3: User Story 2 — Linear mirrors the unattended run (P2)

**Goal**: the loop itself reconciles Linear and reviews with a fresh context.
**Independent test**: drive one task; its issue moves with no human push; findings live in their session.

- [x] T003 Loop reconciliation: `push --hook` at loop start and after each transition in implement-append.md
  - **Traces**: FR-004, SC-002; outcome: loop step 0 and the transitions it causes (task branch created, PR ready) invoke `speckit.linear.push --hook`; unconfigured repos no-op silently; failures report once and never block delivery
  - **Depends on**: none
  - **Boundaries**: `presets/default/commands/implement-append.md` only; no lifecycle hook registrations (plan Alternatives)
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; during this feature's own loop, TDS issues read In Progress/In Review with no human push
  - **Delivery**: single PR into 003-delivery-automation (~40 authored lines)
  - **Completion evidence**: PR #46 (ready 2026-08-31, stacked on #45); +16 net lines at three insertion points; bundles conformance ok; vendored push.md corroborates the --hook contract; self-review no-blocking-findings (session b0165575)

- [x] T004 Fresh-context self-review in the loop (implement-append.md)
  - **Traces**: FR-011, US2.4; outcome: the loop delegates packet reading and findings to a fresh sub-agent (hosts without sub-agents run it themselves), findings written inside the review session directory, never reused
  - **Depends on**: T003
  - **Boundaries**: `presets/default/commands/implement-append.md`; enforcement half lands in T010
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; this loop's own reviews delegate and write per-session findings
  - **Delivery**: single PR into 003-delivery-automation (~30 authored lines)
  - **Completion evidence**: PR #47 (ready 2026-08-31, stacked on #46); the rule was dogfooded on itself — a fresh sub-agent reviewed this PR, found 2 minor findings (bare code-review invocation opens no session; "candidate context" could smuggle residue), both fixed in-branch before ready; verdict no-blocking-findings (session 3d6f1348, per-session findings)

## Phase 4: User Story 3 — One command to implement (P3)

**Goal**: `implement` verifies/opens the feature gate itself.
**Independent test**: run implement with no feature PR; the draft gate opens, then T-first starts.

- [x] T005 Loop step 0: verify or open the draft feature PR in implement-append.md
  - **Traces**: FR-003, SC-005; outcome: before the first task the loop checks the feature branch's PR and, when missing, executes the `speckit.pr` feature-variant routine (idempotent; existing PR reported, never duplicated)
  - **Depends on**: T004
  - **Boundaries**: `presets/default/commands/implement-append.md`; `pr.md` stays the routine's single owner
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; loop text names the gate as step 0 and delegates to `speckit.pr`
  - **Delivery**: single PR into 003-delivery-automation (~30 authored lines)
  - **Completion evidence**: PR #48 (ready 2026-08-31, stacked on #47); fresh review found 3 minor + 1 info (closed gate accepted, optional URL report, two stale cross-references) — the three minors fixed in-branch; verdict no-blocking-findings (session 6044f70f)

## Phase 5: User Story 4 — Setup diagnoses itself (P4)

**Goal**: gaps name their remediation; native coverage stated honestly.
**Independent test**: unlink/misconfigure a fixture repo; read the named fixes.

- [x] T006 Unlinked-repo guard in spec-kit-linear: name `onboard`, never a raw API error
  - **Traces**: FR-005, SC-003; outcome: `push` and `status` short-circuit before any network call when root `speckit-linear.yml` is missing or still placeholder, with a `configuration` diagnostic naming `onboard`; credential failures keep naming their source
  - **Depends on**: none
  - **Boundaries**: `packages/spec-kit-linear/src/spec_kit_linear/{cli,config}.py`, tests; no behavior change for linked repos
  - **Evidence**: `uv run --project packages/spec-kit-linear pytest` green incl. new guard cases; fixture run shows the onboard message
  - **Delivery**: single PR into 003-delivery-automation (~80 authored lines)
  - **Completion evidence**: PR #49 (ready 2026-08-31, stacked on #48); 408 tests green (+10), placeholder guard pre-network proven without client patch, hook no-op preserved, hermetic conformance passed; fresh review 1 info + 1 nit — nit's false test comment fixed in-branch, info recorded as accepted scope (guard scans section values, not only *_id keys; unreachable edge, simplicity kept); verdict no-blocking-findings (session 5b2166bf)

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

- [ ] T009 Tasks parser ignores fenced blocks in spec-kit-linear
  - **Traces**: FR-008, SC-004; outcome: ``` and ~~~ fences skipped for title/phase/task matching; the tasks template's instructive section parses without manual deletion; existing files parse identically
  - **Depends on**: none
  - **Boundaries**: `packages/spec-kit-linear/src/spec_kit_linear/parser.py`, tests (template-section fixture)
  - **Evidence**: `uv run --project packages/spec-kit-linear pytest` green incl. fixture built from `presets/default/templates/tasks-template.md`
  - **Delivery**: single PR into 003-delivery-automation (~60 authored lines)
  - **Completion evidence**: Pending

- [ ] T010 Findings format: correct the docs and bind the findings path to its session (spec-kit-code-review)
  - **Traces**: FR-009, FR-011, SC-004; outcome: `commands/code-review.md` + README show `{"findings": [...]}` exactly as validated; `--findings` outside the session directory it closes is a usage error with a message naming the expected location
  - **Depends on**: T009
  - **Boundaries**: `packages/spec-kit-code-review/{commands/code-review.md,README.md}`, `src/spec_kit_code_review/cli.py`, tests; validator schema unchanged
  - **Evidence**: `uv run --project packages/spec-kit-code-review pytest` green incl. path-bind cases; doc example passes the validator verbatim
  - **Delivery**: single PR into 003-delivery-automation (~70 authored lines)
  - **Completion evidence**: Pending

- [ ] T011 Trunk resolution: `trunk:` key read by pr.md and implement-append.md
  - **Traces**: FR-010, SC-006; outcome: delivery base resolves `trunk:` in `.specify/extensions/git/git-config.yml` → else GitHub default; documented in preset README and root README; this repo's own instance sets `trunk: main`
  - **Depends on**: T010
  - **Boundaries**: `presets/default/commands/{pr.md,implement-append.md}`, `presets/default/README.md`, root `README.md`, this repo's `.specify/extensions/git/git-config.yml` (consumer instance; template untouched, C-001)
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; resolution order stated in both commands; a temporary-repo fixture with `trunk:` ≠ GitHub default exercises the resolution (SC-006 — this repo's own trunk equals its default, so the key here is only the documented example)
  - **Delivery**: single PR into 003-delivery-automation (~50 authored lines)
  - **Completion evidence**: Pending

## Phase 7: Polish and release

**Purpose**: coherent versions, plan extended, transversal evidence.

- [ ] T012 Extend docs/plan.md with this round and groom docs/dogfooding.md
  - **Traces**: A-004, A-001; outcome: `docs/plan.md` gains the delivered-round entry for this feature; `docs/dogfooding.md` entries met during delivery are appended and the graduated ones marked
  - **Depends on**: T011
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
T009 → T010 → T011 (tools chain)
T012 → T013 → T014 (closing chain, after all above)
```

One task in flight: the delivery order is T001…T014 as numbered; chains
above only state which earlier task each one stacks on when unmerged.

## Implementation strategy

**MVP**: T002 — the daily surface every developer touches (US1). Each
later phase lands an independently testable story; T014 closes the
feature only after human merges, per the loop's contract.
