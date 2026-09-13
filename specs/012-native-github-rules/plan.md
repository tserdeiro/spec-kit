# Implementation Plan: Verify native GitHub delivery guarantees

**Feature directory**: `specs/012-native-github-rules`
**Spec**: [spec.md](spec.md)

## Summary

Replace the doctor's two-setting GitHub check with a preset-owned Python
helper that observes settings and effective rules for concrete delivery
branches. Keep the existing doctor category and bounded local `--fix` behavior;
its GitHub component stays read-only. Research, data contract, and validation
are consolidated here, following the resolved template and feature 008 precedent.

## Technical context

- **Language/runtime**: Python 3.11+, matching the existing preset interpreter rule.
- **Primary dependencies**: Python standard library, installed Git and `gh`.
  Tests use pytest 9.1.1 from [uv.lock](../../uv.lock); the root
  [workspace](../../pyproject.toml) and [package manifest](../../packages/spec-kit-linear/pyproject.toml)
  already supply it. Add no dependency.
- **Storage/state**: Ephemeral observations only; consumer Git and configuration remain unchanged.
- **Verification**: Preset pytest fixtures, a synthetic installed-consumer test,
  existing bundle conformance, and `git diff --check`.
- **Target environment**: Existing consumer platforms and selected integrations;
  use `.venv/bin/python` when present, otherwise `python3`.
- **Constraints**: Current 400-line review budget and 2× forecast stop; upstream
  baseline, team policy, release authority, and remote-write authorization preserved.

## Documentation

