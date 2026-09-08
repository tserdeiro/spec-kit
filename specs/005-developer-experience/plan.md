# Implementation Plan: Developer experience

**Feature directory**: `specs/005-developer-experience`
**Spec**: [spec.md](spec.md)

## Summary

Round 005 moves the delivery loop's mechanism out of command prose and into
machinery the pinned CLI already supports, verified in its installed source
rather than assumed from `dx.md`'s own framing. The default preset ships its
eight repeatable procedures as invocable POSIX scripts (`type: "script"`
preset entries, a first-class primitive) instead of inline shell an agent
edits by hand; conformance invokes those installed scripts directly. The
`linear` and `code-review` extensions declare native runtime events
(`session_start`/`post_tool_use`, `pre_tool_use`) so session context and
reconciliation happen without a prose reminder, and the four hard rules
block before the action instead of after. `implement` and `tasks` become
authored replacements of the upstream core instead of a base plus a
contradicting append. The doctor's existing checks already produce most of
FR-012's fixed onboarding order; this round closes the summarization gap,
not the checks. Three neutralized local workarounds are prepared as
upstream deletions. No new extension, no new command, no new persisted
configuration: every new behavior reuses a mechanism already installed —
`type: script` preset entries, extension `events:` manifests, `push
--hook`'s existing config gate, the existing `protected_paths` field.

## Technical context

- **Language/runtime**: preset commands stay agent-executed Markdown; the
  eight FR-001 procedures become POSIX `sh` scripts the commands invoke
  with real argv (no inline blocks, no literal substitution); the two
  extensions' new event handlers are POSIX `sh` scripts invoked by the
  CLI-generated dispatcher (`.specify/events.py`) with the native payload
  on stdin; both packages stay Python ≥3.11, stdlib-only, `uv`-managed;
  conformance stays bash.
- **Primary dependencies**: pinned upstream `specify-cli` 1.0.4
  (`versions.lock.yml`; installed and confirmed — `specify version` reports
  `1.0.4`); `gh`; `git`; each verified agent's own native hook runtime
  (Claude Code, Codex, Cursor — no SDK, no new package). Nothing is added
  to either package's `pyproject.toml`.
- **Storage/state**: no new persisted configuration schema (see Data and
  migration behavior). New physical files only: the preset's eight
  `scripts/bash/*.sh` and the two extensions' three internal command+script
  pairs, all materialized by the existing install mechanism.
- **Verification**: package pytest suites (`uv run pytest
  packages/<package>/tests`); `bash scripts/conformance/bundles.sh`
  (redesigned, D2); live verification on Claude Code and Codex in this
  repository and Cursor in the app-maker consumer (A-002, D12); this
  feature's own delivery as dogfood evidence for SC-002 through SC-004,
  the same way `specs/004-delivery-discipline/plan.md` proved its own loop
  rules through its own transcripts.
- **Target environment**: any upstream-supported agent for the script layer
  (FR-001/FR-002); Claude Code, Codex, and Cursor specifically for the
  events layer this round proves; every other agent (Zed, today) degrades
  explicitly (A-003); macOS/Linux shells, `dash` on Ubuntu CI.
- **Constraints**: C-001 through C-006 (`spec.md`); the extension manifest
  schema allows exactly one handler mapping per event name per extension
  (verified below — shapes D5); the 400-line task budget with the 2× stop;
  release lag (A-002) — this repository's own loop gets the new events
  only once the two extensions are locally reinstalled, other consumers
  only once published and bundle-updated.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| specify-cli (upstream) | 1.0.4 (`versions.lock.yml`) | https://github.com/github/spec-kit |
| specify-cli runtime events (`events:`, `CANONICAL_EVENTS`, the dispatcher) | 1.0.4, installed source | Verified directly in the installed `specify_cli/events.py`, `extensions/__init__.py`, `integrations/{claude,codex,cursor_agent}/__init__.py` — Spec Kit's own reference pages do not document this yet, confirmed while researching this plan |
| Claude Code hooks (SessionStart/PreToolUse/PostToolUse payload shape) | installed Claude Code | https://docs.claude.com/en/docs/claude-code/hooks — confirm exact payload field names (`tool_name`, `tool_input.*`) against this before `guard.sh`/`session-start.sh` are written; not re-derived here |
| Codex CLI (`.codex/config.toml` hooks) | installed codex | https://github.com/openai/codex |
| Cursor CLI hooks (`.cursor/hooks.json`) | installed cursor-agent | https://docs.cursor.com/en/cli/overview |
| gh CLI (`pr merge --delete-branch`, `api -X PATCH`, `auth status`) | consumer-installed | https://cli.github.com/manual/ |
| git | ≥2.41 | https://git-scm.com/docs |

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose a pinned upstream | PASS | PASS | C-001–C-006 scope this round to the preset/extensions/docs this repository owns; no fork or local patch of Specify CLI; `speckit_version` floors only tighten the already-pinned 1.0.4 (D9) |
| II. Preserve the native surface | PASS | PASS | No new `specify`/`speckit` command; the three new event-handler commands are deliberately kept out of `provides.commands` — internal, the same way `--hook` already is (D4, D5) |
| III. Integrations consumer-selected | PASS | PASS | `linear`/`code-review` stay optional (silent no-op without them, FR-006); events proven on Claude, Codex, Cursor (A-002); Zed's explicit degradation is a doctor sentence, not a second-class path (A-003, FR-009) |
| IV. Repository artifacts durable truth | PASS | PASS | The context line, `next_action`, and the two guards derive from repository observables (`tasks.md`, branches, PRs, committed config) exactly as `push`/`status` already do — no new remembered state |
| V. Source and consumer boundaries | PASS | PASS | Scripts and events ship inside this repository's preset and extensions; a consumer's own `tasks.md`/branches are read, never owned, by this source checkout |
| VI. Traceable delivery units | PASS | PASS | `ledger-check.sh` turns "checked box + Completion evidence" into a script-enforced gate instead of trusted agent memory (D1); every task still forecasts lines under the 400-budget |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| `presets/default` (`preset.yml`, `commands/`, new `scripts/bash/`) | this repo | eight scripts (D1); `implement`/`tasks` become `strategy: replace` (D3); `pr.md`/`chore.md`/`bugfix.md`/`doctor.md` prose shrinks to script-invoking steps | no new command, no new flag, no PowerShell twin for the eight scripts (C-005) |
| `packages/spec-kit-linear` | this repo | `events:` block (D4); two new internal commands+scripts; `next_action` redesign (D6); `speckit_version` floor (D9); `completions` removed (D8) | no new config schema; `onboard`/`push`/`status`'s own behavior unchanged |
| `packages/spec-kit-code-review` | this repo | `events:` block (D5); one new internal command+script; `after_implement` hook removed (D8); `completions` removed (D8); `speckit_version` floor (D9) | no new verdict value, no publish-path change; `protected_paths` reused, not changed |
| `scripts/conformance/bundles.sh` | this repo | invokes installed scripts directly (D2); the "retired `scripts/` directory" assertion inverted | `--published` mode and CI scope unchanged |
| `docs/vision.md`, `docs/plan.md`, `docs/dogfooding.md`, `AGENTS.md`, `README.md` | this repo | FR-019 (D10); README's four-commands opening (FR-013) | translating documents; no new sections beyond what FR-019 names |
| Upstream `github/spec-kit` | upstream | three patches prepared (D11), not merged by this round | no fork, no local patch of the pinned tree (Constitution I) |
| App-maker consumer (Cursor verification) | separate repo | none — read-only verification target for A-002/D12 | this plan does not modify app-maker |

