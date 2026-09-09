# Implementation Plan: Developer experience

**Feature directory**: `specs/005-developer-experience`
**Spec**: [spec.md](spec.md)

## Summary

Round 005 moves the delivery loop's mechanism out of command prose into
machinery the pinned CLI already supports. The default preset ships its
eight repeatable procedures as invocable Python scripts (`type: "script"`
preset entries) instead of inline shell an agent edits by hand;
conformance invokes them directly. The `linear` and `code-review`
extensions declare native runtime events so session context and
reconciliation happen without a prose reminder, and the four hard rules
block before the action instead of after. `implement` and `tasks` become
authored replacements of the upstream core instead of a base plus a
contradicting append; the doctor's existing checks already produce most
of the fixed onboarding order, so this round closes the summarization
gap and adds one new check, the Python interpreter. Three neutralized
local workarounds are prepared as upstream deletions. No new extension,
command, or persisted configuration — every new behavior reuses an
already-installed mechanism: `type: script` entries, extension `events:`
manifests, `push --hook`'s config gate, `protected_paths`.

## Technical context

- **Language/runtime**: preset commands stay agent-executed Markdown; the
  eight FR-001 procedures and the two extensions' three event handlers
  are Python 3.11+, standard library only, invoked with the interpreter
  upstream's own `py` script variant resolves — the consumer's `.venv`
  python when present, else `python3` on PATH (C-005); both packages
  already stay Python ≥3.11, stdlib-only, `uv`-managed; conformance
  stays bash.
- **Primary dependencies**: pinned upstream `specify-cli` 1.0.4
  (`versions.lock.yml`, confirmed installed); Python 3.11+ (upstream's
  own prerequisite; `resolve_python_interpreter`'s `.venv`-or-`python3`
  rule); `gh`; `git`; each verified agent's own native hook runtime
  (Claude Code, Codex, Cursor — no SDK, no new package). Nothing added to
  either package's `pyproject.toml`.
- **Storage/state**: no new persisted configuration schema (see Data and
  migration behavior); new physical files only, materialized by the
  existing install mechanism — the preset's eight `scripts/python/*.py`
  and the two extensions' three internal command+script pairs.
- **Verification**: package pytest suites (`uv run pytest
  packages/<package>/tests`); `bash scripts/conformance/bundles.sh`
  (redesigned, D2); live verification on Claude Code and Codex in a
  temporary consumer repository and Cursor in the app-maker consumer
  (A-002, D12); this feature's own delivery as dogfood evidence for
  SC-002 through SC-004, as `specs/004-delivery-discipline/plan.md`
  proved its own loop rules through its own transcripts.
- **Target environment**: any upstream-supported agent for the script
  layer (FR-001/FR-002); Claude Code, Codex, and Cursor for the events
  layer this round proves; every other agent (Zed, today) degrades
  explicitly (A-003); macOS/Linux, with Python 3.11+ on PATH or in a
  project `.venv`.
- **Constraints**: C-001 through C-006 (`spec.md`); the extension
  manifest schema allows exactly one handler mapping per event name per
  extension (shapes D5); the 400-line task budget with the 2× stop;
  release lag (A-002) — this repository's own loop stays on the
  installed releases for the whole round (D12), like every other
  consumer, until they publish and bundle-update.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| specify-cli (upstream) | 1.0.4 (`versions.lock.yml`) | https://github.com/github/spec-kit |
| specify-cli runtime events (`events:`, `CANONICAL_EVENTS`, the dispatcher) | 1.0.4, installed source | `specify_cli/events.py`, `extensions/__init__.py`, `integrations/{claude,codex,cursor_agent}/__init__.py` — Spec Kit's own reference pages do not document this yet |
| Claude Code hooks (SessionStart/PreToolUse/PostToolUse payload shape) | installed Claude Code | https://docs.claude.com/en/docs/claude-code/hooks — confirm exact payload field names (`tool_name`, `tool_input.*`) before the `guard`/`session-start` subcommands are written |
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
| VI. Traceable delivery units | PASS | PASS | `ledger_check.py` turns "checked box + Completion evidence" into a script-enforced gate instead of trusted agent memory (D1); every task still forecasts lines under the 400-budget |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| `presets/default` (`preset.yml`, `commands/`, new `scripts/python/`, new `tests/`) | this repo | eight scripts (D1); a pytest suite (D2); `implement`/`tasks` become `strategy: replace` (D3); `pr.md`/`chore.md`/`bugfix.md`/`doctor.md` prose shrinks to script-invoking steps | no new command, no new flag, no PowerShell twin for the eight scripts (C-005) |
| `packages/spec-kit-linear` | this repo | `events:` block (D4); two new internal commands+scripts; `next_action` redesign (D6); `speckit_version` floor (D9); `completions` removed (D8) | no new config schema; `onboard`/`push`/`status`'s own behavior unchanged |
| `packages/spec-kit-code-review` | this repo | `events:` block (D5); one new internal command+script; `after_implement` hook removed (D8); `completions` removed (D8); `speckit_version` floor (D9) | no new verdict value, no publish-path change; `protected_paths` reused, not changed |
| `scripts/conformance/bundles.sh` | this repo | invokes installed scripts directly (D2); the "retired `scripts/` directory" assertion inverted | `--published` mode and CI scope unchanged |
| `docs/vision.md`, `docs/plan.md`, `docs/dogfooding.md`, `AGENTS.md`, `README.md` | this repo | FR-019 (D10); README's four-commands opening (FR-013) | translating documents; no new sections beyond what FR-019 names |
| Upstream `github/spec-kit` | upstream | three patches prepared (D11), not merged by this round | no fork, no local patch of the pinned tree (Constitution I) |
| App-maker consumer (Cursor verification) | separate repo | none — read-only verification target for A-002/D12 | this plan does not modify app-maker |

