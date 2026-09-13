# Tasks: Native commit message validation

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- `011-native-commit-check` is the integration branch. The draft feature PR
  targets `main`; human review approves spec/plan before implementation, and
  human merge closes the feature after all tasks are complete.
- Create `011-T###-short-slug` before starting each task. Its PR targets the
  previous ready, open task PR, or the feature branch when none is open.
  Deliver one task at a time, in the chain below.
- Each task is one PR with its entire change/tests forecast below 400 authored
  lines. The existing 2× forecast stop remains in force. Record completion
  evidence and check the task in its final commit before ready for review.
- Linear projects observable state. Assignment and technical approval remain
  human gates; publication of this planning PR does not complete either gate.

## Phase 1: User Story 1 - Validate commits outside agent events (P1)

**Goal**: Give native Git the same subject decision as the guard through the
existing doctor installation path.
**Independent evidence**: Real commits in a temporary installed consumer accept
valid subjects and reject invalid editor/file subjects without creating commits.

- [x] T001 [US1] Share the subject rule and deliver the installed message-file validator in packages/spec-kit-code-review/src/spec_kit_code_review/commit_msg.py
  - **Traces**: FR-003, FR-004, FR-010, C-003, C-004, SC-001; outcome: guard and native entry point use one unchanged predicate, with explicit success/rejection/prerequisite results.
  - **Depends on**: none
  - **Boundaries**: Add `commit_policy.py`, `commit_msg.py`, `scripts/bash/commit-msg.sh`, and `tests/unit/test_commit_msg.py`; update `cli.py` and `test_guard.py` to share the predicate. Implement plan D2: one message-file argument, first-line extraction, UTF-8 replacement behavior, preserved file bytes, existing consumer interpreter resolution, and exit 0/1/4. Keep guard command extraction and unreadable-input behavior; the installed entry point directly imports the pure policy and avoids review setup. Handle missing/wrong interpreter and arguments with exact remediation.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_guard.py packages/spec-kit-code-review/tests/unit/test_commit_msg.py -q` -> shared corpus parity, multiline/CRLF/non-ASCII/empty subjects, paths with spaces, file preservation, missing runtime/input, and zero engine/network calls pass.
  - **Delivery**: single PR (~210 authored lines)
  - **Completion evidence**: PR #150; focused suite: 75 passed, 69 subtests passed; `git diff --check` clean; independent review of `6693072` returned `no-blocking-findings`; committed budget 259/400.

- [x] T002 [US1] Diagnose and install one native registration in packages/spec-kit-code-review/src/spec_kit_code_review/commit_hook.py
  - **Traces**: FR-001, FR-002, FR-005, FR-008, FR-009, FR-010, C-001, SC-002, SC-003; outcome: doctor observes Git's effective arrangement and repairs one safely owned entry idempotently.
  - **Depends on**: T001
  - **Boundaries**: Add `commit_hook.py` and `tests/unit/test_commit_hook.py`; replace the obsolete absence-is-healthy hooks logic in `doctor.py` and its `test_doctor.py` assertions. Implement D1/D3/D4 together: Git 2.54 capability, exact owned name/command/event, origin/scope and hook-path reads, shared-worktree payload checks, disabled/foreign/ambiguous classification, exclusive config lock, fresh snapshot comparison, Git-edited temporary content, atomic replacement and effective readback. Preserve unrelated config bytes/order/modes, consumer hook files, `core.hooksPath`, manager dispatchers, and the existing review Git minimum. Expose hooks findings and repair failures through the existing doctor reports even when other groups fail.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_doctor.py packages/spec-kit-code-review/tests/unit/test_commit_hook.py -q` -> missing/active/disabled/unverifiable states, older-Git upgrade action, first install, no-op retry, partial owned recovery, duplicate owned normalization, name/scope conflict, read-only preservation, lock/write failures and stale snapshot refusal pass. Real native behavior is verified in T003/T004; mocked capability alone is not acceptance.
  - **Delivery**: single PR (~380 authored lines)
  - **Completion evidence**: PR #156; full package: 996 passed, 635 subtests passed with Git 2.55 and explicit Git 2.54 native tests; `git diff --check` clean; independent PR review of `53c293b` returned `no-blocking-findings`; 693 authored lines under the user-authorized T002 exception of 700 (default stop: 400).

