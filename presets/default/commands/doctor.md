---
name: speckit.doctor
description: Run every installed extension's doctor and summarize one result with its remediations.
---

# Spec Kit doctor

One health check for the whole setup. You (the agent) run each installed
extension's own doctor and reduce everything to a single answer: healthy,
or exactly what to run to become healthy.

## 1. Discover what is installed

List `.specify/extensions/`. The two doctors this distribution ships are:

```bash
bash .specify/extensions/linear/scripts/bash/run.sh doctor
bash .specify/extensions/code-review/scripts/bash/run.sh doctor
```

An extension that is not installed is **not** a problem — it is simply not
part of this role's bundle; say so in one line and move on. If neither is
installed, say the setup has no extensions to check and point at the
README's Get Started.

## 2. Run each doctor

Run them read-only first. If the user asked to fix (`--fix` or "arregla"),
re-run each failing doctor with `--fix` and report what it repaired —
`--fix` is each doctor's own, bounded repair; you never fix anything
yourself.

## 3. Verify the GitHub repository settings

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

## 4. Summarize one result

- **Everything passed and both settings were verified** → one line: the
  setup is healthy, the installed extensions were checked (name them), with
  `deleteBranchOnMerge=true` and `mergeCommitAllowed=true`.
- **Anything failed** → one short list, one bullet per blocking problem,
  carrying an extension doctor's own remediation **verbatim** or the exact
  GitHub remediation from step 3. End with the single next action: usually
  re-running this command with `--fix`, or the one manual step the
  remediation names.
- **Nothing failed but GitHub could not be verified** → say the checks that
  ran passed, but do not call the setup healthy.

Warnings that block nothing go in one final line, not in the list.

## 5. Mirror the skills across installed agents

Upstream registers extension and preset commands only for the **default**
integration ("active-only registration"); this distribution's portability
principle says no agent is second-class. Close that gap here, without ever
overwriting one integration's own render with another's: extension and
preset skills are copied whole from the default integration's directory;
the five core commands with a registered preset append (`specify`, `plan`,
`tasks`, `analyze`, `implement`) keep each integration's own render and
receive that append. Run `skill_mirror.py` — with the consumer's
`.venv/bin/python` when it exists, else `python3` on PATH, the rule
upstream's own `py` scripts follow. Its one argument replaces
`<true|false>`: `true` when the user asked to fix, else `false`:

```bash
python3 .specify/presets/default/scripts/python/skill_mirror.py <true|false>
```

A core render with no registered append (e.g. `checklist`) is never
touched, and a core skill is never copied across integrations — only its
own append text ever reaches it. Re-run after `bundle update` or
`integration switch`: both refresh only the default agent's copies.

## 6. Add the installer's ignore entries

The installer's cache directories (extension, preset, and integration
catalogs) and the extension payload virtual environments are rarely in
a fresh consumer's ignore file. Run this block, replacing only the
`fix` literal:

```bash
# ignore-entries:start
set -e
fix="<true|false>"
acted=false
for entry in ".specify/extensions/.cache/" ".specify/presets/.cache/" ".specify/integrations/.cache/" ".specify/extensions/*/.venv/"; do
  probe=$(printf '%s' "$entry" | sed 's/\*/x/')
  git check-ignore -q "$probe" && continue
  acted=true
  if [ "$fix" = "true" ]; then
    if [ ! -f .gitignore ]; then
      printf '# tserdeiro/spec-kit installer state\n' > .gitignore
    elif ! grep -q '# tserdeiro/spec-kit installer state' .gitignore; then
      printf '\n# tserdeiro/spec-kit installer state\n' >> .gitignore
    fi
    printf '%s\n' "$entry" >> .gitignore
    echo "ignore: added $entry to .gitignore"
  else
    echo "ignore: $entry is not covered by .gitignore -- run with --fix"
  fi
done
[ "$acted" = "true" ] || echo "ignore: nothing to do"
# ignore-entries:end
```

`check-ignore` honors broader patterns already in the ignore file, so a
repository ignoring `.venv/` globally gets no duplicate entry.

Never mutate anything outside step 2's explicit `--fix` pass-through,
step 5's skill mirror, and step 6's ignore entries; never install,
download, or configure on your own.
