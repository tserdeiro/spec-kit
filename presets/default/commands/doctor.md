---
name: speckit.doctor
description: Run every installed extension's doctor and summarize one result with its remediations.
---

# Spec Kit doctor

One health check for the whole setup. You (the agent) run each installed
extension's own doctor and reduce everything to a single answer: healthy,
or exactly what to run to become healthy.

The aggregator remains the agent command `/speckit.doctor`; it delegates repair
to each extension and does not implement an executable hook aggregator.

## 1. The Python interpreter

Every script this distribution installs, and every runtime event
handler, resolves its interpreter the same way: the consumer's
`.venv/bin/python` when it exists, else `python3` on PATH. This check is
always read-only, including with `--fix`.

Resolve the interpreter with that rule, run `<interpreter> --version`,
and report it.

- **3.11 or newer** → healthy.
- **Older than 3.11, or none found** → a blocking problem. Name the
  exact fix without running it: `uv python install 3.11 --default`, or
  activating the virtual environment that already has the right version.

## 2. Discover what is installed

List `.specify/extensions/`. The two doctors this distribution ships are:

```bash
bash .specify/extensions/linear/scripts/bash/run.sh doctor
bash .specify/extensions/code-review/scripts/bash/run.sh doctor
```

An extension that is not installed is **not** a problem — it is simply not
part of this role's bundle; say so in one line and move on. If neither is
installed, say the setup has no extensions to check and point at the
README's Get Started.

## 3. Run each doctor

Run them read-only first. If the user asked to fix (`--fix` or "arregla"),
re-run each failing or repairable doctor with `--fix` and report what it
repaired — a missing native hook is a repairable warning even when the
extension exits successfully. `--fix` is each doctor's own, bounded repair;
you never fix anything yourself. Preserve every diagnostic from the code-review
doctor's `hooks` group: its effective path, selected scope, state, payload
requirement, and original diagnostic text. The aggregate command must carry
that text through even when another group also fails.

## 4. Verify the GitHub repository settings

The delivery flow depends on GitHub deleting merged branches and allowing
merge commits. These checks are always read-only, including with `--fix`.

- If `gh` is unavailable, report: `GitHub: cannot verify
  deleteBranchOnMerge or mergeCommitAllowed because gh is unavailable.`
- Otherwise run exactly one query:

  ```bash
  gh repo view --json deleteBranchOnMerge,mergeCommitAllowed
  ```

  Report both returned states in one line. A `false` value is a blocking
  problem with its exact manual remediation:
  - `deleteBranchOnMerge=false` → in GitHub, enable **Settings → General →
    Pull Requests → Automatically delete head branches**.
  - `mergeCommitAllowed=false` → in GitHub, enable **Settings → General →
    Pull Requests → Allow merge commits**.

If the query itself fails, report both settings as `cannot verify` and include
the failure as a warning. Never change repository settings.

## 5. Summarize one result

Group every reported gap into seven fixed categories, in this order,
regardless of which sub-doctor produced the underlying diagnostic: (1)
the Python interpreter, (2) GitHub CLI authentication, (3) the Linear
API key, (4) the Linear onboarding binding, (5) the review engine
installation, (6) native commit-message validation, and (7) the repository's
GitHub delivery settings. Native validation is the code-review doctor's full
`hooks` group; do not discard a finding because it does not fit the other
categories.

- **Everything passed and both settings were verified** → one line: the
  setup is healthy, the installed extensions were checked (name them), with
  `deleteBranchOnMerge=true` and `mergeCommitAllowed=true`.
- **Anything failed** → one short list, ordered by the seven categories
  above and skipping any with nothing to report; one bullet per blocking
  problem, carrying its doctor's own remediation **verbatim**, including the
  native-hook path, state, and emitted `doctor --fix` or manual action, plus the
  interpreter fix from step 1 or exact GitHub remediation from step 4 where
  applicable. End with
  the single next action: usually
  re-running this command with `--fix`, or the one manual step a
  report-only category names.
- If the native diagnostic is `git_hooks_write_failed` (`native registration was
  not completed ...; retry doctor`), carry that text verbatim and tell the user
  to inspect the reported config path before retrying. If it is
  `git_hooks_readback_failed`, carry its restoration outcome verbatim and
  require manual inspection when restoration was not applied.
- **Nothing failed but GitHub could not be verified** → say the checks that
  ran passed, but do not call the setup healthy.

