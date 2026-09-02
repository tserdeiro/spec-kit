---
name: speckit.code-review.doctor
description: Validate git, ocr, gh, configuration, and rules; --fix applies the local repairs.
---

# Spec Kit code review doctor

```bash
bash .specify/extensions/code-review/scripts/bash/run.sh doctor
bash .specify/extensions/code-review/scripts/bash/run.sh doctor --fix
```

Without `--fix` it writes nothing at all: every external invocation it makes
(`git --version`, `git rev-parse`, `git status`, `ocr --version`,
`ocr delegate preview --help`, `gh auth status`, `gh api user`) only reads.

It checks the runtime, Spec Kit, `git`, `ocr`, `gh`, the configuration, the
review rules, the evidence root, and the hooks — and prints the three per-user
roots of this distribution **resolved** rather than as templates, plus the
**exact command that installs the pinned `ocr`** and the one that removes it
again. That install goes into this distribution's data root, one directory per
version: never a global install, which would outlive this extension's own
uninstall, and never a per-project one, which the executable guard refuses with
exit code 4.

`--fix` repairs: the `.gitignore` entries for this extension's local files, the
shared and local configuration files when they are absent, a starting
`.opencodereview/rule.json` when the repository has none, evidence-root
permissions that are not `0700`, and **the pinned `ocr` when it is missing**. It
never overwrites a file that already exists. The shared configuration it writes
is a starting point for a person to review and commit.

The engine install is the only thing this extension ever installs, and only
here: `npm install` by argv, never through a shell, into the canonical path for
the version the lock pins, followed by a digest check against the lock. A digest
that does not match removes the whole directory and fails — no unverified binary
survives the command. An explicit `SPECKIT_CODE_REVIEW_OCR_BIN` is the
operator's decision and is checked, never replaced. `review` installs nothing on
any path.