## Technical decisions

### D1. Preset scripts: layout and invocation contract (preset)

- **Decision**: eight POSIX `sh` scripts at
  `presets/default/scripts/bash/{task-base,budget-stop,stack-propagate,
  pr-create,merge-root-first,ledger-check,skill-mirror,ignore-entries}.sh`,
  each a `preset.yml` entry with `type: "script"`, explicit
  `file: "scripts/bash/<name>.sh"`, hyphenated `name` (matches
  `presets/__init__.py:518`'s `^[a-z0-9-]+$` rule for non-command
  templates), `strategy: "replace"` — the only sensible
  `VALID_SCRIPT_STRATEGIES` value here (`presets/__init__.py:274`; there is
  no upstream base script to `wrap`). Verified: `type: "script"` is a
  first-class preset primitive
  (`presets/__init__.py:271`, `VALID_PRESET_TEMPLATE_TYPES = {"template",
  "command", "script"}`) that installs by full-directory
  `shutil.copytree(source_dir, dest_dir)` (`presets/__init__.py:3874`), so
  every consumer materializes the file at
  `.specify/presets/default/scripts/bash/<name>.sh`; the owning command's
  prose invokes it there directly
  (`bash .specify/presets/default/scripts/bash/task-base.sh ...`),
  mirroring the extensions' own established
  `bash .specify/extensions/<id>/scripts/bash/run.sh ...` convention. The
  "replace only the literal" pattern is gone by construction — commands
  pass real argv instead of the agent editing placeholder text before
  running `sh -c`.
- `task-base.sh` absorbs three related setup blocks that exist today as
  separate marked shell — `task-base`, `first-task-refresh`, and
  `work-item-branch` (byte-identical, pasted in both `chore.md` and
  `bugfix.md`) — as three modes of one script, since FR-001 names
  "per-task setup" as a single procedure and all three exist only to put
  the right branch under the developer before work starts:
  - `task-base.sh refresh` — today's `first-task-refresh` (merge the
    delivery base into the feature branch, once per feature).
  - `task-base.sh task <NNN-T###-slug>` — today's `task-base` (branch from
    the open task stack's top, or the feature branch).
  - `task-base.sh work-item <branch-name>` — today's `work-item-branch`
    (branch from the delivery base), called identically from `chore.md`
    and `bugfix.md`: one script, two callers, instead of one block pasted
    twice — the byte-identity check at `bundles.sh:773-780` becomes
    structural, not textual.
- `pr-create.sh <feature|task|work-item> [named-task]` resolves and prints
  `base=<name>` only — today's base-resolution rules unchanged (trunk
  config wins, else the GitHub default, else the open-task-stack head,
  with the branch-identity check against the ledger's first unchecked
  task). `pr.md`'s own prose keeps composing the canonical title/body and
  running `gh pr create` itself. This is a deliberate split from today's
  single block, which conflates deterministic base-resolution with an
  agent-composed `gh pr create` call — see Alternatives and the friction
  report for the exact inconsistency it corrects: `pr.md` says "Replace
  only the delivery-kind and named-task literals" while its block also
  embeds two more untouched placeholders, `<type(scope): subject>` and
  `<the body>`.
- `budget-stop.sh <task_id> <base>` and `stack-propagate.sh <fixed_branch>`
  are direct translations of today's blocks — unchanged rules, unchanged
  exit-code/message conventions (`exit 2` with an `error: ...` diagnosis
  on stderr; `exit 0` with a one-line summary on stdout).
- `merge-root-first.sh` (no required argument; self-derives the feature
  branch via `check-prerequisites.sh --paths-only`, the pattern
  `task-base`/`budget-stop` already use) is new: it extracts today's
  prose-only "Between tasks" procedure — `git worktree prune`, then for
  each open task PR root-first, retarget by API (`gh api -X PATCH
  repos/{owner}/{repo}/pulls/<n> -f base=<feature-branch>`) and
  `gh pr merge <n> --merge` (never `--delete-branch`, matching the guard
  of D5/FR-007). It runs only on an explicit human instruction in the
  conversation — the script performs the mechanical steps; the human's
  "yes, merge" stays a conversation-level decision, never automated.
- `ledger-check.sh <task_id>` is new: it verifies, deterministically, what
  the loop's prose today only asks the agent to remember — the task's
  checkbox is `[x]` and its **Completion evidence** field is filled (not
  "Pending", not empty) — before the command marks the PR
  `ready for review`. Same fence-aware ledger-parsing approach as
  `budget-stop.sh`/`pr-create.sh`'s task case. `exit 2` names exactly
  what's missing, turning "the agent forgot" (the Problem statement's own
  diagnosis) into a script-enforced gate.
