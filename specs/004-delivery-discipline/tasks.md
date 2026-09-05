---
description: "Dependency-ordered, traceable delivery units for feature implementation"
---

# Tasks: Delivery discipline

**Inputs**: [spec.md](spec.md), [plan.md](plan.md)
**Next work**: The first unchecked task is the next planned delivery unit.

## Delivery strategy

- **The feature branch (`004-delivery-discipline`) is the integration
  branch**: every task merges into it, and the feature enters the
  **delivery base** only once, through the feature PR, as a merge commit.
  The delivery base is the explicit non-empty `trunk:` value, or the
  GitHub default branch when `trunk:` is absent or empty.
- **Closing the product phase opens the gate**: with this file complete,
  commit the feature artifacts on the feature branch and open the
  **draft feature PR** (`004-delivery-discipline` → delivery base) —
  `/speckit.pr` on the feature branch does it with the canonical body.
  Reviewing it is how the team approves the spec and plan before
  implementation; the same PR, ready once every task is checked, later
  closes the feature.
- **One branch per task**, named `004-T###-short-slug`; its pull request
  opens as `draft` **against the feature branch** or, while the previous
  task's PR is ready and unmerged, against that task's branch.
- **One task in flight, one linear stack**: every task here depends on its
  predecessor, so each PR stacks on the previous one until a human merges
  root-first (plan D5, D8); the ledger on the last PR shows every task
  checked. Marking the current PR `ready for review` is what frees the
  developer to start the next task.
- **Starting a task means creating its branch first**: before touching any
  code for `T###`, run `git switch -c 004-T###-short-slug` from the
  up-to-date base — the branch is what projects the task to
  *In Progress*.
- A reviewed PR stays under ~400 authored executable lines and stops at
  twice its forecast (plan D9): the task returns to the human with a
  diagnosis instead of widening its budget in the PR.
- Task states project to Linear from observable reality: the checkbox, the
  task branch, and the PR's draft/ready/merged state.
- No task modifies `spec.md` (C-004); findings that change product intent
  return to the feature PR.

## Task block format

Every task is one resumable delivery unit. Replace all sample values. Use `[US#]` in user-story phases. No parallel markers: tasks are ordered by their dependencies alone.

```markdown
- [ ] T001 [US?] Deliver a concrete outcome in exact/path.ext
  - **Traces**: FR-001, SC-001; outcome: [observable result]
  - **Depends on**: none | T###
  - **Boundaries**: [files or system surfaces changed and protected]
  - **Evidence**: `[command]` -> [expected result or required review]
  - **Delivery**: single PR | stacked PR [N] on [T###'s PR]
  - **Completion evidence**: [filled in the task PR's final commit, before ready for review; the merge lands it on the feature branch]
```

## Phase 1: User Story 1 — One stack, carried by the loop, merged by a human (P1)

**Goal**: the loop adapts to the branch's tooling, keeps one linear stack, carries fixes itself, refuses a misnamed branch, and never merges.
**Independent evidence**: this round's own PR bases (`gh pr list --json headRefName,baseRefName`), the ledger on the last PR, zero agent merges.

- [x] T001 [US1] Loop tooling set, hook silence, and the standard reviewer brief in presets/default/commands/implement-append.md
  - **Traces**: FR-001, FR-009, FR-019, SC-008; outcome: step 0 fixes the run's tooling set from `.specify/extensions/{linear,code-review}` on the feature branch and reports it once; reconcile calls run only with `linear`; without `code-review` the fresh reviewer gets `gh pr diff <n>` and posts findings with `gh pr comment`; tasks never install or remove extensions; the reviewer brief is fixed text (verify claims, question the mechanism before edge cases, packets over 100 KB file by file, findings inside the session); optional hooks are never announced (plan D4, D10, D12)
  - **Depends on**: none
  - **Boundaries**: `presets/default/commands/implement-append.md`; regenerated `.agents/skills/speckit-implement/SKILL.md` and the append in `.claude/skills/speckit-implement/SKILL.md`; core templates untouched (C-001)
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed; `grep` of the installed implement skill shows the tooling-set, brief, and hook-silence rules; later transcripts of this round carry the tooling line and no hook announcement
  - **Delivery**: single PR (~70 authored lines)
  - **Completion evidence**: PR #65 (ready 2026-09-03, root of the stack, base `004-delivery-discipline`); +38 net lines in `implement-append.md`, both renders regenerated with byte-identical append tails; `bash scripts/conformance/bundles.sh` passed on the final candidate `7a8b462` (implementer run and orchestrator run); `git diff --check` clean; fresh Sonnet review (session `9712e67f`) found 2 minor + 1 info — F003 fixed in-branch (`7a8b462`: the degraded reviewer also gets `gh pr view <n>`), F001 accepted as-is (step 0 runs once per run), F002 informational (the rules file lands in T007); verdict no-blocking-findings

