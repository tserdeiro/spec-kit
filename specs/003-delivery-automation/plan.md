# Implementation Plan: Unattended delivery automation

**Feature directory**: `specs/003-delivery-automation`
**Spec**: [spec.md](spec.md)

## Summary

Make the workflow act instead of remind, on three surfaces this repository
owns: the `default` preset (phase-close behavior, the implement loop, the
doctor), the `spec-kit-linear` package (parser, first-run diagnosis,
automation docs), and the `spec-kit-code-review` package (findings format
and integrity). No new commands, no upstream patches; upstream-rooted
causes stay recorded in `docs/dogfooding.md`.

## Technical context

- **Language/runtime**: preset/commands are agent-executed Markdown +
  bash launchers; packages are Python ≥3.11 (`uv`-managed, zero runtime
  deps by policy).
- **Primary dependencies**: pinned upstream `specify-cli` 1.0.1
  (`versions.lock.yml`); `gh` CLI for platform checks; Linear GraphQL API
  (already the linear package's only remote).
- **Storage/state**: consumer config instances only — `trunk:` key in
  `.specify/extensions/git/git-config.yml` (committed, consumer-owned);
  no new state files.
- **Verification**: package pytest suites, package conformance scripts
  (`packages/*/scripts/conformance/`), bundles conformance in CI,
  `git diff --check`, and this feature's own delivery as the dogfood
  evidence for SC-001/002/005.
- **Target environment**: any upstream-supported agent; macOS/Linux bash
  (PowerShell parity where the touched assets already have it).
- **Constraints**: C-001 upstream assets untouched; C-004 command surface
  frozen; 400-line review budget per task.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| specify-cli (upstream) | 1.0.1 | https://github.com/github/spec-kit |
| Linear GraphQL / GitHub integration | current | https://linear.app/developers/graphql · https://linear.app/docs/github |
| gh CLI | consumer-installed | https://cli.github.com/manual/ |

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose a pinned upstream | PASS | PASS | C-001: only preset + packages change; upstream frictions logged in `docs/dogfooding.md` |
| II. Preserve the native surface | PASS | PASS | No new commands or flags; appends extend existing commands (C-004) |
| III. Integrations consumer-selected | PASS | PASS | Linear install here is this repo acting as its own consumer (A-002); generated-asset checks stay separate from runtime evidence |
| IV. Repository artifacts durable truth | PASS | PASS | Spec/plan/tasks + `docs/dogfooding.md`; Linear stays a projection (D2) |
| V. Source and consumer boundaries | PASS | PASS | Changes ride preset-owned surfaces and package releases; consumer config instances hold the only new key (D4) |
| VI. Traceable delivery units | PASS | PASS | tasks.md blocks with traces, forecasts ≤ 400 lines, single/feature-chain strategy |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| `presets/default` commands + appends | this repo | phase-close behavior, loop step 0 + reconcile + fresh review, doctor platform checks, trunk resolution | patching core command templates (upstream) |
| `packages/spec-kit-linear` | this repo | parser fence handling, unlinked-repo diagnosis, automation-coverage docs | new lifecycle hook registrations (removed by design, stay removed) |
| `packages/spec-kit-code-review` | this repo | findings doc corrected; findings path bound to its session | any change to verdicts, publishing, or budget |
| `.specify/extensions/git` payload | upstream | none (C-001) | fixing `auto-commit.sh` staging or hook announcements at the root |
| Consumer GitHub/Linear settings | consumer | diagnosed by doctor, documented | mutating platform settings automatically |

## Technical decisions

### D1. Phase-close behavior via preset appends

- **Decision**: one preset append applied to `speckit.specify`,
  `speckit.plan`, `speckit.tasks` (folded into the existing
  `tasks-append.md`), and `speckit.analyze`: never announce optional
  hooks (enabled-by-config → execute silently, otherwise skip), and end
  the command by committing the feature's artifacts —
  `specs/<feature>/` only — with a `type(scope): subject` message,
  skipping when clean.
- **Rationale**: appends are the distribution's sanctioned override
  surface (`strategy: "append"`, precedent: "this loop wins"); the
  upstream hook text stays untouched (C-001) while its observed behavior
  disappears.
- **Trade-off**: the rule is prompt-enforced, not deterministic; the
  dogfood run and conformance text checks are the guard.

### D2. Loop reconciliation with `push --hook`

- **Decision**: `implement-append.md` runs
  `speckit.linear.push --hook` at loop start (catches
  merged-while-away work) and after each transition it causes (task
  branch created, PR ready). Verified semantics: `--hook` is a clean
  no-op without valid configuration and honors `hooks.lifecycle_enabled`
  / `hooks.auto_apply` (cli.py:990–998).
- **Rationale**: "push stays the reconciler" (plan.md, Stage 7.4) —
  this invokes the reconciler at the moments the loop itself creates,
  instead of re-registering the announced YAML hooks removed by "Native
  over custom".
- **Trade-off**: a few extra idempotent API round-trips per task; none
  when Linear is absent.

### D3. Feature PR gate folded into `implement`

- **Decision**: loop step 0 checks for the feature PR
  (`gh pr view` on the feature branch) and, when missing, executes the
  `speckit.pr` feature-variant routine before the first task.
- **Rationale**: `pr.md` is already idempotent; folding removes the one
  ordering rule the consumer run proved nobody should need (US3).
- **Trade-off**: `speckit.pr` remains available standalone; two paths to
  the same routine, one document owning its text.

### D4. Trunk key in the git extension's consumer config

- **Decision**: `trunk: <branch>` in the consumer's
  `.specify/extensions/git/git-config.yml`; the feature-PR path in
  `pr.md` and the `implement-append.md` loop resolve the delivery base
  as: explicit `trunk:` key → else
  `gh repo view --json defaultBranchRef`. Documented in the preset README
  and the root README.
- **Rationale**: the file is committed, consumer-owned configuration the
  team already edits; upstream ignores unknown keys; no per-machine
  state (rejected: `git config`), no upstream schema intrusion
  (rejected: `init-options.json`).
- **Trade-off**: a preset command reads another extension's config file;
  acceptable because product and developer — the roles that own these
  paths — install both.

### D5. Parser ignores fenced blocks

- **Decision**: the tasks parser tracks ``` / ~~~ fences and skips their
  content for task, phase, and title matching; covered by parser tests
  with the template's own instructive section as fixture.
- **Rationale**: the template's example block is legitimate content;
  deleting it by hand was the consumer workaround (SC-004).
- **Trade-off**: none material; indented code blocks stay out of scope
  (no observed case).

### D6. Findings format: docs corrected, path bound to session

- **Decision**: correct `commands/code-review.md` + README to the shape
  the validator accepts (`{"findings": [...]}`); additionally,
  `--findings` must resolve inside the session directory it closes —
  a path outside it is a usage error.
- **Rationale**: FR-009 fixes the observed doc/validator mismatch;
  binding the path makes cross-review reuse (FR-011) structurally
  impossible instead of prompt-discouraged.
- **Trade-off**: agents must write findings into the session directory;
  the command doc says so where it says everything else.

### D7. Unlinked-repo diagnosis before any network call

- **Decision**: `push` and `status` short-circuit when the root
  `speckit-linear.yml` is missing or still carries placeholder IDs:
  category `configuration`, message naming `onboard`. Credential errors
  keep naming their source (existing behavior), never the raw GraphQL
  text for this case.
- **Rationale**: FR-005/SC-003 — the consumer run burned ~2 h reverse-
  engineering a 401 that meant "never linked".
- **Trade-off**: placeholder detection is a heuristic (zeroed IDs);
  kept to exactly what the shipped template writes.

### D8. Platform checks in the preset doctor

- **Decision**: `doctor.md` adds two read-only `gh repo view` checks —
  `deleteBranchOnMerge` and `mergeCommitAllowed` — reported with the
  exact setting to change; Linear binding stays covered by the linear
  doctor it already runs.
- **Rationale**: the flow's closing step depends on both; the consumer
  repo had auto-delete off and nothing said so (FR-006).
- **Trade-off**: agent-executed checks, not package code — consistent
  with the doctor being a preset command.

### D9. Native-automation coverage stated honestly

- **Decision**: the linear package README (and a consumer note in the
  root README) document: Linear PR automations are team-level; target-
  branch rules are configurable and a rule for feature branches
  (`^\d{3}-`) is required for task-PR merges to move issues natively;
  branches carry no issue key, so linking rides the PR-body magic word;
  `push` reconciles everything regardless.
- **Rationale**: FR-007 — Stage 7.4 promised "links natively" without
  stating the coverage conditions; the consumer run hit the gap.
- **Trade-off**: documentation, not automation; the reconciler (D2) is
  the guarantee.

### D10. Self-review in a fresh context

- **Decision**: the loop delegates packet reading and findings to a
  fresh sub-agent (hosts without sub-agents run it themselves, as
  today), writing findings into the session directory (D6).
- **Rationale**: FR-011 — 19 consumer PRs closed with one reused empty
  findings file; independence plus the D6 bind restores the review's
  value.
- **Trade-off**: one more sub-agent per task; bounded by the existing
  budget warning.

### D11. Dogfooding sequence and its known limitation

- **Decision**: install the published `spec-kit-linear` 0.10.0 into this
  repository (consumer path, catalogs already in the README), onboard to
  the TDS team, and project this feature. 0.10.0 lacks D5, so this
  feature's own `tasks.md` omits the template's instructive section (the
  very workaround D5 eliminates); SC-004 is proven by the 0.11.0 parser
  tests plus a regenerated fixture, and the install is upgraded on the
  next release.
- **Rationale**: A-002 — eating the released dogfood exercises the real
  consumer path and the projection half of the flow where its work is
  tracked.
- **Trade-off**: one release lag between fixing and consuming the fix
  here; recorded in `docs/dogfooding.md` if it bites again.

## Data and migration behavior

No durable state changes. The `trunk:` key is additive and optional;
absent means today's behavior. Parser fence-skipping only removes false
positives; existing well-formed `tasks.md` files parse identically.

## Failure, retry, rollout, and rollback

- **Failure behavior**: loop reconciliation failures report once and
  never block delivery (US2 edge case); unlinked repos no-op (D2) or
  name `onboard` (D7); doctor checks degrade to "cannot verify" when
  `gh` is absent.
- **Retry/idempotency**: `push` keeps its idempotent reconciler
  contract; `pr` routines stay idempotent (existing step 3 check).
- **Rollout**: preset 0.7.0 → 0.8.0, linear 0.10.0 → 0.11.0,
  code-review 0.2.1 → 0.3.0; bundle pins bumped with
  `publish.sh --bump`; consumers adopt by bundle update. Releases and
  publication stay human-controlled.
- **Rollback**: preset changes are text (revert commit); packages are
  pinned per release, consumers stay on the prior pin.

## Security and privacy

No new secrets or credential paths. Non-interactive Linear mutations in
the loop ride the existing lifecycle gates (`hooks.auto_apply: false`
disables them) and idempotent reconciler; human-facing `push` stays
preview-by-default (C-003). Doctor platform checks are read-only `gh`
queries. Nothing mutates GitHub or Linear settings.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-008 / SC-004 (parser) | parser tests incl. template-section fixture | `uv run --project packages/spec-kit-linear pytest` |
| FR-005 / SC-003 (unlinked) | config-guard tests, message names onboard | `uv run --project packages/spec-kit-linear pytest` |
| FR-009/FR-011 (findings) | validator/doc parity + session-bound path tests | `uv run --project packages/spec-kit-code-review pytest` |
| FR-001/002 / SC-001 (phase close) | this feature's own phases: no announcements, clean `git status` | transcript + `git log` of this delivery |
| FR-003 / SC-005 (gate in implement) | loop step 0 opens the feature PR | dogfood run of this feature |
| FR-004 / SC-002 (reconcile) | task transitions reflected in TDS with no human push | Linear states during this feature's loop |
| FR-006 / SC-003 (doctor) | doctor output naming auto-delete remediation | `speckit.doctor` run in this repo |
| FR-010 / SC-006 (trunk) | resolution order exercised with `trunk:` set | dogfood + preset conformance text check |
| Regression safety | full suites + conformance | `packages/*/scripts/conformance/`, CI bundles conformance, `git diff --check` |

## Source layout

```text
presets/default/preset.yml                     # 0.8.0; new append registrations
presets/default/commands/phase-close-append.md # new: hook silence + artifact commit (specify, plan, analyze)
presets/default/commands/tasks-append.md       # phase-close folded in
presets/default/commands/implement-append.md   # step 0 gate, reconcile calls, fresh review, trunk
presets/default/commands/pr.md                 # trunk resolution
presets/default/commands/doctor.md             # platform checks
presets/default/README.md                      # trunk key, phase-close behavior
packages/spec-kit-linear/src/spec_kit_linear/parser.py    # fence handling
packages/spec-kit-linear/src/spec_kit_linear/{cli,config}.py  # unlinked guard
packages/spec-kit-linear/tests/                # new cases
packages/spec-kit-linear/README.md · CHANGELOG.md  # automation coverage (D9), 0.11.0
packages/spec-kit-code-review/commands/code-review.md      # findings shape
packages/spec-kit-code-review/src/spec_kit_code_review/cli.py  # session-bound findings path
packages/spec-kit-code-review/tests/ · README.md · CHANGELOG.md  # 0.3.0
README.md                                      # consumer notes (trunk, Linear automations)
docs/plan.md                                   # new round entry (A-004)
docs/dogfooding.md                             # standing log (created at specify)
.specify/extensions/git/git-config.yml         # trunk: main (this repo's own instance)
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Re-register YAML lifecycle hooks for loop sync | removed as no-op announcements by "Native over custom"; the loop invoking the reconciler needs no registry |
| Patch upstream templates / `auto-commit.sh` | violates Principle I and C-001; recorded as upstream candidates instead |
| Bound the overnight PR stack | rejected by product decision 2026-08-31 (C-002) |
| `git config speckit.trunk` for D4 | per-machine, invisible to the team, uncommitted |

## Product handoff

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | — | pending |
| Technical approval of plan and tasks | — | pending |
| Reviewed Linear dry-run and synchronization | after install + onboard (D11) | pending |
| Every executable task individually assignable and assigned | — | pending |