- `skill-mirror.sh <true|false>` and `ignore-entries.sh <true|false>` are
  direct translations of `doctor.md`'s two largest blocks — 110 and 22
  lines, dogfooding entry 41 — unchanged logic, called from `doctor.md`'s
  steps 5 and 6 with the `fix` argument taken from whether the user asked
  to fix.
- **Rationale**: FR-001/FR-002 require every one of these eight procedures
  to be a dedicated, directly-invocable script; `type: "script"` is the
  CLI's own supported mechanism for exactly this, verified rather than
  invented, and it installs with zero new dependency.
- **Trade-off**: `task-base.sh`'s three modes are one script with a mode
  argument rather than three separate FR-001-adjacent scripts — simpler
  surface, at the cost of one positional argument every caller must pass
  correctly.

### D2. Conformance invokes the installed scripts directly (scripts)

- **Decision**: `scripts/conformance/bundles.sh` drops its
  `sed -n '/X:start/,/X:end/p' "$installed_skill"` extraction and its
  `render_*` sed-substitution helpers (`render_pr_create`,
  `render_task_base`, `render_stack_propagate`, `render_budget_stop`,
  `render_fix` — `bundles.sh:642-645,872-874,967-969,1024-1027,1099`)
  entirely. Each scenario instead invokes the installed file directly —
  `bash "$consumer_root/.specify/presets/default/scripts/bash/<name>.sh"
  <argv>` — against the same fake-`git`/fake-`gh` PATH harness
  (`fake_bin`, the `gh_calls`/`git_calls` JSONL logs) already in place;
  the scenario-level assertions (which git/gh calls happen, in what
  order, with what argv) are unchanged, because the scripts' behavior is
  unchanged from the blocks they replace.
- `bundles.sh:550-551` —
  `[ -e "$consumer_root/.specify/presets/default/scripts" ] &&
  fail "trunk: the retired scripts/ directory is still installed"` — is a
  direct regression trap for this round: round 004 retired a Python
  `resolve-delivery-base` script in favor of inline shell specifically to
  avoid a `scripts/` directory; round 005 reintroduces one, this time
  through the CLI's own supported `type: script` primitive, not an ad hoc
  resolver. This assertion is replaced with its opposite — the eight files
  exist at that path — while `bundles.sh:636-637`'s
  `python3|resolve-delivery-base` grep stays valid and now runs against
  the new `implement.md`/`pr.md`/`chore.md`/`bugfix.md` content.
- A new assertion proves SC-001 directly against the installed artifact:
  the installed command files (`speckit-implement`, `speckit-pr`,
  `speckit-chore`, `speckit-bugfix`, `speckit-doctor`) contain no
  `# <name>:start`/`# <name>:end` marker pairs at all.
- The `work_item_branch`/`bugfix_work_item_branch` byte-identity
  assertion (`bundles.sh:773-780`) is replaced by asserting both
  `chore.md` and `bugfix.md` invoke the same
  `task-base.sh work-item <branch>` call — identity is now structural
  (one script, two call sites), the direct product of D1's consolidation.
- **Rationale**: FR-002 — conformance must report the script's own result,
  never a block extracted from prose; direct invocation is also
  materially simpler (no `render_*` sed layer, no placeholder syntax to
  keep in sync with the command prose).
- **Trade-off**: none identified — this is a strict simplification of the
  existing harness.

### D3. `implement` and `tasks` become authored replacements (preset)

- **Decision**: `preset.yml`'s `speckit.implement` and `speckit.tasks`
  entries change `strategy: "append"` → `strategy: "replace"`, with new,
  freestanding `commands/implement.md` and `commands/tasks.md` (replacing
  `implement-append.md`/`tasks-append.md`). `speckit.specify`,
  `speckit.plan`, and `speckit.analyze` keep `strategy: "append"`
  unchanged — their append (`phase-close-append.md`) has no equivalent
  contradiction with their upstream cores. Verified:
  `presets/__init__.py:6053-6056` — "If the top (highest-priority) layer
  is replace, it wins entirely — lower layers are irrelevant regardless of
  their strategies" — so with `strategy: replace` the rendered command is
  the new file's raw content alone; upstream's core `implement.md`/
  `tasks.md` (`core_pack/commands/{implement,tasks}.md`, read in full —
  222/219 lines, ~12.4/10.8 KB) contributes nothing, closing FR-010/FR-011
  by construction instead of by an appended sentence telling the agent
  which half to disregard.
- Because `replace` discards the upstream file wholesale, including its
  frontmatter, the new files must carry their own `scripts:` frontmatter
  block verbatim from upstream core (`sh: scripts/bash/
  check-prerequisites.sh --json --require-tasks --include-tasks` for
  implement; `sh: scripts/bash/setup-tasks.sh --json` for tasks) — this is
  what resolves the body's `{SCRIPT}` placeholder; dropping it silently
  breaks the command. This is the single non-negotiable correctness
  constraint of this decision.
