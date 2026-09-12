# Implementation Plan: Publish after product approval

**Feature directory**: `specs/010-product-approval`
**Spec**: [spec.md](spec.md)

## Summary

Replace per-phase artifact commits with one approved product close through
`/speckit.pr`. Use the existing open feature PR as the publication record and
one small read-only guard before implementation mechanics. Keep Linear's current
projection and native assignment ownership. Research and design are consolidated
here, following the resolved preset template; no additional design files are needed.

## Technical context

- **Language/runtime**: Markdown/YAML composition; Python 3.11+ standard library.
- **Primary dependencies**: Existing Git, GitHub CLI, and pinned Specify 1.0.4
  (`versions.lock.yml`). `packages/spec-kit-linear/pyproject.toml` declares zero
  runtime dependencies and pytest 8+ for tests; reuse the preset's existing suite.
- **Storage/state**: Consumer feature directory, Git trees, feature PR, and
  native Linear Project/Issues. `.specify/feature.json` remains local selection.
- **Verification**: Temporary Git repositories, structured fake `gh`/Linear,
  pytest, installed bundle/mirror conformance, and a bounded live agent scenario.
- **Target environment**: Every upstream-selected integration; existing Python
  interpreter resolution and GitHub-hosted delivery.
- **Constraints**: Stable task IDs; one sequential task per PR; forecasts below
  400 authored executable lines; upstream assets and unrelated dirty work protected.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| Specify preset composition | 1.0.4 pinned | `presets/default/preset.yml`; installed `specify preset --help` |
