# Implementation Plan: Delivery discipline

**Feature directory**: `specs/004-delivery-discipline`
**Spec**: [spec.md](spec.md)

## Summary

Make the loop disciplined by construction on the four surfaces this
repository owns: the `spec-kit-code-review` package (a deterministic
protected-path finding and the engineering principles in the base rules),
the `spec-kit-linear` package (worktree-aware configuration), the `default`
preset (one linear stack, fix propagation, branch identity, tooling
detection, budget stop, reviewer brief, never-merge closure, revert path,
doctor mirror and ignore entries, hook silence), and the conformance
scripts (published digests). Plus the documentation rules 4, 10 and 14.
No new commands, no upstream patches, no runtime dependencies.

## Technical context

- **Language/runtime**: preset commands are agent-executed Markdown with
  POSIX shell blocks (`set -e`, no `pipefail`; conformance runs them with
  `sh`); packages are Python ≥3.11, standard library only, `uv`-managed;
  conformance scripts are bash.
- **Primary dependencies**: pinned upstream `specify-cli` 1.0.1
  (`versions.lock.yml`); `gh` for PR and repository queries; `git`;
  `curl` only inside published-mode conformance. Nothing new.
- **Storage/state**: consumer configuration only — a `protected_paths`
  list in `speckit-code-review.yml` (committed, consumer-owned), the base
  `.opencodereview/rule.json` the doctor writes, and `.gitignore` entries
  the preset doctor adds. No new state files.
- **Verification**: package pytest suites (`uv run pytest
  packages/<package>/tests`), `bash scripts/conformance/bundles.sh`
  (default and `--published`), `git diff --check`, and this feature's own
  delivery as the dogfood evidence for SC-001, SC-002, SC-004, SC-008.
- **Target environment**: any upstream-supported agent; macOS and Linux
  shells (`sh` is `dash` on Ubuntu CI).
- **Constraints**: C-001 upstream assets untouched; C-002 surface frozen;
  C-005 release lag (this round's loop runs on linear 0.11.0 and
  code-review 0.3.0); 400-line budget per task with the 2× stop applied
  to this feature itself.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| specify-cli (upstream) | 1.0.1 | https://github.com/github/spec-kit |
| open-code-review rule file | v1.8.3 | https://github.com/alibaba/open-code-review |
| gh CLI (`pr list/view/merge`, `--jq`) | consumer-installed | https://cli.github.com/manual/ |
| git (`rev-parse --git-common-dir`, `worktree prune`, `archive`, `revert`) | ≥2.41 | https://git-scm.com/docs |

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose a pinned upstream | PASS | PASS | C-001: preset, packages, scripts and docs only; entries 18, 22–25 stay logged |
| II. Preserve the native surface | PASS | PASS | No new commands or flags; one configuration key; appends extend existing commands |
| III. Integrations consumer-selected | PASS | PASS | The mirror keeps every integration's own render (D11); generated-asset checks stay separate from runtime evidence |
| IV. Repository artifacts durable truth | PASS | PASS | Rules and protected paths are committed files; the ledger accumulates on one stack (D5) |
| V. Source and consumer boundaries | PASS | PASS | Package releases and preset text; consumer files touched only by the doctor's explicit `--fix` |
| VI. Traceable delivery units | PASS | PASS | Every task forecasts its lines; the 2× stop (D9) enforces the split rule this principle states |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| `packages/spec-kit-code-review` | this repo | `protected_paths` finding at phase two; principles in the base rule template | new verdict values; publishing changes; budget changes |
| `packages/spec-kit-linear` | this repo | config and env resolution fall back to the main checkout | writing into the main checkout; onboard changes |
| `presets/default` commands and README | this repo | loop steps 0–4, `pr.md` base and identity check, doctor steps 5–6 | patching core templates; new commands |
| `scripts/conformance/bundles.sh` | this repo | `--published` recomputes the lock digests | CI running published mode (stays in `publish.sh`) |
| `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/plan.md`, `docs/dogfooding.md` | this repo | rules 4, 10, 14; second agent; single source; round entry; statuses | translating documents; new sections beyond the rules |
| `.opencodereview/rule.json` (this repo) | this repo | committed base rules so this round's packets carry the principles | per-language rule sets |
| Upstream Git payload, core templates, `.specify/scripts` | upstream | none (C-001) | hook announcements at the root; `auto-commit.sh` staging |