- Content shape, verified against upstream core's actual text: the new
  files keep upstream's still-useful, non-contradicted Outline steps (the
  prerequisites-script Setup step; the checklist-status gate; loading
  `plan.md`/`data-model.md`/`research.md`/`quickstart.md`/
  `constitution.md` when present; `implement.md`'s ignore-file
  verification), rewritten in this distribution's voice, and fold in this
  repository's own loop as the sole execution-order model — replacing
  upstream's generic "phase-by-phase, `[P]`-parallel, TDD-first" model
  wholesale. That model is exactly what this repository's
  `tasks-template.md` and delivery loop already supersede: upstream
  `tasks.md`'s own "Checklist Format" section requires `[P]` markers
  ("3. **[P] marker**: Include ONLY if task is parallelizable") and
  "Create parallel execution examples per user story" — the literal
  contradiction FR-011 names, confirmed by reading the file, not assumed.
  The hook-announcement boilerplate (`Pre-Execution Checks`/`Mandatory
  Post-Execution Hooks`, upstream's printed "Optional Hook" block) is
  authored directly as this distribution's silent behavior instead of
  surviving as text an override bullet then contradicts.
- **Rationale**: FR-010's own wording — "MUST NOT contain both an upstream
  base procedure and a locally authored override that contradicts it" —
  is only satisfiable by removing the base from the render entirely;
  deleting the contradicting sentences while keeping `strategy: append`
  would still leave upstream's parallel-task model physically present in
  the same document.
- **Trade-off**: this is real authoring work — a document rewritten from
  two ~200-line sources, not a mechanical merge — and it is the largest
  single task User Story 4 produces; sized and reviewed as its own
  delivery unit. The two files then drift from upstream silently on a
  future CLI upgrade (no append left to reconcile against) — accepted,
  consistent with how `speckit.doctor` and `speckit.pr` are already full
  replacements today with no upstream base at all.

### D4. Linear runtime events: session_start and post_tool_use (linear)

- **Decision**: `packages/spec-kit-linear/extension.yml` gains:

  ```yaml
  events:
    session_start:
      command: session-start
    post_tool_use:
      command: post-tool-use
      matcher: "Bash"
  ```

  Two new files, deliberately **not** listed in `provides.commands` (kept
  outside the user-facing surface, the same intent as `--hook`):
  `commands/session-start.md` and `commands/post-tool-use.md`, each with
  a `scripts: {sh: scripts/bash/<name>.sh}` frontmatter block (no `ps`/`py`
  variant — see the Constraints note below) and no other required field.
- **Naming, verified precisely**: because these two commands are not
  registered under `provides.commands`, the dispatcher resolves them
  through `_find_command_template`'s on-disk fallback
  (`events.py:165-174`), which matches a file under `commands/` by stem
  against either the raw `command:` string or that string with a
  `speckit.`/`spec.` prefix stripped (`events.py:123`). A dotted name like
  `speckit.linear.session-start` would need a file literally named
  `speckit.linear.session-start.md` or `linear.session-start.md` to
  resolve — a plain `session-start.md` matches neither. Naming the command
  (and the file) `session-start`/`post-tool-use` — undotted, unlike the
  public `speckit.linear.*` commands, which resolve through the
  registered-manifest path instead (`events.py:125-163`) and so tolerate
  any filename — avoids that mismatch by construction. This is why these
  two names deliberately break the extension's own dotted convention; a
  short comment at the `events:` block should say so, or a future edit
  risks "fixing" it back into a silently broken dispatch (the dispatcher
  fails open on a resolution miss — see Failure behavior below).
- `session-start.sh` does two things, in order: (1) `push --hook`
  (unchanged entrypoint, unchanged config gate —
  `hooks.lifecycle_enabled`/`auto_apply` in `speckit-linear.yml`, already
  documented as a clean no-op without configuration, reused verbatim, no
  new config field); (2) reads the current branch and calls
  `status --current --json` (existing, read-only) to build one context
  block.
- **Context content, by branch shape (FR-003)**, fixing the required
  fields and their order — exact spacing is an implementation choice:
  - Feature or task branch (`NNN-...` or `NNN-T###-...`): the branch, the
    feature identifier, the first unchecked task from `status`'s
    `task_rows[].tasks[]` (first entry with `local_complete: false`),
    every open task pull request (rows whose `state_source == "pr"`), and
    the next command from the redesigned `next_action` (D6). Indicative
    shape:
    `Linear: <feature> on <branch> — next <T###> (unchecked); open task
    PRs: <branch> -> #<n> (<review|started>)[, ...]; next: <command>`
  - Work-item branch (`<team-key>-<n>-...`): the issue key, its derived
    state, and the next command, from `status`'s `work_items[]` row for
    that key:
    `Linear: <ISSUE-KEY> (<state>) — next: <command>`
  - Neither shape, or no `speckit-linear.yml`: no line at all (FR-006) —
    the script prints nothing and exits 0, which the dispatcher's `_emit`
    already treats as "emit nothing" for empty output
    (`events.py:331-332`).
- `post-tool-use.sh`, matcher `Bash` (so the native hook fires only for
  Bash calls — the default `"*"` matcher would fire on every tool
  otherwise): reads the PostToolUse payload's `tool_input.command`; when
  it matches `git push` or `gh pr (create|ready|merge)`, runs
  `push --hook`; otherwise exits 0 silently. This mechanically replaces
  the loop's three "reconcile now" sentences (FR-005), none of which need
  to survive in `implement.md`'s replacement (D3).
- Both handlers reuse the same `push`/`status` entrypoints and config
  gates the extension already ships — no new config schema, no new
  credential path.
- **Rationale**: FR-003 through FR-006, reusing rather than reimplementing
  `push`/`status`, per the repository's own simplicity principle.
- **Trade-off**: the context line duplicates a subset of what `status`
  already renders — accepted, since it is a summary for a moment (session
  start) `status` does not otherwise reach automatically.

### D5. Code-review runtime events: one `pre_tool_use` registration, two guards (code-review)

- **Decision**: `packages/spec-kit-code-review/extension.yml` gains
  exactly one event registration:

  ```yaml
  events:
    pre_tool_use:
      command: guard
      matcher: "Bash|Edit|Write"
  ```

  One new file `commands/guard.md` (outside `provides.commands`, undotted
  for the same file-stem resolution reason as D4),
  `scripts: {sh: scripts/bash/guard.sh}`.
- **Why one registration, not two — verified against the schema rather
  than `dx.md`'s own two-handler framing**: an extension manifest's
  `events.<name>` value must be a single mapping, never a list.
  `extensions/__init__.py:391-393` routes any `events:` key to
  `events.py`'s `validate_events`, which raises `"Invalid event '<name>':
  expected a mapping"` the moment `event_config` is not a `dict`
  (`events.py:1843-1847`). `collect_extension_events`
  (`events.py:1029-1105`) only ever accumulates handlers **across
  different extensions** declaring the same event name — never two
  handlers from the same extension's own manifest. So code-review's two
  guard concerns (`dx.md`'s "matcher `Bash`" and "matcher `Edit|Write`"
  framing) cannot be two top-level `pre_tool_use` entries in one
  `extension.yml`; they are two branches inside the one handler script,
  dispatched on the native payload's `tool_name` field, under a matcher
  that is the union of the tools either concern needs
  (`"Bash|Edit|Write"`, so the native hook fires only for these three
  tools at all). This corrects `dx.md`'s own framing; recorded here so
  the tasks phase does not re-derive it, and repeated in the friction
  report.
- `guard.sh` behavior:
  - `tool_name == "Bash"`: reads `tool_input.command`; blocks (`exit 2`,
    message naming the fix) a `git commit -m` whose subject fails
    `^[a-z]+\([a-z0-9-]+\): .+$` — the exact pattern
    `.github/workflows/conventions.yml` already enforces server-side
    (`conventions.yml`, the "Commit subjects follow type(scope) subject"
    step); any form of `git push --force`/`-f`/`--force-with-lease`; and
    any `gh pr merge ... --delete-branch`. Anything else: `exit 0`,
    silent.
  - `tool_name` in `("Edit", "Write")`: reads the target path and the
    current branch; on a `NNN-T###-*` branch (the numeric-prefix rule
    `specs/004-delivery-discipline/plan.md`'s D1 already established for
    the phase-two finding — reused, not reinvented), blocks a write
    matching any `protected_paths` glob (`speckit-code-review.yml`,
    unchanged default `specs/*/spec.md` and
    `.specify/memory/constitution.md`), naming the protected path. A
    feature branch (no `T###` segment) is exempt, matching round 004's
    own exemption and this round's own C-006 (this feature's `spec.md` is
    protected on its own task branches).
  - Everything else: `exit 0`, silent — C-002's "no guard beyond the four
    named" holds by construction, since the script has exactly four block
    conditions.
