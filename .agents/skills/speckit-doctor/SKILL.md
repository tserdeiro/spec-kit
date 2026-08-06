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

## 3. Summarize one result

- **Everything passed** → one line: the setup is healthy, both extensions
  checked (name them).
- **Anything failed** → one short list, one bullet per blocking problem,
  each carrying the doctor's own remediation **verbatim** (the messages
  already say exactly what to run — do not paraphrase commands). End with
  the single next action: usually re-running this command with `--fix`,
  or the one manual step the remediation names.

Warnings that block nothing go in one final line, not in the list.

Never mutate anything outside step 2's explicit `--fix` pass-through;
never install, download, or configure on your own.