- [ ] T002 [US1] One linear stack: base selection in implement-append.md, stack-aware task base in presets/default/commands/pr.md, ledger rule in tasks-append.md
  - **Traces**: FR-003, SC-001; outcome: step 1 branches from the top of the open ready stack (open non-draft PRs with heads `004-T###-`, the head no other open task PR uses as base) or from the feature branch when none is open, naming it in `Stack:`; `pr.md`'s `task)` case resolves the same base (nearest open task head that is an ancestor of `HEAD`, else the feature branch) instead of always the feature branch; `Depends on` documents order, never the base (plan D5)
  - **Depends on**: T001
  - **Boundaries**: `presets/default/commands/{implement-append.md,pr.md,tasks-append.md}`, `presets/default/templates/tasks-template.md` (stack bullet; keep the phrases `bundles.sh` asserts), `presets/default/README.md`; a stacked-base scenario in `scripts/conformance/bundles.sh`; regenerated skills
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed including the stacked and unstacked task-base cases; `git diff --check` clean; from T003 on, this round's task PRs list their predecessor as base
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending

- [ ] T003 [US1] Fix propagation through the stack: `stack-propagate` block in presets/default/commands/implement-append.md
  - **Traces**: FR-002; outcome: after a commit on a task branch with open PRs stacked on it, each stacked branch receives `git merge --no-ff -m "merge(task): carry the T### fix into T###"` in stack order and is pushed; a conflict aborts the merge, stops the loop, and names the branch (plan D6)
  - **Depends on**: T002
  - **Boundaries**: `presets/default/commands/implement-append.md` (POSIX block with `# stack-propagate:start/end` markers); a propagation scenario against the fake `git`/`gh` shims in `scripts/conformance/bundles.sh`; regenerated skills
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed including propagation order and the conflict stop; `sh -n` on the extracted block
  - **Delivery**: single PR (~70 authored lines)
  - **Completion evidence**: Pending

- [ ] T004 [US1] Branch identity check in presets/default/commands/pr.md
  - **Traces**: FR-004; outcome: the `pr-create` block's `task)` case compares the branch's `T###` with the task the user named or the first unchecked task outside fenced blocks and exits 2 naming both on a mismatch, before `gh pr create` (plan D7)
  - **Depends on**: T003
  - **Boundaries**: `presets/default/commands/pr.md`; the mismatch and match cases in `scripts/conformance/bundles.sh`; regenerated skills
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed including exit 2 on a misnamed branch; the awk rule agrees with `parser.py` on the template's fenced example
  - **Delivery**: single PR (~50 authored lines)
  - **Completion evidence**: Pending

- [ ] T005 [US1] Closure rules: the loop never merges, root-first merging, on-request merge with worktree prune, and the revert path in implement-append.md and README.md
  - **Traces**: FR-005, FR-012, FR-013, SC-002; outcome: step 4 ends the run with every PR ready and its review closed; states root-first and why (retarget is an `edited` event); on an explicit human request runs `git worktree prune` then `gh pr merge <n> --merge --delete-branch` root-first; feature closure prunes before deleting; a "reverting a delivered task" paragraph fixes `git revert --no-commit` + `revert(scope): subject`; the README's golden rules carry rules 4 and 10 and the ruleset note (plan D8, A-006)
  - **Depends on**: T004
  - **Boundaries**: `presets/default/commands/implement-append.md`, `presets/default/README.md`, root `README.md` (Spanish); regenerated skills; no code
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed; `git diff --check` clean; the installed skill names the root-first rule, the request path, and the revert subject
  - **Delivery**: single PR (~80 authored lines)
  - **Completion evidence**: Pending

## Phase 2: User Story 2 — The task stops at its budget and the review questions complexity (P2)

**Goal**: tasks stop at twice their forecast; every agent's review reads the same principles.
**Independent evidence**: a diff past the stop line halts before a PR; `doctor --fix` writes the principles into an empty consumer.

