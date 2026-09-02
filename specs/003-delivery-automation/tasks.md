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

- [x] T007 Platform checks in the preset doctor (doctor.md)
  - **Traces**: FR-006, SC-003; outcome: doctor additionally reports `deleteBranchOnMerge` and `mergeCommitAllowed` via read-only `gh repo view`, each with the exact setting to change; degrades to "cannot verify" without `gh`
  - **Depends on**: T006
  - **Boundaries**: `presets/default/commands/doctor.md` only; never mutates settings
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; doctor run in this repo names both settings' states
  - **Delivery**: single PR into 003-delivery-automation (~30 authored lines)
  - **Completion evidence**: PR #50 (ready 2026-09-01, stacked on #49); bundles conformance and `git diff --check` passed; both extension doctors completed; live read-only check reported `deleteBranchOnMerge=true` and `mergeCommitAllowed=true`; fresh review no-blocking-findings (session 5d2de1fa, per-session findings)

- [x] T008 Document native Linear automation coverage (spec-kit-linear README + root README note)
  - **Traces**: FR-007, US4.3; outcome: docs state PR automations are team-level, default rules cover every linked PR, target-branch rules are optional overrides, linking rides the PR-body magic word (branches carry no issue key), and `push` reconciles regardless
  - **Depends on**: T007
  - **Boundaries**: `packages/spec-kit-linear/README.md`, root `README.md` (Spanish consumer note); no code
  - **Evidence**: doc sections present; `git diff --check` clean
  - **Delivery**: single PR into 003-delivery-automation (~50 authored lines)
  - **Completion evidence**: PR #51 (ready 2026-09-01, stacked on #50); official Linear docs confirmed default Team rules cover every linked PR and target-branch rules are optional overrides; `git diff --check` passed; fresh review found one major factual error in the original required-rule premise, corrected in docs, plan, task, and PR body; final review no-blocking-findings (session e99eeaba, per-session findings)

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

- [x] T015 Wire runtime trunk resolution into feature delivery commands
  - **Traces**: FR-010, SC-006; outcome: feature PR and first-task refresh invoke T011's helper; task/work-item PR bases derive at runtime; all repository-derived branch names remain inert argv; behavior is documented and this repo sets `trunk: main`
  - **Depends on**: T011
  - **Boundaries**: `presets/default/commands/{pr.md,implement-append.md}` and `presets/default/templates/tasks-template.md`; preset/root READMEs; this repo's consumer `git-config.yml`; command conformance in `scripts/conformance/bundles.sh`; `spec.md`/`plan.md` clarifications
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; temporary consumers execute feature/task/work-item creation and first-task refresh with configured/fallback/metacharacter/failure cases
  - **Delivery**: single PR into 003-delivery-automation (≤400 authored executable lines), stacked on T011
  - **Completion evidence**: PR #56 (ready 2026-09-01, stacked on #55; replaces obsolete #54); feature PR and first-task refresh invoke T011's helper, task PRs and branch invariants use authoritative prerequisite JSON `BRANCH`, and work items query the GitHub default; installed command blocks passed configured/fallback/metacharacter/distinct-feature-state/wrong-branch/fetch-merge-push failure cases; generated tasks template and READMEs describe the delivery base; `bash scripts/conformance/bundles.sh`, syntax checks, and `git diff --check` passed; effective executable budget 195/400; fresh PR review no findings

## Phase 7: Polish and release

**Purpose**: coherent versions, plan extended, transversal evidence.

- [x] T012 Extend docs/plan.md with this round and groom docs/dogfooding.md
  - **Traces**: A-004, A-001; outcome: `docs/plan.md` gains the delivered-round entry for this feature; `docs/dogfooding.md` entries met during delivery are appended and the graduated ones marked
  - **Depends on**: T015
  - **Boundaries**: `docs/` only
  - **Evidence**: `git diff --check` clean; round entry cites the feature directory
  - **Delivery**: single PR into 003-delivery-automation (~40 authored lines)
  - **Completion evidence**: PR #57 (ready 2026-09-01, stacked on #56); `docs/plan.md` records the ready-but-unmerged round and separates T013 release preparation from human publication and consumer adoption; `docs/dogfooding.md` marks only PR-delivered work graduated and records open hook, tooling, split-stack, branch-identity, template, and worktree frictions; manual audit verified PR states/bases, Linear mappings, pins, and 368/195 budgets; `git diff --check` passed; fresh PR review no findings