## Technical decisions

### D1. Preset scripts: layout and invocation contract (preset)

- **Decision**: eight Python 3.11+ scripts, standard library only, at
  `presets/default/scripts/python/{task_base,budget_stop,stack_propagate,
  pr_create,merge_root_first,ledger_check,skill_mirror,ignore_entries}.py`
  — snake_case, upstream's own naming convention for its `python` script
  variant (`scripts/python/setup_plan.py` and siblings) — each a
  `preset.yml` entry with `type: "script"` (a first-class primitive,
  `presets/__init__.py:271`), a hyphenated `name`
  (`presets/__init__.py:518`'s `^[a-z0-9-]+$` rule, e.g. `task-base`) and
  a `file:` field naming the matching snake_case file (e.g.
  `file: "scripts/python/task_base.py"`), and `strategy: "replace"`
  (`presets/__init__.py:274`; no upstream base to
  `wrap`). A shared helper module — fence-aware ledger parsing, the
  `gh --json` and `git` calls every script needs — lives beside them in
  the same directory and ships with the directory copy; it is not
  independently invocable and takes no `preset.yml` entry of its own,
  only the eight scripts do. Installed by full-directory
  `shutil.copytree` (`presets/__init__.py:3874`) to
  `.specify/presets/default/scripts/python/`; the owning command invokes
  the script there directly — `python3
  .specify/presets/default/scripts/python/task_base.py ...`, mirroring
  upstream's own rendered `py` variant (the interpreter
  `resolve_python_interpreter` picks: the consumer's `.venv` python when
  present, else `python3` on PATH; C-005) — never the extensions' own
  `run.sh` (`uv run`) indirection, which stays reserved for the
  user-facing extension commands (D4, D5). The "replace only the
  literal" pattern is gone by construction — commands pass real argv
  instead of the agent editing placeholder text before invocation.
- `task_base.py` absorbs three setup blocks that exist today as separate
  marked shell — `task-base`, `first-task-refresh`, and `work-item-branch`
  (byte-identical, pasted in both `chore.md` and `bugfix.md`) — as three
  modes of one script, since FR-001 names "per-task setup" as a single
  procedure:
  - `task_base.py refresh` — today's `first-task-refresh` (merge the
    delivery base into the feature branch, once per feature).
  - `task_base.py task <NNN-T###-slug>` — today's `task-base` (branch from
    the open task stack's top, or the feature branch).
  - `task_base.py work-item <branch-name>` — today's `work-item-branch`
    (branch from the delivery base), called identically from `chore.md`
    and `bugfix.md`: one script, two callers — the byte-identity check at
    `bundles.sh:773-780` becomes structural, not textual.
  - Every mode ends the same way: when `.specify/extensions/linear`
    exists, it calls `bash .specify/extensions/linear/scripts/bash/run.sh
    push --hook` — silent no-op without the extension. `post_tool_use`
    (D4) fires only on `git push`/`gh pr`, never on a local branch
    creation, so today's reconcile-right-after-branch sentences —
    `implement-append.md:61-62` after `task-base`, `chore.md`/
    `bugfix.md`'s `push --apply` after `work-item-branch` — have no event
    to replace them; ending the script this way makes the branch's *In
    Progress* projection mechanical instead, and neither sentence
    survives into any command this round ships (FR-005, SC-002).
- `pr_create.py <feature|task|work-item> [named-task]` resolves and
  prints `base=<name>` only, unchanged base-resolution rules (trunk
  config wins, else the GitHub default, else the open-task-stack head,
  with the branch-identity check against the ledger's first unchecked
  task); `pr.md`'s own prose keeps composing the title/body and running
  `gh pr create` itself. This deliberately splits deterministic
  base-resolution from the agent-composed `gh pr create` call — see
  Alternatives and `docs/dogfooding.md` entry 44 for the inconsistency it
  corrects: `pr.md` says "Replace only the delivery-kind and named-task
  literals" while its block also embeds two more untouched placeholders,
  `<type(scope): subject>` and `<the body>`.
- `budget_stop.py <task_id> <base>` and `stack_propagate.py <fixed_branch>`
  are direct translations of today's blocks — unchanged rules and
  exit-code/message conventions (`exit 2` with an `error: ...` diagnosis
  on stderr; `exit 0` with a one-line summary on stdout).
- `merge_root_first.py` (no required argument; self-derives the feature
  branch via `check-prerequisites.sh --paths-only`, as `task_base.py`/
  `budget_stop.py` already do) extracts today's prose-only "Between
  tasks" procedure — `git worktree prune`, then for each open task PR
  root-first, retarget by API (`gh api -X PATCH
  repos/{owner}/{repo}/pulls/<n> -f base=<feature-branch>`) and
  `gh pr merge <n> --merge` (never `--delete-branch`, the guard of
  D5/FR-007) — and runs only on an explicit human instruction in the
  conversation: the script performs the mechanical steps, the "yes,
  merge" itself stays a conversation-level decision.
