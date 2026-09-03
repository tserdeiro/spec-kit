# Feature Specification: Delivery discipline

**Feature directory**: `specs/004-delivery-discipline`
**Status**: Draft
**Input**: "Harden the delivery loop against the frictions recorded in docs/dogfooding.md after delivering 003-delivery-automation: every entry marked ronda 004 plus the three rules to document (4, 10, 14)"

## Problem and affected users

Delivering `003-delivery-automation` through its own loop (2026-08-31 →
09-02) produced sixteen PRs merged by the agent with zero human reviews,
two parallel stacks whose task ledgers diverged, a fix propagated by hand
to the PRs stacked on it, a branch carrying the wrong task number, a task
at seven times its forecast and another that widened its own budget inside
the PR that broke it, reviews that pushed a 190-line resolver where three
lines of shell sufficed, a task that edited the product contract to
justify its design, a reviewer stalled ten minutes on a 120 KB packet, a
plain `git revert` that failed the naming check, and a release whose
published digests nothing re-verifies. Installing a second agent then
showed the doctor's skill mirror overwriting one agent's command renders
with another's, the installer leaving untracked cache and
virtual-environment noise, and `implement` still announcing hooks the
product phases already silence.

Affected: the maintainer reviewing an overnight stack each morning, the
agents running the loop unattended, and every consumer repository that
installs the distribution on more than one agent. `docs/dogfooding.md`
records each friction with its agreed solution; this feature delivers the
entries marked *ronda 004* and documents rules 4, 10 and 14.

## Desired outcome

The loop is disciplined by construction. It adapts to the tooling the
feature branch has instead of requiring it, keeps one linear stack whose
ledger never diverges, carries fixes through the stack itself, refuses a
branch that names the wrong task, stops when a task outgrows its forecast,
and never merges: the human merges root-first, or asks. The review reads
the engineering principles from one rules file shared by every agent,
questions a mechanism before asking for its edge cases, verifies claims
instead of repeating experiments, and blocks any task PR that touches the
product contract. Worktrees, reverts, and published assets stay
verifiable. A second agent installs with its own command renders intact
and no installer noise.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - One stack, carried by the loop, merged by a human (Priority: P1)

The maintainer starts `implement` on a feature and goes to sleep. The loop
finds out which delivery tools the feature branch has and works with that
set. Every task stacks on the previous one, a fix made low in the stack
reaches every PR above it without help, a branch with the wrong task
number never opens a PR, and in the morning the maintainer finds every PR
ready with its fresh review closed — and nothing merged.

**Why this priority**: the overnight stack is the product's primary mode;
each of these frictions cost a manual repair or a skipped human gate in
the previous round.

**Independent test**: drive a feature with at least three tasks through
the loop unattended and inspect the PR bases, the ledger on the last PR,
the merge commits, and the absence of agent merges.

**Acceptance scenarios**:

1. **Given** a feature branch with neither the Linear nor the review
   extension installed, **When** the loop starts, **Then** it reports the
   tooling set once and still delivers every task — branch, draft PR,
   independent fresh review with its findings recorded on the PR, ready
   for review — with reconciliation omitted silently.
2. **Given** a ready, unmerged task PR, **When** the next task starts,
   **Then** its branch is created from that PR's head and its `Stack:`
   line names it; the loop never opens a second stack from the feature
   branch, and the ledger on the stack's last PR shows every delivered
   task checked.
3. **Given** a fix committed on a task branch that has PRs stacked on it,
   **When** the loop continues, **Then** each stacked branch receives the
   fix as an explicit merge commit with a conventional subject, in stack
   order, and is pushed — no PR stays red for want of a fix already made.
4. **Given** a checked-out branch whose task number is not the task being
   delivered, **When** the PR command runs, **Then** it stops naming the
   branch's task and the expected one, and opens nothing.