## Phase 2: User Story 2 - Preserve the consumer's hook workflow (P1)

**Goal**: Preserve Git and manager hook behavior across installation and retries.
**Independent evidence**: Existing hooks/managers retain content, arguments,
relative order and rejection effect, with one Spec Kit invocation per commit.

- [x] T003 [US2] Prove native hook composition and worktree safety in packages/spec-kit-code-review/tests/unit/test_commit_hook.py
  - **Traces**: FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, C-002, SC-001, SC-002, SC-003; outcome: real Git composition preserves previous hooks and refuses ambiguous ownership or disabled validation.
  - **Depends on**: T002
  - **Boundaries**: Extend `test_commit_hook.py` using existing temporary-repository helpers; keep required contract fixes in `commit_hook.py`/`doctor.py`. On real Git 2.54+ cover default/custom/absolute/relative hooks paths, spaces, linked worktrees with shared config and existing worktreeConfig, missing sibling payload, foreign-scope includes, duplicate manual invocation, symlink targets, and disabled entries. Exercise prior hooks that succeed, reject, or rewrite the message, preserving original bytes/modes and arguments and documenting actual native order. Add Git 2.55 per-event disabling evidence when that runtime is used. Record native bypass and later-rewrite limits explicitly.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_commit_hook.py -q` -> real-Git matrix passes; two repairs produce one validator call; previous rejection blocks a valid subject; unsafe cases preserve bytes/modes/configuration. Git below 2.54 yields a named unmet acceptance prerequisite, never a passing native test.
  - **Delivery**: single PR (~290 authored lines)
  - **Completion evidence**: PR #159; native Git 2.54/2.55 matrix: 22 passed; doctor/CLI regression: 15 passed; consumer module origin verified; `git diff --check` clean; independent review of `0b48311` returned `no-blocking-findings`; committed budget 273/400.

- [x] T004 [US2] Verify consumer installation and manager coexistence in packages/spec-kit-code-review/scripts/conformance/commit-msg.sh
  - **Traces**: FR-002, FR-003, FR-004, FR-006, FR-007, FR-008, C-003, C-004, SC-001, SC-002, SC-003, SC-004; outcome: independently installed payloads validate real commits while Husky and Lefthook continue running unchanged.
  - **Depends on**: T003
  - **Boundaries**: Add the package conformance script and extend the existing fixture in `scripts/conformance/review.sh` where the new doctor diagnosis changes expectations. Install through the native pinned Specify extension path in a disposable consumer. Use real Git 2.54+ and exact recorded Husky/Lefthook fixture versions, installed only in temporary test locations. Exercise native/plain, Husky, and Lefthook arrangements, editor/file messages, two fixes, prior manager rejection and one validator invocation. Verify installed paths, absent source references, no agent events, and no OCR/network calls during commits. Run the existing review regression with its engine/GitHub fixtures; describe those as synthetic. Keep package versions and release authority unchanged.
  - **Evidence**: `bash packages/spec-kit-code-review/scripts/conformance/commit-msg.sh` -> real installed Git/manager matrix passes with versions and execution counts recorded; `bash packages/spec-kit-code-review/scripts/conformance/review.sh` -> existing installed synthetic review passes; `git diff --check` -> clean. Missing Git/manager acceptance prerequisites return an explicit failure with install instructions, not a silent skip or success.
  - **Delivery**: single PR (~300 authored lines)
  - **Completion evidence**: PR #161; installed native matrix: six combinations passed (Git 2.54/2.55, plain/Husky 9.1.7/Lefthook 2.1.12), eight validator calls for eight attempts per consumer; installed synthetic review passed; prerequisite failure visible with exit 4; `git diff --check` clean; independent review of `fee0b13` returned `no-blocking-findings`; committed budget 312/400.

## Final phase: Cross-cutting verification

- [x] T005 Document the native repair and preserve doctor visibility in presets/default/commands/doctor.md
  - **Traces**: FR-001, FR-002, FR-009, FR-010, C-001, C-002, C-003, SC-003, SC-004; outcome: consumers can diagnose, enable, retry, and remove validation with truthful version, scope, and bypass expectations.
  - **Depends on**: T004
  - **Boundaries**: Update `packages/spec-kit-code-review/commands/doctor.md`, its `README.md`, the root Spanish `README.md`, and `presets/default/commands/doctor.md`. Replace claims that the extension installs no hooks or only installs OCR. Make the aggregate doctor's current prose retain native-hook errors instead of dropping them from its fixed category list; pass through the extension's exact remedy and `--fix`. Describe Git 2.54+, local/shared/worktree scope, payload requirements, preserved managers, installed/disabled/unverifiable states, rollback from D4, native bypasses and subsequent message rewriting. Keep the aggregator as the existing agent command. Record actual conformance and regression results in this task's completion evidence.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests -q` -> full package passes; `uv run --frozen --offline --project presets/default pytest presets/default/tests -q` -> preset regressions pass; installed conformance from T004 passes; review generated doctor guidance for preserved exact native-hook diagnostics; `git diff --check` -> clean. Report generated guidance separately from live agent execution.
  - **Delivery**: single PR (~190 authored lines)
  - **Completion evidence**: PR #163; full package: 1007 passed, 635 subtests passed with native Git 2.54/2.55; preset: 71 passed; installed native/synthetic conformance passed in T004; final installed guidance readback matched source (preset SHA256 `11fa0cafe7c37749537315e03b9cc9a248e54458310d4253be54de6f47a55582`), not live agent execution; `git diff --check` clean; fresh independent review of `d538fae` returned `no-blocking-findings`; its sole outdated-ledger-hash finding is corrected here; executable budget 0/380.