- [ ] T006 [US2] Budget stop at twice the forecast in presets/default/commands/implement-append.md and the forecast rule in tasks-append.md
  - **Traces**: FR-006, SC-004; outcome: before `/speckit.pr`, a POSIX block measures added lines of `git diff --numstat <base>...HEAD` (written to a file, no pipeline) over the files the review budget counts, reads `~N authored lines` from the task's Delivery line (absent → 400), and stops at the smaller of `2 × N` and 400 with a diagnosis (what does not fit, proposed split); the forecast is never edited in the breaching PR; `tasks-append.md` requires the forecast form on every Delivery line (plan D9)
  - **Depends on**: T005
  - **Boundaries**: `presets/default/commands/{implement-append.md,tasks-append.md}`, `presets/default/README.md`; a budget-stop scenario in `scripts/conformance/bundles.sh`; regenerated skills
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed including a diff over the stop line exiting non-zero with the diagnosis; `sh -n` on the block
  - **Delivery**: single PR (~60 authored lines)
  - **Completion evidence**: Pending

- [ ] T007 [US2] Engineering principles in the base review rules: RULE_TEMPLATE in packages/spec-kit-code-review/src/spec_kit_code_review/doctor.py, this repository's .opencodereview/rule.json, and the AGENTS.md single source
  - **Traces**: FR-007, FR-008; outcome: `doctor --fix` writes a `**/*` rule stating the principles (simplest implementation, no compatibility layers, no speculative abstraction, reuse what is installed, question the mechanism before edge cases; over-engineering and speculative abstraction `major`, a new runtime dependency `blocking`); this repository commits the same file so its packets carry the rules; `AGENTS.md` gains the `docs/dogfooding.md` exception and `CLAUDE.md` becomes `@AGENTS.md` (plan D2, D14)
  - **Depends on**: T006
  - **Boundaries**: `doctor.py` (`RULE_TEMPLATE`), `tests/unit/test_doctor.py` (`FixTests`), `packages/spec-kit-code-review/{README.md,CHANGELOG.md}` (unreleased entry), `.opencodereview/rule.json`, `AGENTS.md`, `CLAUDE.md`; no version bump (T013)
  - **Evidence**: `uv run pytest packages/spec-kit-code-review/tests` -> green including the rewritten fix test; `diff <(python3 -c 'print(RULE_TEMPLATE)') .opencodereview/rule.json` -> identical content; `git diff --check` clean
  - **Delivery**: single PR (~60 authored lines)
  - **Completion evidence**: Pending

## Phase 3: User Story 3 — The product contract is protected deterministically (P3)

**Goal**: a task PR touching a protected path is blocked by the command itself.
**Independent evidence**: phase-two tests on a numeric-prefixed base versus a trunk base.

- [ ] T008 [US3] `protected_paths` deterministic finding in packages/spec-kit-code-review
  - **Traces**: FR-010, SC-003; outcome: `protected_paths` in `DEFAULT_CONFIG` (defaults `specs/*/spec.md`, `.specify/memory/constitution.md`), validated as a non-empty list of strings and mirrored in the config template; phase two injects one `blocking` / `contract` finding per touched protected path, anchored to the path's first changed hunk (base side for deletions), when the candidate's base branch has a final segment matching `^[0-9]+-`; trunk-based candidates and working-tree reviews unaffected; documented in `commands/code-review.md` and the README (plan D1)
  - **Depends on**: T007
  - **Boundaries**: `src/spec_kit_code_review/{config,cli}.py` (a small helper module is acceptable), `config/speckit-code-review.template.yml`, `commands/code-review.md`, `README.md`, `CHANGELOG.md` (unreleased entry), `tests/unit/` (phase-two and config cases); verdict values, publishing, and budget untouched; no version bump (T013)
  - **Evidence**: `uv run pytest packages/spec-kit-code-review/tests` -> green including: modified, added, and deleted protected path on a `004-…` base → blocking finding + `changes-requested`; the same diff on a `main` base → no generated finding; invalid `protected_paths` → configuration error
  - **Delivery**: single PR (~140 authored lines)
  - **Completion evidence**: Pending

## Phase 4: User Story 4 — Worktrees, reverts, and published assets stay verifiable (P4)

**Goal**: Linear works from a worktree; published digests are re-verified.
**Independent evidence**: a `git worktree add` fixture resolves the main checkout's files; `--published` fails on an altered digest.

