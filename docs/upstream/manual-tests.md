# Upstream manual-test evidence

Manual testing required by upstream `CONTRIBUTING.md` ("Manual testing",
"Determining which tests to run", "Reporting results") for the patches in
this directory. Covers `0001`, `0002`, `0005`, `0006`, `0007`, `0008` and
`0009`. `0003` and `0004` are parked and were not tested.

## Environment

| Item | Value |
| --- | --- |
| Distribution checkout | `tserdeiro/spec-kit` at `f09df307`, clean |
| Upstream base | `github/spec-kit` v1.0.4, `cb610277fdea781fcfa83d20522c2db37c94068d` (`versions.lock.yml`) |
| Patched tree | scratch worktree of the pinned clone; patches applied with `git apply --index` in order 0001, 0002, 0005, 0006, 0007, 0008, 0009, one commit each, all applied cleanly |
| Patch commits | `e74d97aa` 0001, `0484ef52` 0002, `6ee67873` 0005, `e88de9fc` 0006, `6f5113f3` 0007, `3418a7f5` 0008, `df688b10` 0009 |
| Contrast tree | second scratch worktree at `cb610277`, unpatched, used for the before/after comparisons below |
| CLI under test | `uv sync --extra test`; `specify version` → `1.0.4`; `specify_cli.__file__` resolves to the patched worktree's `src/specify_cli/__init__.py` |
| Python / pytest | 3.14.6 / 9.1.1 |
| OS / shell | macOS (Darwin 25.6.0) / zsh |
| Agent | Claude Code 2.1.236, headless: `claude -p "<slash command>" --model haiku --dangerously-skip-permissions` |
| Model | `claude-haiku-4-5-20251001` |
| Script type | `sh` (POSIX). `pwsh` is not installed on this machine |
| Codex | `codex` is not installed on this machine |

Every slash-command result below comes from a real headless agent session,
not from executing the skill instructions by hand. Where a run is reported
at script level rather than through the agent, the row says so.

### Automated gates

Gate check on the patched tree, before any manual test:

```
uv run --offline --extra test python -m pytest tests/test_agent_config_consistency.py -q
30 passed in 1.23s
```

Full suite on the patched tree:

```
.venv/bin/python -m pytest tests -q
11 failed, 7445 passed, 189 skipped, 48 warnings in 241.18s
```

The same 11 failures reproduce on the **unpatched** pin
(`11 failed, 228 passed, 53 skipped` for the same six files), so they are
pre-existing and unrelated to these patches. All eleven are PowerShell
paths that need a `pwsh` this machine does not have:
`tests/integrations/test_events.py::TestCommandRunner::test_ps_variant_prefixed_with_powershell_launcher`
and the `test_all_variants_*` parity cases in
`test_check_prerequisites_python_parity.py`,
`test_create_new_feature_python_parity.py`,
`test_resolve_template_python_parity.py`,
`test_setup_plan_python_parity.py` and
`test_setup_tasks_python_parity.py`.

### Not run

| Item | Reason |
| --- | --- |
| Every Codex (`codex` CLI) run | `codex` is not installed on this machine. No patch was exercised through a Codex session. |
| PowerShell twins (`auto-commit.ps1`, `create-new-feature-branch.ps1`, `create-new-feature.ps1`) | `pwsh` is not installed on this machine. Bash and Python twins were run instead; the patches' own parity tests cover the rest. |
| Pre-patch agent run for 0006 | A single agent run cannot prove what the unpatched instruction would have produced. The rendered-instruction diff plus the post-patch run are the evidence instead. |
| Bundle route for 0008 | No bundle is published for the preset used. The shared install sink was exercised through `specify preset add --dev`; the bundle route is covered by the patch's second test. |

### Testing setup