`--fix` passes through each doctor's own bounded repair for categories 2
through 6, where the doctor offers one. The native-hook repair is the
code-review doctor's `doctor --fix`: it may register the named hook in the
Git config selected by that doctor, while preserving existing hooks and
managers. Its cooperative lock, early and late snapshot checks, atomic
replacement, readback, and conditional restoration limits remain the extension
doctor's exact diagnostics; do not strengthen them in the aggregate. Do not implement a second aggregator
or edit Git configuration here.
Categories 1 and 7 stay
report-only even with `--fix`: installing or activating an interpreter,
and changing GitHub's delivery settings, are both human decisions.

Warnings and informational hook diagnostics that block nothing stay visible in
the final output with their original path and message, including when the
healthy line is reported.

## 6. Check the runtime-events wiring

Read-only; nothing here is ever written, even with `--fix`.

Report once whether `.specify/events.py`, the dispatcher every wired
integration shares, exists. Then, for each key in
`.specify/integration.json`'s `installed_integrations`, report whether
that integration's own native hook file carries the dispatcher's marker
— `__speckit_event__` in the JSON hook files (`.claude/settings.json`
for claude, `.cursor/hooks.json` for cursor), `speckit_marker = true`
in the TOML one (`.codex/config.toml` for codex); for any other
integration, the hook file its `specify integration upgrade` writes —
when you cannot name it, report that integration's wiring as
unverified. An integration whose hook file carries no marker is unwired
whatever the dispatcher's state — one with no hook file at all (Zed,
today), or one wired before the extensions declared events: state
plainly that the code-review guard and the Linear session-start and
tool-use handlers do not run there, and that the prose rules stay
authoritative.

For each installed extension declaring `events:` under
`.specify/extensions/<id>/extension.yml`, check that every
`events.<event>.command` equals the stem of a file under that
extension's `commands/` directory — a mismatch resolves to nothing at
the dispatcher, silently, so the event simply never fires — and name any
mismatch you find.

The fix for a gap this step finds is never run here: once the extension
itself declares events, it is `specify integration upgrade <key>` — an
`install` of a key already installed changes nothing; `--force` when the
upgrade reports locally modified files, which the mirrored appends are —
followed by this doctor with `--fix`, so step 7 restores the preset layer
the upgrade re-rendered.

This runtime-events check covers agent wiring. Native Git commit-message state
comes from the code-review doctor's `hooks` group in step 5 and remains in the
aggregate result independently of agent-event support.

## 7. Mirror the skills across installed agents

Upstream registers extension and preset commands only for the **default**
integration ("active-only registration"); this distribution's portability
principle says no agent is second-class. Close that gap here, without ever
overwriting one integration's own render with another's: extension and
preset skills are copied whole from the default integration's directory;
the three core commands with a registered preset append (`specify`,
`plan`, `analyze`) keep each integration's own render and receive that
append; the two core commands the preset **replaces** (`tasks`,
`implement`) are copied whole instead, like an extension skill, since
the preset's file is their whole render. Run `skill_mirror.py` — with the
consumer's `.venv/bin/python` when it exists, else `python3` on PATH,
the rule upstream's own `py` scripts follow. Its one argument replaces
`<true|false>`: `true` when the user asked to fix, else `false`:

```bash
python3 .specify/presets/default/scripts/python/skill_mirror.py <true|false>
```

A core render with no registered append or replace strategy (e.g.
`checklist`) is never touched, and a core skill with an append only ever
receives its own append text, never a whole copy, across integrations; a
registered command strategy the script does not compose (`prepend`,
`wrap`) stops it before any write, naming the command. Re-run after
`preset add` (the `preset remove` + `preset add` pair of a dev reinstall
included), `bundle update`, or `integration switch`, which compose the
preset for the default integration only, and after `integration upgrade
<key> --force`, which re-renders that integration's core commands from
upstream alone.

## 8. Add the installer's ignore entries

The installer's cache directories (extension, preset, and integration
catalogs) and the extension payload virtual environments are rarely in
a fresh consumer's ignore file. Run `ignore_entries.py` — with the
consumer's `.venv/bin/python` when it exists, else `python3` on PATH, the
rule upstream's own `py` scripts follow. Its one argument replaces
`<true|false>`: `true` when the user asked to fix, else `false`:

```bash
python3 .specify/presets/default/scripts/python/ignore_entries.py <true|false>
```

`check-ignore` honors broader patterns already in the ignore file, so a
repository ignoring `.venv/` globally gets no duplicate entry.

Never mutate anything outside step 3's explicit `--fix` pass-through,
step 7's skill mirror, and step 8's ignore entries; never install,
download, or configure on your own.
