# tserdeiro/spec-kit — Delivery plan

Amended 2026-08-03. This plan derives from the product vision in
[`vision.md`](vision.md); on conflict, the vision wins.
It supersedes the previous 1,291-line plan and the design contracts
`spec-kit-linear.md` and `spec-kit-code-review.md`, which are deleted;
each package's README is now its reference.

**Status: stages 0–5 delivered** and accepted against the published
artifacts on 2026-08-04; the acceptance evidence lives under
[`validation/`](../validation/). Stage 6 is in progress — the first feature
delivered through the product's own workflow. New work measures itself
against the vision and extends this plan explicitly.

## Product

An ultra-light, portable SDD distribution composed on top of pinned
`github/spec-kit` v0.13.0. It covers the whole daily delivery cycle —
business need → spec → plan → tasks → implementation → review → merge — for
features, bugs, and chores, with Linear as the tracking system and a single
agentic code-review command. Three role bundles: `product`, `developer`,
`reviewer`. It must work completely with every agent upstream supports.
DX is the priority; nothing speculative.

## Non-negotiable principles

- Compose upstream; never fork or reimplement the Specify CLI. Exact
  versions pinned in `versions.lock.yml`; upgrades explicit and reviewed.
- Repository artifacts are durable truth. Linear is a projection and never
  writes feature artifacts.
- Zero runtime dependencies in first-party extensions; commands ship as
  `.md` + bash/PowerShell launchers so every upstream agent works.
- Human-only product approval, PR approval, and merge. The review command
  can never approve or merge.
- Security: treat model output and remote content as potentially hostile;
  never commit secrets or operator identity; preview remote mutations;
  never rewrite history or delete remote resources automatically; run
  deterministic tests independently of agent-declared success.

## Command surface (the whole product)

Native upstream: `specify` plus `/speckit.*` (constitution, specify,
clarify, plan, checklist, tasks, analyze, implement, converge).

`spec-kit-linear` extension:

- `onboard` — one-shot binding of repository ↔ Linear team; resolves every
  ID itself.
- `push` — projects current feature state (`--dry-run` preview, `--apply`
  to write, idempotent): Project at plan, Issues at tasks, task/PR/review
  states through delivery, and work-item states for Issue-key branches
  (bugs and chores).
- `status`, `doctor` (with `--fix`), `completions`.

`spec-kit-code-review` extension:

- `speckit.code-review` — the single review command. It detects its
  context: on a working tree it reviews the pending diff; on a PR it
  reviews the anchored candidate and can `--publish`. The packet/findings
  two-phase protocol is internal, never user-facing. It warns when the
  diff exceeds the review budget. Delegates to pinned OCR; fails closed.
- `doctor` (with `--fix`) — environment diagnosis; `--fix` installs the
  pinned engine into the distribution's data root and verifies its digest
  against the pin the extension ships. `completions`.

Anything not listed is out of surface. Flags follow the same rule: a
command exposes only what its step needs.

## Delivery conventions

- One branch per task; PRs open as `draft`; bodies use the canonical
  `.github/PULL_REQUEST_TEMPLATE.md`.
- Review budget: a reviewed PR stays under ~400 authored executable lines;
  larger tasks split into stacked PRs. This is a convention plus a warning
  in the review command, not a subsystem.
- The developer self-reviews with `speckit.code-review` before
  `ready for review`; the reviewer runs the same command plus human review
  before approving.

## Stages

Sequential. Done means working end-to-end and verified, not merely
specified — and every stage below is done:

| Stage | Accepted | Evidence |
| --- | --- | --- |
| 0 — Truth repair | 2026-08-03 | retirement notices in `specs/001`, lock cleanup |
| 1 — Prune to the vision | 2026-08-03 | structural surface tests; both suites green |
| 2 — One-path installation | 2026-08-04 | `validation/clean-install-acceptance.md` |
| 3 — Workflow steps 4–7 | 2026-08-04 | `validation/linear-stage3-acceptance.md` |
| 4 — Roles | 2026-08-04 | `validation/bundles-stage4-acceptance.md` |
| 5 — Bugs and chores | 2026-08-04 | `validation/linear-stage5-acceptance.md` |
| 6 — Guided flow | in progress | the feature's own `specs/` artifacts and PRs |

### Stage 0 — Truth repair (done)

- Reconcile `specs/001-repository-file-sync` with reality: its deliverables
  were deleted in `0d1e494` while `tasks.md` still claims 10/10 with
  evidence; amend `tasks.md`, `plan.md`, `quickstart.md`, and the README
  sections that still describe the removed scripts.