- [ ] T009 [US4] Worktree-aware configuration and credentials resolution in packages/spec-kit-linear
  - **Traces**: FR-011, SC-007; outcome: `git_refs.main_worktree_root(root)` (parent of `git rev-parse --git-common-dir`, `None` in the main checkout); `resolve_config_path` and `load_dotenv_files` fall back to it when the worktree lacks the file and no explicit override is set; the doctor names the resolved env path; `persist_process_credential` unchanged (plan D3)
  - **Depends on**: T008
  - **Boundaries**: `src/spec_kit_linear/{git_refs,config,env_files,cli}.py`, `tests/unit/{test_config,test_env_files}.py` (real `git init` + `git worktree add` fixtures), `packages/spec-kit-linear/{README.md,CHANGELOG.md}` (unreleased entry); no version bump (T013)
  - **Evidence**: `uv run pytest packages/spec-kit-linear/tests` -> green including: worktree without files resolves the main checkout's config and env; worktree-local files win; main checkout unchanged; `bash packages/spec-kit-linear/scripts/conformance/installed-artifact.sh` -> passed
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending

- [ ] T015 [US4] Project at plan: `tasks.md` optional in the packages/spec-kit-linear parser and projection
  - **Traces**: FR-020, SC-010; outcome: `parse_feature` treats a missing `tasks.md` as an empty ledger with an info diagnostic `tasks_pending`; `push --hook` after plan creates the feature's Project with zero Issues and exits 0; `status` reports the Project and names the ledger as the next artifact; `spec.md` and `plan.md` stay required (plan D15)
  - **Depends on**: T009
  - **Boundaries**: `src/spec_kit_linear/{parser,cli}.py` (`reporting.py` only if the empty table needs the diagnostic), `tests/unit/{test_parser,test_cli}.py`, `packages/spec-kit-linear/{README.md,CHANGELOG.md}` (unreleased entry); hook registrations untouched; no version bump (T013)
  - **Evidence**: `uv run pytest packages/spec-kit-linear/tests` -> green including: a feature with spec and plan only projects one Project and no Issues; the hook path exits 0; a missing `plan.md` still fails with `artifact_missing`
  - **Delivery**: single PR (~70 authored lines)
  - **Completion evidence**: Pending

- [ ] T010 [US4] Published-asset digests in scripts/conformance/bundles.sh `--published`
  - **Traces**: FR-014, SC-005; outcome: for `linear` and `code-review` in `versions.lock.yml`, published mode downloads the catalog's release zip and compares it with `release_zip_sha256`, recomputes `subtree_archive_sha256` with `git archive --mtime="@<commit epoch>" --format=tar "<tag>:<path>"` and `manifest_sha256` with `git show <tag>:<path>/extension.yml`, failing with the asset and both digests on a mismatch and naming the fetch command when a tag is missing; default mode unchanged (plan D13)
  - **Depends on**: T015
  - **Boundaries**: `scripts/conformance/bundles.sh`; `README.md` "Integridad" line naming the re-verification; `scripts/release/*` untouched
  - **Evidence**: `bash scripts/conformance/bundles.sh --published` -> passed on the published tree (tags `spec-kit-linear/v0.11.0`, `spec-kit-code-review/v0.3.0`); the same run against a temporary copy of the lock with one altered digest -> fails naming the asset; `bash scripts/conformance/bundles.sh` -> passed
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending

## Phase 5: User Story 5 — A second agent installs cleanly (P5)

**Goal**: the doctor mirrors safely and ignores the installer's noise.
**Independent evidence**: `/speckit.doctor --fix` in this two-agent repository changes nothing but appends.

- [ ] T011 [US5] Doctor: safe skill mirror and ignore entries in presets/default/commands/doctor.md
  - **Traces**: FR-016, FR-018, SC-006, SC-009; outcome: step 5 copies extension and preset skills whole and, for the five core commands, keeps each integration's own render and appends the preset's registered `strategy: append` layers from `.specify/presets/<id>/` after three blank lines, idempotently, never copying a core skill across integrations; step 6 checks `.specify/extensions/.cache/`, `.specify/presets/.cache/`, `.specify/extensions/*/.venv/` with `git check-ignore -q`, reports the missing ones, and appends them to `.gitignore` with `--fix` (plan D11)
  - **Depends on**: T010
  - **Boundaries**: `presets/default/commands/doctor.md`, `presets/default/README.md`; a two-integration fixture in `scripts/conformance/bundles.sh` (core render keeps its frontmatter and gains the appends once; extension skills identical; ignore entries added once); regenerated skills
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> conformance passed including the mirror and ignore cases; `/speckit.doctor --fix` in this repository -> `.claude/skills` core renders unchanged except their appends, nothing left to mirror on a second run
  - **Delivery**: single PR (~90 authored lines)
  - **Completion evidence**: Pending

