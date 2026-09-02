# Feature Specification: Unattended delivery automation

**Feature directory**: `specs/003-delivery-automation`
**Status**: Draft
**Input**: "Automate the repetitive Git and Linear chores of the delivery workflow and fix the frictions found in the first real consumer run"

## Problem and affected users

The first real consumer run (app-maker, 2026-08-31: 21 tasks, 19 PRs
delivered overnight) exposed that the workflow *documents* its automation
but delegates it to memory. Commands print "Optional Hook" blocks a junior
cannot interpret — and following the printed instruction does nothing,
because the hook's own config disables it. Artifacts stay uncommitted
behind "run `/speckit.git.commit` when you want" reminders. Linear stayed
at *Todo* through the entire overnight loop and after the human merged:
the native GitHub integration never moved a task issue and nobody runs the
reconciler mid-flow. The first Linear push failed three times in a row
(no tasks yet, then the tasks template's own example broke the parser,
then an unexplained 401 because the extension was never linked). The flow
pointed the developer to `/speckit.pr` when the natural next step was
`implement`. Merged branches survived because a repository setting the
flow depends on was off and nothing diagnoses it. The self-review closed
19 PRs reusing one empty findings file. The feature PR targeted the GitHub
default branch while the repository's real trunk was another branch.

Affected: junior developers running the flow, the maintainer reviewing the
overnight output each morning, and the unattended mode itself — the
product's primary way of working.

## Desired outcome

The workflow acts instead of reminding. Product-phase commands leave their
artifacts committed. After a clean analysis, `implement` is the only
command a developer needs — it opens the feature gate itself. Linear
mirrors reality at every loop transition and catches up on
merged-while-away work without anyone remembering `push`. Setup gaps —
unlinked Linear, missing platform automation — are diagnosed with named
remediations instead of raw API errors. The flow's own templates and
documentation never break its tools. Morning review over an unbounded
stack of finished PRs is the primary mode and stays unlimited.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - The flow acts instead of reminding (Priority: P1)

A developer runs the product phase (`specify` → `plan` → `tasks` →
`analyze`). Each command ends with its artifacts committed under a
conventional message. No hook announcements, no commit reminders, nothing
to remember.

**Why this priority**: this is the daily surface every developer touches;
it is where the junior-DX promise is won or lost.

**Independent test**: run one product-phase command in a repository with
the distribution installed and inspect the transcript and `git status`.

**Acceptance scenarios**:

1. **Given** a product-phase command completes, **When** the developer
   reads its report, **Then** no "Optional Hook" block appears and the
   feature artifacts are already committed on the feature branch.
2. **Given** a product-phase command that changed nothing, **When** it
   completes, **Then** no empty commit is created and no reminder is
   printed.
3. **Given** unrelated uncommitted files in the working tree, **When** a
   phase command commits its artifacts, **Then** only the feature's own
   artifacts are staged — unrelated files are never swept in.

### User Story 2 - Linear mirrors the unattended run (Priority: P2)

Agents implement tasks overnight. Each observable transition the loop
causes — task started, PR ready — is reflected in Linear by the loop
itself. Next morning the maintainer opens Linear and sees the true state
of every task, including work merged while the loop was not running.

**Why this priority**: stale tracking is the second-most reported failure
of the consumer run and breaks the morning-review mode.

**Independent test**: drive one task through the loop with Linear bound
and watch its issue change state with no human action.

**Acceptance scenarios**:

1. **Given** the loop creates a task branch, **When** the loop proceeds,
   **Then** the task's issue reads *In Progress* without human action.
2. **Given** task PRs were merged while no session was running, **When**
   the loop (or `status`) next runs, **Then** those issues read *Done*.
3. **Given** Linear is not configured in the repository, **When** the
   loop runs, **Then** delivery proceeds normally and the reconciliation
   step is a silent no-op.
4. **Given** the loop self-reviews a task PR, **Then** the review runs in
   a fresh context independent of the orchestrator that directed the
   implementation, and its findings are produced for that review alone.

### User Story 3 - One command to implement (Priority: P3)