- [x] T013 Release preparation: coherent version bump and publication hardening (preset 0.8.0, linear 0.11.0, code-review 0.3.0, bundles)
  - **Traces**: plan Rollout; outcome: `scripts/release/publish.sh --bump` produces manifests, bundle pins, package lock, and changelog entries; `--local-manifests` validates the pending composition while publication itself stays human
  - **Depends on**: T012
  - **Boundaries**: `scripts/release/publish.sh`, `scripts/release/build-release.sh`, `scripts/release/build-bundles.sh`, `scripts/conformance/bundles.sh`, manifests, changelogs, package lock, bundle pins, and conformance mode; public catalogs and `versions.lock.yml` stay on the published releases until publication can record real artifacts and digests; historical lock-hash verification is a future integrity check; no product behavior changes
  - **Evidence**: `publish.sh --bump` rolls back all touched paths when `uv lock` fails; retries always rebuild tagged extension artifacts and retain their digests even when releases already have assets; pre-remote publication preparation uses temporary artifacts, restores local commits, and removes only tags created by that invocation on failure; default conformance rejects manifest/catalog drift; tagged bundle builds read content from the tag and checksum only invocation outputs; `bash scripts/conformance/bundles.sh --local-manifests` and `scripts/release/test-publish-retry.sh` green on the bumped tree; `git diff --check` clean
  - **Delivery**: single PR into 003-delivery-automation (release preparation and publication hardening; 549 effective authored executable lines against a 700-line budget)
  - **Completion evidence**: PR #58 (draft; ready pending); commits `59493e6` and `e13d1f7`; preset 0.8.0, linear 0.11.0, code-review 0.3.0, bundle 0.14.0, and `uv.lock` updated; six `--local-manifests` conformance scenarios passed (product, developer, reviewer, coexist, update, and trunk); published mode rejected the expected catalog drift; Linear 410 tests and Code Review 786 tests passed; release fixtures passed; F001 was found and corrected; formal source review of candidate `e13d1f7` found no findings; GitHub 4/4 checks green. Formal review budget was 615/400, recorded as over budget; executable task budget remains 549/700. **Reverted by T016** (2026-09-02 review: over the 400-line budget, `publish.sh` published on any unrecognized flag, `main` red on merge, no branch guard); redone minimally as T019.

