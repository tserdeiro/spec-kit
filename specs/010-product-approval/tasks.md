# Tasks: Publish after product approval

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: T001 after the current product handoff gates are satisfied.

## Delivery strategy

- `010-product-approval` integrates the feature. The authorized product close opens
  its draft PR to `main`; technical review and native Linear assignments remain
  human prerequisites. This ledger specifies future approval behavior, while its
  own publication follows the currently installed contract.
- One task branch and one draft PR per task: `010-T###-short-slug`. Deliver one
  task at a time, stack on the previous ready open task PR, otherwise the feature
  branch. Dependencies document order; the native task-base routine chooses bases.
- Each task forecasts its complete authored executable diff below 400 lines,
  including tests and conformance. Keep permanent IDs; check tasks and record
  evidence in their final task commits. Final review and merges remain human.
- MVP: T001–T004 deliver local refinement, approved repeatable publication, and
  enforced consumption. T005–T006 complete installation and acceptance evidence.

## Phase 1: User Story 1 - Refine a local draft (P1)

**Goal**: All five product phases keep drafts local and provide a usable approved close.
**Independent evidence**: Rendered phase/hook matrix plus an approval/no-approval
scenario proves the new command precedence; live evidence follows in T006.

- [ ] T001 [US1] Deliver coordinated local refinement and approved close in presets/default/commands/phase-close-append.md
  - **Traces**: FR-001, FR-002, FR-003, FR-005, FR-007, FR-010, C-001, C-002, C-004, SC-001, SC-005; outcome: product phases preserve drafts until a human approves concrete analyzed artifacts, then the existing feature PR path can publish them.
  - **Depends on**: none
  - **Boundaries**: Update `presets/default/commands/{phase-close-append,tasks,pr}.md`, `preset.yml`, and `templates/{plan-template,tasks-template}.md`; add `presets/default/tests/test_product_commands.py`. Deliver plan D1 and the initial D2 close together: preserve the mirror marker, register clarify, suppress phase Git commits/hooks for every eligibility combination, retain mandatory Linear hooks, scope approved commits including unrelated staged-file protection, and make analysis read-only before separate approved closure. Move stable-ID timing to approved publication. Keep the current CLI and upstream/Git payload untouched. Required PR idempotency/error paths are completed and exercised in T002.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_product_commands.py presets/default/tests/test_skill_mirror.py -q` -> all five phases use one approval boundary, enabled optional/mandatory commit hooks cannot override it, Linear hooks remain, templates agree, and scoped closure preserves unrelated staged content. Rendered-command evidence is identified as such.
  - **Delivery**: single PR (~300 authored lines)
  - **Completion evidence**: Pending

## Phase 2: User Story 2 - Publish the approved handoff once (P1)

**Goal**: Retry approved publication without duplicate resources or invented readiness.
**Independent evidence**: Existing/open/closed PR and interrupted publication cases
record the exact Git/GitHub/Linear operations and remaining prerequisites.

- [ ] T002 [US2] Complete repeatable feature publication and handoff in presets/default/commands/pr.md
  - **Traces**: FR-002, FR-003, FR-004, FR-005, FR-007, FR-008, FR-009, C-002, C-003, SC-002, SC-003, SC-004; outcome: unchanged or interrupted closure reuses the feature PR and preserves honest readiness.
  - **Depends on**: T001
  - **Boundaries**: Refine `presets/default/commands/{pr,phase-close-append,tasks}.md` and `presets/default/tests/test_product_commands.py` for plan D2/D5. Observe existing head and PR before mutation, distinguish lookup failure from absence, skip unchanged commit/push/body updates, reuse only OPEN gates, and read back ambiguous writes before retry. Use the canonical body and body-file input. Require renewed approval for material changes, preserve normal task progress and stable IDs, and read the existing Linear preview/apply/status for synchronization and assignment. Keep Linear's assignment allowlist unchanged and technical approval distinct from publication permission.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_product_commands.py -q` -> command contract covers fresh approval, edits after approval, two unchanged retries, lost push/PR responses, closed gate, failed lookup, incomplete Linear and unassigned tasks; unchanged close requests zero duplicate writes. T006 demonstrates execution through an actual agent.
  - **Delivery**: single PR (~240 authored lines)
  - **Completion evidence**: Pending

## Phase 3: User Story 3 - Start from a coherent published gate (P1)

**Goal**: Implementation consumes verified publication before any task mutation.
**Independent evidence**: Real temporary Git histories and structured provider
fixtures demonstrate valid fresh-session start and rejected stale/missing gates.