After a clean analysis the developer runs `implement`. The command
verifies the feature gate — the draft feature PR — and opens it itself
when missing, then starts the first task.

**Why this priority**: removes the one ordering rule the consumer run
proved nobody should have to know.

**Independent test**: run `implement` right after `analyze` in a
repository with no feature PR and observe the gate open without any other
command.

**Acceptance scenarios**:

1. **Given** a clean analysis and no feature PR, **When** `implement`
   starts, **Then** the draft feature PR opens with the canonical body and
   the loop proceeds to the first task.
2. **Given** the feature PR already exists, **When** `implement` starts,
   **Then** it is reported and never duplicated.

### User Story 4 - Setup diagnoses itself (Priority: P4)

On first run — or after platform drift — the developer learns exactly
what is missing and how to fix it, from the flow itself.

**Why this priority**: every setup gap in the consumer run surfaced as a
cryptic failure deep inside an unrelated command.

**Independent test**: run the flow's diagnosis in a repository with a
known gap and read the remediation it names.

**Acceptance scenarios**:

1. **Given** the Linear extension is present but never linked, **When**
   `push` or `status` runs, **Then** the output says the repository is not
   linked and names `onboard` — never a raw API error.
2. **Given** the repository does not auto-delete merged branches, **When**
   the distribution's doctor runs, **Then** the gap is reported with the
   exact setting to change.
3. **Given** the native Linear↔GitHub automation cannot cover a
   transition the flow relies on, **Then** the documentation states which
   transitions are native and which only the reconciler covers.

### User Story 5 - The flow never breaks its own tools (Priority: P5)

Artifacts generated by the flow are always consumable by the rest of the
flow, and the documentation always matches what the tools accept.

**Why this priority**: each break here costs a debugging detour mid-flow;
three occurred in a single consumer command.

**Independent test**: regenerate the failing artifacts of the consumer
run against the fixed flow and watch them pass.

**Acceptance scenarios**:

1. **Given** a `tasks.md` that keeps the template's instructive format
   section, **When** the Linear parser reads it, **Then** fenced example
   lines are ignored and parsing succeeds.
2. **Given** review findings written exactly as the review command's
   documentation shows, **When** the review closes, **Then** they are
   accepted on the first attempt.
3. **Given** a repository whose real trunk differs from the GitHub
   default branch, **When** the feature PR or the loop resolves its
   delivery base, **Then** the configured trunk is used.

### Edge cases

- A phase command runs while unrelated files (for example a mid-upgrade
  `.specify/` state) are dirty: the artifact commit stays scoped and the
  unrelated files are left exactly as found.
- Linear credentials expire mid-loop: the loop reports it once, keeps
  delivering, and leaves reconciliation to the next run — tracking never
  blocks delivery.
- The trunk configuration is absent: the GitHub default branch applies, as today.
- A fenced block contains a line that looks like a real checked task: it
  is ignored regardless of content.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: Each product-phase command (`specify`, `plan`, `tasks`, and
  the applied remediation of `analyze`) MUST leave the feature's artifacts
  committed on the feature branch under a `type(scope): subject` message,
  staging only those artifacts and skipping cleanly when nothing changed.
- **FR-002**: Workflow commands MUST NOT announce optional hooks. A hook
  whose configuration enables it is executed; anything else is skipped
  silently.
- **FR-003**: `implement` MUST verify the draft feature PR exists before
  the first task and open it (canonical body) when missing, idempotently.
- **FR-004**: The implement loop MUST reconcile Linear at loop start —
  catching state changes that happened while no session ran — and after
  each transition it causes (task branch created, PR ready), applying
  without human interaction and degrading to a silent no-op when Linear is
  not configured.
- **FR-005**: `push` and `status` on a repository whose Linear binding is
  absent or still a placeholder MUST say the repository is not linked and
  name `onboard`, never surface a raw API error.
- **FR-006**: The distribution's doctor surface MUST verify the platform
  dependencies the delivery flow relies on — Linear binding, auto-delete
  of merged branches, merge-commit closure — each reported with a named
  remediation.