| Git trees/index/worktree | 2.50.1 observed | [git diff](https://git-scm.com/docs/git-diff) |
| GitHub CLI PR state/body | 2.97.0 observed | [pr view](https://cli.github.com/manual/gh_pr_view), [pr edit](https://cli.github.com/manual/gh_pr_edit) |
| Linear projection/status | 0.13.0 source manifest | `packages/spec-kit-linear/commands/push.md`, `commands/status.md`, `src/spec_kit_linear/allowlist.py` |
| Preset ledger/fixtures | Current repository | `presets/default/scripts/python/_common.py`, `presets/default/tests/conftest.py` |

Official Git/GitHub references were checked on 2026-09-12. Use existing APIs and
verify any additional API against its official documentation before implementation.

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose a pinned upstream | PASS | PASS | Preset overrides only; installed core/Git payload stays unchanged. |
| II. Preserve the native surface | PASS | PASS | Existing product commands and PR routine; internal script only. |
| III. Consumer-selected integrations | PASS | PASS | Shared append/replacement and mirror; no agent registry fork. |
| IV. Durable repository truth | PASS | PASS | Published feature tree/PR; explicit selector; no chat-dependent registry. |
| V. Source/consumer boundaries | PASS | PASS | Consumer-local installed helper and artifacts; no source runtime path. |
| VI. Traceable delivery units | PASS | PASS | Tasks carry FR/C/SC traces, dependencies, boundaries, evidence, forecasts. |
| Delivery and safety constraints | PASS | PASS | Temporary fixtures, canonical PR, protected secrets, unchanged merge authority. |
| Human governance and handoff | PASS | PASS | Planned policy wording retains human approval and all four existing gates. |

The present commands retain their current approved operating contract until this
feature is implemented. Planning publication authorized in this task is distinct
from claiming this future behavior already exists. The constitution amendment
clarifies delegated mechanics, with rationale and version/date update under its
existing governance rules; it does not remove human authority.

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| Phase close, tasks, PR commands | Default preset | Local refinement; approved feature close; idempotent PR reuse | New product CLI or approval storage |
| Implementation and task entry scripts | Default preset | Read published gate before mutation | Resumption/merge/ready redesign |
| Product plan and ledger templates | Default preset | One approval boundary; IDs stable at approved publication | Assignment management in Git |
| Linear hooks/status | Linear extension | Preserve projection; read synchronization/assignment evidence | New fields or assignment writes in push |
| Vision, constitution, README, AGENTS | Project policy | Human decision, delegated mechanics, separate discovery | Upstream/Git payload patches |
| Generated skills and installed scripts | Native installer/mirror | Regenerate and validate from authored preset | Hand-edit generated files |

## Technical decisions

### D1. Compose one local-draft policy across all product phases

- **Decision**: Retain the exact `## Phase close (tserdeiro/spec-kit)` replacement
  marker in `commands/phase-close-append.md`. Register it for `clarify` as well as
  `specify`, `plan`, and `analyze`; adapt the authored `tasks` replacement. Explicitly
  suppress product-phase `git.commit` hooks, including mandatory/default-enabled
  configurations, and their end-of-phase commits. Preserve native branch creation
  and mandatory Linear hooks. Analysis itself remains read-only; its post-report
  approval/publication closure is a separately authorized action.
- **Rationale**: `skill_mirror.py` replaces the installed append by that heading;
  changing it could leave old commit instructions alongside new ones.
- **Trade-off**: This governs supported command execution, not arbitrary direct
  Git commands. Conformance must test rendered precedence and actual agent behavior.

### D2. Close through the existing feature PR routine

- **Decision**: After clean analysis, present exact artifacts and outstanding
  prerequisites. Consume explicit human product approval before the feature
  variant of `pr.md` commits/pushes. Scope commits with explicit feature paths;
  exclude unrelated staged content. Recheck the approved diff before mutation.
  Observe branch/head/PR before retries; skip unchanged commits and pushes, reuse
  an OPEN PR, and update its canonical body only when content differs. A failed
  lookup is not proof of absence. CLOSED/MERGED stops for a human decision.
- **Rationale**: Existing Git and PR publication is the durable handoff, without
  an approval flag, new command, hash registry, or independently mutable state.
- **Trade-off**: The human decision is enforced by the agent workflow; Git cannot
  prove that an out-of-band push received consent. A new session may consume an
  unchanged published handoff, but cannot invent approval for unpublished edits.

### D3. Compare product content against the observed feature PR

- **Decision**: Add `scripts/python/product_gate.py` with a reusable check and a
  native installed-script entrypoint: no arguments, exit 0 with gate URL/head on
  success; exit 2 with `product close pending` and a specific recovery action on
  missing, closed, mismatched, unreadable, or inconsistent evidence. Resolve the
  active feature through existing prerequisites and validate head branch, delivery
  base, repository, and OPEN state. Fetch the advertised head, compare its OID,
  and reread the PR after comparison to reject a concurrent head/base/state change.
- **Rationale**: An open PR alone misses unstaged, staged, and committed but
  unpublished product changes. Compare file inventories and content in the remote
  feature tree, local HEAD, index, and worktree, including new/deleted artifacts.
- **Trade-off**: Remote observation is required. Fetch may update object/ref caches;
  the guard never commits, checks out, creates branches, pushes, or writes remotely.

For `tasks.md`, normalize only real task checkbox markers and each task's
`Completion evidence` value, including correctly indented continuation lines.
Reuse the existing fence helpers. Preserve every other byte, file mode, and
field: IDs, descriptions, Traces, Depends on, Boundaries, Evidence, Delivery,
forecasts, task additions/removals, and fenced samples. Malformed/ambiguous blocks,
missing required artifacts, symlink substitution, and conflicted index entries
fail closed. Other feature files compare exactly. This permits published task
stacks to carry completion progress without accepting scope drift.

### D4. Consume the gate before all task-start mechanics

- **Decision**: In `implement.md`, validate D3 and existing handoff prerequisites
  before any `before_implement` hook, refresh, branch, or task work. Remove its
  missing-gate `/speckit.pr` fallback. Reuse D3 in `task_base.py` refresh/task and
  `pr_create.py` task paths before their mutations; work-item paths stay independent.
  Repeat at each new task boundary so later product drift is detected.
- **Rationale**: Placing the guard after the current hook dispatch permits a
  before-implement auto-commit to hide the unpublished artifact state.
- **Trade-off**: The helper proves publication consistency; command-level handoff
  checks additionally verify clean analysis, human technical approval, current
  Linear preview/apply results, and an assignee for each executable task through
  existing status output. Missing, disabled, or failed Linear evidence remains pending.

### D5. Preserve handoff and task identity ownership

- **Decision**: Keep mandatory after-plan/after-tasks projection. Before development,
  review/apply a fresh projection and verify every task's native assignment. Preserve
  the existing plan handoff table and canonical PR evidence, without recording personal
  identity or adding an approval database. Freeze IDs at first approved publication;
  later additions use the next unused ID and require renewed product approval.
- **Rationale**: Linear's mutation allowlist excludes assignment; `status` already
  reports it. Projection, approval, and assignment are separate existing responsibilities.
- **Trade-off**: An approved feature can be published while development remains
  pending for assignment/synchronization. Agents report that gap rather than fill it
  from an inferred assignee or treat a draft PR as technical approval by itself.

## Data and migration behavior

No new persisted schema. Update authored preset policy and project guidance;
regenerate consumer skills using native install/mirror. Existing published open
feature PRs remain the handoff record when their content is coherent. Unpublished
or modified artifacts use the same approval close; closed gates stay closed.
Task completion progress preserves approval; product changes replace the handoff
only after renewed approval and publication.

## Failure, retry, rollout, and rollback

- **Failure behavior**: Distinguish analysis/approval, publication, gate, Linear,
  and assignment failures. Stop before task mutation; preserve local artifacts.
- **Retry/idempotency**: Reread exact resources after uncertain responses. Resume
  missing operations only; unchanged closure has no Git/PR/Linear writes.
- **Rollout**: Deliver D1/D2 and required template wording together as one usable
  local-refinement/approved-close unit; add the consumer guard, entrypoint coverage,
  then installed/adversarial evidence and policy alignment. Release separately.
- **Rollback**: Stop handoff and restore the last reviewed preset through the
  normal release process; retain consumer artifacts and PR history.

## Security and privacy

Human approval authorizes only the presented scope; no model-generated approval
or remote content instructs a mutation. Use subprocess argument arrays, scoped
paths, existing authentication, and sanitized failures. Never persist credentials,
operator identity, or unrelated staged content in feature commits or PR bodies.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001–005, FR-007–010; SC-001/002/005 | Rendered commands, hook precedence, scoped/idempotent close, handoff contract | `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_product_commands.py presets/default/tests/test_skill_mirror.py -q` |
| FR-006–009; SC-003/004 | Real temporary Git, remote head consistency, all artifact states, ledger exceptions | `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_product_gate.py -q` |
| FR-006/009; SC-003/004 | Entry guard precedes mutation; work-item behavior preserved | `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests/test_task_base.py presets/default/tests/test_pr_create.py -q` |
| C-001–004; SC-005 | Native installed preset/mirror with structured fake provider calls | `bash scripts/conformance/bundles.sh` |
| FR-001–010; SC-001–005 | Actual agent phase sequence, explicit decision, repeated close, fresh-session start | Record bounded live scenario in `docs/dogfooding.md`, separately from fixtures |
| Regression and artifact integrity | Preset suite, whitespace, unchanged upstream baseline | `uv run --frozen --offline --project packages/spec-kit-linear pytest presets/default/tests -q`; `git diff --check` |

## Source layout

```text
presets/default/preset.yml
presets/default/commands/{phase-close-append,tasks,pr,implement}.md
presets/default/templates/{plan-template,tasks-template}.md
presets/default/scripts/python/{product_gate,task_base,pr_create,skill_mirror,_common}.py
presets/default/tests/{test_product_commands,test_product_gate,test_task_base,test_pr_create,test_skill_mirror,conftest}.py
scripts/conformance/bundles.sh
AGENTS.md
.specify/memory/constitution.md
README.md
docs/{vision,plan,dx,dogfooding}.md
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| New approval marker/digest service | Duplicates Git/PR state and adds another invalidation model. |
| Open gate existence alone | Admits unpublished scope and hooks that commit before validation. |
| Exact full ledger comparison | Blocks normal task completion and stacked development. |
| Patch upstream Git/core hooks | Violates pinned composition; authored command precedence is sufficient here. |

## Product handoff

`ready-for-development` requires all rows complete. This planning PR presents the
artifacts for human review; publication permission is not technical approval.
Evidence from this run is reported in the feature PR after analysis/synchronization.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | Final read-only report and coverage in the feature PR | See final PR evidence |
| Technical approval of plan and tasks | Human review of this concrete candidate | Pending |
| Reviewed Linear dry-run and synchronization | Authorized preview/apply and post-apply readback, reported in PR | See final PR evidence |
| Every executable task individually assignable and assigned | One Issue per permanent task ID; verify native assignees | Pending assignment |