- No new config: the commit-subject pattern and the force-push/
  `--delete-branch` forms are structural (mirroring CI exactly, not meant
  to be configurable); `protected_paths` already exists.
- **Rationale**: FR-007, FR-008; reuse of the exact server-side regex
  keeps the two checks (client-side block, server-side gate) from ever
  disagreeing.
- **Trade-off**: one script now owns two logically separate concerns —
  accepted; the alternative (two registrations) is not schema-valid, not
  a stylistic choice.

### D6. `next_action` returns runnable commands (linear)

- **Decision**: `packages/spec-kit-linear/src/spec_kit_linear/
  work_state.py`'s `next_action` (lines 161-190, read in full) is
  rewritten so every non-`None` return is either a slash command or the
  literal "wait for a human merge" sentence — never a gesture the agent
  has to translate. One of its five branches is FR-004's own negative
  example almost verbatim: `state == STATE_UNSTARTED` today returns
  `f"start: create branch {prefix}-<slug>"` (`work_state.py:187-189`) —
  the exact "create the branch" gesture FR-004's acceptance scenario 3
  names as what must stop happening.

  | Derived state | Current text (`work_state.py:177-189`) | Redesigned |
  | --- | --- | --- |
  | `completed`, `checked=False` | "record completion evidence and check the box in tasks.md" | `None` — this combination means the merge outran a local sync; nothing local is actionable |
  | `review` | "await the final review and the human merge" | unchanged — already FR-004-compliant |
  | `started`, source `pr` | "self-review (/speckit.code-review), then mark ready for review" | `/speckit.code-review <PR>` — ready-for-review is the review command's own completion instruction, not a second gesture named here |
  | `started`, source `branch` | "open the draft PR" | `/speckit.pr` |
  | `unstarted` (feature task) | `"start: create branch {feature}-{task}-<slug>"` | `/speckit.implement <feature>` — the command that now runs `task-base.sh task`, not the developer by hand |
  | `unstarted` (work item) | same, with `feature`/`task` both `None` → literally `"start: create branch NNN-T###-<slug>"` | `/speckit.chore <ISSUE-KEY>` |

- The work-item row surfaces a real signature gap, not only a wording
  change: `reporting.py:129` calls `next_action(item.state, item.source)`
  with neither the issue key nor whether it is a bug or a chore —
  `next_action` has no parameter today to build a work-item command from.
  `next_action` gains `identifier: str | None`, threaded from
  `WorkItemState.identifier` (already available at the call site).
  Distinguishing `/speckit.bugfix` from `/speckit.chore` needs a signal
  the current `WorkItemState` does not carry (bug vs. chore is a Linear
  issue-type distinction this extension does not read today); resolved
  here by naming `/speckit.chore <ISSUE-KEY>` as the safe generic default
  — a chore path with no triage trio still lets a human redirect to
  `/speckit.bugfix` — documented as a known imprecision rather than a
  silent guess. Threading the PR number for the `review`/`started(pr)`
  rows is a tasks-phase implementation choice; the data is already in
  scope at both call sites (`build_task_rows`/`build_work_item_rows`).
- **Rationale**: FR-004's own wording, and its own negative example is
  code that exists today.
- **Trade-off**: `next_action`'s existing contract ("pure text over the
  observable state... never adds signals") stays true — only the emitted
  text and the function's parameters change, never what it observes.

### D7. Doctor's fixed onboarding order (preset)

- **Decision**: `doctor.md`'s summarization step (today's step 4) gains
  explicit instructions to group every reported gap into five fixed
  categories, in this order, regardless of which sub-doctor produced the
  underlying diagnostic: (1) GitHub CLI authentication, (2) the Linear API
  key, (3) the Linear onboarding binding, (4) the review engine
  installation, (5) the repository's GitHub delivery settings (unchanged
  step 3, still report-only per FR-012's own carve-out). No change to
  either package's own `doctor` implementation.
- **Verified this is a report-ordering fix, not a check-ordering one**:
  linear's `run_doctor` (`cli.py:384-428`) already emits, in this
  relative order, `github_cli_diagnostic` (`cli.py:404`) before
  `linear_auth` (the API-key check, `cli.py:422`) before `linear_binding`
  (the onboarding check, `cli.py:423`) — categories 1-2-3 already come
  out in the right relative order from one sub-doctor call. Code-review's
  `run_doctor` (`doctor.py:204-221`) calls `_check_ocr` (category 4,
  `doctor.py:215`) **before** `_check_gh` (`doctor.py:216`) — its own
  internal order does not match categories 1 and 4 cleanly, so "run
  linear's doctor, then code-review's doctor, print everything in that
  order" (today's literal doctor.md step 1/2 listing) is not sufficient.
  The fix is the agent's categorization at summary time: map each
  diagnostic's code (`github_cli_diagnostic`/`_check_gh`'s codes →
  category 1, `linear_auth` → 2, `linear_binding` → 3, `_check_ocr`'s
  codes → 4) into the fixed list, independent of which sub-doctor
  produced it or in what order it printed.