## Technical decisions

### D1. Protected paths as a deterministic finding (code-review)

- **Decision**: a top-level `protected_paths` list in `DEFAULT_CONFIG`
  (`config.py:36-60`), default `["specs/*/spec.md",
  ".specify/memory/constitution.md"]`, validated in `_validate_effective`
  as a non-empty list of non-empty strings and mirrored in the shipped
  template. Phase two (`cli.py:1385-1395`) computes
  `Git.changed_paths(merge_base, head)` (`git.py:216`), matches each
  path with `fnmatch` against the globs, and — when the candidate's
  `base_branch` (`session.json["candidate"]["base_branch"]`,
  `candidate.py:35`) has a final path segment matching `^[0-9]+-` — adds
  one generated entry per touched path to the agent's entries before
  `normalize_findings`: `severity: blocking`, `category: contract`, a
  fixed title, content naming the path and the rule, anchored to the
  path's first changed hunk (`load_hunks`, `cli.py:1386`; a deleted path
  anchors on the base side the way `findings.py:434-541` already checks
  deleted lines). It then flows through validation, ordering, the verdict
  (`verdict.py:99`), the report, and the publication plan exactly like an
  agent finding. Working-tree reviews and trunk-based candidates are
  exempt by construction (no base, or a base without the numeric prefix).
- **Rationale**: FR-010 needs a check no prompt can skip; the base branch
  and the changed paths are already in the session; injecting before
  normalization reuses every existing guarantee and adds no second
  finding model. The numeric-prefix rule covers sequential and timestamp
  numbering and `branch_template` forms, whose final segment always starts
  with the number, without a second `gh` call for the trunk name.
- **Trade-off**: a trunk named with a leading number would be treated as
  a feature branch — documented, not handled. The existing
  `Packet.seeded_findings` (`packet.py:523-547`) stays as it is: it is
  data without anchors and nothing consumes it; this feature does not
  wire it.

### D2. The engineering principles live in the base rules (code-review)

- **Decision**: `RULE_TEMPLATE` (`doctor.py:104-114`) gains a `**/*` rule
  stating the principles in the engine's free-text form: the simplest
  implementation that meets the current requirement; no compatibility
  layers, fallbacks or migrations; no speculative abstraction or
  configuration; reuse what is installed; ask whether a mechanism is
  needed before asking for its edge cases; report over-engineering and
  speculative abstraction as `major` and any new runtime dependency as
  `blocking`. `doctor --fix` keeps writing it only when
  `.opencodereview/rule.json` is absent (`doctor.py:758-762`). This
  repository commits the same file at its root so this round's review
  packets carry the principles (`packet.py:448` embeds the rules;
  `rules.py:247` warns today that the set is empty).
- **Rationale**: the package doctor already owns, writes and tests the
  base rule file; the preset doctor runs that doctor, so "the doctor
  writes it" (FR-007) holds through the same `--fix`. The rule text is
  what every agent's review reads, whichever host runs it.
- **Trade-off**: the log worded the base file as preset-shipped; a preset
  JSON copied by an agent would duplicate a mechanism the package already
  provides deterministically, so the package keeps it (recorded in
  Alternatives). Consumers with an existing rule file merge the base rule
  by hand; the changelog says so.

### D3. Worktree-aware resolution (linear)

- **Decision**: a new leaf helper in `git_refs.py`,
  `main_worktree_root(root) -> Path | None`: `git -C <root> rev-parse
  --git-common-dir`, made absolute against `root`, parent directory;
  `None` when git fails or the parent is `root` itself (main checkout).
  `resolve_config_path` (`config.py:418`) uses it when no explicit
  `--config`/environment override is set and `<root>/speckit-linear.yml`
  is absent; `load_dotenv_files` (`env_files.py:90`) uses it when
  `<root>/.speckit-linear.env` is absent, before the operator-global
  file. `_doctor_local_file_diagnostics` (`cli.py:348`) names the path
  actually resolved. `persist_process_credential` keeps writing to the
  root it was given.
- **Rationale**: FR-011; the two files are per-checkout by design and a
  worktree shares the repository's common dir — the parent of
  `--git-common-dir` is the main checkout on every platform (probed
  2026-09-03: `.git` in the main checkout, an absolute `.git` path in a
  worktree).
