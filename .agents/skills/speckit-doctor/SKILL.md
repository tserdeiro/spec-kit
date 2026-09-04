---
name: speckit-doctor
description: Run every installed extension's doctor and summarize one result with
  its remediations.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: preset:default
---

# Speckit Doctor Skill

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
receive that append. Run this block, replacing only the `fix` literal
(`true` when the user asked to fix, else `false`):

```bash
# skill-mirror:start
set -e
fix="<true|false>"
default_ai=$(sed -n 's/.*"ai": *"\([^"]*\)".*/\1/p' .specify/init-options.json | head -1)
installed=$(awk '
  /"installed_integrations":/ { inside = 1; next }
  inside && /\]/ { exit }
  inside { gsub(/[",]/, ""); gsub(/^[ \t]+|[ \t]+$/, ""); if (length($0)) print }
' .specify/integration.json)
count=$(printf '%s\n' "$installed" | grep -c .)
if [ "$count" -le 1 ]; then
  echo "mirror: only one integration installed, skipped"
  exit 0
fi

manifest_paths() {
  grep -Eo '"[^"]*/speckit-[^"/]*/SKILL\.md"' "$1" | tr -d '"'
}

appends=$(mktemp)
: > "$appends"
for preset_yml in .specify/presets/*/preset.yml; do
  [ -f "$preset_yml" ] || continue
  preset_dir=$(dirname "$preset_yml")
  awk -v dir="$preset_dir" '
    function flush() {
      if (t == "command" && s == "append" && n != "" && fl != "") {
        gsub(/^speckit\./, "speckit-", n); print n, dir "/" fl
      }
    }
    /^[ \t]*- type:/ { flush(); t = ($0 ~ /"command"/) ? "command" : ""; n = ""; fl = ""; s = ""; next }
    /name:/     && t == "command" { n = $0;  sub(/^.*name:[ \t]*"/, "", n);     sub(/".*$/, "", n) }
    /file:/     && t == "command" { fl = $0; sub(/^.*file:[ \t]*"/, "", fl);    sub(/".*$/, "", fl) }
    /strategy:/ && t == "command" { s = $0;  sub(/^.*strategy:[ \t]*"/, "", s); sub(/".*$/, "", s) }
    END { flush() }
  ' "$preset_yml" >> "$appends"
done

default_paths=$(manifest_paths ".specify/integrations/$default_ai.manifest.json")
default_dir=$(printf '%s\n' "$default_paths" | head -1 | sed -E 's#/speckit-[^/]*/SKILL\.md$##')
if [ -z "$default_dir" ]; then
  echo "mirror: default integration $default_ai has no skills to mirror"
  exit 0
fi

acted=false
for key in $installed; do
  [ "$key" = "$default_ai" ] && continue
  manifest=".specify/integrations/$key.manifest.json"
  paths=$(manifest_paths "$manifest")
  lag_dir=$(printf '%s\n' "$paths" | head -1 | sed -E 's#/speckit-[^/]*/SKILL\.md$##')
  if [ -z "$lag_dir" ]; then
    echo "mirror: $key is command-mode, no skills to mirror"
    continue
  fi
  core=$(mktemp)
  printf '%s\n' "$paths" | sed -E 's#.*/(speckit-[^/]*)/SKILL\.md$#\1#' > "$core"

  for src in "$default_dir"/speckit-*/; do
    [ -d "$src" ] || continue
    name=$(basename "$src")
    grep -qxF "$name" "$core" && continue
    srcfile="$default_dir/$name"
    dst="$lag_dir/$name"
    if [ ! -f "$dst/SKILL.md" ] || ! cmp -s "$srcfile/SKILL.md" "$dst/SKILL.md"; then
      acted=true
      if [ "$fix" = "true" ]; then
        mkdir -p "$lag_dir"
        cp -R "$srcfile" "$lag_dir/"
        echo "mirror: copied $name into $lag_dir ($key)"
      else
        echo "mirror: $name missing or differs in $lag_dir ($key) -- run with --fix"
      fi
    fi
  done

  while read -r name; do
    [ -n "$name" ] || continue
    append_file=$(awk -v n="$name" '$1 == n { print $2; exit }' "$appends")
    [ -n "$append_file" ] || continue
    render="$lag_dir/$name/SKILL.md"
    if [ ! -f "$render" ]; then
      acted=true
      echo "mirror: $name missing in $lag_dir ($key) -- run: specify integration install $key"
      continue
    fi
    heading=""
    [ -f "$append_file" ] && heading=$(awk '/^## /{ print; exit }' "$append_file")
    if [ -z "$heading" ]; then
      echo "mirror: append $append_file for $name is missing or has no heading" >&2
      exit 2
    fi
    prefix=$(awk -v h="$heading" '$0 == h { exit } { print }' "$render")
    body=$(cat "$append_file")
    expected=$(printf '%s\n\n\n%s\n' "$prefix" "$body")
    actual=$(cat "$render")
    if [ "$expected" != "$actual" ]; then
      acted=true
      if [ "$fix" = "true" ]; then
        printf '%s\n\n\n%s\n' "$prefix" "$body" > "$render"
        echo "mirror: appended the preset layer to $name in $lag_dir ($key)"
      else
        echo "mirror: $name in $lag_dir ($key) needs the preset append -- run with --fix"
      fi
    fi
  done < "$core"
done

[ "$acted" = "true" ] || echo "mirror: nothing to do"
# skill-mirror:end
```

A core render with no registered append (e.g. `checklist`) is never
touched, and a core skill is never copied across integrations — only its
own append text ever reaches it. Re-run after `bundle update` or
`integration switch`: both refresh only the default agent's copies.

## 6. Add the installer's ignore entries

The installer's cache directories and the extension payload virtual
environments are rarely in a fresh consumer's ignore file. Run this
block, replacing only the `fix` literal:

```bash
# ignore-entries:start
set -e
fix="<true|false>"
acted=false
for entry in ".specify/extensions/.cache/" ".specify/presets/.cache/" ".specify/extensions/*/.venv/"; do
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