- `--fix` scope is unchanged: FR-012's "resolves every gap ... that can be
  resolved mechanically" is already each doctor's own `--fix` passed
  through (doctor.md's existing step 2, "you never fix anything
  yourself"); the GitHub-settings category stays read-only even under
  `--fix` — this round's own scope boundary, applying them is the
  releases round's.
- **Rationale**: FR-012, minimal-footprint per AGENTS.md — a prose
  reordering closes the gap; neither package's doctor needs new flags or
  new check sequencing.
- **Trade-off**: the fixed order lives in agent-executed prose, not in a
  script — acceptable, since it is a summarization judgment over two
  tools' free-text diagnostics, not a mechanical procedure with clean
  argv (unlike the eight FR-001 procedures).

### D8. Hygiene: `completions` and `after_implement` removed (linear + code-review)

- **Decision**: both extensions' `provides.commands` drop the
  `speckit.<ext>.completions` entry; `commands/completions.md` and
  `src/spec_kit_<ext>/completions.py` (and its CLI wiring) are deleted;
  each README's `completions`/"Shell completions" content is removed; the
  matching unit test module (confirmed present:
  `packages/spec-kit-linear/tests/unit/test_completions.py`) is deleted,
  not left red or skipped.
- `packages/spec-kit-code-review/extension.yml`'s `hooks.after_implement`
  entry (verified: `command: speckit.code-review`, `optional: true`,
  `priority: 30`) is deleted outright — the advisory review of the
  working tree it wires never fires in this distribution's own loop (the
  loop always has a PR by the time review happens, `implement-append.md`
  step 2), matching FR-015 exactly.
- **Rationale**: FR-014, FR-015; both are dead surface by the spec's own
  finding (User Story 6), confirmed by grep against this checkout.
- **Trade-off**: none — no consumer-visible behavior depends on either.

### D9. Manifest version floors (linear + code-review)

- **Decision**: both `packages/spec-kit-linear/extension.yml` and
  `packages/spec-kit-code-review/extension.yml` change
  `requires.speckit_version` from `">=1.0.1,<1.1.0"` to
  `">=1.0.4,<1.1.0"` — the version where runtime events and the
  `event run` stdin fix ship (A-001, already pinned in
  `versions.lock.yml`: `tag: v1.0.4`, `package_version: 1.0.4`, verified
  installed and matching). `presets/default/preset.yml`'s own
  `requires.speckit_version` is left unchanged — the preset's new surface
  (`type: script` entries) is a general 1.0.x primitive, not
  events-specific, and C-004's wording scopes the floor to "both
  extensions" only.
- **Rationale**: C-004.
- **Trade-off**: none.

### D10. Documentation (docs)

- **Decision**: `docs/vision.md`'s "Portabilidad" section gains runtime
  events as the mechanism layer and the explicit degradation on agents
  without event support; its autocompletion line is corrected to say
  command autocompletion is each agent's own, replacing the current
  wording, since `completions` (D8) is gone. `docs/plan.md` (the roadmap,
  distinct from `specs/*/plan.md`) gains a round-005 entry, matching the
  existing "Maintenance (2026-09-08)" entry's style (SRC-005).
  `docs/dogfooding.md` section J's entries (36-42, this round's own
  findings) graduate to *resuelta* as each lands, task by task, not in
  this plan. `AGENTS.md`'s Spanish-exception sentence gains `docs/dx.md`
  and `docs/releases.md` (A-004), the open question `dx.md` itself left.
- **Rationale**: FR-019.
- **Trade-off**: none.

### D11. Upstream pull requests, prepared not published (upstream)

- **Decision**: three patches against `github/spec-kit`, each turning a
  local workaround into the upstream deletion it should be:
  1. Register extension/preset commands across every installed
     integration, not only the default one, and preserve
     `installed_integrations` across `init --force` — root cause of
     dogfooding entries 17, 29, and this repository's whole
     `skill-mirror` workaround (D1), and of entry 35's `init --force`
     regression.
  2. Remove `git add .` from `auto-commit.sh` — entry 24.
  3. Stop registering the sixteen `git.commit` hooks when
     `auto_commit.default` is `false` — entry 25, and dogfooding entry 37
     (the append's own hook-silence rule exists only because this bug is
     not fixed upstream yet).
- These are prepared as patches against the pinned `v1.0.4` tag's tree —
  this repository does not fork or vendor upstream (Constitution I).
  Opening them is a human, credentialed act outside this plan's scope,
  tracked as its own task with the PR URLs as evidence once done.
- **Rationale**: FR-016 through FR-018, SC-008.
- **Trade-off**: none — publication of these three PRs is out of this
  round's control once opened (upstream review timeline).

### D12. Cross-agent verification (linear + code-review)

- **Decision**: the two extensions' event declarations are proven, during
  this round's own delivery, on Claude Code and Codex in this repository
  (both already-installed integrations, per `.specify/integration.json`)
  and Cursor in the app-maker consumer (A-002). Verified wiring: after
  `specify integration install <key> --force`, the handler appears in
  `.claude/settings.json` (`events_format: "json-nested"`,
  `integrations/claude/__init__.py:57-66`) and `.codex/config.toml`
  (`events_format: "toml"`, `integrations/codex/__init__.py:32-41`)
  respectively; a `session_start` handler's stdout surfaces as context on
  both (Claude and Codex both use the default "plain" envelope —
  `events.py:326` — passthrough, no JSON wrapping); a `pre_tool_use`
  handler's `exit 2` blocks the native tool call on both — `_run_inline`
  (`events.py:274-303`) propagates the handler's own exit code as the
  dispatcher's exit code, which each agent's own native hook runner
  treats as "block".
- Cursor's own format (`events_format: "json-flat"`, native names
  camelCased — `integrations/cursor_agent/__init__.py:41-49`) and its
  `events_context_envelope` (`session_start` → `additional_context`,
  everything else → `suppress`, `cursor_agent/__init__.py:55-59`) mean
  Cursor's `preToolUse` communicates block/allow by exit code alone,
  never by injected text — verification there is exit-code-only, which is
  all `guard.sh` needs anyway (its message lands on stderr regardless of
  agent, `events.py:294-295`).