- **Trade-off**: one git subprocess per command in worktrees only; a
  bare-repository layout has no main checkout and keeps today's behavior.

### D4. Tooling detected at loop start (preset)

- **Decision**: `implement-append.md` step 0 fixes the run's tooling set
  from the feature branch — `[ -d .specify/extensions/linear ]` and
  `[ -d .specify/extensions/code-review ]` — and reports it once. Every
  reconcile call is conditioned on `linear`; the review step keeps the
  session flow with `code-review` and, without it, hands the fresh
  reviewer the PR's diff (`gh pr diff <n>`) and the same brief, its
  findings posted with `gh pr comment` and fixed on the branch. A sentence
  states that tasks never install or remove extensions: that is a trunk
  chore.
- **Rationale**: FR-001; a directory test is the observable installed
  state on the branch and needs no parser.
- **Trade-off**: findings posted as comments are not a review session:
  no verdict, no evidence root — accepted as the degraded mode.

### D5. One linear stack, and a stack-aware PR base (preset)

- **Decision**: step 1 picks the task branch's base from observable
  state: among open, non-draft PRs whose head matches
  `NNN-T###-` (`gh pr list --state open --json
  headRefName,baseRefName,isDraft --jq ...`), the top of the stack is the
  head no other open task PR uses as base; the new branch is created from
  it (after `git fetch`) and the PR's `Stack:` line names it; with no
  open ready task PR the base is the feature branch. An open draft task
  PR means a task is still in flight and the loop does not start another
  (existing one-task rule). `pr.md`'s `task)` case resolves the same base
  — the nearest open task head that is an ancestor of `HEAD`
  (`git merge-base --is-ancestor`), else the feature branch — instead of
  always the feature branch (`pr.md:458-461`), which is what 003's
  stacked PRs actually used (#45→`003-T001-…`, #46→`003-T002-…`;
  GitHub retargets after the base merges). `Depends on` in the ledger
  documents order; it no longer chooses the base. `tasks-append.md` says
  so.
- **Rationale**: FR-003 and SC-001; a single stack makes the ledger
  accumulate every checked box and makes root-first merging (D8) the
  only integration order. Deriving the base from open PRs keeps the
  loop resumable from repository state alone (Principle IV).
- **Trade-off**: a task stacks on an unrelated predecessor and waits for
  its merge to retarget — accepted; the previous round proved parallel
  stacks cost more than the wait, and nothing pauses the loop.

### D6. Fix propagation through the stack (preset)

- **Decision**: a loop step "carrying a fix": after any commit on a task
  branch that has open PRs stacked on it (open task PRs whose base is
  that branch, transitively, from the same `gh pr list` data), for each
  stacked branch in stack order: `git switch`, `git merge --no-ff -m
  "merge(task): carry the T### fix into T###" <previous>`, `git push`; a
  conflict runs `git merge --abort`, stops the loop and names the
  branch. Marked shell block (`# stack-propagate:start/end`), POSIX.
- **Rationale**: FR-002; the `merge(task)` subject is the form the
  conventions check accepts and the one 003 used by hand (`e96c9e5`,
  `e0277d9`).
- **Trade-off**: one merge commit per stacked PR per fix; history stays
  truthful and nothing is rewritten.

### D7. Branch identity check in `pr.md` (preset)