## Dependencies and stack order

- **Critical path**: T001 → T002 → T003 → T004 → T005.
- **Stack order**: T001 PR → T002 PR → T003 PR → T004 PR → T005 PR;
  merge root-first into `011-native-commit-check` after human review.
- **MVP**: T001–T005 together: native enforcement, safe composition, consumer
  evidence, and actionable doctor guidance form one bounded feature.

## Phase 3: Convergence

Astra's independent review of `16a7952` identified the six partial gaps below.
They extend the open stack after T005, one task per PR. Keep the original
implementation and its evidence; human review and root-first merges remain
pending. Each task preserves consumer configuration and upstream assets.

- [ ] T006 Revalidate the selected configuration immediately before replacement per FR-009 and SC-003 (partial)
  - **Traces**: FR-009, SC-003, plan D4; outcome: direct edits during temporary configuration preparation are preserved and reported as stale observations.
  - **Depends on**: T005
  - **Boundaries**: Update `packages/spec-kit-code-review/src/spec_kit_code_review/commit_hook.py` and `tests/unit/test_commit_hook.py`; compare the selected destination and effective observation again immediately before replacement, refuse detected changes, and preserve bytes/mode. Keep Git's native exclusive lock. Document the distinction between cooperative Git writers and external writers ignoring that lock in package doctor guidance/README; describe restoration attempts truthfully without promising an impossible atomic compare-and-swap against arbitrary writers.
  - **Evidence**: Focused hook tests on real Git 2.54/2.55 reproduce a direct edit after temporary preparation, confirm it survives, and retain first-install/idempotency/readback behavior; `git diff --check` passes.
  - **Delivery**: single PR (~150 authored lines)
  - **Completion evidence**: Pending

- [ ] T007 Detect manual validator invocation behind the Husky dispatcher per FR-007 and FR-008 (partial)
  - **Traces**: FR-006, FR-007, FR-008, FR-009, SC-002, SC-003; outcome: an existing Husky user hook invoking the validator is diagnosed before another registration is added.
  - **Depends on**: T006
  - **Boundaries**: Update `packages/spec-kit-code-review/src/spec_kit_code_review/commit_hook.py`, its hook tests, and the installed `scripts/conformance/commit-msg.sh` where needed. Inspect the effective Husky hook source behind its unchanged dispatcher without executing it or introducing a manager adapter/dependency. Preserve ordinary Husky/Lefthook composition and diagnose duplicate or unreadable effective invocation sources with a concrete manual action.
  - **Evidence**: Real Git/Husky 9.1.7 fixture with a manual installed-validator call refuses repair without modifying config/dispatcher/user hook; one existing invocation remains. Ordinary installed-manager matrix still passes; `git diff --check` passes.
  - **Delivery**: single PR (~160 authored lines)
  - **Completion evidence**: Pending