```bash
# from the patched worktree
uv sync --extra test
uv run specify version            # 1.0.4, resolving to the worktree's src/
uv run specify init <tmp>/speckit-test --integration claude --ignore-agent-tools

# subsequent CLI calls are made from the test project with the worktree's
# binary, so the project (not the worktree) is the install target:
<worktree>/.venv/bin/specify <subcommand> ...
```

Slash commands run from `<tmp>/speckit-test` against the `.claude/skills/`
the patched CLI rendered. Separate throwaway projects carry states the main
project must not hold (`--force` re-init, a second extension, a preset, a
cleared execute bit).

---

## 0001 — preserve installed integrations on force reinit

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `src/specify_cli/commands/init.py` | `specify init` | T1, T2 | `src/specify_cli/*.py` → test the affected CLI command. The changed branch is the `--force` re-init path, which needs a project that already has more than one installed integration. |
| `src/specify_cli/commands/init.py` | `/speckit.specify` | T3 | Same rule: init/scaffolding changes require at minimum `/speckit.specify`. |
| `tests/integrations/test_cli.py` | — | — | Test file; defines no command. |

### Required tests

- T1: `specify init <dir> --integration claude` then `specify integration install codex --script sh` — prerequisite state with two installed integrations.
- T2: `specify init --here --force --integration claude` — the changed path.
- T3: `/speckit.specify` — scaffolding still yields a working spec run.

### Manual test results

**Agent**: Claude Code 2.1.236 headless (`claude -p`, `claude-haiku-4-5-20251001`) | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `specify init <dir> --integration claude --ignore-agent-tools` (T1) | Pass. |
| `specify integration install codex --script sh` (T1) | Pass. `installed_integrations` → `["claude","codex"]`; `integration_settings` holds both keys. |
| `specify init --here --force --integration claude --ignore-agent-tools` (T2) | Pass. Exit 0; `codex` preserved. |
| `/speckit.specify` (T3) | Pass — the run reported under 0006 T1. |

State after T2 on the patched tree:

```json
{
  "installed_integrations": ["claude", "codex"],
  "integration_settings": {
    "claude": {"script": "sh", "invoke_separator": "-"},
    "codex":  {"script": "sh", "invoke_separator": "-"}
  },
  "integration": "claude",
  "default_integration": "claude"
}
```

Same sequence on the unpatched pin:

```json
{
  "installed_integrations": ["claude"],
  "integration_settings": {"claude": {"script": "sh", "invoke_separator": "-"}}
}
```

`codex` and its settings are dropped before the patch and kept after it.
Active-integration semantics are unchanged: `claude` stays the default in
both trees, and only its commands are re-registered.

---

## 0002 — scope auto-commit `git add`

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `extensions/git/scripts/bash/auto-commit.sh` | `/speckit.git.commit` | T2, T4, T5 | `extensions/X/scripts/*` → every extension command that invokes the script. `grep` over `extensions/*/commands/` matches only `speckit.git.commit.md`. |
| `extensions/git/scripts/bash/auto-commit.sh` | `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, and by the same manifest wiring `constitution`, `clarify`, `implement`, `checklist`, `analyze`, `taskstoissues` | T1, T3, T5 | Transitive: `extensions/git/extension.yml` attaches `speckit.git.commit` to the `before_`/`after_` hooks of those nine core commands, so the core commands the hooks attach to are affected. |
| `extensions/git/scripts/bash/auto-commit.sh` | `/speckit.git.commit` | T6, T7, T8 | The patch adds three distinct staging scopes and a new transitive dependency (`common.sh` for `get_feature_paths`). Each scope and the missing-resolver fallback needs its own test. |
| `extensions/git/scripts/powershell/auto-commit.ps1` | `/speckit.git.commit` (PowerShell) | not run | `pwsh` is not installed on this machine. |
| `extensions/git/scripts/python/auto_commit.py` | `/speckit.git.commit` (Python script type) | T8 | Same command, Python twin. |
| `tests/extensions/git/test_git_extension.py`, `tests/extensions/git/test_git_extension_python_parity.py` | — | — | Test files; define no command. |

### Required tests

- T1: `/speckit.specify` — prerequisite; produces the feature directory the scoped stage resolves.
- T2: `/speckit.git.commit` as `after_specify` — feature-directory scope, through the agent.
- T3: `/speckit.plan` — prerequisite for T4.
- T4: `/speckit.git.commit` as `after_plan` — feature-directory scope on a larger artifact set.
- T5: `/speckit.tasks` then `/speckit.git.commit` as `after_tasks` — third event through the agent.
- T6: `auto-commit.sh after_constitution` — the `.specify/memory/` scope.
- T7: `auto-commit.sh after_implement` — the whole-tree (`git add -A`) scope.
- T8: `auto-commit.sh after_specify` with no resolvable feature — tracked-only (`git add -u`) fallback; plus `auto_commit.py after_specify` for Python parity.

### Extra setup

```bash
<worktree>/.venv/bin/specify extension add <worktree>/extensions/git --dev
git init && git add -A && git commit -m "chore(scaffold): baseline project"