- `ledger_check.py <task_id>` verifies, deterministically, what the
  loop's prose today only asks the agent to remember — the task's
  checkbox is `[x]` and its **Completion evidence** field is filled, not
  "Pending" or empty — before the command marks the PR
  `ready for review`; same fence-aware ledger parsing (the shared helper
  module above) as `budget_stop.py`/`pr_create.py`'s task case. `exit 2`
  names exactly what's missing, turning "the agent forgot" into a
  script-enforced gate.
- `skill_mirror.py <true|false>` and `ignore_entries.py <true|false>` are
  direct translations of `doctor.md`'s two largest blocks — 110 and 22
  lines, dogfooding entry 41 — called from `doctor.md`'s steps 5 and 6
  with `fix` taken from whether the user asked to fix.
- **Rationale**: FR-001/FR-002 require each of these eight procedures to
  be a dedicated, directly-invocable script; `type: "script"` is the
  CLI's own mechanism for exactly this, and it installs with zero new
  dependency — Python 3.11+ is already an upstream prerequisite and the
  language both packages are already written in (see Alternatives).
- **Trade-off**: `task_base.py`'s three modes are one script with a mode
  argument rather than three separate scripts — simpler surface, at the
  cost of one positional argument every caller must pass correctly.

### D2. Conformance invokes the installed scripts directly (scripts)

- **Decision**: `scripts/conformance/bundles.sh` drops its
  `sed -n '/X:start/,/X:end/p' "$installed_skill"` extraction and its
  `render_*` sed-substitution helpers (`render_pr_create`,
  `render_task_base`, `render_stack_propagate`, `render_budget_stop`,
  `render_fix` — `bundles.sh:642-645,872-874,967-969,1024-1027,1099`)
  entirely. Each scenario instead invokes the installed file directly —
  `python3
  "$consumer_root/.specify/presets/default/scripts/python/<name>.py"
  <argv>` — against the same fake-`git`/fake-`gh` PATH harness already in
  place; the scenario-level assertions (which git/gh calls happen, in
  what order, with what argv) are unchanged, since the scripts' behavior
  is unchanged from the blocks they replace. `bundles.sh` itself stays a
  bash script — only what it invokes changes language — and this
  installed-artifact smoke is now the second layer: the preset also
  gains its own `presets/default/tests/` pytest suite (fixtures for the
  ledger, the stack, and the budget) exercising each script's logic
  directly, run the same way the two packages' own suites already are —
  `uv run pytest presets/default/tests`. `bundles.sh` keeps proving the
  installed, packaged artifact behaves the same way; the pytest suite
  proves the logic.
- `bundles.sh:550-551` —
  `[ -e "$consumer_root/.specify/presets/default/scripts" ] &&
  fail "trunk: the retired scripts/ directory is still installed"` — is a
  regression trap from round 004, which retired a Python
  `resolve-delivery-base` script specifically to avoid a `scripts/`
  directory; round 005 reintroduces one through the CLI's own `type:
  script` primitive, not an ad hoc resolver. The assertion is replaced
  with its opposite — the eight files exist at that path.
- `bundles.sh:636-637`'s own regression trap — `grep -Eq
  'python3|resolve-delivery-base' "$skill" && fail "... still references
  the retired Python resolver"` — stops being valid once this round's own
  `pr.md`/`implement.md` legitimately invoke `python3` for D1's scripts;
  its pattern narrows to `resolve-delivery-base` alone, the literal name
  of the round-004-retired script it was written to catch.
- A new assertion proves SC-001 directly: the installed command files
  (`speckit-implement`, `speckit-pr`, `speckit-chore`, `speckit-bugfix`,
  `speckit-doctor`) contain no `# <name>:start`/`# <name>:end` marker
  pairs at all.
- The `work_item_branch`/`bugfix_work_item_branch` byte-identity
  assertion (`bundles.sh:773-780`) is replaced by asserting both
  `chore.md` and `bugfix.md` invoke the same
  `task_base.py work-item <branch>` call — identity is now structural
  (one script, two call sites), the direct product of D1's consolidation.
- **Rationale**: FR-002 — conformance must report the script's own
  result, never a block extracted from prose; also materially simpler,
  with no `render_*` sed layer or placeholder syntax to keep in sync.
- **Trade-off**: none — a strict simplification of the existing harness.

### D3. `implement` and `tasks` become authored replacements (preset)

- **Decision**: `preset.yml`'s `speckit.implement` and `speckit.tasks`
  entries change `strategy: "append"` → `strategy: "replace"`, with new,
  freestanding `commands/implement.md` and `commands/tasks.md` (replacing
  `implement-append.md`/`tasks-append.md`). `speckit.specify`,
  `speckit.plan`, and `speckit.analyze` keep `strategy: "append"` — their
  append (`phase-close-append.md`) has no equivalent contradiction with
  their upstream cores. `presets/__init__.py:6053-6056`: "If the top
  (highest-priority) layer is replace, it wins entirely — lower layers
  are irrelevant regardless of their strategies," so the rendered command
  becomes the new file's raw content alone; upstream's core
  `implement.md`/`tasks.md` (`core_pack/commands/{implement,tasks}.md` —
  222/219 lines, ~12.4/10.8 KB) contributes nothing, closing FR-010/
  FR-011 by construction instead of by an appended sentence telling the
  agent which half to disregard.
- Because `replace` discards the upstream file wholesale, including its
  frontmatter, the new files carry their own `scripts:` frontmatter block
  verbatim from upstream core (`sh: scripts/bash/check-prerequisites.sh
  --json --require-tasks --include-tasks` for implement;
  `sh: scripts/bash/setup-tasks.sh --json` for tasks), which resolves the
  body's `{SCRIPT}` placeholder — dropping it silently breaks the
  command, the one non-negotiable constraint here.