- Zed carries no `events:` wiring — no `CANONICAL_TO_NATIVE`/
  `events_config_file` exists for it in `integrations/zed/` — A-003's
  explicit degradation; FR-009's doctor sentence is the only artifact this
  round owes Zed users.
- **Rationale**: A-002; proves the mechanism on every agent this round
  can reach, exactly as named.
- **Trade-off**: publication lag — other consumers get the events layer
  only once the extensions publish and the consumer's bundle updates
  (unchanged from how every prior release already worked).

### D13. Release sequencing (release)

- **Decision**: version bumps, matching `docs/plan.md`'s existing
  convention and `specs/004-delivery-discipline/plan.md`'s own D14 style,
  current → next (semver MINOR — new scripts/events are additive
  capability, not a fix): `preset 0.9.0 → 0.10.0`,
  `linear 0.12.0 → 0.13.0`, `code-review 0.4.0 → 0.5.0`,
  `bundles 0.15.0 → 0.16.0`, applied with
  `publish.sh --bump preset=0.10.0 linear=0.13.0 code-review=0.5.0
  bundles=0.16.0` as the last delivery task of the round (A-006), after
  every other task's PR has merged into the feature branch. Publication
  itself (the tag push, the GitHub release) stays a human, post-merge
  act.
- **Rationale**: A-006; matches the established release discipline.
- **Trade-off**: none.

## Data and migration behavior

No new persisted configuration schema. New physical files: the preset's
eight `scripts/bash/*.sh` (materialized by `specify preset add`, not
runtime state) and the two extensions' three internal command+script
pairs (materialized by `specify extension add`/`upgrade`). Both event
handlers reuse existing config gates verbatim — linear's
`hooks.lifecycle_enabled`/`auto_apply` in `speckit-linear.yml` (already
default `true`, already documented as a clean no-op without them) and
code-review's existing `protected_paths` in `speckit-code-review.yml`
(round-004 default, unchanged). `next_action`'s signature gains
parameters (D6); no stored data changes shape. A consumer upgrading
mid-round, before the extensions publish, keeps working exactly as
before — events are additive capability, not a breaking change to
`push`/`status`/`review`'s existing contracts.

## Failure, retry, rollout, and rollback