## Final phase: Cross-cutting verification

- [ ] T012 Documentation: rule 14 in presets/default/README.md, second agent and digest re-verification in README.md, the round in docs/plan.md, statuses in docs/dogfooding.md
  - **Traces**: FR-015, FR-017, A-001, A-005; outcome: the preset README states that every executable block is POSIX (`set -e`, no `pipefail`) and that conformance runs them with `sh`; the root README's second-agent steps are verified and its Integridad section names the published digest re-verification; `docs/plan.md` records this round; `docs/dogfooding.md` marks the delivered entries resolved (20 included) and records the frictions met during this round (plan D14)
  - **Depends on**: T011
  - **Boundaries**: `presets/default/README.md`, `README.md`, `docs/plan.md`, `docs/dogfooding.md`; no code
  - **Evidence**: `git diff --check` -> clean; the round entry cites `specs/004-delivery-discipline/`; every *ronda 004* entry carries its new status
  - **Delivery**: single PR (~80 authored lines)
  - **Completion evidence**: Pending

- [ ] T013 Release preparation: `publish.sh --bump preset=0.9.0 linear=0.12.0 code-review=0.4.0 bundles=0.15.0`
  - **Traces**: plan Rollout, A-007; outcome: manifests, bundle pins, changelog headings, and `uv.lock` bumped coherently by the script; publication stays human, from `main`, after the feature merges
  - **Depends on**: T012
  - **Boundaries**: the files `--bump` writes (`packages/*/extension.yml`, `packages/*/pyproject.toml`, `packages/*/CHANGELOG.md`, `presets/default/{preset.yml,README.md}`, `bundles/*/bundle.yml`, `uv.lock`); no script changes
  - **Evidence**: `bash scripts/conformance/bundles.sh` -> passed on the bumped tree; `uv run pytest packages/spec-kit-linear/tests` and `uv run pytest packages/spec-kit-code-review/tests` -> green; `bash scripts/conformance/bundles.sh --published` -> fails only with the expected parity lines before publication
  - **Delivery**: single PR (generated bump, ~20 authored lines)
  - **Completion evidence**: Pending

- [ ] T014 Transversal verification: SC-001…SC-010 evidence on the integrated feature branch in specs/004-delivery-discipline/tasks.md
  - **Traces**: SC-001..SC-010; outcome: consolidated evidence — one stack and complete ledger (SC-001), zero agent merges (SC-002), protected-path tests (SC-003), no task past its stop line and no in-PR forecast change (SC-004), published digests verified (SC-005), doctor mirror in this two-agent repository (SC-006), worktree tests (SC-007), silent implement transcripts (SC-008), ignore entries idempotent (SC-009), the Project born at plan on the next feature (SC-010); the consumer upgrade of this repository's installed extensions to 0.12.0 / 0.4.0 is a trunk chore after publication (FR-001), recorded here as evidence only
  - **Depends on**: T013; needs the task chain merged by a human and the published releases
  - **Boundaries**: evidence recording in this file and `docs/dogfooding.md`; no source changes; `.specify/extensions/**` untouched (the upgrade is a trunk chore)
  - **Evidence**: each SC's command or artifact recorded in Completion evidence
  - **Delivery**: single PR (evidence only)
  - **Completion evidence**: Pending

## Dependencies and stack order

- **Critical path**: T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008 -> T009 -> T015 -> T010 -> T011 -> T012 -> T013 -> T014 (file order; T015 was added at the gate and keeps the Linear identifiers stable)
- **Stack order**: PR 1 -> PR 2 -> … -> PR 15, each stacked on the previous one until a human merges root-first; the loop rules of US1 land first so every later task of this round runs under them

## Implementation strategy

**MVP**: T001–T005 — the loop rules the previous round paid for (US1). Each
later phase lands an independently testable story; T014 closes the
feature only after human merges and publication, per the loop's contract.