5. **Given** every task of the run ready for review, **When** the run
   ends, **Then** no PR has been merged by the agent, and the loop's
   closing guidance and the README state that stacks merge root-first and
   why.
6. **Given** the human explicitly asks the agent to merge in the
   conversation, **When** it merges, **Then** it merges root-first with
   merge commits, deleting each branch, after pruning stale worktrees.

### User Story 2 - The task stops at its budget and the review questions complexity (Priority: P2)

An implementer sees a task outgrow its forecast and stops instead of
absorbing it. The reviewer, on any agent, reads the same engineering
principles the implementer follows, asks whether a mechanism is needed
before asking for its edge cases, and verifies claims instead of
re-running experiments.

**Why this priority**: the previous round's worst outcomes — a 7× task, a
budget widened in its own PR, a review-driven 190-line resolver — came
from the agent's process, not from the tools.

**Independent test**: run a task whose diff passes twice its forecast and
watch it stop; read the rules file a fresh consumer receives and the
reviewer brief the loop hands out.

**Acceptance scenarios**:

1. **Given** a task whose authored executable lines pass twice its
   forecast, **When** the implementer measures the diff before opening or
   readying the PR, **Then** it stops and returns to the human with a
   diagnosis — what does not fit and a proposed split — and no PR opens
   as-is.
2. **Given** a PR that exceeds its task's budget, **When** anyone proposes
   widening the forecast inside that PR, **Then** the loop refuses: a
   budget is amended only by a human in the ledger, never in the PR that
   breached it.
3. **Given** a consumer repository with no review rules file, **When** the
   doctor runs in fix mode, **Then** the distribution's base rules file is
   written: over-engineering and speculative abstraction are major
   findings, a new runtime dependency is a blocking finding.
4. **Given** the loop hands a review to a fresh context, **When** the
   reviewer reads its brief, **Then** the brief tells it to verify the
   implementer's claims rather than repeat its experiments, to ask
   whether a mechanism is needed before asking for an edge case, and to
   review a packet above 100 KB file by file.
5. **Given** this repository, **When** an implementing agent looks for the
   engineering principles, **Then** `AGENTS.md` is the single source and
   `CLAUDE.md` imports it instead of duplicating it.

### User Story 3 - The product contract is protected deterministically (Priority: P3)

A task PR that touches the feature's `spec.md` or the constitution is
blocked by the review command itself, whatever the reviewing agent
thinks; the feature PR, where the contract legitimately changes, is not.

**Why this priority**: a prompt rule already forbade it and was broken
in the previous round; only a deterministic check holds.

**Independent test**: review a task PR that edits a protected path and a
feature PR that edits the same path; compare the verdicts.

**Acceptance scenarios**:

1. **Given** a task PR — one whose base is a feature branch — whose diff
   touches a protected path, **When** the review command runs, **Then** it
   emits an automatic blocking finding naming the path and the verdict is
   changes-requested, regardless of the agent's own findings.
2. **Given** a PR based on the delivery trunk that touches the same path,
   **When** the review command runs, **Then** no automatic finding is
   emitted.
3. **Given** a review configuration without the key, **When** the command
   runs, **Then** the defaults apply: every feature's `spec.md` and the
   constitution.

### User Story 4 - Worktrees, reverts, and published assets stay verifiable (Priority: P4)

A developer working in a worktree gets the same Linear behavior as in the
main checkout; feature closure no longer trips on stale worktrees; a
revert passes the naming check like any other commit; and the published
release is re-verified asset by asset against the lock.

**Why this priority**: each is a small, closed gap that broke a delivery
step in the previous round.

**Independent test**: run status from a worktree without local Linear
files; revert a delivered change through the loop; run published-mode
conformance against an altered digest.

**Acceptance scenarios**:

1. **Given** a worktree of a bound repository with no local Linear
   configuration or credentials file, **When** status or push runs there,
   **Then** it resolves the main checkout's files and behaves as in the
   main checkout; files present in the worktree win.