- **Failure behavior**: the events dispatcher fails **open** by design —
  an unresolvable command or script variant returns exit 0, a silent
  no-op (`events.py`'s `_run_inline`, "command not found: fail open
  (no-op) for lifecycle events", and `_resolve_argv` returning `None`), so
  a wrong handler filename (D4's naming constraint) or a missing script
  does not block the agent's session or tool call — it just silently
  never fires. This is why D12's live verification across Claude, Codex,
  and Cursor is this round's only way to catch that class of mistake, not
  a conformance assertion. `guard.sh`/`session-start.sh`/
  `post-tool-use.sh` exit 2 with a stderr message naming the fix on every
  blocking path, matching the existing script convention (D1).
- **Retry/idempotency**: `push --hook` is already idempotent (unchanged);
  the guard script is pure per invocation (re-evaluates the payload every
  call, remembers nothing); `ledger-check.sh`/`merge-root-first.sh`
  re-derive from repository state exactly like `task-base.sh`/
  `stack-propagate.sh` already do.
- **Rollout**: the eight preset scripts and the `implement`/`tasks`
  replacement apply to this repository immediately through the
  dev-installed preset (`specify preset remove default && specify preset
  add --dev presets/default`, matching dogfooding entry 35's own
  documented upgrade recipe); the two extensions' `events:` declarations
  apply to this repository's own loop only once locally reinstalled
  (`specify extension add ... --dev` per package) and to other consumers
  (app-maker) only once published and bundle-updated there (A-002's
  release lag) — Claude and Codex here prove it during the round; Cursor
  in app-maker proves the cross-consumer path; Zed and any other
  non-event agent get the documented degradation (A-003), never a broken
  command.
- **Rollback**: every changed file is text or a script — revert by
  commit, matching `specs/004-delivery-discipline/plan.md`'s own D8
  revert convention (`git revert --no-commit`, `revert(scope): subject`);
  no data migration exists to unwind.

## Security and privacy

No new credential and no new remote write. `session-start.sh`/
`post-tool-use.sh` call the same `push --hook` entrypoint that already
resolves `LINEAR_API_KEY`/`LINEAR_OAUTH_ACCESS_TOKEN` exactly as
documented. `guard.sh` reads only the native tool-call payload the
agent's own runtime already handed it (command text, file path) and the
repository's own committed config (`protected_paths`) — never a secret,
never a remote call. The PreToolUse/PostToolUse/SessionStart payloads
land on the handler script's stdin and nowhere else (`events.py`'s
`_run_inline`, `input=payload`); nothing this round adds writes that
payload to a file or logs it. Trust boundary: a handler script now runs
on every relevant tool call in a session, so its own correctness joins
the agent's control flow for the first time (a bug in `guard.sh` could
wrongly block, or — the more dangerous direction — wrongly allow); the
fail-open dispatcher behavior above means a broken handler degrades to
"no guard," never to "agent hangs" or "a wrong action force-blocks
something safe," and the prose rules stay authoritative underneath it
regardless (FR-009's own framing).

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001, FR-002, SC-001 (eight scripts; conformance runs them directly) | `bundles.sh`'s eight scenarios invoke the installed script files with real argv; a new assertion finds zero `:start`/`:end` markers in the installed commands | `bash scripts/conformance/bundles.sh` |
| FR-003, FR-006, SC-002 (session-start context line, clean no-op) | unit tests for the context-line formatter over `status`'s existing JSON shape; ten consecutive sessions during this round's own delivery, transcripts as evidence | `uv run pytest packages/spec-kit-linear/tests`; this round's own session transcripts |
| FR-004 (`next_action` returns commands) | table-driven unit tests over every `(state, source)` pair, asserting no returned string lacks a leading `/speckit.` or the literal wait-for-merge sentence | `uv run pytest packages/spec-kit-linear/tests` |
| FR-005 (post_tool_use reconcile, no prose reconcile instruction left) | unit test of the Bash-payload filter; grep confirms no "reconcile" instruction survives in the new `implement.md` | `uv run pytest packages/spec-kit-linear/tests`; `grep -n reconcile presets/default/commands/implement.md` |
| FR-007, FR-008, SC-003, SC-004 (guards block before the action) | unit tests over `guard.sh` for all four rules plus the branch/path exemptions; live verification on Claude and Codex here, Cursor in app-maker (D12) | `bash packages/spec-kit-code-review/scripts/conformance/*.sh`; this round's own transcripts on each agent |
| FR-009 (doctor names the degradation) | doctor.md text review; a conformance fixture without an events-capable agent | manual read; `bash scripts/conformance/bundles.sh` |
| FR-010, FR-011, SC-005 (single coherent `implement`/`tasks`) | manual read of the installed `speckit-implement`/`speckit-tasks` skill finds no "core" vs. "this loop wins" contradiction language | review of the rendered command after `specify integration install` |
| FR-012, SC-006 (doctor's fixed order) | `doctor.md`'s summary step names the five categories explicitly; a fresh, unconfigured consumer fixture shows the gaps in order | `bash scripts/conformance/bundles.sh`; `/speckit.doctor` on a clean fixture |
| FR-013 (README opens with four commands) | manual read; golden rules split into dev-does / loop-guarantees | review |
| FR-014, SC-007 (`completions` gone) | grep across both packages' source, `commands/`, README; CLI invocation confirms no subcommand | `grep -rn completions packages/spec-kit-linear packages/spec-kit-code-review`; `bash .../run.sh completions` exits nonzero |
| FR-015 (`after_implement` hook gone) | grep confirms no hook entry | `grep -n after_implement packages/spec-kit-code-review/extension.yml` (no match) |
| FR-016, FR-017, FR-018, SC-008 (three upstream PRs) | PR URLs recorded as evidence once opened | `gh pr list --repo github/spec-kit --author @me` |
| FR-019 (documentation) | files carry the text; `AGENTS.md` lists the two new Spanish exceptions | `git diff --check`; review |
| Regression safety | both package suites, conformance, this round's own dogfooding | `uv run pytest packages/*/tests`; `bash scripts/conformance/bundles.sh` |

## Source layout

```text
presets/default/scripts/bash/{task-base,budget-stop,stack-propagate,pr-create,merge-root-first,ledger-check,skill-mirror,ignore-entries}.sh  # FR-001 (D1)
presets/default/commands/{implement,tasks}.md           # new, strategy: replace (D3); implement-append.md, tasks-append.md removed
presets/default/commands/{pr,chore,bugfix,doctor}.md    # prose shrinks to script-invoking steps (D1, D7)
presets/default/{preset.yml,README.md}                  # type: script entries, replace strategy, 0.10.0 (D1, D3, D13)
packages/spec-kit-linear/extension.yml                  # events: session_start, post_tool_use (D4); speckit_version floor (D9); completions removed (D8)
packages/spec-kit-linear/commands/{session-start,post-tool-use}.md       # new, internal (D4)
packages/spec-kit-linear/scripts/bash/{session-start,post-tool-use}.sh   # new (D4)
packages/spec-kit-linear/src/spec_kit_linear/work_state.py              # next_action redesign (D6)
packages/spec-kit-linear/src/spec_kit_linear/reporting.py               # next_action call sites threaded (D6)
packages/spec-kit-linear/src/spec_kit_linear/completions.py             # removed (D8)
packages/spec-kit-linear/{README.md,CHANGELOG.md}                       # 0.13.0
packages/spec-kit-code-review/extension.yml              # events: pre_tool_use (D5); after_implement hook removed (D8); speckit_version floor (D9); completions removed (D8)
packages/spec-kit-code-review/commands/guard.md           # new, internal (D5)
packages/spec-kit-code-review/scripts/bash/guard.sh        # new (D5)
packages/spec-kit-code-review/src/spec_kit_code_review/completions.py   # removed (D8)
packages/spec-kit-code-review/{README.md,CHANGELOG.md}    # 0.5.0
scripts/conformance/bundles.sh                             # direct script invocation (D2)
docs/{vision.md,plan.md,dogfooding.md} · AGENTS.md · README.md           # FR-019, D10
.github/workflows/conventions.yml                          # regex read, not changed (D5)
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Two `pre_tool_use` registrations for code-review, matching `dx.md`'s literal framing | the manifest schema allows one handler mapping per event name per extension (`events.py:1843-1847`); a second top-level entry is schema-invalid, not merely unsupported |
| Keep `first-task-refresh`/`work-item-branch` as their own scripts (ten-plus scripts total) | speculative fragmentation past FR-001's eight named procedures; `task-base.sh`'s three modes cover the same ground as one FR-001 script |
| `pr-create.sh` also issues `gh pr create` itself, matching today's shape | conflates deterministic base-resolution with agent-authored title/body; reproduces the exact "replace only two of four placeholders" inconsistency found in today's `pr.md` |
| A new extension owning the eight scripts and/or the events | C-001 forbids it; the preset already owns the mechanism, `linear`/`code-review` already own their two concerns |
| Delete only the contradicting append sentences, keep `strategy: append` | leaves upstream's `[P]`-marker/parallel-execution model physically present in the rendered document; does not satisfy FR-010's "MUST NOT contain both" |
| A new config flag gating the new guards/reconcile | reuses `push --hook`'s existing `hooks.*` gate and the existing `protected_paths` field; a new flag is speculative configuration surface |
| Re-order the doctor by adding new flags to each sub-doctor's CLI so their checks interleave | a larger, cross-package change for a report-ordering requirement the summarization step can satisfy alone (D7) |

## Product handoff

`ready-for-development` requires all rows to be complete. Analysis
consistency is not technical approval.

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | not yet run — `/speckit.analyze` follows `/speckit.tasks` | pending |
| Technical approval of plan and tasks | this plan awaits human review | pending |
| Reviewed Linear dry-run and synchronization | `after_plan` hook result recorded in this phase's own report; `after_tasks` follows task generation | pending |
| Every executable task individually assignable and assigned | tasks not yet generated | pending |
