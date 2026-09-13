---
name: speckit.code-review.doctor
description: Validate git, native commit-message validation, ocr, gh, configuration, and rules; --fix applies the local repairs.
---

# Spec Kit code review doctor

```bash
bash .specify/extensions/code-review/scripts/bash/run.sh doctor
bash .specify/extensions/code-review/scripts/bash/run.sh doctor --fix
```

Without `--fix` this command writes nothing. Its external calls, including
`git --version`, `git rev-parse`, `git status`, `git config`, `git hook list`,
`git worktree list`, `ocr`, and `gh`, are read-only. It reports every finding
from every check, including the native-hook path, scope, state, payload, and
the exact repair or manual action.

It checks the runtime, Spec Kit, `git`, `ocr`, `gh`, configuration, review
rules, evidence root, and native commit-message validation. It prints the
three resolved per-user roots, the exact command that installs the pinned
`ocr`, and the command that removes it. The engine remains in this
distribution's data root, one directory per version; it is never installed
globally or in a project tree.

`--fix` repairs missing `.gitignore` entries, absent shared or local
configuration files, a missing `.opencodereview/rule.json`, evidence-root
permissions that are not `0700`, the pinned `ocr` when it is absent, and native
commit-message validation when the arrangement is safe. It never overwrites
an existing hook or manager file. An explicit `SPECKIT_CODE_REVIEW_OCR_BIN` is
checked and never replaced. The engine is verified against the lock before it
is left on disk. A digest mismatch removes the incomplete engine directory and
fails.

## Native commit-message validation

The review minimum remains Git 2.41. Automatic native registration requires
Git 2.54 or newer and a working `git hook list`; an older Git receives an
upgrade diagnostic and `doctor --fix` does not upgrade it. After upgrading,
run `doctor --fix` again.

The repair registers one named `commit-msg` hook through Git's native
composition:

```ini
[hook "speckit-commit-message"]
    command = sh .specify/extensions/code-review/scripts/bash/commit-msg.sh
    event = commit-msg
```

Git's effective `core.hooksPath` is reported, including custom and linked
worktree paths. The local scope is the repository-shared config path. If
`extensions.worktreeConfig` is enabled, the entry is in
Git's resolved `config.worktree` path for the current worktree; otherwise it is
in the shared repository config path and applies to every linked worktree.
Shared scope requires the installed validator payload in every active linked
checkout, because the command resolves its own checkout when Git runs it. A
worktree scope requires the payload in that checkout. The payload is the
launcher `scripts/bash/commit-msg.sh` plus `__init__.py`, `commit_msg.py`, and
`commit_policy.py` under `src/spec_kit_code_review/`. Missing or unreadable
payload files name the path and say to reinstall the code-review extension,
then run `doctor --fix`.

The named hook runs in Git's native order before the traditional hook path.
Existing hooks, `core.hooksPath`, Husky dispatchers, and Lefthook dispatchers
remain owned by the consumer and keep their bytes, modes, arguments, order,
and rejection behavior. Repeating a successful repair is a no-op with one
effective Spec Kit registration.

The hook diagnosis distinguishes `missing`, `installed`, `disabled`, and
`unverifiable`, and also reports partial, duplicate, foreign-scope, conflicting,
payload, lock, permission, stale-snapshot, write, and readback failures. A
disabled entry is preserved and must be enabled explicitly before retrying;
the diagnostic names its origin and scope. An unverifiable result is never
reported as healthy. Every such diagnostic remains visible when another doctor
group fails, with its path and exact remedy.

Repair uses the selected Git config's exclusive lock, compares the diagnosed
bytes, mode, and effective snapshot, edits a temporary file through Git,
atomically replaces the destination, and reads the effective config and hook
list back. A lock, concurrent change, unsafe destination, write error, or
failed readback leaves the original configuration intact and reports the
retry or manual action.

To remove a registration manually, first confirm the scope reported by the
doctor, then remove only the owned section:

```bash
git config --local --remove-section hook.speckit-commit-message
git config --worktree --remove-section hook.speckit-commit-message
```

Use the command matching the diagnosed scope. This leaves traditional hooks,
Husky, and Lefthook files untouched. A local hook remains bypassable with
`git commit --no-verify` and per-event disabling; GitHub and CI enforcement are
separate. A later traditional hook may rewrite the message after validation,
so the native check validates the subject it observes rather than an immutable
final subject.