- **FR-007**: The documentation MUST state which Linear transitions the
  native GitHub integration actually covers for this flow's PR topology
  (task PRs merging into a feature branch) and which only the reconciler
  covers.
- **FR-008**: The Linear tasks parser MUST ignore fenced code blocks, so
  the tasks template's instructive section never requires manual deletion.
- **FR-009**: The review command's documented findings format MUST be the
  format the command accepts.
- **FR-010**: The feature PR and the implement loop MUST resolve the
  delivery base from an explicit repository configuration when present,
  falling back to the GitHub default branch.
- **FR-011**: The loop's self-review MUST run in a context independent of
  the orchestrator that directed the implementation, producing its
  findings per review — a findings file is never reused across reviews.

### Constraints and boundaries

- **C-001**: Upstream-managed assets (core command templates, the Git
  extension payload, `.specify/scripts`, `.specify/templates`) stay
  untouched. Behavior changes land only through preset-owned surfaces and
  this repository's packages; upstream-rooted frictions are recorded in
  `docs/dogfooding.md` as upgrade candidates, not patched.
- **C-002**: No limit on tasks or PRs in flight. The overnight stack is
  unbounded by explicit product decision (2026-08-31); nothing may pause
  the loop to wait for a human merge.
- **C-003**: `push` remains preview-by-default for humans. Only the
  loop's own invocations apply without asking, and every mutation keeps
  the reconciler's idempotency guarantees.
- **C-004**: No new commands and no new flags beyond what a step needs;
  the command surface stays exactly as `docs/plan.md` lists it.
- **C-005**: Native `specify` and `speckit` command names are unchanged.

## Success criteria *(mandatory)*

- **SC-001**: A full product phase (`specify` → `plan` → `tasks` →
  `analyze`) completes with zero hook announcements and zero commit
  reminders, and `git status` is clean after every phase command —
  measured on this feature's own delivery.
- **SC-002**: After an unattended implement run followed by morning
  merges, every task issue in Linear matches observable reality with no
  human `push`.
- **SC-003**: The consumer run's three first-run failures reproduce as
  named remediations: unlinked Linear names `onboard`; disabled
  auto-delete is named by doctor; no raw GraphQL/HTTP error text reaches
  the user for these cases.
- **SC-004**: A generated `tasks.md` that keeps the template's
  instructive section parses on the first `push`, and a findings close
  following the documentation succeeds on the first attempt.
- **SC-005**: `implement`, run immediately after a clean `analyze`,
  reaches the first task *In Progress* with no other command issued.
- **SC-006**: In a repository whose trunk differs from the GitHub
  default, the feature PR and the first task's delivery target the
  configured trunk.

## Assumptions and dependencies

- **A-001**: This feature is delivered through the workflow it fixes;
  every friction met on the way is recorded in `docs/dogfooding.md`,
  which this feature creates as the standing friction log.
- **A-002**: The Linear extension is installed into this repository from
  its published release (consumer path) and bound to the TDS team, so the
  projection half of the flow is dogfooded here.
- **A-003**: The root cause of hook announcements lives in upstream
  command templates and remains; the distribution neutralizes the
  behavior through its own surfaces (C-001).
- **A-004**: `docs/plan.md` gains this work as an explicit new round, per
  its own rule that new work extends the plan explicitly.

## Source references

- **SRC-001**: DX review of the first consumer run (app-maker session,
  2026-08-31): six reported frictions plus nine found in analysis; root
  causes verified against this repository and the consumer.
- **SRC-002**: `docs/plan.md` — Stage 7.4 ("Linear links natively",
  "push stays the reconciler") and the post-delivery rounds "Native over
  custom" and "Platform enforcement", which this feature completes with
  verification and in-loop reconciliation.
- **SRC-003**: Verified defects: Linear tasks parser has no fence
  handling; review command documents a findings shape its validator
  rejects; consumer repository had auto-delete of merged branches off
  while the loop's closing step assumes it on.
- **SRC-004**: Product decision 2026-08-31: unlimited overnight stacked
  PRs; morning review is the primary mode.