Official GitHub sources checked during planning on 2026-09-12. Verify additional
APIs against their official documentation before implementation.

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| GitHub REST | `gh` authenticated REST API | [Repository settings](https://docs.github.com/en/rest/repos/repos#get-a-repository), [effective branch rules and rulesets](https://docs.github.com/en/rest/repos/rules), [classic protection](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection) |
| GitHub rule semantics | Current hosted service | [Layering and availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets), [rule types](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets), [bypass](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository#granting-bypass-permissions-for-your-branch-or-tag-ruleset) |
| GitHub errors and cleanup | Current hosted service | [REST troubleshooting](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api), [automatic branch deletion](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-the-automatic-deletion-of-branches) |
| GitHub CLI | Consumer-installed | [gh api and pagination](https://cli.github.com/manual/gh_api), [repository selection](https://cli.github.com/manual/gh_repo_view) |
| Python / pytest | 3.11+ / locked 9.1.1 | [Subprocess](https://docs.python.org/3.11/library/subprocess.html), [pytest invocation](https://docs.pytest.org/en/stable/how-to/usage.html) |

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose pinned upstream | PASS | PASS | Authored preset only; locks and generated baseline preserved. |
| II. Preserve native surface | PASS | PASS | Existing doctor invokes an installed internal helper; no new lifecycle command. |
| III. Consumer-selected integrations | PASS | PASS | One helper and common command; synthetic evidence labelled separately. |
| IV. Durable repository truth | PASS | PASS | Stable FR/SC identifiers and ordered ledger; observations claim only their run's scope. |
| V. Source/consumer boundary | PASS | PASS | Installed preset resolves consumer state with no source-checkout runtime dependency. |
| VI. Reviewable delivery | PASS | PASS | One dependency chain; each task includes tests, traces, boundaries, and a forecast below 400. |
| Sequential delivery and human gates | PASS | PASS | User requested implementation on 2026-09-12; task delivery remains sequential and final review/merge human-controlled. |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| GitHub doctor category | `presets/default/commands/doctor.md` | Invoke helper; summarize settings, scope, protections, uncertainty, and remediations | Replacing the full doctor or its other categories |
| Observation / evaluation | New `github_delivery.py`, `github_delivery_rules.py` under preset scripts | Read native evidence; evaluate per guarantee; render concise findings | GitHub writes, private rule matching, or a general policy engine |
| Preset distribution | `presets/default/preset.yml` | Register both installed scripts | Editing generated consumer skills or upstream scripts |
| Tests / guidance | Preset tests and README | Exercise real helper with fake GitHub; document meanings and native next actions | Live destructive acceptance, release or promotion repair |

## Technical decisions

### D1. Keep a runnable GitHub component inside the existing doctor

- **Decision**: `github_delivery.py` is the single report entry point; its pure
  evaluator lives in `github_delivery_rules.py`. Register both as preset scripts.
  Replace doctor steps 4/5's settings-only contract atomically with the caller.
- **Rationale**: The source already ships small Python helpers through the preset;
  `_common.delivery_base()` owns trunk resolution. Neither an extension nor a
  new public command is needed. Inspect/reuse its read helpers where suitable.
- **Trade-off**: Additional remote reads are necessary to avoid a false pass.
  The full executable-doctor project remains entry 17.

The internal invocation is `python3 .specify/presets/default/scripts/python/github_delivery.py`
with the existing interpreter selection. It accepts no mutation flag. Print
scope and per-guarantee findings in deterministic order; return 0 only for a
fully compatible observed scope and 1 for any gap or uncertainty. The doctor
continues collecting other categories after a nonzero result, including under
`--fix`; it never forwards `--fix` to this helper.

### D2. Let GitHub resolve effective scope and rules

- **Decision**: Resolve the repository through authenticated `gh`; use configured
  trunk or the GitHub default via `_common.delivery_base()`. List remote branches
  completely; inspect trunk plus feature/task names defined by spec A-001.
- **Rationale**: Local refs can be stale. GitHub's effective-branch-rules endpoint
  already applies repository/inherited rules, include/exclude patterns, and enforcement.
- **Trade-off**: Current branch inventory is a snapshot, not proof about future
  branches or external branch conventions. State that limit in the report.

Use argument arrays, explicit REST `GET`, and encoded repository/branch path
segments. Use `gh api --paginate --slurp` for collections, validate every page,
and retain a failed final page as incomplete observation. Read repository
settings (`allow_merge_commit`, `delete_branch_on_merge`), branch inventory,
`rules/branches/{branch}`, and `branches/{branch}/protection`. Fetch each relevant
ruleset detail once per run, including parent rulesets, to inspect source and
bypass. No locally reconstructed glob matching or persistent cache is needed.

REST observations use `GET`; the fixed read-only classic merge-queue GraphQL
document uses `POST` with separately bound variables. No GraphQL mutation is
allowed.

Repository/branch identity and successful-empty responses are validated.
Missing settings, omitted `bypass_actors`, missing detail, or malformed required
fields are unknown, never false or an empty ruleset. An explicit documented
"Branch not protected" response for an otherwise verified existing accessible
branch can establish absence of classic protection; an ambiguous 404 cannot.
A branch disappearing during observation invalidates its affected guarantees.

### D3. Combine all layers conservatively

- **Decision**: Evaluate each guarantee using active applicable rulesets and
  effective classic protection; keep evidence source, enforcement, and known
  bypass exceptions together. A restrictive layer cannot be cancelled by a
  permissive layer.
- **Rationale**: The two current settings do not describe effective protection.
- **Trade-off**: Limited visibility can prevent compatibility from being certified
  even when visible settings appear correct.

| Guarantee | Compatible evidence / conflict |
| --- | --- |
| Force-push protection | Enforced `non_fast_forward` or classic `allow_force_pushes.enabled=false`; include `enforce_admins` and observed exceptions. No protection after complete observation is missing configuration. |
| Merge commits | `allow_merge_commit=true`; effective `required_linear_history`, classic linear history or branch lock, and `pull_request.allowed_merge_methods` excluding `merge` are conflicts. A required merge queue with a non-merge method is incompatible; an unproven queue interaction remains unverified. |
| Cleanup | `delete_branch_on_merge=true`; on feature/task branches, active `deletion`, classic `allow_deletions.enabled=false`, or branch lock conflict with ordinary cleanup. Trunk retention is compatible. |

Known privileged bypass is reported as an exception, not authorization to use
it or proof of universal protection. A `pull_request` bypass does not permit
force-push/deletion; `always`/`exempt` identify broader exceptions. Omitted bypass
information leaves exception coverage unknown. Diagnose restrictions for the
ordinary delivery path without relying on bypass. Preserve required checks and
reviews as team policy; do not suggest disabling them to make a report pass.
Unknown/new rule semantics that may affect a guarantee leave it unverified.

### D4. Make the next action depend on evidence

- **Decision**: Use four result states: `compatible`, `incompatible`,
  `capability-unavailable`, `unverified`; attach a separate cause to each gap.
- **Rationale**: Missing configuration, lack of capability, and unreadable
  configuration require different remedies.
- **Trade-off**: A generic API error may only support retry/access guidance.

Causes include missing configuration, conflicting configuration, explicit plan
limitation, insufficient permissions, rate limiting, read failure, partial
inventory, hidden fields, and unsupported rule semantics. Classify a plan limit
only with positive evidence; visibility and HTTP 403/404 alone do not identify
it. Sanitize error text and never print raw headers, tokens, or whole payloads.

Configuration findings name the native setting and intended value, or the rule
source/ID and proposed scope adjustment. For example: enable Allow merge commits;
enable Automatically delete head branches; protect trunk and shared delivery
branches from non-fast-forward updates; scope deletion restrictions to retained
branches. Inherited rules name the owning organization/enterprise. Keep bypass,
checks, and review policy intact for human assessment. Permission/capability
findings name the necessary access or owner/plan action; transient findings name
retry. These are reviewable proposals, never submitted repairs.

## Data and migration behavior

In memory, one repository observation owns scope completeness, settings, and
branch observations. Each branch carries its role (trunk/feature/task), active
rules, classic protection, known exceptions, sources, and read diagnostics.
Evaluation emits a guarantee, scope, state, cause, evidence, and next action.

Each guarantee combines all relevant facts: a confirmed conflict remains visible
alongside missing evidence. Overall compatibility requires complete inventory
and all required guarantees compatible. An unavailable capability or unknown
layer is never coerced into missing configuration. There is no durable schema,
migration, cache, or new consumer configuration.

## Failure, retry, rollout, and rollback

- **Failure behavior**: Missing `gh`, authentication, unresolved trunk, API errors,
  hidden fields, and partial pagination produce bounded diagnostic results.
  Continue independent reads where possible and retain confirmed findings.
- **Retry/idempotency**: Every run takes fresh observations with zero local/remote
  mutation; a later successful run can resolve an earlier unknown result.
- **Rollout**: Deliver settings/caller first, then effective rules, classic/bypass,
  compatibility, failure detail, and installed evidence. Intermediate coverage
  remains explicitly unverified until its checks exist. Release is separately authorized.
- **Rollback**: Revert the authored preset change; existing GitHub configuration
  and Git state need no repair.

## Security and privacy

`gh` owns authentication and the configured host. The helper issues REST reads
with `GET` and one fixed read-only GraphQL queue document with `POST`, uses no
shell evaluation, and redacts diagnostic content. Fixtures record argv and
reject REST writes (`POST`, `PUT`, `PATCH`, `DELETE`), GraphQL mutations and
every document except the fixed query, `gh repo edit`, push, merge, or delete.
Bypass configuration is evidence, never consent. Other doctor categories retain
their existing explicitly bounded local repairs.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001–FR-005, SC-001 | Settings, branch scope, inherited/classic layers, bypass, linear history, merge methods, deletion/lock | `uv run --frozen --offline pytest presets/default/tests/test_github_delivery.py presets/default/tests/test_github_delivery_rules.py -q` |
| FR-006–FR-009, SC-002–SC-003, C-002/C-004 | Capability/access/read distinctions, missing fields, second-page failure, no-write logs and unchanged files | Same focused suite; inspect expected report and call log |
| FR-008–FR-009, SC-004, C-001/C-003 | Installed scripts and generated caller in a temporary consumer; fake GitHub only | `uv run --frozen --offline pytest presets/default/tests/test_github_delivery_install.py -q` |
| Preset regressions / distribution | Existing script consumers, manifest registration, full bundle lifecycle | `uv run --frozen --offline pytest presets/default/tests -q`; `bash scripts/conformance/bundles.sh`; `git diff --check` |

These are commands for implementation acceptance; the new test files do not
exist yet. Installed conformance loads the preset into a temporary consumer and
executes its installed helper with source paths absent from imports. It verifies
the generated doctor's invocation and report-only GitHub `--fix` contract;
command-text inspection is generated-asset evidence, not a live agent run.

## Source layout

```text
presets/default/commands/doctor.md
presets/default/scripts/python/github_delivery.py          # new entry point
presets/default/scripts/python/github_delivery_rules.py    # new evaluator
presets/default/preset.yml
presets/default/tests/test_github_delivery.py               # new
presets/default/tests/test_github_delivery_rules.py         # new
presets/default/tests/test_github_delivery_install.py       # new installed check
presets/default/tests/conftest.py
presets/default/README.md
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Continue with only two repository booleans | Misses effective protection and cleanup blockers. |
| Match raw ruleset patterns locally | Duplicates native applicability and inheritance behavior. |
| Add automatic remote repair to doctor | Violates read-only diagnosis and consumer policy authority. |
| Build the entire executable doctor now | Expands into reliability entry 17. |

## Product handoff

`ready-for-development` requires all rows complete; analysis is not technical approval.
Product handoff updated from the 2026-09-12 implementation instruction; final
human review and merge remain pending.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | PR #149: 0 findings, 100% FR/SC/constraint coverage | Complete |
| Technical approval of plan and tasks | User explicitly requested implementation of these tasks on 2026-09-12 | Complete |
| Reviewed Linear dry-run and synchronization | 2026-09-12: Project 012 and TDS-116–TDS-121 created; post-apply read verified; repeat preview 0 operations and status 0 drift | Complete |
| Every executable task individually assignable and assigned | User assigned T001–T006 to one fresh supervised implementation agent each; TDS-116–TDS-121 retain human assignee fields | Complete |