- [ ] T014 Transversal verification: SC-001…SC-006 evidence on the integrated feature branch
  - **Traces**: SC-001..SC-006; outcome: consolidated evidence — silent committed phases (this delivery's transcript/git log), TDS states with no human push, gate opened by implement, parser/findings first-try passes (0.11.0 suites), trunk resolution exercised; installed linear upgraded to 0.11.0 when its release is published
  - **Depends on**: T019; needs the task chain merged by a human and, for the upgrade check, the published 0.11.0 release
  - **Boundaries**: evidence recording in this file and `docs/dogfooding.md`; no source changes
  - **Evidence**: each SC's command or artifact recorded in Completion evidence
  - **Delivery**: single PR into 003-delivery-automation (evidence only)
  - **Completion evidence**: Pending

## Phase 8: Correction round (2026-09-02 review)

**Purpose**: revert what the review rejected as units, replace the
over-engineered trunk resolver, fix the findings bind, and redo release
preparation within budget. Nothing new in scope.

- [x] T016 Revert release preparation #58 (merge `827788b`) to restore the pre-release tree
  - **Traces**: plan Rollout, C-004; outcome: `git revert -m 1 827788b` on a task branch — manifests, pins, changelogs, `uv.lock`, release scripts, and CI back to the published 0.10.0 / 0.2.1 / 0.7.0 / 0.13.0 state; default `bundles.sh` green again
  - **Depends on**: none
  - **Boundaries**: the revert only, no new content
  - **Evidence**: `bash scripts/conformance/bundles.sh` → conformance passed; both package suites green; `git diff 1080a48 -- scripts/ bundles/ packages/*/extension.yml` empty
  - **Delivery**: single PR into 003-delivery-automation (mechanical revert)
  - **Completion evidence**: PR #59 (ready 2026-09-02); tree diff vs `1080a48` empty for every reverted path, only docs/specs kept at the feature-branch version; default `bundles.sh` conformance passed; linear 410 and code-review 786 tests green; fresh Sonnet review: 1 blocking (revert subject failed the `type(scope)` naming check) — commit reworded in-branch; session 1563f75b

- [ ] T017 Replace the trunk resolver with shell resolution and remove C-006 from the spec
  - **Traces**: FR-010, SC-006, C-001, C-004; outcome: `presets/default/scripts/resolve-delivery-base.py` deleted; `pr.md` and `implement-append.md` resolve the delivery base in three shell lines (`sed` of `^trunk:` in `.specify/extensions/git/git-config.yml` with quotes stripped → else `gh repo view --json defaultBranchRef` → `git check-ref-format --branch`); spec C-006 removed and the trunk edge case back to its original wording; plan D4 rewritten to the shell decision; preset and root README updated; `tasks-template.md` wording kept
  - **Depends on**: T016
  - **Boundaries**: `presets/default/{commands/pr.md,commands/implement-append.md,README.md,preset.yml,scripts/}`, root `README.md`, `spec.md` (C-006 and the trunk edge case only), `plan.md` (D4 only), regenerated skills
  - **Evidence**: `bash scripts/conformance/bundles.sh` green; a temporary repository with `trunk: dev` ≠ GitHub default resolves `dev`; no `.py` remains under `presets/default/`
  - **Delivery**: single PR into 003-delivery-automation (~40 authored lines, net negative)
  - **Completion evidence**: Pending

- [ ] T018 Fix the findings session bind in spec-kit-code-review: separate normalized output, exact-path bind, real doc-parity test
  - **Traces**: FR-009, FR-011; outcome: phase two writes its normalized document to its own filename, leaving `findings.json` as the agent's untouched input; `--findings` must equal `<session>/findings.json` (equality, not containment); the doc-parity test asserts every ```` ```json ```` fence of `commands/code-review.md` loads through `load_document`; `expanduser` failures are usage errors
  - **Depends on**: T017
  - **Boundaries**: `packages/spec-kit-code-review/src/spec_kit_code_review/cli.py`, tests and golden fixtures, `commands/code-review.md` and README where the filename appears; publication semantics untouched
  - **Evidence**: `uv run pytest packages/spec-kit-code-review/tests` green; negative tests: a sibling file inside the session is refused, the input bytes survive a close, `~nosuchuser` is a usage error
  - **Delivery**: single PR into 003-delivery-automation (~40 authored lines)
  - **Completion evidence**: Pending

- [ ] T019 Release preparation, minimal: coherent version bump and the publication guards (preset 0.8.0, linear 0.11.0, code-review 0.3.0, bundles 0.14.0)
  - **Traces**: plan Rollout; outcome: `publish.sh --bump` produces manifests, pins, changelogs, and `uv.lock` (rolling back when `uv lock` fails); `publish.sh` rejects unknown flags, requires `main` with `origin/main` as ancestor, and guards empty arrays for bash 3.2; `build-bundles.sh` builds from the tag; conformance validates local manifests by default with its cross-checks, and a `--published` mode (used by `publish.sh` after publication, and by CI on `main` only once catalogs match) asserts catalog parity; nothing else from #58
  - **Depends on**: T018
  - **Boundaries**: `scripts/release/publish.sh`, `scripts/release/build-bundles.sh`, `scripts/conformance/bundles.sh`, `.github/workflows/conformance.yml`, manifests, changelogs, pins, `uv.lock`; ≤ 400 authored lines — split, never extend the budget
  - **Evidence**: `bundles.sh` green by default on the bumped tree; `publish.sh --dryrun` exits 2; `publish.sh --dry-run` in a temporary clone; both suites green
  - **Delivery**: single PR into 003-delivery-automation (~100 authored lines + generated bump); human review before the first publication
  - **Completion evidence**: Pending

## Dependencies

```text
T001 (setup, independent)
T001 → T002 (phase-close chain)
T003 → T004 → T005 (implement-append chain)
T006 → T007 → T008 (diagnosis chain)
T009 → T010 → T011 → T015 (tools chain)
T012 → T013 (closing chain, T013 reverted by T016)
T016 → T017 → T018 → T019 → T014 (correction round, after all above)
```

One task in flight: delivery follows file order (T001…T011, T015,
T012, T013, T016…T019, T014); chains above state which earlier task each
one stacks on when unmerged.

## Implementation strategy

**MVP**: T002 — the daily surface every developer touches (US1). Each
later phase lands an independently testable story; T014 closes the
feature only after human merges, per the loop's contract.