- **Decision**: inside the `pr-create` block's `task)` case:
  `branch_task` is the `T###` of the current branch (`sed -nE
  's/^[0-9]+-(T[0-9]{3})-.*/\1/p'`), `expected_task` is the task the user
  named or the first unchecked task outside fenced blocks (the awk
  equivalent of `parser.py:16,56-90`: toggle on ```` ``` ````/`~~~`
  with ≤3 spaces of indent, first `- [ ] T###`); a mismatch prints both
  and exits 2 before `gh pr create`. Conformance gains the mismatch case
  in its `pr-create` scenarios (`bundles.sh:515-586`).
- **Rationale**: FR-004; #54 opened with T011's branch for T015 because
  only the syntax was checked.
- **Trade-off**: the awk rule mirrors the parser; both are covered by
  their own tests, and drift shows up as a conformance failure.

### D8. The loop never merges; root-first; revert path; worktree prune (preset + README)

- **Decision**: step 4 ends the run with every PR ready and its review
  closed and says merging is a human decision made root-first (a
  retarget is an `edited` event, no workflow runs; leaf-first
  `synchronize`s every open PR and re-runs every check); when the human
  explicitly asks in the conversation, the agent runs `git worktree
  prune` then `gh pr merge <n> --merge --delete-branch` root-first and
  reconciles. Feature closure prunes before `git branch -d`. A "reverting
  a delivered task" paragraph: the revert is a ledger task delivered like
  any other; the commit is `git revert --no-commit <sha>` (`-m 1` for a
  merge) followed by `git commit -m "revert(scope): <subject>"`, never the
  default subject. The README's golden rules carry rules 4 and 10 and the
  ruleset note (A-006); the preset README carries rule 14.
- **Rationale**: FR-005, FR-012, FR-013, FR-015; every item is text the
  previous round paid for in PRs.
- **Trade-off**: none; the on-request merge is the only new agent action
  and it requires an explicit human sentence each time.

### D9. Budget stop at twice the forecast (preset)

- **Decision**: step 2, before `/speckit.pr`: a POSIX block writes
  `git diff --numstat <base>...HEAD` to a temporary file (no pipeline),
  sums added lines over files the review budget counts (same exclusions
  as `budget.py:27-30`: `.md .rst .txt .lock .svg .png .jpg .jpeg .gif
  .ico .pdf`, `uv.lock package-lock.json poetry.lock Cargo.lock`), reads
  the forecast from the task's `Delivery` line (`~N authored lines`;
  absent → 400) and stops when the sum passes the smaller of `2 × N` and
  400: no PR, a diagnosis to the human (what does not fit, a proposed
  split). The text states the forecast is never edited in the breaching
  PR. `tasks-append.md` requires every `Delivery` line to carry the
  forecast in that form.
- **Rationale**: FR-006; T011 reached 7× and T013 widened 400 → 700
  inside its own PR.
- **Trade-off**: added lines approximate "authored executable lines" as
  the review budget does; deletions are free, which is the intended bias.

### D10. Standard reviewer brief (preset)

- **Decision**: step 2 hands the fresh reviewer a fixed brief with the
  packet path: verify the claims in the packet's evidence instead of
  repeating the experiments; ask whether the mechanism is needed before
  asking for an edge case (a simpler design is a `major` finding, a new
  runtime dependency `blocking`, per the rules file); a packet over
  100 KB (`wc -c`) is reviewed one file at a time, findings consolidated
  at the end; write `findings.json` inside the session directory.
- **Rationale**: FR-009; entries 8 and 11.
- **Trade-off**: prompt-enforced; the rules file (D2) is the
  deterministic half.

### D11. Doctor: safe mirror and ignore entries (preset)

- **Decision**: step 5 distinguishes two kinds. Extension and preset
  skills are copied whole from the default integration's directory
  (today's rule). The five core commands (`specify`, `plan`, `tasks`,
  `analyze`, `implement`) keep each integration's own render — the file
  `specify integration install` produced, with its own frontmatter and
  invocation tokens (`/speckit-…` vs `$speckit-…`) — and receive the
  preset's registered append layers from `.specify/presets/<id>/preset.yml`
  (`strategy: "append"` entries, files under
  `.specify/presets/<id>/commands/`) concatenated after three blank
  lines, as upstream does for the default integration. Idempotent: a
  render already ending with the append text is unchanged; one containing
  the append's first heading with different content is cut at that
  heading and re-appended. A core skill is never copied across
  integrations. New step 6: the installer's cache directories
  (`.specify/extensions/.cache/`, `.specify/presets/.cache/`) and the
  payload virtual environments (`.specify/extensions/*/.venv/`) are
  checked with `git check-ignore -q`; missing ones are reported, and
  `--fix` appends them to `.gitignore`.
- **Rationale**: FR-016, FR-018; entries 17 and 19. `check-ignore`
  honors broader patterns, so a repository ignoring `.venv/` globally
  gets no duplicate.
- **Trade-off**: agent-executed text, not package code — consistent with
  the doctor being a preset command; conformance checks the text.

### D12. Hook silence in `implement` (preset)