2. **Given** a stale worktree record for a branch about to be deleted at
   feature closure, **When** closure runs, **Then** it prunes stale
   records first and the deletion succeeds.
3. **Given** a delivered change to undo, **When** the loop reverts it,
   **Then** the revert travels in a task branch and PR whose commit
   subject follows `revert(scope): subject`, never the tool's default.
4. **Given** published-mode conformance, **When** it runs, **Then** it
   recomputes the digest of every published asset the lock references and
   fails when any differs.
5. **Given** the preset documentation, **When** a contributor reads it,
   **Then** it states that every executable block in the preset's commands
   is POSIX shell and that conformance executes them with `sh`.

### User Story 5 - A second agent installs cleanly (Priority: P5)

A team adds a second agent to an initialized repository by following the
README; the doctor mirrors the skills without damaging either agent's own
command renders, adds the ignore entries the installer forgets, and
`implement` runs as silently as the product phases.

**Why this priority**: multi-agent repositories are the norm the vision
promises; the previous round proved the mirror unsafe.

**Independent test**: install two agents, run the doctor in fix mode, and
diff each agent's core skills against its own render plus the preset
layers.

**Acceptance scenarios**:

1. **Given** two installed agents, **When** the doctor mirrors in fix
   mode, **Then** extension and preset skills are copied whole and each
   core command skill equals that agent's own render plus the preset's
   layers — never another agent's render.
2. **Given** the README, **When** a team adds an agent, **Then** it finds
   the steps: install the integration, run the doctor's fix, commit.
3. **Given** a consumer whose ignore file lacks the installer's cache
   directories or the extension payload virtual environments, **When** the
   doctor runs in fix mode, **Then** the entries are added; read-only mode
   reports them; a second fix run changes nothing.
4. **Given** `implement` runs with optional hooks registered, **When** it
   reaches a hook point, **Then** no hook announcement appears; a hook
   its configuration enables runs silently.

### Edge cases

- The feature branch has no extension at all: the loop still delivers
  every task; only tracking and the deterministic contract check are
  absent, and the tooling report says so once.
- Fix propagation meets a conflict on a stacked branch: the loop stops
  naming that branch; nothing is forced and nothing below it is touched.
- The human merges the open stack root-first while the loop is between
  tasks: the next task finds no open task PR and branches from the
  feature branch.
- The user names a task that is not the first unchecked one: the branch
  check compares against the named task; the loop itself always takes the
  first unchecked task.
- A task's forecast is missing from the ledger: the review budget is the
  stop line.
- The review budget is below twice the forecast: the stop line is
  whichever comes first.
- The feature PR touches a protected path: allowed, since its base is
  the delivery trunk.
- A worktree has its own Linear files: they win over the main checkout's.
- A revert targets a merge commit: it reverts against the base branch's
  parent, with the same conventional subject rule.
- An ignore entry is already covered by a broader existing pattern: it is
  not duplicated.
- Only one agent is installed: the mirror step is skipped silently, as
  today.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: The loop MUST determine, at start, which delivery tools the
  feature branch has and use that set for every task of the run: without
  the Linear extension, reconciliation is omitted silently; without the
  review extension, every task PR is still reviewed by a fresh,
  independent context that records its findings on the PR. A task MUST
  NOT install or remove an extension.
- **FR-002**: After a fix lands on a task branch that has PRs stacked on
  it, the loop MUST carry the fix into every branch stacked on it, in
  stack order, as explicit merge commits with a conventional subject, and
  push each; a conflict stops the loop with a report and is never forced.
- **FR-003**: The loop MUST keep one linear stack per feature: a task
  branches from the head of the most recent ready, unmerged task PR
  (declared in its `Stack:` line) or from the feature branch when none is
  open; it MUST NOT start a task that would open a second stack.
- **FR-004**: The PR command MUST verify that the task number in the
  branch name is the task being delivered — the task the user named, else
  the first unchecked task of the ledger on that branch — and stop,
  naming both, on a mismatch.