- Content shape: the new files keep upstream's still-useful,
  non-contradicted Outline steps — the prerequisites-script Setup step,
  the checklist-status gate, and loading `plan.md` and `tasks.md`, plus
  `data-model.md`/`research.md`/`quickstart.md`/`constitution.md` when
  present — rewritten in this distribution's voice, and fold in this
  repository's own loop as the sole execution-order model, replacing
  upstream's generic "phase-by-phase, `[P]`-parallel, TDD-first" model
  wholesale. `implement.md`'s own "Project Setup Verification" step —
  its per-language `.gitignore`/`.dockerignore` pattern list, some sixty
  lines — is dropped outright: it is not the loop's concern, and the
  doctor already owns ignore entries end to end (D1's
  `ignore_entries.py`, `doctor.md` step 6). That upstream model is
  exactly what `tasks-template.md` and the delivery loop already
  supersede: upstream `tasks.md`'s own "Checklist Format" section
  requires `[P]` markers ("3. **[P] marker**: Include ONLY if task is
  parallelizable") and "Create parallel execution examples per user
  story" — the literal contradiction FR-011 names. The hook-announcement
  boilerplate (`Pre-Execution Checks`/`Mandatory Post-Execution Hooks`,
  upstream's printed "Optional Hook" block) is authored directly as this
  distribution's silent behavior instead of surviving as text an
  override bullet then contradicts.
- **Rationale**: FR-010's own wording — "MUST NOT contain both an
  upstream base procedure and a locally authored override that
  contradicts it" — is only satisfiable by removing the base from the
  render entirely; deleting the contradicting sentences while keeping
  `strategy: append` would still leave upstream's parallel-task model
  physically present in the same document.
- **Trade-off**: real authoring work — a document rewritten from two
  ~200-line sources, not a mechanical merge — the largest single task
  User Story 4 produces, sized and reviewed as its own delivery unit; the
  two files then drift from upstream silently on a future CLI upgrade
  (no append left to reconcile against) — accepted, consistent with how
  `speckit.doctor`/`speckit.pr` are already full replacements with no
  upstream base at all.

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
  a `scripts: {py: scripts/python/<name>.py}` frontmatter block (no
  `sh`/`ps` variant — none needed) and no other required field. Each
  `.py` — `session_start.py`, `post_tool_use.py` — is a three-line shim:
  add the package's own `src/` to `sys.path`, call the matching
  subcommand of the existing CLI module
  (`packages/spec-kit-linear/src/spec_kit_linear/cli.py`), exit with its
  return code. The logic described below, and its unit tests, live in
  that subcommand, not in the shim. The dispatcher runs the shim with
  its own interpreter (`sys.executable`, already resolved when the
  dispatcher itself was generated), so this hook path never goes through
  `run.sh`'s `uv run` indirection — 0.02 s instead of 0.12 s. The
  user-facing commands (`push`, `status`, `onboard`) keep `run.sh`
  unchanged; this shim exists only for the two events.
- **Naming**: because these two commands are not registered under
  `provides.commands`, the dispatcher resolves them by matching a
  `commands/` file's stem against the raw `command:` string
  (`_find_command_template`'s on-disk fallback, `events.py:123,165-174`)
  — never against the `speckit.`/`spec.`-prefixed form the
  registered-manifest path tolerates (`events.py:125-163`) — so
  `session-start`/`post-tool-use` must stay undotted and equal to their
  own filename, breaking the extension's dotted convention on purpose.
  `docs/dogfooding.md` entry 46 records why and the risk of "fixing" it
  back: the dispatcher fails open (exit 0, no error) on a resolution
  miss, so a mismatch here means the event silently never fires, not a
  startup error.
- The `session-start` subcommand does two things, in order: (1)
  `push --hook` (unchanged entrypoint and config gate —
  `hooks.lifecycle_enabled`/`auto_apply` in `speckit-linear.yml`, already
  a documented clean no-op without configuration); (2) reads the current
  branch and calls `status --current --json` (existing, read-only) to
  build one context block.
- **Context content, by branch shape (FR-003)**, fixing the required
  fields and their order — exact spacing is an implementation choice:
  - Feature or task branch (`NNN-...` or `NNN-T###-...`): the branch, the
    feature identifier, the first unchecked task from `status`'s
    `task_rows[].tasks[]` (first entry with `local_complete: false`),
    every open task pull request (rows whose `state_source == "pr"`), and
    the next command from the redesigned `next_action` (D6): `Linear:
    <feature> on <branch> — next <T###> (unchecked); open task PRs:
    <branch> -> #<n> (<review|started>)[, ...]; next: <command>`
  - Work-item branch (`<team-key>-<n>-...`): the issue key, its derived
    state, and the next command, from `status`'s `work_items[]` row for
    that key: `Linear: <ISSUE-KEY> (<state>) — next: <command>`
  - Neither shape, or no `speckit-linear.yml`: no line at all (FR-006) —
    the subcommand prints nothing and exits 0, which the dispatcher's
    `_emit` already treats as "emit nothing" for empty output
    (`events.py:331-332`).
- The `post-tool-use` subcommand, matcher `Bash` (so the native hook
  fires only for Bash calls — the default `"*"` matcher would fire on
  every tool otherwise): reads the PostToolUse payload's
  `tool_input.command`; when it matches `git push` or
  `gh pr (create|ready|merge)`, runs `push --hook`; otherwise exits 0
  silently. This mechanically replaces the loop's
  reconcile-after-push/PR sentences (FR-005); the
  reconcile-after-branch-creation sentence is `task_base.py`'s own
  `push --hook` instead (D1), since `post_tool_use` never fires on a
  local branch creation — between the two, no reconcile sentence survives
  in `implement.md`'s replacement (D3) or in `chore.md`/`bugfix.md`.
- **Rationale**: FR-003 through FR-006; both handlers reuse the same
  `push`/`status` entrypoints and config gates the extension already
  ships — no new config schema, no new credential path.
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
  `scripts: {py: scripts/python/guard.py}`. `guard.py` is the same
  three-line shim as D4's: it adds the package's own `src/` to
  `sys.path` and calls the `guard` subcommand of the existing CLI module
  (`packages/spec-kit-code-review/src/spec_kit_code_review/cli.py`),
  where the two guards below and their unit tests live; the dispatcher's
  own interpreter runs it, no `run.sh`/`uv run` indirection in this path.
- **Why one registration, not two**: an extension manifest's
  `events.<name>` value must be a single mapping, never a list —
  `extensions/__init__.py:391-393` routes any `events:` key to
  `events.py`'s `validate_events`, which raises `"Invalid event '<name>':
  expected a mapping"` the moment `event_config` is not a `dict`
  (`events.py:1843-1847`), and `collect_extension_events`
  (`events.py:1029-1105`) only ever accumulates handlers **across
  different extensions**, never two from the same manifest. So
  code-review's two guard concerns (`dx.md`'s "matcher `Bash`" and
  "matcher `Edit|Write`" framing) cannot be two top-level `pre_tool_use`
  entries in one `extension.yml`; they are two branches inside the one
  `guard` subcommand, dispatched on the native payload's `tool_name`,
  under the union matcher `"Bash|Edit|Write"`. Documented in
  `docs/dogfooding.md` entry 45.
- `guard` subcommand behavior:
  - `tool_name == "Bash"`: reads `tool_input.command`; blocks (`exit 2`,
    message naming the fix) a `git commit -m` whose subject fails
    `^[a-z]+\([a-z0-9-]+\): .+$` — the pattern
    `.github/workflows/conventions.yml` already enforces server-side;
    any form of `git push --force`/`-f`/`--force-with-lease`; and any
    `gh pr merge ... --delete-branch`. Anything else: `exit 0`, silent.
  - `tool_name` in `("Edit", "Write")`: reads the target path and the
    current branch; on a `NNN-T###-*` branch (the numeric-prefix rule
    `specs/004-delivery-discipline/plan.md` D1 already established),
    blocks a write matching any `protected_paths` glob
    (`speckit-code-review.yml`, unchanged default `specs/*/spec.md` and
    `.specify/memory/constitution.md`), naming the protected path. A
    feature branch (no `T###` segment) is exempt, matching round 004's
    own exemption and this round's own C-006.
  - Everything else: `exit 0`, silent — C-002's "no guard beyond the four
    named" holds by construction.
- No new config: the commit-subject pattern and the force-push/
  `--delete-branch` forms are structural, mirroring CI exactly;
  `protected_paths` already exists.
- **Rationale**: FR-007, FR-008; reusing the exact server-side regex
  keeps the client-side block and the server-side gate from ever
  disagreeing.
- **Trade-off**: one subcommand now owns two logically separate concerns
  — accepted; two registrations is not schema-valid, not a stylistic
  choice.

### D6. `next_action` returns runnable commands (linear)

- **Decision**: `packages/spec-kit-linear/src/spec_kit_linear/
  work_state.py`'s `next_action` (lines 161-190, read in full) is
  rewritten so every non-`None` return is either a slash command or the
  literal "wait for the human merge" sentence — never a gesture the agent
  has to translate. Its `STATE_UNSTARTED` branch today returns
  `f"start: create branch {prefix}-<slug>"` (`work_state.py:187-189`) —
  the exact "create the branch" gesture FR-004's acceptance scenario 3
  names as what must stop happening.

  | Derived state | Current text (`work_state.py:177-189`) | Redesigned |
  | --- | --- | --- |
  | `completed`, `checked=False` | "record completion evidence and check the box in tasks.md" | `None` — this combination means the merge outran a local sync; nothing local is actionable |
  | `review` | "await the final review and the human merge" | "wait for the human merge" |
  | `started`, source `pr` | "self-review (/speckit.code-review), then mark ready for review" | `/speckit.code-review <n>` — ready-for-review is the review command's own completion instruction, not a second gesture named here |
  | `started`, source `branch` | "open the draft PR" | `/speckit.pr` |
  | `unstarted` (feature task only) | `"start: create branch {feature}-{task}-<slug>"` | `/speckit.implement <feature>` — the command that now runs `task_base.py task`, not the developer by hand |

- The work-item `unstarted` row is gone, not reworded: a work item is
  listed by `status` only when a branch or PR names it — "an Issue
  nobody has started is never observed" (`packages/spec-kit-linear/
  README.md`, "Bugs and chores") — so `build_work_item_rows`' call to
  `next_action` (`reporting.py:129`) never receives `STATE_UNSTARTED`;
  the row was always unreachable, and `next_action` gains no issue-key
  parameter. What it gains is a PR number, for the `started`/`pr` row
  alone, identical for a task or a work item. That number is not in
  scope today: `PullRequest` carries only `head_branch`, `is_draft` and
  `state`, and `GH_JSON_FIELDS` requests `headRefName,isDraft,state`
  (`github.py`). It becomes one more field on the existing `gh pr list`
  query and on `PullRequest`, threaded through `build_task_rows` and
  `build_work_item_rows` — not a new `gh` call.
- **Rationale**: FR-004's own wording, and its own negative example is
  code that exists today.
- **Trade-off**: `next_action`'s existing contract ("pure text over the
  observable state... never adds signals") stays true — only the emitted
  text and the function's parameters change, never what it observes.

### D7. Doctor's fixed onboarding order (preset)

- **Decision**: `doctor.md` gains a new first step that resolves the
  Python interpreter with upstream's own rule (`.venv/bin/python` when
  present, else `python3` on PATH — the same rule C-005 binds every
  FR-001 script and event handler to), reports its version, and names
  the fix when it is older than 3.11 or absent — for example `uv python
  install 3.11 --default`, or activating the right venv; a consumer's
  old `.venv` is the case this catches. Its summarization step (today's
  step 4) gains explicit instructions to group every reported gap into
  six fixed categories, in this order, regardless of which sub-doctor
  produced the underlying diagnostic: (1) the Python interpreter, (2)
  GitHub CLI authentication, (3) the Linear API key, (4) the Linear
  onboarding binding, (5) the review engine installation, (6) the
  repository's GitHub delivery settings (unchanged step 3, still
  report-only per FR-012's own carve-out). No change to either package's
  own `doctor` implementation — the interpreter check is new prose
  `doctor.md` owns directly, the same way it already owns the
  GitHub-settings check.
- **A report-ordering fix for five of six categories, plus one new
  check**: linear's `run_doctor` (`cli.py:384-428`) already emits
  `github_cli_diagnostic` (`cli.py:404`) before `linear_auth`
  (`cli.py:422`) before `linear_binding` (`cli.py:423`) — categories
  2-3-4 already come out in order from one sub-doctor call. Code-review's
  `run_doctor` (`doctor.py:204-221`) calls `_check_ocr` (category 5,
  `doctor.py:215`) **before** `_check_gh` (`doctor.py:216`), so "run
  linear's doctor, then code-review's, print everything in order" is not
  sufficient. The fix for categories 2-6 is categorization at summary
  time: map each diagnostic's code (`github_cli_diagnostic`/`_check_gh`
  → 2, `linear_auth` → 3, `linear_binding` → 4, `_check_ocr` → 5) into
  the fixed list, independent of which sub-doctor produced it or in what
  order it printed. Category 1 has no sub-doctor diagnostic to
  categorize — it is the one check `doctor.md` performs itself.
- `--fix` scope is unchanged: FR-012's "resolves every gap ... that can be
  resolved mechanically" is already each doctor's own `--fix` passed
  through (doctor.md's existing step 2, "you never fix anything
  yourself"); the GitHub-settings category stays read-only even under
  `--fix` — this round's own scope boundary, applying them is the
  releases round's. The Python interpreter category is report-only the
  same way: the doctor names the fix, never runs it.
- **FR-009's own doctor step, read-only**: for each key in
  `.specify/integration.json`'s `installed_integrations`, checks whether
  its runtime events are wired — the generated dispatcher
  `.specify/events.py` exists, and the integration's native hook file
  (its `events_config_file`: `.claude/settings.json`,
  `.codex/config.toml`, `.cursor/hooks.json`, one per integration class)
  carries the `__speckit_event__` marker every generated hook writes
  (`events.py:50`). No `events_config_file` at all (Zed, today) means
  nothing to check; the doctor states plainly that FR-007/FR-008's
  guards and FR-003/FR-005's Linear behaviors do not run there and the
  prose rules stay authoritative — the whole of what FR-009 owes. Two
  file reads per installed integration, nothing written, even under
  `--fix`.
- **Rationale**: FR-009, FR-012, minimal-footprint per AGENTS.md — one
  new interpreter check, a prose reordering, and a read-only wiring
  check close all three gaps; neither package's doctor needs new flags
  or new check sequencing.
- **Trade-off**: the fixed order lives in agent-executed prose, not in a
  script — acceptable, since categorizing five diagnostics and reading
  one interpreter's version are summarization judgments, not a
  mechanical procedure with clean argv (unlike the eight FR-001
  procedures).

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
  `event run` stdin fix ship (A-001; `versions.lock.yml` already pins
  `tag: v1.0.4`, `package_version: 1.0.4`). `presets/default/preset.yml`'s
  own `requires.speckit_version` is left unchanged — its new surface
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
  this round's own delivery, on Claude Code and Codex inside a temporary
  consumer repository, and on Cursor in app-maker once published (A-002)
  — never by dev-installing into this checkout, which commits its
  installed extension payloads (`.specify/extensions/{linear,
  code-review}/`, vendored from the published tags, PR #80); AGENTS.md
  requires a fixture for exactly this kind of state-changing
  verification. Built the way `bundles.sh`'s `new_consumer` builds its
  fixture (`bundles.sh:330-344`: fresh directory, `git init`,
  `specify init --here --force`), then `specify extension add <path>
  --dev` against `packages/spec-kit-linear` and
  `packages/spec-kit-code-review`, and `specify preset add --dev`
  against `presets/default`, so the events under test are this round's
  own in-progress code. Verified wiring: after
  `specify integration install <key> --force`, the handler appears in
  `.claude/settings.json` (`events_format: "json-nested"`,
  `integrations/claude/__init__.py:57-66`) and `.codex/config.toml`
  (`events_format: "toml"`, `integrations/codex/__init__.py:32-41`); a
  `session_start` handler's stdout surfaces as context on both (the
  default "plain" envelope, `events.py:326`, passthrough, no JSON
  wrapping); a `pre_tool_use` handler's `exit 2` blocks the tool call on
  both, since `_run_inline` (`events.py:274-303`) propagates the
  handler's exit code as the dispatcher's, which each agent's hook
  runner treats as "block".
- Cursor's format (`events_format: "json-flat"`, camelCased native names
  — `integrations/cursor_agent/__init__.py:41-49`) and its
  `events_context_envelope` (`session_start` → `additional_context`,
  everything else → `suppress`, `cursor_agent/__init__.py:55-59`) mean
  its `preToolUse` communicates block/allow by exit code alone, never
  injected text — exit-code-only verification, which is all `guard`
  needs anyway (its message lands on stderr regardless of agent,
  `events.py:294-295`).
- Zed has no `events:` wiring at all — no `CANONICAL_TO_NATIVE`/
  `events_config_file` in `integrations/zed/` — A-003's explicit
  degradation; FR-009's doctor sentence is the only artifact this round
  owes Zed users.
- **Rationale**: A-002; proves the mechanism on every agent this round
  can reach, without a fixture-rule violation on this checkout's own
  vendored payloads.
- **Trade-off**: publication lag — other consumers get the events layer
  only once the extensions publish and bundle-update, same as every
  prior release; this repository's own loop keeps running on the
  installed releases for the whole round, exactly as round 004's loop
  did (`specs/004-delivery-discipline/plan.md` D14's trade-off).

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
eight `scripts/python/*.py` (materialized by `specify preset add`, not
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
  (no-op) for lifecycle events"; `_resolve_argv` returning `None`), so a
  wrong handler filename (D4's naming constraint) or a missing script
  never fires but never blocks either — why D12's live cross-agent
  verification, not a conformance assertion, is this round's only way to
  catch that class of mistake. `guard`/`session-start`/
  `post-tool-use` exit 2 with a stderr message naming the fix on every
  blocking path, matching the existing script convention (D1).
- **Retry/idempotency**: `push --hook` is already idempotent (unchanged);
  the guard subcommand is pure per invocation (re-evaluates the payload
  every call, remembers nothing); `ledger_check.py`/`merge_root_first.py`
  re-derive from repository state exactly like `task_base.py`/
  `stack_propagate.py` already do.
- **Rollout**: the eight preset scripts and the `implement`/`tasks`
  replacement apply to this repository immediately through the
  dev-installed preset (`specify preset remove default && specify preset
  add --dev presets/default`, dogfooding entry 35's own upgrade recipe);
  the two extensions' `events:` declarations apply here, like to every
  other consumer, only once published and bundle-updated (A-002) —
  proven beforehand in a temporary consumer repository for Claude and
  Codex, and in app-maker for Cursor once published (D12); Zed and any
  other non-event agent get the documented degradation (A-003), never a
  broken command.
- **Rollback**: every changed file is text or a script — revert by
  commit, matching `specs/004-delivery-discipline/plan.md`'s own D8
  revert convention (`git revert --no-commit`, `revert(scope): subject`);
  no data migration exists to unwind.

## Security and privacy

No new credential and no new remote write. The `session-start`/
`post-tool-use` subcommands call the same `push --hook` entrypoint that
already resolves `LINEAR_API_KEY`/`LINEAR_OAUTH_ACCESS_TOKEN`. `guard`
reads only the native tool-call payload the agent's runtime already
handed it (command text, file path) and the repository's own committed
`protected_paths` — never a secret, never a remote call. The
PreToolUse/PostToolUse/SessionStart payload lands on the handler
shim's stdin and nowhere else (`events.py`'s `_run_inline`,
`input=payload`); nothing this round writes it to a file or logs it.
Trust boundary: a handler now runs on every relevant tool call, so its
correctness joins the agent's control flow for the first time (a bug in
`guard` could wrongly block or, worse, wrongly allow); the fail-open
dispatcher means a broken handler degrades to "no guard," never to
"agent hangs" or "a wrong action force-blocks something safe," and the
prose rules stay authoritative underneath regardless (FR-009).

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-001, FR-002, SC-001 (eight scripts; conformance runs them directly) | a `presets/default/tests/` pytest suite exercises each script's logic directly (ledger, stack, and budget fixtures); `bundles.sh`'s eight scenarios invoke the installed `.py` files with real argv as an installed-artifact smoke; a new assertion finds zero `:start`/`:end` markers in the installed commands | `uv run pytest presets/default/tests`; `bash scripts/conformance/bundles.sh` |
| FR-003, FR-006, SC-002 (session-start context line, clean no-op) | unit tests for the context-line formatter over `status`'s existing JSON shape; ten consecutive sessions during this round's own delivery, transcripts as evidence | `uv run pytest packages/spec-kit-linear/tests`; this round's own session transcripts |
| FR-004 (`next_action` returns commands) | table-driven unit tests over every `(state, source)` pair, asserting no returned string lacks a leading `/speckit.` or the literal wait-for-merge sentence | `uv run pytest packages/spec-kit-linear/tests` |
| FR-005 (post_tool_use reconcile, no prose reconcile instruction left) | unit test of the Bash-payload filter; grep confirms no "reconcile" instruction survives in the new `implement.md` | `uv run pytest packages/spec-kit-linear/tests`; `grep -n reconcile presets/default/commands/implement.md` |
| FR-007, FR-008, SC-003, SC-004 (guards block before the action) | unit tests over the `guard` subcommand for all four rules plus the branch/path exemptions; live verification on Claude and Codex in a temporary consumer repository, Cursor in app-maker (D12) | `uv run pytest packages/spec-kit-code-review/tests`; `bash packages/spec-kit-code-review/scripts/conformance/*.sh`; this round's own transcripts on each agent |
| FR-009 (doctor names the degradation) | doctor.md text review; a conformance fixture without an events-capable agent | manual read; `bash scripts/conformance/bundles.sh` |
| FR-010, FR-011, SC-005 (single coherent `implement`/`tasks`) | manual read of the installed `speckit-implement`/`speckit-tasks` skill finds no "core" vs. "this loop wins" contradiction language | review of the rendered command after `specify integration install` |
| FR-012, SC-006 (doctor's fixed order) | `doctor.md`'s summary step names the six categories explicitly; a fresh, unconfigured consumer fixture shows the gaps in order | `bash scripts/conformance/bundles.sh`; `/speckit.doctor` on a clean fixture |
| FR-013 (README opens with four commands) | manual read; golden rules split into dev-does / loop-guarantees | review |
| FR-014, SC-007 (`completions` gone) | grep across both packages' source, `commands/`, README; CLI invocation confirms no subcommand | `grep -rn completions packages/spec-kit-linear packages/spec-kit-code-review`; `bash .../run.sh completions` exits nonzero |
| FR-015 (`after_implement` hook gone) | grep confirms no hook entry | `grep -n after_implement packages/spec-kit-code-review/extension.yml` (no match) |
| FR-016, FR-017, FR-018, SC-008 (three upstream PRs) | PR URLs recorded as evidence once opened | `gh pr list --repo github/spec-kit --author @me` |
| FR-019 (documentation) | files carry the text; `AGENTS.md` lists the two new Spanish exceptions | `git diff --check`; review |
| Regression safety | both package suites, the preset's own suite, conformance, this round's own dogfooding | `uv run pytest packages/*/tests presets/default/tests`; `bash scripts/conformance/bundles.sh` |

## Source layout

```text
presets/default/scripts/python/{task_base,budget_stop,stack_propagate,pr_create,merge_root_first,ledger_check,skill_mirror,ignore_entries}.py  # FR-001 (D1), + a shared helper module
presets/default/tests/                                  # new, pytest suite: ledger/stack/budget fixtures (D2)
presets/default/commands/{implement,tasks}.md           # new, strategy: replace (D3); implement-append.md, tasks-append.md removed
presets/default/commands/{pr,chore,bugfix,doctor}.md    # prose shrinks to script-invoking steps (D1, D7)
presets/default/{preset.yml,README.md}                  # type: script entries, replace strategy, 0.10.0 (D1, D3, D13)
packages/spec-kit-linear/extension.yml                  # events: session_start, post_tool_use (D4); speckit_version floor (D9); completions removed (D8)
packages/spec-kit-linear/commands/{session-start,post-tool-use}.md       # new, internal (D4)
packages/spec-kit-linear/scripts/python/{session_start,post_tool_use}.py # new shims (D4)
packages/spec-kit-linear/src/spec_kit_linear/cli.py                     # session-start, post-tool-use subcommands (D4)
packages/spec-kit-linear/src/spec_kit_linear/work_state.py              # next_action redesign (D6)
packages/spec-kit-linear/src/spec_kit_linear/reporting.py               # next_action call sites threaded (D6)
packages/spec-kit-linear/src/spec_kit_linear/completions.py             # removed (D8)
packages/spec-kit-linear/{README.md,CHANGELOG.md}                       # 0.13.0
packages/spec-kit-code-review/extension.yml              # events: pre_tool_use (D5); after_implement hook removed (D8); speckit_version floor (D9); completions removed (D8)
packages/spec-kit-code-review/commands/guard.md           # new, internal (D5)
packages/spec-kit-code-review/scripts/python/guard.py      # new shim (D5)
packages/spec-kit-code-review/src/spec_kit_code_review/cli.py          # guard subcommand (D5)
packages/spec-kit-code-review/src/spec_kit_code_review/completions.py   # removed (D8)
packages/spec-kit-code-review/{README.md,CHANGELOG.md}    # 0.5.0
scripts/conformance/bundles.sh                             # direct script invocation, python3 argv (D2)
docs/{vision.md,plan.md,dogfooding.md} · AGENTS.md · README.md           # FR-019, D10
.github/workflows/conventions.yml                          # regex read, not changed (D5)
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| POSIX `sh` scripts matching the blocks they replace | rejected: the awk/sed in those blocks is the hard part to maintain, JSON payloads and `gh --json` parse natively in Python, Python 3.11+ is already an upstream prerequisite and the language of both packages, and no PowerShell twin is needed |
| Two `pre_tool_use` registrations for code-review, matching `dx.md`'s literal framing | the manifest schema allows one handler mapping per event name per extension (`events.py:1843-1847`); a second top-level entry is schema-invalid, not merely unsupported |
| Keep `first-task-refresh`/`work-item-branch` as their own scripts (ten-plus scripts total) | speculative fragmentation past FR-001's eight named procedures; `task_base.py`'s three modes cover the same ground as one FR-001 script |
| `pr_create.py` also issues `gh pr create` itself, matching today's shape | conflates deterministic base-resolution with agent-authored title/body; reproduces the exact "replace only two of four placeholders" inconsistency found in today's `pr.md` |
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