- Remove the orphan `repository_files.pull_request_template` entry from
  `versions.lock.yml`.
- Remove versioned generated state (`.specify/linear-push-plan.json`,
  `.specify/linear-seed-plan.json`) and package caches from the tree.

### Stage 1 — Prune to the vision (done)

- Code review: collapse `run` + `local` into `speckit.code-review`; delete
  `--engine`, `upgrade`, `rules`, `status`, and the ceremony flags
  (`--yes-i-reviewed-this`, `--require-sdd-context`, `--allow-candidate-rules`,
  `--republish`, `--allow-closed`); reduce the budget subsystem to the
  warning above.
- Linear: delete `seed`, `propose`, `upgrade`, `install`, the git-hook
  machinery, the `reconcile.*` config block, phase milestones, and the
  persisted-plan protocol.
- Distribution: reduce release scripts to reproducible archive + digest;
  reduce the OCR supply-chain ledger to the single binary digest `doctor`
  verifies.
- Exit: each extension has at most 5 commands and ~15 flags; tests green;
  a real Linear apply and a real review still work.

### Stage 2 — One-path installation (done)

- Publish extension releases; a consumer never installs from this checkout.
- One documented path from zero to working — install CLI, init, add
  extensions, install OCR — automated where upstream allows, with
  `doctor --fix` closing the gaps.
- `docs/` gets the single install/usage/update guide. (Later folded
  into the README as the single front door.)
- Exit: a new machine reaches a working review and Linear push following
  one page.

### Stage 3 — Workflow completion, steps 4–7 (done)

- Branch per task; draft PR; Linear state per step: in progress at
  implement, draft PR opened, ready for review after self-review, closed on
  approval/merge.
- Stacked-PR convention documented in the task and PR templates.
- Exit: one feature driven through all 7 vision steps with its states
  visible in Linear.

### Stage 4 — Roles (done)

- `product`, `developer`, and `reviewer` bundles plus the `default` preset;
  template overrides fold into the preset (no duplicated templates).
- Exit: each role installs its bundle and runs only its part of the flow.

### Stage 5 — Bugs and chores (done)

- Short paths per the vision: an Issue born in Linear → an Issue-key branch
  (`wor-123-slug`) → fix or change → PR → review, with states derived like
  feature tasks and the harness never creating or editing Issue content.
- Bugs use upstream's bundled `bug` extension (assess → fix → test), its
  reports traveling in the PR as evidence; the developer bundle ships it.

### Stage 6 — Guided flow (in progress)

The middle of the workflow (steps 4–5) is where an inexperienced developer
gets lost: branch naming, opening the draft PR, filling the canonical body.
This stage makes the flow tell — and do — the next step. It is also the
first feature **dogfooded through the product's own workflow**: one spec,
one task per point below, one branch and one draft PR per task, states in
Linear, self-review before ready, human review and merge.

- 6.1 The tasks template instructs the implementing agent to create the
  task branch (`NNN-T###-slug`) when it starts a task; today the naming is
  a documented convention nobody enforces at start. (`default` preset.)
- 6.2 `/speckit.pr` — a preset agent command that guarantees the branch
  invariant (validates the name, creates the branch if missing), fills the
  canonical PR body from the feature artifacts (tracker, evidence, `Stack`
  line), and opens the draft PR with `gh`. No CLI code.
- 6.3 `status` gains a `NEXT` column: the suggested next action per task
  and work item, derived from the same observable state the projection
  already computes. Output only — no new command, no new flag.
- 6.4 `/speckit.doctor` — a preset agent command that runs both
  extensions' doctors and summarizes one result with remediations.
- 6.5 `scripts/release/publish.sh` — the maintainer release in one step:
  tags, builds, lock digests, push, GitHub releases.
- Exit: every point lands through the seven steps it improves, and the
  frictions each point closes are felt (and recorded) while delivering it.

## Releases

`versions.lock.yml` pins upstream and each extension (tag, commit, digest).
Releases, commits, and publication are human-controlled. Nothing follows
upstream automatically.

## References

- Product vision (authoritative): [`vision.md`](vision.md)
- Spec Kit: https://github.com/github/spec-kit
- open-code-review (OCR): https://github.com/alibaba/open-code-review
- Linear GraphQL API: https://linear.app/developers/graphql
- Packages: [`packages/spec-kit-linear`](../packages/spec-kit-linear),
  [`packages/spec-kit-code-review`](../packages/spec-kit-code-review)