- **FR-005**: The loop MUST NOT merge. A run ends with every task PR
  ready for review and its fresh review closed; merging is a human
  decision, done root-first by the human or by the agent only when the
  human explicitly asks in the conversation — then with merge commits,
  root-first, deleting each branch. The loop's closing guidance and the
  README MUST state the root-first rule and its reason: retargeting a
  stacked PR is an edit event that triggers no workflow, while merging
  leaf-first re-runs every check at every step.
- **FR-006**: When a task's authored executable lines pass twice its
  forecast — or the review budget, whichever comes first — the
  implementer MUST stop before opening or readying the PR and return to
  the human with a diagnosis: what does not fit and a proposed split. A
  task's forecast or budget MUST NOT be amended in the PR that exceeds it.
- **FR-007**: The distribution MUST ship a base review rules file that
  encodes the engineering principles with severities — over-engineering
  and speculative abstraction are major findings; a new runtime
  dependency is a blocking finding — and the doctor's fix mode MUST write
  it into a consumer that has none.
- **FR-008**: In this repository, `AGENTS.md` MUST be the single source of
  the operating contract for implementing agents, and `CLAUDE.md` MUST
  import it rather than duplicate it.
- **FR-009**: The loop MUST hand every fresh review a standard brief:
  verify the implementer's claims instead of repeating its experiments;
  ask whether a mechanism is needed before asking for an edge case; review
  a packet above 100 KB file by file.
- **FR-010**: The review command MUST honor a configured list of protected
  paths, defaulting to every feature's `spec.md` and the constitution.
  When a PR whose base is a feature branch touches a protected path, the
  command MUST emit an automatic blocking finding naming the path and
  derive the verdict changes-requested; a PR based on the delivery trunk
  is exempt.
- **FR-011**: The Linear extension MUST resolve its configuration and
  credentials file from the repository's main checkout when the worktree
  it runs in lacks them; files present in the worktree win.
- **FR-012**: Feature closure MUST prune stale worktree records before
  deleting branches, on both the loop's closing step and the on-request
  merge path.
- **FR-013**: The loop MUST provide a revert path: a delivered change is
  undone through a task branch and PR whose commit subject follows
  `revert(scope): subject`, so it passes the repository's naming check.
- **FR-014**: Published-mode conformance MUST recompute the digest of
  every published asset the lock file references and fail on any
  mismatch.
- **FR-015**: The preset documentation MUST state that every executable
  block in its commands is POSIX shell — `set -e`, no pipeline that
  needs `pipefail` — and that conformance executes those blocks with
  `sh`.
- **FR-016**: The doctor's skill mirror MUST copy extension and preset
  skills whole and, for the core commands (specify, plan, tasks, analyze,
  implement), MUST append the preset's registered layers to each
  integration's own render; it MUST NOT overwrite one integration's render
  with another's.
- **FR-017**: The README MUST document adding a second agent to an
  initialized repository: install the integration, run the doctor's fix
  mode, commit the result.
- **FR-018**: The doctor's fix mode MUST add the installer's cache
  directories and the extension payload virtual environments to the
  consumer's ignore file when they are not already covered; read-only mode
  MUST report them as missing.
- **FR-019**: The `implement` command MUST NOT announce optional hooks; a
  hook its configuration enables runs silently, as the product phases
  already do.

### Constraints and boundaries

- **C-001**: Upstream-managed assets (core command templates, the Git
  extension payload, `.specify/scripts`, `.specify/templates`) stay
  untouched. Behavior lands only through the preset, this repository's
  packages, its conformance scripts, and its documentation; the
  upstream-rooted entries of `docs/dogfooding.md` (18, 22–25) stay
  recorded, not patched.
- **C-002**: No new commands. New flags only where a step needs them; a
  new configuration key is acceptable where a command already reads its
  configuration. The command surface stays as `docs/plan.md` lists it.