- [ ] T008 Validate hook composition in every affected shared worktree per FR-005 and FR-008 (partial)
  - **Traces**: FR-005, FR-008, FR-009, SC-002, SC-003; outcome: a shared registration is refused when a sibling checkout already invokes the validator through its own hook arrangement.
  - **Depends on**: T007
  - **Boundaries**: Update `packages/spec-kit-code-review/src/spec_kit_code_review/commit_hook.py` and `tests/unit/test_commit_hook.py`; extend existing shared-worktree observation beyond payload presence to each affected checkout's effective hook arrangement. Report the unsafe sibling and preserve configuration. Keep worktree-local installation isolated and reuse the existing read-only observation mechanism.
  - **Evidence**: Real linked-worktree fixture with relative `core.hooksPath` and a sibling manual invocation preserves all bytes and refuses duplicate registration; safe shared and worktree-local fixtures retain exactly one invocation; `git diff --check` passes.
  - **Delivery**: single PR (~130 authored lines)
  - **Completion evidence**: Pending

- [ ] T009 Preserve Git 2.55 explicit event resets per FR-009 and FR-010 (partial)
  - **Traces**: FR-009, FR-010, SC-003, plan D3; outcome: an explicitly cleared native hook event list remains disabled until the consumer changes it.
  - **Depends on**: T008
  - **Boundaries**: Update `packages/spec-kit-code-review/src/spec_kit_code_review/commit_hook.py` and `tests/unit/test_commit_hook.py`; respect Git 2.55 empty-event reset semantics, diagnose the effective disabled state and origin, and preserve configuration on `doctor --fix`. Retain recognized accidental partial-entry recovery and Git 2.54 support.
  - **Evidence**: Real Git 2.55 fixtures with explicit empty event values remain byte-identical after repair, emit a concrete manual remedy, and execute no reactivated validator; existing partial-entry/idempotency tests pass; `git diff --check` passes.
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending

- [ ] T010 Report unreadable installed validator modules as prerequisite failures per FR-010 (partial)
  - **Traces**: FR-010, C-004, plan D2; outcome: an unreadable installed module rejects the commit with exit 4 and an exact recovery action instead of a traceback.
  - **Depends on**: T009
  - **Boundaries**: Update `packages/spec-kit-code-review/scripts/bash/commit-msg.sh` and `tests/unit/test_commit_msg.py`; check the required readable payload consistently before importing it. Preserve the shared predicate, installed interpreter selection, read-only message behavior, and zero review/network initialization.
  - **Evidence**: Installed payload fixture with unreadable validator/policy module returns 4 with reinstall/repair guidance and no traceback; valid/invalid subject and missing-runtime tests pass; `git diff --check` passes.
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending

- [ ] T011 Report native hook order and message-rewrite limits in doctor diagnostics per FR-001 and plan D3 (partial)
  - **Traces**: FR-001, FR-006, C-002, plan D3; outcome: the doctor itself explains named-before-traditional ordering and later-message rewriting limits.
  - **Depends on**: T010
  - **Boundaries**: Update `packages/spec-kit-code-review/src/spec_kit_code_review/commit_hook.py` and focused doctor/hook tests. Emit concise informational diagnostics alongside state/path/scope with no consumer-hook execution; preserve aggregate guidance's passthrough behavior. Record complete package/preset and installed conformance results for the composed corrections.
  - **Evidence**: Doctor output includes order and bypass/rewrite limitations on an installed arrangement; package and preset suites, real installed Git/manager matrix, synthetic installed review, and `git diff --check` pass. Independent Astra review rechecks the final composed candidate.
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending
