# Tasks: Correct review finding categories

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: T001; human approval and assignment to supervised Luna agents
were given on 2026-09-12.

## Delivery strategy

- Use `008-review-findings` as the integration branch. Every task has one branch
  `008-T###-short-slug` and one draft PR; the next task stacks on the preceding
  ready, unmerged task PR, or on the feature branch when none is open. The
  feature reaches the configured delivery base through its feature PR.
- Work one task at a time in dependency order. Create the task branch from the
  resolved stack base before changing code. Complete its evidence and mark its
  PR ready before starting the next task; final review and merge remain human.
- Review each complete deliverable within 400 authored executable lines and the
  existing 2× forecast stop. Forecasts below include implementation, tests,
  fixture changes, and conformance. Record actual evidence before checking a task.
- Product approval, commits, remote synchronization, task assignment, and the
  feature PR retain their current authorization gates. The human decided on
  2026-09-12 to omit entry 03; this feature follows entry 02 directly.
- The smallest demonstrable slice is T001–T002. Completing this feature includes
  T003's adversarial checks and T004's installed-consumer evidence.

## Phase 1: User Story 1 - Use the accepted categories (P1)

**Goal**: Provide one accepted catalog and actionable category diagnostics.
**Independent evidence**: Packet/validator catalog equality and an invalid
submission that identifies its exact input position, value, and accepted choices.

- [x] T001 [US1] Share the category catalog and precise diagnostics in packages/spec-kit-code-review/src/spec_kit_code_review/findings.py
  - **Traces**: FR-001, FR-002, SC-001; outcome: generated review guidance and validation agree, and category errors are actionable in human and JSON output.
  - **Depends on**: none
  - **Boundaries**: Update `findings.py`, packet rendering in `packet.py`, diagnostic context in `cli.py`, and `test_findings.py`, `test_packet.py`, `test_phase_two.py`, `test_golden_packet.py` with affected packet fixtures. Follow plan D1: reuse `CATEGORIES`, avoid the import cycle through a renderer-local import, report one-based indices and missing/non-string values, and retain strict schema errors. Protect the shared error schema and native review invocation. T002 supplies the preserved-original path once that evidence exists.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_findings.py packages/spec-kit-code-review/tests/unit/test_packet.py packages/spec-kit-code-review/tests/unit/test_golden_packet.py packages/spec-kit-code-review/tests/unit/test_phase_two.py -q` -> exact catalog equality, supported values, and indexed unknown/missing/non-string diagnostics pass; invalid findings leave the session open.
  - **Delivery**: single PR (~170 authored lines)
  - **Completion evidence**: PR #136; 160 focused tests and 47 subtests passed. Budget 96/340; diff check clean. Independent review of 9c37476 found no actionable defects: https://github.com/tserdeiro/spec-kit/pull/136#issuecomment-5646576167. All four CI checks passed on that implementation candidate; this final commit records completion only.

## Phase 2: User Story 2 - Correct a category without losing review work (P1)

**Goal**: Preserve original evidence and accept only valid category edits in the same session.
**Independent evidence**: Category rejection → reviewer correction → same-session
closure; unchanged original bytes and blocking severity; no repeated engine analysis.

- [x] T002 [US2] Deliver category-only recovery with durable evidence in packages/spec-kit-code-review/src/spec_kit_code_review/finding_corrections.py
  - **Traces**: FR-003, FR-004, FR-005, FR-006, FR-007, SC-002, SC-003, SC-004; outcome: a reviewer resubmits categories while the tool proves preservation, keeps the original, and records validation before closing.
  - **Depends on**: T001
  - **Boundaries**: Add `finding_corrections.py` and `tests/unit/test_finding_corrections.py`; wire `findings.py`, `cli.py`, and `session.py`, with focused cases in `test_phase_two.py`, `test_session.py`, and session goldens in `test_golden_review.py`/`tests/golden/`. Implement plan D2–D4 together: single-read bytes, fresh attempt identity, exclusive private original capture, atomic redacted records/session binding, type-sensitive comparison of all document fields, and distinct pending/rejected/validated outcomes. Validate category changes before normalized/generated findings; reject discard/truncation and any non-category change. Keep original directories across reopen, require fresh-format sessions, and preserve existing freshness, verdict, environment, and publication guards. Protect reviewer input from tool writes and raw evidence from rendered outputs.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_finding_corrections.py packages/spec-kit-code-review/tests/unit/test_phase_two.py packages/spec-kit-code-review/tests/unit/test_session.py packages/spec-kit-code-review/tests/unit/test_golden_review.py -q` -> exact original bytes, same-session correction, unchanged coverage/severity, duplicate retry, non-category rejection, discard/truncation rejection, evidence-write failure, and preserved blocking verdict pass; engine invocations do not increase on resubmission.
  - **Delivery**: single PR (~390 authored lines)
  - **Completion evidence**: PR #137; 144 focused tests and 46 subtests passed, plus 11 cases after the final record-detail adjustment. Budget 394/400; diff check clean. Independent review of 54ec4ff reported one unused variable, removed in 8b61878: https://github.com/tserdeiro/spec-kit/pull/137#issuecomment-5646805420. All four CI checks passed on the implementation candidate; this final commit records completion only.