- [ ] T003 [US3] Validate published product content before implement in presets/default/scripts/python/product_gate.py
  - **Traces**: FR-006, FR-007, FR-008, FR-009, C-001, C-003, C-004, SC-003, SC-004; outcome: a valid open gate permits continuation while unpublished product changes return product close pending.
  - **Depends on**: T002
  - **Boundaries**: Add `presets/default/scripts/python/product_gate.py`, register its script in `preset.yml`, and invoke it in `commands/implement.md` before hooks. Add `tests/test_product_gate.py` with existing `conftest.py` fixtures; reuse `_common.py` prerequisites, Git/gh wrappers, and fence helpers. Implement plan D3: exact repository/head/base/OPEN observation, fetch/OID verification, final PR reread, required artifact inventory, and remote/HEAD/index/worktree comparison. Normalize only real task checkbox/completion-evidence values and their indented continuations; preserve all product definitions. Remove automatic gate creation from implement and require plan D4/D5 handoff checks before task work.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_product_gate.py presets/default/tests/test_product_commands.py -q` -> valid gate/fresh session, missing/closed/merged/mismatched gate, failed fetch, dirty/staged/committed-unpublished scope, and legitimate completion-only progress pass their expected allow/stop outcomes. Every denial preserves branch, index, worktree, and remote write counts.
  - **Delivery**: single PR (~390 authored lines)
  - **Completion evidence**: Pending

- [ ] T004 [US3] Enforce the product gate at task entrypoints and verify adversarial drift in presets/default/scripts/python/task_base.py
  - **Traces**: FR-006, FR-007, FR-008, FR-009, C-002, C-004, SC-003, SC-004; outcome: direct task-start/publication helpers cannot bypass product consistency, and completion normalization cannot hide product edits.
  - **Depends on**: T003
  - **Boundaries**: Call the existing `product_gate.py` check before mutation in `task_base.py` refresh/task and `pr_create.py` task; update `tests/{test_task_base,test_pr_create,test_product_gate,conftest}.py`. Keep work-item behavior independent. Cover added/deleted artifacts, missing files, file-mode/symlink substitutions, index conflicts, moving head/base/state, stale remote refs, stacked completion progress, multiline evidence, task additions/renames, every immutable ledger field/forecast, fenced samples, and malformed blocks. Retain the existing task-base and PR-base rules after a valid gate; diagnostics specify product closure actions.
  - **Evidence**: `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_product_gate.py presets/default/tests/test_task_base.py presets/default/tests/test_pr_create.py -q` -> all invalid entrypoints stop before commit/checkout/branch/push/PR/Linear mutation; valid task and independent work-item paths retain their expected behavior.
  - **Delivery**: single PR (~360 authored lines)
  - **Completion evidence**: Pending

## Final phase: Cross-cutting verification

- [ ] T005 Verify native installation, mirror replacement, and gate execution in scripts/conformance/bundles.sh
  - **Traces**: FR-001, FR-003, FR-006, FR-007, FR-008, FR-010, C-001, C-004, SC-001, SC-003, SC-004, SC-005; outcome: consumers receive and execute the same approval policy and gate without source-checkout runtime dependencies.
  - **Depends on**: T004
  - **Boundaries**: Extend `scripts/conformance/bundles.sh`, `presets/default/tests/test_skill_mirror.py`, and `scripts/python/skill_mirror.py` only if existing replacement handling needs adjustment. Verify the new helper/support imports are installed; all five phase renders include one current policy; reinstall/mirror replaces the former commit append once; additional consumer-selected integrations remain supported. Execute installed gate/task helpers in isolated consumers with complete structured `gh` fixtures, including changed scope and valid fresh-session continuation. Keep generated assets unmodified in source and distinguish these fixtures from live execution.
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> installed consumers and rerender/retry scenarios pass; `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests -q` -> preset regressions pass; `git diff --check` -> clean.
  - **Delivery**: single PR (~300 authored lines)
  - **Completion evidence**: Pending

- [ ] T006 Align human approval policy and record actual command acceptance in docs/vision.md
  - **Traces**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, C-001, C-002, C-003, C-004, SC-001, SC-002, SC-003, SC-004, SC-005; outcome: policy and observed acceptance agree on the complete product handoff.
  - **Depends on**: T005
  - **Boundaries**: Update `AGENTS.md`, `.specify/memory/constitution.md`, `README.md`, and `docs/{vision,plan,dx,dogfooding}.md`, plus authored templates only for discovered wording gaps. Preserve required document languages and human merge authority; document constitution rationale/version/date, exact approval boundary, remaining native assignment step, and discovery separation. Run one bounded actual-agent workflow in a designated temporary consumer: all five phases before approval, approved closure, two unchanged retries, fresh-session implementation check, material product drift, and missing/closed gate failures. Use the host's available agent surface and authorized test resources; remove personal identity/credentials from evidence. If live execution or human approval/assignment is unavailable, record the precise unmet scenario and leave this task incomplete.
  - **Evidence**: Inspect the actual agent transcript and Git/provider operation logs: zero preapproval publication, one PR/Project/Issue-per-task after repeated close, no task mutation for rejected gates or pending handoff, and unchanged-scope continuation. Record test-resource links and sanitized counts in `docs/dogfooding.md`; `git diff --check` -> clean. Compare affected policy/command surfaces against FR-010 and report generated, synthetic, and actual-runtime evidence separately.
  - **Delivery**: single PR (~180 authored lines)
  - **Completion evidence**: Pending

## Dependencies and stack order

- **Critical path**: T001 → T002 → T003 → T004 → T005 → T006.
- **Stack order**: T001 PR → T002 PR → T003 PR → T004 PR → T005 PR → T006 PR,
  each based on the previous ready open PR, otherwise `010-product-approval`.