- **C-003**: The loop never waits for a human merge: one linear stack
  keeps it unblocked; a budget stop is a return to the human with a
  diagnosis, not a wait.
- **C-004**: This feature's own `spec.md` is not modified by any of its
  tasks. Findings that change product intent return to the feature PR.
- **C-005**: Package changes of this round reach this repository only
  when published; the round's own loop runs on the installed releases
  (linear 0.11.0, code-review 0.3.0) and the dev-installed preset, whose
  changes apply as each task lands.
- **C-006**: The review never approves or merges; native `specify` and
  `speckit` command names are unchanged.

## Success criteria *(mandatory)*

- **SC-001**: This feature's own delivery runs as one stack: every task PR
  stacks on its predecessor, the last PR's ledger shows every task
  checked, and no fix is propagated by hand.
- **SC-002**: The loop ends this round with zero PRs merged by the agent
  and every task PR ready for review with its fresh review closed.
- **SC-003**: A task PR that modifies a protected path receives the
  automatic blocking finding and the changes-requested verdict; the same
  change in a PR based on the trunk receives none.
- **SC-004**: No task in this round passes twice its forecast without
  stopping, and no forecast changes inside the PR that breached it.
- **SC-005**: Published-mode conformance verifies the digest of every
  published asset the lock references and fails when one is altered.
- **SC-006**: With two agents installed, one doctor fix run leaves each
  core skill equal to that agent's own render plus the preset layers, and
  each extension and preset skill identical across agents.
- **SC-007**: From a worktree without local Linear files, status and push
  behave exactly as in the main checkout.
- **SC-008**: The `implement` transcripts of this round contain zero hook
  announcements.
- **SC-009**: A consumer missing the ignore entries receives them in one
  doctor fix run; a second run changes nothing.

## Assumptions and dependencies

- **A-001**: This feature is delivered through the workflow it hardens;
  every friction met on the way is appended to `docs/dogfooding.md`, and
  the log's statuses graduate in the closing documentation task —
  including entry 20, whose test invocation the README already documents.
- **A-002**: Release lag: the Linear and review package changes are
  consumed here only after publication, so their requirements are proven
  by tests and fixtures during the round and by this repository once
  published. The review package's tasks come first in the stack so the
  maintainer can publish it mid-round if wanted.
- **A-003**: "No parallel stacks" (entry 3) is read as one linear stack
  per feature: the next task branches from the head of the latest ready,
  unmerged task PR, whether or not the ledger declares a dependency on
  it. The feature PR review is where to correct this reading.
- **A-004**: Without the review extension, the fresh reviewer records its
  findings as a comment on the task PR; the loop fixes them on the branch
  as it would a command's findings.
- **A-005**: `docs/plan.md` gains this round as an explicit entry, per its
  own rule that new work extends the plan explicitly.
- **A-006**: A GitHub ruleset requiring approval on `NNN-*` branches
  stays off in this single-maintainer repository — GitHub does not count
  the PR author's approval — and is documented as the step to take once a
  second reviewer or a bot identity exists.
- **A-007**: This round bumps the preset, both extensions, and the
  bundles; publication remains human, from the trunk, after the feature
  merges.

## Source references

- **SRC-001**: `docs/dogfooding.md` — entries 1–3, 5–9, 11, 13, 15, 17,
  19, 21 (*ronda 004*) and rules 4, 10, 14; the record of the 003
  delivery and its correction round (2026-08-31 → 09-03).
- **SRC-002**: `specs/003-delivery-automation/` — the precedent round;
  its correction phase (T016–T019) is the evidence behind entries 7, 8,
  12, 13 and 16.
- **SRC-003**: `docs/plan.md` — "Delivery conventions" and the
  "Unattended delivery automation" round entry this feature extends.
- **SRC-004**: Operating brief of 2026-09-03: orchestrator-and-reviewer
  mode, the loop never merges, the 400-line budget with the 2× stop.