- [ ] T003 [US2] Verify destructive edits and recovery boundaries in packages/spec-kit-code-review/tests/unit/test_finding_corrections.py
  - **Traces**: FR-004, FR-005, FR-006, FR-007, SC-003, SC-004; outcome: adversarial corrections and stale or damaged evidence cannot produce closure or publication, and reopening preserves history without reusing it.
  - **Depends on**: T002
  - **Boundaries**: Extend `test_finding_corrections.py`, `test_phase_two.py`, `test_session.py`, and same-head reopen cases in `test_cli.py`, using existing fixtures. Exercise multiple/partial categories, missing-vs-null, boolean-vs-number changes, duplicate object keys, valid-category edits, deletion/addition/reordering, optional fields, and coverage edits. Verify whitespace/key-order-only reformatting succeeds. Exercise candidate/configuration/packet/inventory drift, missing/tampered original or records, symlinks, pending writes, repeated digest retries, old-format sessions, and closed-session rejection; include `--publish` failure cases with zero GitHub writes. Verify valid corrections retain an inconclusive verdict for existing coverage/engine gaps. Any contract fix stays in T002's named runtime modules and follows D2–D4.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_finding_corrections.py packages/spec-kit-code-review/tests/unit/test_phase_two.py packages/spec-kit-code-review/tests/unit/test_session.py packages/spec-kit-code-review/tests/unit/test_cli.py -q` -> preservation/freshness matrix passes, invalid attempts leave the session open, history survives same-head reopen, and valid correction is distinguished from a conclusive review.
  - **Delivery**: single PR (~260 authored lines)
  - **Completion evidence**: Pending

## Final phase: Cross-cutting verification

- [ ] T004 Verify installed recovery and document the retry procedure in packages/spec-kit-code-review/scripts/conformance/review.sh
  - **Traces**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, SC-001, SC-002, SC-003, SC-004; outcome: an installed consumer completes a lossless correction with discoverable evidence and an exact retry procedure.
  - **Depends on**: T003
  - **Boundaries**: Extend the installed-consumer fixture in `scripts/conformance/review.sh`; update `commands/code-review.md`, package `README.md`, and affected packet guidance/goldens. Point static guidance to the generated catalog, show editing only invalid categories followed by the existing close command, and describe original/attempt evidence, explicit ambiguity diagnosis, and fresh-review recovery for substantive edits. Conformance exercises the installed launcher and generated guidance with valid reading receipts, original/corrected digests, a preserved blocker, a still-invalid attempt, unchanged engine-call count, and no GitHub writes. Preserve source-checkout Git state, upstream assets, package versions, and release authority.
  - **Evidence**: `bash packages/spec-kit-code-review/scripts/conformance/review.sh` -> installed rejection/correction/closure passes; `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests -q` -> package regressions pass; `git diff --check` -> clean. Record installed synthetic evidence separately from live agent execution.
  - **Delivery**: single PR (~240 authored lines)
  - **Completion evidence**: Pending

## Dependencies and stack order

- **Critical path**: T001 → T002 → T003 → T004.
- **Stack order**: T001 PR → T002 PR → T003 PR → T004 PR; each begins after its
  predecessor is ready for review. Delivery scripts resolve actual bases.