# enable one event in .specify/extensions/git/git-config.yml
#   auto_commit.after_specify.enabled: false -> true
# later also before_plan/after_plan/before_tasks/after_tasks (T3-T5) and,
# in a separate fixture, after_constitution/after_implement (T6-T7)

# stray paths that must never be swept in
mkdir -p src notes
echo x > src/unrelated.py && echo y > notes/scratch.txt && echo z > .env.local
```

### Manual test results

**Agent**: Claude Code 2.1.236 headless (`claude -p`, `claude-haiku-4-5-20251001`) | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `/speckit.specify` (T1) | Pass. Branch `001-task-board` created by the mandatory `before_specify` hook; `specs/001-task-board/spec.md` and `checklists/requirements.md` written; `.specify/feature.json` → `specs/001-task-board`. |
| `/speckit.git.commit` as `after_specify` (T2) | Pass. Agent ran `./.specify/extensions/git/scripts/bash/auto-commit.sh after_specify`. Commit `[Spec Kit] Add specification` contains only `specs/001-task-board/spec.md` and `specs/001-task-board/checklists/requirements.md`. `.env.local`, `notes/`, `src/` and a modified `git-config.yml` stayed out. |
| `/speckit.plan` (T3) | Pass. Agent ran `.specify/scripts/bash/setup-plan.sh --json`; wrote `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`. The optional `after_plan` hook was offered, not executed — upstream's optional-hook behaviour, unchanged by this patch. |
| `/speckit.git.commit` as `after_plan` (T4) | Pass. Commit `[Spec Kit] Add implementation plan` contains only the six `specs/001-task-board/` files; `.env.local`, `notes/`, `src/` still untracked. |
| `/speckit.tasks` + `/speckit.git.commit` as `after_tasks` (T5) | Pass. `setup-tasks.sh --json` ran and `tasks.md` was written; commit `[Spec Kit] Add tasks` contains only `specs/001-task-board/tasks.md`. |
| `auto-commit.sh after_constitution` (T6) | Pass — script level, not through the agent. Commit contains only `.specify/memory/constitution.md`; `.env.local`, `notes/`, `src/` and `specs/.../plan.md` left untracked. |
| `auto-commit.sh after_implement` (T7) | Pass — script level. `git add -A` as intended: the commit carries `.env.local`, `notes/scratch.txt`, `src/unrelated.py` and `specs/001-task-board/plan.md`. |
| `auto-commit.sh after_specify`, no `.specify/feature.json`, no `SPECIFY_FEATURE*` (T8) | Pass — script level. Commit contains only the tracked edit `src/unrelated.py`; `untracked-new.txt` left untracked. |
| `auto_commit.py after_specify` (T8, Python twin) | Pass — script level. Commit contains only `specs/001-task-board/spec.md`; four stray paths left untracked. |
| `auto-commit.ps1` | **Not run** — `pwsh` is not installed. |

Before/after contrast, identical repository state and event:

```
# pinned auto-commit.sh (git add .)
[Spec Kit] Add specification
 .env.local                                     |  1 +
 .specify/extensions/git/git-config.yml         |  2 +-
 .../extensions/git/scripts/bash/auto-commit.sh | 60 +------
 notes/scratch.txt                              |  1 +
 src/unrelated.py                               |  1 +

