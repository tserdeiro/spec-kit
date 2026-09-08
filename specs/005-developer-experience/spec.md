# Feature Specification: Developer experience

**Feature directory**: `specs/005-developer-experience`
**Status**: Draft
**Input**: "Deliver the developer-experience round agreed in docs/dx.md: the
loop's mechanism leaves the prose. The default preset ships its inline
shell blocks as scripts (task-base, budget-stop, stack-propagate,
pr-create, the on-request root-first merge, the ledger check) and
replaces the implement command instead of appending to it; the linear
extension declares runtime events (session_start context and reconcile,
post_tool_use reconcile after git push and gh pr) and its NEXT column
names commands; the code-review extension declares pre_tool_use guards
(commit-subject convention, force-push, --delete-branch, protected paths
on task branches) and drops the after_implement hook; completions leaves
both extensions; /speckit.doctor drives onboarding; the README opens with
the day in four commands; upstream pull requests turn the neutralized
behaviors into deletions. Suggested short name: developer-experience."

## Problem and affected users

Round 004 finished the policy layer: a stack, budgets, gates, derived
states. The mechanism layer is not finished — it lives in prose the agent
has to remember and in shell blocks it has to copy and edit by hand.
`docs/dogfooding.md`'s sections D and G, plus the four hand repairs the
v1.0.4 bump took (a stale dev-installed preset re-rendered
`speckit-doctor`; `init --force` orphaned the second integration;
reinstalling it lost the preset's appends; an ignore entry was missing),
all show the same single failure: the agent forgot, broke, or
hand-mirrored something a machine should have guaranteed instead.

- `speckit-implement` renders about 32 KB; roughly half of it is the
  upstream base procedure that the round's own append later tells the
  agent to disregard.
- Linear only reconciles when the agent remembers to run `push --hook`, at
  three separate points inside the loop's own prose; nothing else
  triggers it.
- The four hard rules — conventional commit subjects, no force-push, no
  explicit branch deletion on merge, no edits to a protected path from a
  task branch — are caught by CI or by review, after the commit or the
  edit already happened.
- Six blocks of 22 to 110 lines travel inside command prose; the agent is
  expected to "replace only the literal" inside them, and a weaker agent
  breaks them.
- A junior reads about 700 words of golden rules to learn a flow that,
  task by task, is four commands.

Affected: every developer and reviewer running the loop, the unattended
agent executing it overnight, and every consumer repository installing
this distribution.

## Desired outcome

The loop's mechanism leaves the prose. Every repeatable procedure it
performs runs as a script the command invokes, not a block the agent
copies and edits; Linear reports what's next and reconciles on its own, at
the moments that call for it, without a phrase telling the agent to
trigger it; the four hard rules block before the action they'd otherwise
allow, not after; `implement` is one coherent procedure instead of an
upstream base the round's own text tells the agent to ignore; a fresh
consumer's remaining setup comes from one command, in one fixed order; and
the README leads with the four commands a day actually takes. What today
depends on an agent remembering, copying correctly, or mirroring by hand
becomes something the tooling itself guarantees.

## User scenarios and acceptance *(mandatory)*

### User Story 1 - The loop's repeatable steps run as scripts, not prose the agent edits (Priority: P1)

An implementer runs a task through the loop, and the doctor onboards a
consumer. Every repeatable procedure — setting up a task's branch,
checking whether a task has passed its budget, propagating a fix up a
stack, opening a pull request, merging a stack root-first on request,
checking a ledger's completeness, mirroring skills across installed
integrations, and adding the installer's ignore entries — executes as a
script the owning command calls, not a block of shell the agent has to
keep intact inside its own context.

**Why this priority**: the largest and most foundational change of the
round — it removes the fragile "replace only the literal" pattern a
weaker agent breaks, and every later story in this feature builds on
commands that call scripts instead of embedding shell.

**Independent test**: invoke each script directly against fixtures,
without going through the full loop, and confirm it produces the result
the owning command relies on; read each command's own prose and confirm
none of the eight procedures is authored there as inline shell.

**Acceptance scenarios**:

1. **Given** a task ready for its setup, budget check, stack-fix
   propagation, PR creation, root-first merge, or ledger check, or a
   doctor run ready to mirror skills across installed integrations or add
   the installer's ignore entries, **When** the owning command reaches
   that step, **Then** it invokes a dedicated script for that step
   instead of running shell authored inline in the command's own text.
2. **Given** a script for one of these eight procedures, **When**
   conformance runs, **Then** it invokes the script directly against
   fixtures and reports that script's own pass or fail, not the pass or
   fail of a block copied out of a command's prose.
3. **Given** a consumer that has this preset dev-installed, **When** a
   command runs one of the eight procedures, **Then** the behavior
   matches what conformance verified against the same script file.

### User Story 2 - Linear names what's next and reconciles on its own (Priority: P2)

A developer, or the unattended agent, starts a session on a branch bound
to a feature and finds, without asking, the branch, the feature, the
first unchecked task, every open task pull request, and a command to run
next. After a push or a pull-request action, Linear is already
reconciled by the time anyone looks.

**Why this priority**: replaces the friction of an agent that must
remember to run `push --hook` at three separate points, and of a "next
step" that today can read as a manual instruction instead of a runnable
command.

**Independent test**: start a session on a feature or task branch with
Linear configured and read the greeting before typing anything; run
`git push` or a `gh pr` action and check Linear's state immediately
after, with no reconcile command anywhere in the transcript; read the
next-step field of `status` across a few different states.

**Acceptance scenarios**:

1. **Given** a session starting on a feature, task, or work-item branch,
   with Linear configured, **When** the session begins, **Then** a
   context line names what applies to it, before the agent does anything
   else — for a feature or task branch: the branch, the feature, the
   first unchecked task, every open task pull request, and the next
   command to run; for a work-item branch: the issue, its derived state,
   and the next command to run.
2. **Given** the agent has just run `git push` or a `gh pr create`,
   `ready`, or `merge` command, **When** that command finishes, **Then**
   Linear has already reconciled, with no separate reconcile instruction
   anywhere in the loop's own text.
3. **Given** any state the session-start context line or the `status`
   command reports, **When** it names what to do next, **Then** it names
   a runnable command, or explicitly says to wait for a human merge —
   never a manual gesture such as "create the branch."
4. **Given** a branch with no Linear configuration, **When** a session
   starts, or a push or pull-request action runs, **Then** the context
   line and the reconciliation are silently absent, with no error.

### User Story 3 - The four hard rules block before they run (Priority: P3)

An agent attempts a commit with a non-conventional subject, a
force-push, a pull-request merge that deletes its branch explicitly, or
an edit to a protected path from a task branch. Each is refused at the
moment it's attempted, naming the fix — not caught later by CI or by
review.

**Why this priority**: dx.md names this among the round's top frictions —
hard rules "caught by CI or by review, after the fact" — a correctness
and safety story that follows directly once commands call scripts and
Linear's events are in place.

**Independent test**: attempt each of the four actions on a task branch,
on a coding agent that supports runtime events, and confirm each is
refused before it takes effect, with the fix named; attempt the same on
an agent without event support and confirm the doctor reports that
degradation explicitly.

**Acceptance scenarios**:

1. **Given** a commit whose subject does not match the repository's
   `type(scope): subject` convention, **When** the agent attempts it,
   **Then** it is refused before it is created, naming the convention it
   must follow.
2. **Given** any form of a force-push, **When** the agent attempts it,
   **Then** it is refused before it reaches the remote.
3. **Given** a pull-request merge invocation that requests explicit
   branch deletion, **When** the agent attempts it, **Then** it is
   refused before the merge happens.
4. **Given** an edit or a write to a protected path — a feature's
   `spec.md`, or the constitution — on a task branch, **When** the agent
   attempts it, **Then** it is refused before the write lands, naming the
   protected path.
5. **Given** a coding agent with no runtime-event support, **When** any
   of the four actions above is attempted there, **Then** nothing blocks
   it beforehand, and the doctor states that degradation explicitly
   rather than staying silent.

### User Story 4 - `implement` is one procedure, not a base the round tells the agent to ignore (Priority: P4)

An agent opens the `implement` command and reads one coherent procedure
for the delivery loop, with nothing telling it to disregard a paragraph
that appears earlier in the same document.

**Why this priority**: the direct fix for the ~32 KB render where roughly
half is an upstream base procedure the round's own append contradicts;
lower priority than the mechanism and event stories because it changes
how the loop reads, not what it does.

**Independent test**: read the rendered `implement` command and confirm
no instruction tells the agent to disregard another instruction already
present in the same document; compare its size before and after.

**Acceptance scenarios**:

1. **Given** the `implement` command as installed, **When** an agent
   reads it, **Then** it finds a single procedure for the delivery loop,
   with no upstream base text that a later paragraph overrides or tells
   it to ignore.
2. **Given** the `tasks` command's own local customization, **When** it
   would otherwise contradict its base procedure the same way, **Then**
   it is likewise a single coherent procedure rather than a base plus a
   contradicting append.

### User Story 5 - One command drives onboarding, and the README opens with the day in four commands (Priority: P5)

A fresh consumer installs their role's bundle and runs one command. It
lists everything still missing, in the same fixed order every time, and
fixes whatever it can fix mechanically. Reading the README, they see
their day expressed as four commands before anything else.

**Why this priority**: dx.md's own framing — a junior reads about 700
words of golden rules to learn a flow that, task by task, is four
commands — is the round's junior-facing payoff, delivered last because it
documents and onboards onto behavior the earlier stories already built.

**Independent test**: on a freshly bundle-installed, unconfigured
consumer, run the doctor and read its gap list's order; run its fix mode
and confirm it resolves the mechanical gaps; read the README's opening
section.

**Acceptance scenarios**:

1. **Given** a consumer that installed a role bundle and configured
   nothing yet, **When** the doctor runs, **Then** it reports every
   remaining gap in this order: GitHub CLI authentication, the Linear API
   key, the Linear onboarding binding, the review engine installation,
   and the repository's GitHub delivery settings.
2. **Given** the same consumer, **When** the doctor runs in fix mode,
   **Then** every gap in that list that can be resolved mechanically is
   resolved, and the GitHub delivery settings are still only reported:
   this round's doctor never changes them, and applying them is the
   releases round's scope.
3. **Given** the README, **When** a reader opens it, **Then** the day's
   workflow appears as four commands before any other content, and the
   golden rules further down are split into what the developer does and
   what the loop guarantees.

### User Story 6 - Dead surface is removed, and neutralized workarounds become upstream fixes (Priority: P6)

An extension's CLI no longer offers a `completions` subcommand nobody's
shell ever saw. The advisory review hook the loop's own flow never
reaches is gone. Three fixes this distribution carries only as local
workarounds are proposed upstream as the deletions they should be.

**Why this priority**: hygiene — real, but the smallest value of the
round, and the last step in dx.md's own delivery sequence.

**Independent test**: invoke `completions` on each extension's CLI and
confirm it's gone; confirm the `after_implement` hook registry carries no
review entry; find the three upstream pull requests and read what each
one removes.

**Acceptance scenarios**:

1. **Given** either extension's CLI, **When** `completions` is invoked,
   **Then** no such subcommand exists, and no doctor, README, or skill
   text mentions it.
2. **Given** the `after_implement` hook, **When** the hook registry is
   read, **Then** it carries no code-review entry.
3. **Given** upstream `github/spec-kit`, **When** this round closes,
   **Then** three pull requests are open there, each turning one of this
   distribution's local workarounds into an upstream deletion.

### Edge cases

- A branch with no Linear extension: the context line and the automatic
  reconciliation of User Story 2 are silently absent; the loop still
  delivers task by task without them, exactly as round 004 already
  guarantees.
- A coding agent with no runtime-event support: none of User Story 2's or
  3's automatic behaviors fire there; the prose rules remain authoritative,
  and the doctor names the gap explicitly rather than staying silent.
- The root-first merge script meets User Story 3's merge guard: the
  script relies on the repository's automatic branch-deletion setting
  instead of requesting deletion explicitly, so the guard never fires on
  the sanctioned path.
- A protected-path write on a feature branch rather than a task branch:
  the guard does not fire, matching round 004's own exemption for the
  branch where the contract legitimately changes.
- A consumer whose `auto_commit.default` is already `false`: until the
  upstream fix of FR-018 is merged and consumed, the sixteen `git.commit`
  hooks stay registered in `.specify/extensions.yml` and silenced by the
  phase-close rules like everywhere else; afterwards, they are simply
  absent.
- An agent tries the exact upstream-neutralized behavior this round
  proposes to delete (for example, mirroring commands across
  integrations by hand): the local workaround this repository already
  ships keeps working until the upstream pull request is merged and
  consumed here.

## Requirements *(mandatory)*

### Functional requirements

- **FR-001**: The default preset MUST execute each of the following eight
  procedures as a dedicated script that the owning command invokes, never
  as shell authored inline in the command's own prose: per-task setup,
  the budget-stop check, stack-fix propagation, pull-request creation,
  the on-request root-first merge, the ledger-completeness check,
  mirroring skills across installed integrations, and adding the
  installer's ignore entries.
- **FR-002**: Automated conformance MUST invoke each of these eight
  scripts directly against fixtures and report that script's own result;
  it MUST NOT report passing conformance from a block extracted out of a
  command's prose.
- **FR-003**: Starting a session on a feature or task branch, with Linear
  configured, MUST show, before the agent takes any other action, a
  context line naming the branch, the feature, the first unchecked task,
  every open task pull request, and the next command to run. Starting a
  session on a work-item branch (a bug's or a chore's issue-key branch,
  such as `wor-123-slug`) MUST show a context line naming what applies to
  it instead: the issue, its derived state, and the next command to run.
- **FR-004**: Wherever Linear names what to do next — the session-start
  context line of FR-003, and the `status` command — it MUST name a
  runnable command, or explicitly say to wait for a human merge; it MUST
  NOT describe a manual gesture the agent would have to translate into a
  command itself.
- **FR-005**: Whenever the agent runs `git push`, or a `gh pr` create,
  ready, or merge command, Linear MUST reconcile automatically afterward,
  with no prose instruction in the loop telling the agent to trigger it.
- **FR-006**: The behaviors of FR-003 and FR-005 MUST degrade to a clean
  no-op, without error, when Linear is not configured on the branch.
- **FR-007**: Before it executes, the loop MUST block: a commit whose
  subject does not match the repository's `type(scope): subject`
  convention; a force-push in any form; and a pull-request merge that
  requests explicit branch deletion. Each block MUST name the fix the
  agent needs to make.
- **FR-008**: Before an edit or a write to a protected path — every
  feature's `spec.md`, and the constitution — lands on a task branch, the
  loop MUST block it at the point of the write, naming the protected
  path; this replaces after-the-fact detection as the first line of
  defense for this case.
- **FR-009**: On a coding agent with no runtime-event support, the doctor
  MUST state explicitly that the guards of FR-007 and FR-008 and the
  Linear behaviors of FR-003 and FR-005 do not run there, and that the
  prose rules remain authoritative.
- **FR-010**: The rendered `implement` command MUST be a single coherent
  procedure; it MUST NOT contain both an upstream base procedure and a
  locally authored override that contradicts it.
- **FR-011**: Where the `tasks` command's local customization would
  otherwise contradict its base procedure the same way, it MUST likewise
  become a single coherent procedure rather than a base plus a
  contradicting append.
- **FR-012**: After a role bundle is installed, running the doctor MUST
  report every remaining onboarding gap in this fixed order: GitHub CLI
  authentication, the Linear API key, the Linear onboarding binding, the
  review engine installation, and the repository's GitHub delivery
  settings. Its fix mode MUST resolve every gap in that list that can be
  resolved mechanically, without a human decision, except the GitHub
  delivery settings: this round's doctor only reports them, and applying
  them is the releases round's scope.
- **FR-013**: The README MUST open with the day's workflow expressed as
  four commands before any other content, and MUST split the golden
  rules further down into what the developer does and what the loop
  guarantees.
- **FR-014**: The `completions` command MUST be removed from both
  extensions' command-line interfaces, with no doctor, README, or skill
  text referencing it.
- **FR-015**: The advisory `after_implement` code-review hook — a review
  of the working tree the loop's own flow never reaches — MUST be
  dropped from the hook registry.
- **FR-016**: This round MUST open an upstream pull request against
  `github/spec-kit` that registers extension and preset commands across
  every installed integration, not only the default one, and preserves
  `installed_integrations` across `init --force`.
- **FR-017**: This round MUST open an upstream pull request against
  `github/spec-kit` that removes `git add .` from `auto-commit.sh`.
- **FR-018**: This round MUST open an upstream pull request against
  `github/spec-kit` that stops registering the sixteen `git.commit` hooks
  when `auto_commit.default` is `false`.
- **FR-019**: This round MUST update its documentation: `docs/vision.md`
  records runtime events as the mechanism layer, the explicit degradation
  on coding agents without event support, and that command autocompletion
  is each agent's own — replacing the current autocompletion line;
  `docs/plan.md` records the round; `docs/dogfooding.md`'s entries this
  round resolves move to *resuelta* as each lands; and `AGENTS.md`'s list
  of Spanish-language exceptions gains `docs/dx.md` and
  `docs/releases.md`.

### Constraints and boundaries

- **C-001**: No new extension is introduced for this round's mechanism
  layer. The eight scripts of FR-001 ship inside the default preset;
  runtime events are declared only by the two extensions that already
  own each concern — linear for context and reconciliation, code-review
  for guards. Event handlers are internal commands of their extension,
  outside the user-facing command surface, the same way `--hook` already
  is.
- **C-002**: No `stop` handler runs on every turn, and no guard beyond
  the four named in FR-007 and FR-008 is added this round.
- **C-003**: The loop is not reimplemented as an interactive `specify
  workflow`; `gh stack` and an installation bootstrap script stay out of
  scope. The README remains the sole installation front door.
- **C-004**: Both extensions require `speckit_version >=1.0.4,<1.1.0` —
  the version where runtime events and the `event run` stdin fix ship.
- **C-005**: The eight scripts of FR-001 are POSIX `sh`, matching the
  blocks they replace; none gains a PowerShell twin this round.
- **C-006**: This feature's own `spec.md` is not modified by any of its
  tasks; the protected-path guard FR-008 builds also governs this
  round's own delivery.

## Success criteria *(mandatory)*

- **SC-001**: A diff of the default preset's commands against today's
  shows zero inline shell blocks for the eight procedures of FR-001; each
  is an independently invocable script that conformance exercises
  directly.
- **SC-002**: Across ten consecutive sessions on a feature or task branch
  with Linear configured, the context line and reconciliation of User
  Story 2 appear every time, with zero agent-issued reconcile commands
  anywhere in the transcripts.
- **SC-003**: Every attempted non-conventional commit, force-push, or
  delete-branch merge is blocked before it takes effect, with a named
  fix, on every tested agent that supports runtime events.
- **SC-004**: Every attempted write to a protected path on a task branch
  is blocked before it lands, on every tested agent that supports
  runtime events.
- **SC-005**: The rendered `implement` command contains no instruction
  that tells the agent to disregard another instruction already present
  in the same document.
- **SC-006**: A freshly bundle-installed consumer reaches a working loop
  after running one doctor command, with no manual setup step the doctor
  did not already name.
- **SC-007**: Neither extension's command-line interface exposes
  `completions`, and no shipped documentation mentions it.
- **SC-008**: Three pull requests are open against upstream
  `github/spec-kit`, each matching one of FR-016 through FR-018.

## Assumptions and dependencies

- **A-001**: The v1.0.4 upstream pin — runtime events and the `event run`
  stdin fix — is already delivered (`chore/upstream-1.0.4`, PR #85); this
  round builds on it without re-verifying the pin itself.
- **A-002**: Release lag: this round's script and command changes apply
  to this repository immediately through the dev-installed preset; the
  two extensions' event declarations apply to this repository's own loop
  only once published, and are proven during the round by tests,
  fixtures, and the agents dx.md names for verification — Claude and
  Codex in this repository, Cursor in the app-maker consumer.
- **A-003**: Event support is agent-dependent; where an agent has none
  (Zed, today), User Stories 2 and 3 degrade to the prose rules exactly
  as before this round, and the doctor names the gap per FR-009.
- **A-004**: `AGENTS.md`'s list of Spanish-language exceptions (the
  README, `vision.md`, `dogfooding.md`) does not yet name `docs/dx.md` or
  `docs/releases.md`; FR-019 amends it as part of this round.
- **A-005**: This feature is delivered through the workflow it changes;
  every friction met on the way is appended to `docs/dogfooding.md`.
- **A-006**: This round bumps the default preset and both extensions;
  publication remains a human, post-merge action, as it already is.

## Source references

- **SRC-001**: `docs/dx.md` — the agreed round design (2026-09-08); the
  authoritative scope source for this feature.
- **SRC-002**: `docs/vision.md` — product vision; the portability, DX,
  and observable-reality principles this round extends into runtime
  events.
- **SRC-003**: `docs/dogfooding.md` — sections D and G, and the four hand
  repairs the v1.0.4 bump took, cited in the Problem statement.
- **SRC-004**: `specs/004-delivery-discipline/` — the precedent round;
  the stack, budget-stop, protected-paths, and revert mechanisms this
  round moves from prose into scripts and events.
- **SRC-005**: `docs/plan.md` — the "Maintenance (2026-09-08)" entry
  recording the v1.0.4 pin this round depends on.