- **Decision**: `implement-append.md` gains the "hooks are acted on,
  never announced" bullet from `phase-close-append.md` — without the
  artifact-commit bullet, since the loop owns its commits.
- **Rationale**: FR-019; entry 21 (FR-002 of 003 was wider than what
  shipped).
- **Trade-off**: none.

### D13. Published digests in conformance (scripts)

- **Decision**: `bundles.sh --published` additionally verifies, for each
  first-party extension in `versions.lock.yml` (`linear`, `code-review`):
  the release zip downloaded from the catalog's `download_url` (`curl
  -fsSL` to a temporary directory) against `release_zip_sha256`; `git
  archive --mtime="@<commit epoch>" --format=tar "<tag>:<path>"` against
  `subtree_archive_sha256`; `git show <tag>:<path>/extension.yml` against
  `manifest_sha256` — the three computations `build-release.sh:45-51`
  performs at publication. A missing tag fails with the fetch command as
  remediation. The lock fields are read with the sed/awk style the script
  already uses for `package_version` (`bundles.sh:66`). Default mode is
  unchanged; `publish.sh` keeps running `--published` after publication
  (`publish.sh:275`), so the uploaded assets are re-verified by the
  release itself.
- **Rationale**: FR-014; entry 15 — today `--published` proves catalog
  version parity and rebuilds locally, never touching a published byte.
- **Trade-off**: published mode needs network access and the tags; it is
  the maintainer's step and stays out of CI.

### D14. Documentation and release

- **Decision**: `AGENTS.md` gains the `docs/dogfooding.md` Spanish
  exception and `CLAUDE.md` becomes the one-line import `@AGENTS.md`;
  the README documents the second-agent steps (verified present at
  `README.md:320-326`, corrected where needed) and the digest
  re-verification; `docs/plan.md` gains this round; `docs/dogfooding.md`
  statuses graduate (entry 20 included). Release: `publish.sh --bump
  preset=0.9.0 linear=0.12.0 code-review=0.4.0 bundles=0.15.0` in the last
  delivery task; publication is human, from `main`, after the feature
  merges. Task order follows story priority so the loop rules (US1)
  land first and govern the rest of the round; a mid-round publication
  of code-review alone would need its PRs on `main`, which the
  integration-branch model only provides through the feature PR — the
  maintainer's option is a trunk chore for those self-contained tasks,
  decided at the gate.
- **Rationale**: FR-008, FR-015, FR-017, A-005, A-007, C-005.
- **Trade-off**: this round's own loop runs on the installed releases; the
  deterministic contract check protects the next round, this one relies
  on C-004 by discipline.

## Data and migration behavior

No durable state changes. `protected_paths` is additive with defaults;
absent keys behave as documented. The rule template only affects
repositories without a rule file. Ignore entries are appended, never
rewritten. Config and env fallback only applies where the files are
absent.

## Failure, retry, rollout, and rollback

- **Failure behavior**: propagation conflicts and identity mismatches
  stop with the branch or tasks named; budget breaches stop before a PR
  exists; published-mode digest mismatches fail the script with the
  asset and both digests; the mirror never writes a core render it did
  not build from the integration's own file.
- **Retry/idempotency**: base selection, propagation, mirror and ignore
  steps re-derive from repository state; the generated finding is
  deterministic per candidate; reconciliation keeps its contract.
- **Rollout**: preset 0.8.0 → 0.9.0, linear 0.11.0 → 0.12.0, code-review
  0.3.0 → 0.4.0, bundles 0.14.0 → 0.15.0; consumers adopt by bundle
  update, then `doctor --fix` for the rules and ignore entries.
- **Rollback**: preset and docs are text (revert commit via D8's path);
  packages are pinned per release.

## Security and privacy

No new credentials or remote writes. The generated finding reads only
the candidate's diff and the session's own data. The worktree fallback
reads files inside the same repository's main checkout, never outside
it. The on-request merge is the one new mutation and runs only on an
explicit human instruction in the conversation. Published-mode
conformance downloads only the catalog's own release URLs and compares
digests; it installs nothing.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-010 / SC-003 (protected paths) | phase-two tests: modified, added, deleted protected path on a numeric base → blocking + changes-requested; trunk base and working tree → none; config validation | `uv run pytest packages/spec-kit-code-review/tests` |
| FR-007 (base rules) | doctor `--fix` writes the principles; parity between the template and this repo's committed file | same suite; `diff` in the task's evidence |
| FR-011 / SC-007 (worktree) | config and env resolved from the main checkout in a `git worktree add` fixture; worktree-local files win | `uv run pytest packages/spec-kit-linear/tests` |
| FR-001, 002, 003, 005, 006, 009, 012, 013, 019 (loop text) | the installed `implement` skill carries each rule; this round's transcripts and PR bases | `bash scripts/conformance/bundles.sh`; `gh pr list` during this delivery |
| FR-004 (identity) | `pr-create` mismatch scenario exits 2 | `bash scripts/conformance/bundles.sh` |
| FR-002 (propagation) | `stack-propagate` block executed against fake `git`/`gh` | `bash scripts/conformance/bundles.sh` |
| FR-016, FR-018 / SC-006, SC-009 (doctor) | two-integration fixture: core renders keep their frontmatter and gain the appends; extension skills identical; ignore entries added once | `bash scripts/conformance/bundles.sh`; `/speckit.doctor --fix` in this repo |
| FR-014 / SC-005 (digests) | published mode passes on the published tree and fails on an altered lock digest | `bash scripts/conformance/bundles.sh --published` |
| FR-008, 015, 017 (docs) | files carry the text; `CLAUDE.md` is the import | `git diff --check`; review |
| Regression safety | both suites, conformance, CI | `uv run pytest packages/*/tests`, `bash scripts/conformance/bundles.sh` |

## Source layout

```text
packages/spec-kit-code-review/src/spec_kit_code_review/{config,cli}.py  # protected_paths, generated finding
packages/spec-kit-code-review/src/spec_kit_code_review/doctor.py        # RULE_TEMPLATE principles
packages/spec-kit-code-review/config/speckit-code-review.template.yml  # protected_paths
packages/spec-kit-code-review/{commands/code-review.md,README.md,CHANGELOG.md,extension.yml,pyproject.toml}
packages/spec-kit-code-review/tests/                                    # new cases
packages/spec-kit-linear/src/spec_kit_linear/{git_refs,config,env_files,cli}.py  # main-checkout fallback
packages/spec-kit-linear/{README.md,CHANGELOG.md,extension.yml,pyproject.toml}
packages/spec-kit-linear/tests/                                         # worktree cases
presets/default/commands/implement-append.md   # steps 0–4: tooling, stack, propagation, budget, brief, closure, revert, silence
presets/default/commands/pr.md                 # stack-aware task base, identity check
presets/default/commands/tasks-append.md       # forecast line, order vs base
presets/default/commands/doctor.md             # safe mirror, ignore entries
presets/default/{README.md,preset.yml}         # rule 14, stack and merge rules, 0.9.0
scripts/conformance/bundles.sh                 # identity + propagation scenarios, published digests
.opencodereview/rule.json                      # this repository's base rules
AGENTS.md · CLAUDE.md                          # single source, import
README.md                                      # rules 4 and 10, second agent, digest re-verification
docs/plan.md · docs/dogfooding.md              # round entry, statuses
.claude/skills/ · .agents/skills/              # regenerated renders (upstream-managed, mirrored)
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Exempt trunk-based PRs by querying the GitHub default branch | one more `gh` call through the allowlist for a fact the base branch name already encodes |
| Wire `Packet.seeded_findings` for the protected-path finding | unanchored data with no consumer; a second finding model where the agent's suffices |
| Preset-shipped `rule.json` copied by the agent doctor | duplicates the package doctor's deterministic, tested write |
| A `git config` or environment fallback for the worktree | invisible to the team; the common dir is the repository's own fact |
| Stack only on declared dependencies (previous rule) | produced the parallel stacks and divergent ledgers of 003 |
| A ruleset requiring approval on `NNN-*` branches | blocks a single maintainer (GitHub does not count the author's approval) |
| Running `--published` digest checks in CI | needs network and tags on every PR; the release gate already runs it |

## Product handoff

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | 2026-09-03: 19/19 FR and 9/9 SC covered, 0 critical, 2 medium remediated in-phase (digest scope, T014 upgrade as trunk chore) | complete |
| Technical approval of plan and tasks | — | pending |
| Reviewed Linear dry-run and synchronization | — | pending |
| Every executable task individually assignable and assigned | — | pending |