# patched auto-commit.sh (scoped stage)
[Spec Kit] Add specification
 specs/001-task-board/checklists/requirements.md |  53 +++++
 specs/001-task-board/spec.md                    | 121 ++++++++++
```

### Observation for the reviewer

`extensions/git/commands/speckit.git.commit.md` still describes step 6 as
"runs `git add .` + `git commit`". The patch changes the scripts only, so
the command prose now overstates what the script stages. Worth a one-line
fix in the same pull request.

---

## 0005 — clarify feature-branch output

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `extensions/git/commands/speckit.git.feature.md` | `/speckit.git.feature` | T2 | `extensions/X/commands/*` → the extension command it defines. |
| `extensions/git/scripts/bash/create-new-feature-branch.sh` | `/speckit.git.feature` | T2, T3 | `extensions/X/scripts/*` → every extension command that invokes it; `grep` matches only `speckit.git.feature.md`. |
| `extensions/git/scripts/python/create_new_feature_branch.py` | `/speckit.git.feature` (Python script type) | T3 | Same command, Python twin. |
| `extensions/git/scripts/powershell/create-new-feature-branch.ps1` | `/speckit.git.feature` (PowerShell) | not run | `pwsh` is not installed on this machine. |
| `extensions/git/commands/speckit.git.feature.md` (hook target) | `/speckit.specify` | T1 | Transitive: `speckit.git.feature` is the mandatory `before_specify` hook of the core `specify` command. |
| `scripts/bash/create-new-feature.sh`, `scripts/python/create_new_feature.py` | no slash command at this pin | T4 | `grep` over `templates/commands/` and `extensions/*/commands/` finds no invoker of the core `create-new-feature` script at `cb610277`; the core `specify` command creates the directory itself. Exercised directly instead. |
| `scripts/powershell/create-new-feature.ps1` | no slash command at this pin | not run | Same, and `pwsh` is absent. |
| `tests/**` (5 files) | — | — | Test files; define no command. |

### Required tests

- T1: `/speckit.specify` — runs `/speckit.git.feature` as the mandatory `before_specify` hook.
- T2: `/speckit.git.feature` — invoked directly through the agent, JSON parsed from stdout.
- T3: `create-new-feature-branch.sh` and `create_new_feature_branch.py` in both output modes — stdout/stderr separation.
- T4: `create-new-feature.sh` and `create_new_feature.py` — persist hints removed.

### Manual test results

**Agent**: Claude Code 2.1.236 headless (`claude -p`, `claude-haiku-4-5-20251001`) | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `/speckit.specify` (T1) | Pass. The mandatory hook created and checked out `001-task-board`; the agent reported no `SPECIFY_FEATURE` export instruction, and downstream state came from `.specify/feature.json`. |
| `/speckit.git.feature` (T2) | Pass. Agent ran the script exactly once: `.specify/extensions/git/scripts/bash/create-new-feature-branch.sh --json --short-name "export-button" "Add an export button that downloads the board as JSON"`. Tool output was pure JSON `{"BRANCH_NAME":"004-export-button","FEATURE_NUM":"004"}`; branch created and checked out; the full description survived quoting intact. |
| `create-new-feature-branch.sh` (T3) | Pass — script level. `--json` run: stdout is the JSON object only, stderr empty. Non-JSON run: `# The core specify command persists feature state in .specify/feature.json.` replaces the export hint. |
| `create_new_feature_branch.py` (T3) | Pass — script level. Same two modes, same result. |
| `create-new-feature.sh` (T4) | Pass — script level. stderr empty on a real run; non-JSON stdout carries the `.specify/feature.json` note. |
| `create_new_feature.py` (T4) | Pass — script level. Same. |
| `create-new-feature-branch.ps1`, `create-new-feature.ps1` | **Not run** — `pwsh` is not installed. |

Before/after contrast:

```
# pin, create-new-feature-branch.sh --json   (stderr)
# To persist: export SPECIFY_FEATURE=003-third
# patched, same call                          (stderr)
(empty)

# pin, create_new_feature_branch.py --json    (stderr)
# To persist: export SPECIFY_FEATURE=004-py-pin
# patched, same call                          (stderr)
(empty)

# pin, create-new-feature-branch.sh           (stdout, non-JSON)
# To persist in your shell: export SPECIFY_FEATURE=002-second-feature
# patched, same call                          (stdout, non-JSON)
# The core specify command persists feature state in .specify/feature.json.

# pin, create_new_feature.py                  (stderr)
# To persist: export SPECIFY_FEATURE=001-probe
#              export SPECIFY_FEATURE_DIRECTORY=<abs>/specs/001-probe
# patched, same call                          (stderr)
(empty)
```

---

## 0006 — use the native template resolver

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `templates/commands/specify.md` | `/speckit.specify` | T1, T2 | `templates/commands/X.md` → the command it defines. |
| `templates/commands/specify.md` | no other command | — | The new instruction names `.specify/scripts/{bash,powershell,python}/resolve-template.*`, already installed and already invoked by `/speckit.constitution`; no other command's contract changes. |
| `tests/integrations/test_integration_copilot.py`, `tests/test_native_template_resolver_contract.py` | — | — | Test files; define no command. |

### Required tests

- T1: `/speckit.specify` with the stock templates — the resolver path works at all.
- T2: `/speckit.specify` with a preset that replaces `spec-template` — proves the resolver's `TEMPLATE_CONTENT` is what reaches `spec.md`, not the core template.

### Extra setup for T2

```bash
<worktree>/.venv/bin/specify preset add --dev <repo>/presets/default
bash .specify/scripts/bash/resolve-template.sh spec-template --json   # returns the preset's template
```

### Manual test results

**Agent**: Claude Code 2.1.236 headless (`claude -p`, `claude-haiku-4-5-20251001`) | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `/speckit.specify` (T1, stock templates) | Pass. `specs/001-task-board/spec.md` written with the core `spec-template` section order (`User Scenarios & Testing`, `Requirements`, `Success Criteria`, `Assumptions`); `checklists/requirements.md` created; `.specify/feature.json` persisted. |
| `/speckit.specify` (T2, `default` preset active) | Pass. The agent's first tool call was `bash .specify/scripts/bash/resolve-template.sh spec-template --json`; it then wrote `specs/001-shortcut-palette/spec.md` with the **preset's** headings — `Problem and affected users`, `Desired outcome`, `User scenarios and acceptance`, `Source references` — matching `presets/default/templates/spec-template.md` and not the core template. |

Rendered-instruction diff (pin → patched) in the installed
`.claude/skills/speckit-specify/SKILL.md`:

```diff
-   - Resolve the active `spec-template` through the Spec Kit preset/template resolution stack (equivalent to `specify preset resolve spec-template`)
-   - Copy the resolved `spec-template` file to `SPECIFY_FEATURE_DIRECTORY/spec.md` as the starting point
+   - Resolve the active `spec-template` by invoking the installed native resolver once, from the project root:
+     - Bash: `bash .specify/scripts/bash/resolve-template.sh spec-template --json`
+     - PowerShell: `pwsh -File .specify/scripts/powershell/resolve-template.ps1 spec-template -Json`
+     - Python: `python3 .specify/scripts/python/resolve_template.py spec-template --json`
+   - Parse the resolver's JSON and use `TEMPLATE_CONTENT` as the starting content for `SPECIFY_FEATURE_DIRECTORY/spec.md`. ...
```

---

## 0007 — preserve command examples

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `src/specify_cli/agents.py` | `specify init` | T1 | `src/specify_cli/*.py` → CLI commands. `CommandRegistrar.rewrite_command_paths` renders every core command into the agent's skill files at init. |
| `src/specify_cli/agents.py` | `specify extension add` | T2 | `rewrite_extension_paths` is the second changed function; it renders extension commands. |
| `src/specify_cli/agents.py` | `specify preset add`, `specify integration install` | T3, T4 | Same renderer; both re-scaffold command files. |
| `src/specify_cli/agents.py` | `/speckit.specify` | T5 | Same rule: init/scaffolding changes require at minimum `/speckit.specify`. |
| `src/specify_cli/agents.py` | `/speckit.code-review.code-review` | T2 | The extension command whose rendered body carries the affected example. |
| `pyproject.toml` | packaging/bundling | T1 | `pyproject.toml` → test `specify init` and verify bundled assets. Adds the `markdown-it-py` runtime dependency. |
| `tests/test_agent_config_consistency.py` | — | — | Test file; defines no command. |

### Required tests

- T1: `specify init` — commands render, bundled assets present, new dependency resolves.
- T2: `specify extension add <ext> --dev` with an extension whose command contains a data fence holding paths, then read the rendered command.
- T3: `specify preset add --dev` — second render route (shared with 0008 T1).
- T4: `specify integration install codex --script sh` — third render route (shared with 0009 T1).
- T5: `/speckit.specify` — the rendered core command still executes end to end.

### Extra setup for T2

```bash
<worktree>/.venv/bin/specify extension add <repo>/packages/spec-kit-code-review --dev
```

That extension's `commands/code-review.md` holds a ```json fence whose
`"path"` value is `src/module.py`, and the extension has a top-level `src/`
subdirectory — exactly the case the renderer used to rewrite.

### Manual test results

**Agent**: Claude Code 2.1.236 headless (`claude -p`, `claude-haiku-4-5-20251001`) | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `specify init` (T1) | Pass. The ten core commands rendered into `.claude/skills/`; `.specify/scripts/bash/` (6 scripts) and `.specify/templates/` (5 templates) installed; no `.sh` left without an execute bit; `markdown-it-py 4.2.0` resolves in the project environment. |
| `specify extension add ... --dev` (T2) | Pass. Both extension commands registered (12 skills total); the example is preserved as `"path": "src/module.py"`. |
| `specify preset add --dev` (T3) | Pass — see 0008 T1. |
| `specify integration install codex --script sh` (T4) | Pass — see 0009 T1. |
| `/speckit.specify` (T5) | Pass — the run reported under 0006 T1. |

Before/after contrast, same extension and same command file:

```diff
  "findings": [
    {
-     "path": ".specify/extensions/code-review/src/module.py",     # pin
+     "path": "src/module.py",                                     # patched
```

Regression check: `diff -ru` of the two rendered `.claude/skills` trees
(pin vs patched, same project shape, same extension installed) reports
exactly two hunks — the example above and 0006's `specify.md` rewording.
Every other core and extension command renders identically, so the
fence-aware refactor changed no real path rewrite.

---

## 0008 — preserve rendered script modes

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `src/specify_cli/presets/__init__.py` | `specify preset add` | T1 | `src/specify_cli/*.py` → CLI commands. `PresetManager.install_from_directory` is the shared sink for every preset install route, the bundle route included. |
| `src/specify_cli/presets/__init__.py` | `/speckit.specify` | T2 | Same rule, plus `presets/*/*` → test preset scaffolding. Run with the preset active so the restored scripts are actually used. |
| `tests/integrations/test_preset_modes.py` | — | — | Test file; defines no command. |

### Required tests

- T1: `specify preset add --dev <preset>` on a project whose `.specify/scripts/bash/*.sh` lost their execute bits.
- T2: `/speckit.specify` in that project.

### Extra setup

```bash
uv run specify init <tmp>/p0008 --integration claude --ignore-agent-tools
chmod 644 .specify/scripts/bash/check-prerequisites.sh .specify/scripts/bash/setup-plan.sh
<worktree>/.venv/bin/specify preset add --dev <repo>/presets/default
```

### Manual test results

**Agent**: Claude Code 2.1.236 headless (`claude -p`, `claude-haiku-4-5-20251001`) | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `specify preset add --dev` (T1) | Pass. CLI reported `Updated execute permissions on 2 script(s) recursively` and `✓ Preset 'Default Workflow Templates' v0.10.0 installed (priority 10)`. |
| `/speckit.specify` (T2) | Pass. Same run as 0006 T2: the agent executed `bash .specify/scripts/bash/resolve-template.sh spec-template --json` — one of the scripts whose bit had been cleared — and produced `specs/001-shortcut-palette/spec.md` from the preset template. |

```
# before preset add
-rw-r--r-- .specify/scripts/bash/check-prerequisites.sh
-rw-r--r-- .specify/scripts/bash/setup-plan.sh
# after preset add (patched)
-rwxr-xr-x .specify/scripts/bash/check-prerequisites.sh
-rwxr-xr-x .specify/scripts/bash/setup-plan.sh
```

---

## 0009 — clarify agentless integration install

### Test selection reasoning

| Changed file | Affects | Test | Why |
|---|---|---|---|
| `docs/reference/integrations.md` | no slash command | T1, T2 | Documentation only. No CONTRIBUTING mapping rule maps `docs/**` to a command, and the patch touches no template, script or CLI code. The documented behaviour is verified anyway so the claim is not merely asserted. |
| `tests/integrations/test_integration_subcommand.py` | — | — | Test file; defines no command. |

### Required tests

- T1: `specify integration install codex --script sh` with the `codex` binary absent.
- T2: `specify check` — the remediation the new sentence points at.

### Manual test results

**Agent**: not applicable — no slash command is affected. | **OS/Shell**: macOS/zsh

| Command tested | Notes |
|----------------|-------|
| `specify integration install codex --script sh` (T1) | Pass. `which codex` → not found. Install succeeded: `✓ Integration 'Codex CLI' installed successfully`, `Default integration remains: claude`, and `.agents/skills/` was scaffolded with the ten core commands. |
| `specify check` (T2) | Pass. Reports `● Codex CLI (not found)`, the diagnosis the new sentence directs the reader to. |
| any `/speckit.*` command | **Not run, and not required** — the patch is documentation plus a regression test; no command behaviour changes. |

The unpatched pin behaves identically: `specify integration install codex`
also succeeds there with no binary present. That is the patch's point — it
documents existing, previously undocumented behaviour and pins it with a
test.

---

## Coverage summary

| Patch | Slash commands run through the agent | CLI commands run | Result |
| --- | --- | --- | --- |
| 0001 | `/speckit.specify` | `init`, `integration install`, `init --here --force` | Pass |
| 0002 | `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, `/speckit.git.commit` ×3 events | `extension add` | Pass; PowerShell twin not run |
| 0005 | `/speckit.specify`, `/speckit.git.feature` | `extension add` | Pass; PowerShell twins not run |
| 0006 | `/speckit.specify` ×2 (stock and preset) | `init`, `preset add` | Pass |
| 0007 | `/speckit.specify` | `init`, `extension add`, `preset add`, `integration install` | Pass |
| 0008 | `/speckit.specify` | `preset add` | Pass |
| 0009 | none required | `integration install`, `check` | Pass |

No manual test failed. The open gaps are the PowerShell twins and every
Codex run, both blocked by tooling absent from this machine rather than by
a patch defect. The full suite's 11 failures are pre-existing on the
unpatched pin and have the same cause.
