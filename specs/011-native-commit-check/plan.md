# Implementation Plan: Native commit message validation

**Feature directory**: `specs/011-native-commit-check`
**Spec**: [spec.md](spec.md)

## Summary

Share the guard's subject predicate with a small installed message-file entry
point. Extend the current doctor to diagnose and register one named `commit-msg`
hook using Git 2.54's native configuration. Git composes it with existing hooks,
including Husky/Lefthook dispatchers, without editing them. Research, interface
contracts, and validation stay here, following the resolved default template.

## Technical context

- **Language/runtime**: Python 3.11+, standard library, installed POSIX launcher.
- **Primary dependencies**: existing Git and pytest 9.1.1; runtime dependencies
  remain empty. Sources: [manifest](../../packages/spec-kit-code-review/pyproject.toml),
  [lock](../../packages/spec-kit-code-review/uv.lock), [pins](../../versions.lock.yml).
- **Storage/state**: consumer repository Git configuration; existing hook files
  and manager configuration retain their ownership.
- **Verification**: shared acceptance corpus, isolated real Git repositories,
  existing doctor/guard tests, installed-consumer conformance, and diff checks.
- **Target environment**: existing consumer platforms; automatic registration
  requires Git 2.54+. The authoring machine has Git 2.50.1. Older Git receives an
  upgrade diagnostic; the existing review minimum, Git 2.41, remains unchanged.
- **Constraints**: one native installation route, no new runtime dependency,
  public command/flag, manager adapter, upstream patch, or automatic Git upgrade.
  Every task forecasts its whole deliverable below 400 authored lines.

## Documentation

| Library or API | Version in use | Documentation |
| --- | --- | --- |
| Git hooks | 2.54+ installation | [Named hooks and ordering](https://git-scm.com/docs/git-hook/2.54.0), [message-file contract](https://git-scm.com/docs/githooks) |
| Git configuration | 2.54+ installation | [Scopes, includes, config edits](https://git-scm.com/docs/git-config/2.54.0), [worktree configuration](https://git-scm.com/docs/git-worktree#_configuration_file) |
| Git 2.55 controls | when present | [Per-event disabling and serial commit-msg](https://git-scm.com/docs/git-hook) |
| Husky / Lefthook | consumer-installed | [Husky hook files](https://typicode.github.io/husky/how-to.html), [Lefthook configuration](https://lefthook.dev/configuration/) |
| Python standard library | 3.11+ | [File operations](https://docs.python.org/3.11/library/os.html), [subprocess argv](https://docs.python.org/3.11/library/subprocess.html) |
| pytest | locked 9.1.1 | [Invocation](https://docs.pytest.org/en/stable/how-to/usage.html) |

Git and manager documentation was checked during planning. Verify additional
APIs against their official source before implementation.

## Constitution check

| Principle or constraint | Pre-design | Post-design | Evidence |
| --- | --- | --- | --- |
| I. Compose pinned upstream | PASS | PASS | Only authored package, preset guidance, and tests change. |
| II. Native surface | PASS | PASS | Existing doctor and Git hook configuration. |
| III. Consumer-selected integrations | PASS | PASS | Execution is independent of agent events. |
| IV. Durable truth | PASS | PASS | Git configuration and installed files are inspectable; no parallel registry. |
| V. Source/consumer boundary | PASS | PASS | Relative installed launcher resolves the executing checkout. |
| VI. Traceable delivery | PASS | PASS | Sequential tasks with traces, evidence, and complete forecasts. |
| Stages and human gates | PASS | PASS | Entry 10 only; technical approval and assignment remain pending. |

## System boundaries and interfaces

| Boundary or interface | Owner | Change | Explicit non-goals |
| --- | --- | --- | --- |
| Subject rule | `cli.py`, new `commit_policy.py` | Share exact existing predicate | Broader convention or command parser |
| Native entry point | new installed launcher and `commit_msg.py` | Read Git's single message-file argument; exit 0/1/4 | Review initialization or network access |
| Diagnosis and repair | `doctor.py`, new `commit_hook.py` | Discover, classify, register, verify one named hook | Rewrite existing hook files or manager configurations |
| Doctor guidance | package command/README and preset doctor | Explain repair, prerequisites, scope, and bypasses | Executable aggregate doctor or GitHub enforcement |

## Technical decisions

### D1. Use one native composition route

- **Decision**: Require Git 2.54+ and verify `git hook list` capability before
  automatic repair. Register the unique name `speckit-commit-message` with one
  `event=commit-msg` and the exact installed launcher command. Preserve all
  existing hook files, `core.hooksPath`, and manager settings.
- **Rationale**: Git now provides composition itself. The current doctor's
  `git_hook_diagnostics()` instead assumes `.git/hooks` and treats absence as
  healthy; replace that obsolete diagnosis.
- **Trade-off**: Earlier Git requires a user-managed upgrade for this feature.
  Git runs configured hooks before the traditional hook. Later consumer hooks
  may rewrite the message; this validation covers the subject it observes,
  not an immutable final subject or a server guarantee. Consumers retain the
  relative ordering and rejection behavior of their own hooks.

### D2. Keep commit execution independent of review setup

- **Decision**: Extract `_COMMIT_SUBJECT_RE` unchanged into `commit_policy.py`
  with a predicate imported by the guard and new `commit_msg.py`. Preserve
  guard message extraction and its existing exemption for unavailable input.
  The internal module accepts exactly one file, reads its first line with the
  guard's UTF-8 replacement behavior, never writes it, and returns 0 for valid,
  1 for invalid, 4 for missing/unreadable input or prerequisites.
- **Rationale**: A pure shared predicate proves equivalence without copying a
  policy into shell. Keep the exact pattern `^[a-z]+\([a-z0-9-]+\): .+$`,
  including its current whitespace behavior; no merge/fixup/breaking-change
  exemptions are added by this feature.
- **Trade-off**: A small installed `scripts/bash/commit-msg.sh` resolves its own
  extension directory, sets its source import path, selects the consumer's
  `.venv/bin/python` when present else `python3`, and calls that internal module.
  The configured command is `sh .specify/extensions/code-review/scripts/bash/commit-msg.sh`;
  Git supplies the quoted file argument. No CLI session, uv invocation, OCR,
  credentials, or network is involved. Missing runtime fails with remediation.

### D3. Diagnose the effective arrangement, never run consumer hooks

- **Decision**: Use the existing guarded Git client for version, effective
  `hook.*` configuration with origin/scope, and
  `git hook list -z --show-scope commit-msg`. Resolve the traditional path with
  `git rev-parse --path-format=absolute --git-path hooks/commit-msg`. Report the
  actual shared/local/worktree scope and named-before-traditional order.
- **Rationale**: A `.git` file is normal in a linked worktree, and configuration
  can be inherited or explicitly disabled. Source-file presence is insufficient
  to declare the hook active.
- **Trade-off**: A foreign command under the owned name, foreign-scope entries,
  duplicate/manual invocations, explicit disabling, ambiguous includes, unsafe
  config destinations, missing installed payload, or unreadable observations
  produce a blocking configuration diagnosis with exact origin and next action.
  Missing Git capability is a prerequisite diagnosis. Preserve all explicit
  disabling, including `hook.commit-msg.enabled=false` on Git 2.55+.

### D4. Repair only an unambiguous owned configuration entry

- **Decision**: Select `config.worktree` only when `extensions.worktreeConfig`
  is already enabled; otherwise use repository-local shared config and report
  that every linked checkout is affected. The command resolves its own checkout
  at execution, so each affected checkout needs the installed payload.
  Doctor checks those payloads before shared registration.
- **Rationale**: Changing worktree configuration mode or pinning a command to
  the source worktree would change consumer policy or break other checkouts.
- **Trade-off**: Repair only an absent name or a recognizable partial/duplicate
  owned entry in the selected file. Lock that config file exclusively, compare
  its bytes/mode and effective scope snapshot with the diagnosis, and use Git's
  config editor on an adjacent temporary copy. Set the exact command and one
  event there, preserve unrelated config, then atomically replace under the
  lock. Re-read the effective configuration and hook list before reporting
  success. A collision, stale snapshot, permissions failure, or occupied lock
  yields no hook/config change. Mid-write failure leaves the original intact.
  Use Git's parser, not a new configuration parser or persistence protocol.

## Data and migration behavior

The only durable addition is the owned named-hook entry in existing Git config.
No new registry or migration is needed. A matching active entry is a no-op;
recognized incomplete owned state can converge through the same repair. An
explicitly disabled or foreign entry stays untouched. No consumer hook content,
manager configuration, global configuration, or worktree mode is rewritten.

## Failure, retry, rollout, and rollback

- **Failure behavior**: `hooks` diagnosis uses existing error/report structures
  and remains visible even when another doctor group fails. Hooks use concise
  stderr and do not echo the full commit message or configuration values.
- **Retry/idempotency**: Repeated repair makes zero changes after success and
  reports exactly one effective entry. Unverifiable post-write state is a
  failure with the precise inspect/retry action, never a healthy result.
- **Rollout**: Publish through the existing reviewed release process separately;
  consumers update the extension, upgrade Git when necessary, then run doctor
  and its explicit `--fix` path. This planning PR installs no hook.
- **Rollback**: Show `git config --local --remove-section hook.speckit-commit-message`
  (or `--worktree` for that diagnosed scope), after confirming ownership. Removing
  the entry restores prior hook behavior without changing the manager or files.

## Security and privacy

All repair targets are consumer Git metadata and must be regular writable files
under the resolved Git directories, with symlink/ownership ambiguity refused.
Git commands use argv; only the fixed owned hook command uses Git's documented
shell execution. Keep secrets and arbitrary config values out of diagnostics.
Doctor does not execute existing hooks to test them. Real commits and manager
execution belong in disposable fixtures. Local bypasses, including
`--no-verify`, remain possible and are documented.

## Verification strategy

| Requirement or risk | Evidence | Command or review |
| --- | --- | --- |
| FR-003/004/010, SC-001 | Shared subject corpus; file arguments, editor, failures | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_guard.py packages/spec-kit-code-review/tests/unit/test_commit_msg.py -q` |
| FR-001/002/005/008/009, SC-002/003 | Read-only diagnosis, native config transaction, retry and collision tests | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests/unit/test_doctor.py packages/spec-kit-code-review/tests/unit/test_commit_hook.py -q` |
| FR-005/006/007, SC-002/003 | Real custom hooks, inherited scopes, linked checkouts, message rewriting and previous rejection | Same hook suite plus installed conformance below |
| C-004, SC-004 | Installed payload, real Git 2.54+ commits, no agent/engine/network | `bash packages/spec-kit-code-review/scripts/conformance/commit-msg.sh` |
| Existing review behavior | Full package and installed synthetic review regression | `uv run --frozen --offline --project packages/spec-kit-code-review pytest packages/spec-kit-code-review/tests -q`; `bash packages/spec-kit-code-review/scripts/conformance/review.sh` |
| Artifact integrity | Parser, links, traces, forecasts, whitespace | `bash .specify/scripts/bash/check-prerequisites.sh --json --require-spec --require-tasks --include-tasks`; `git diff --check` |

The acceptance corpus includes valid ASCII/non-ASCII subjects, empty input,
missing scope, uppercase, punctuation, breaking-change/fixup/merge subjects,
multiline bodies, CRLF, file paths with spaces, unreadable input, and missing
runtime. Use equal observed subjects for parity; separately record Git cleanup
and later-hook rewriting limitations. Real Git 2.54+ is mandatory for native
acceptance; fake capability output or a skipped test is not completion evidence.
Husky/Lefthook fixtures use exact recorded installed versions, with both valid
commits and rejection by the prior manager. Generated assets and synthetic
engine fixtures are reported separately from actual agent execution.

## Source layout

```text
packages/spec-kit-code-review/
  src/spec_kit_code_review/{cli,doctor,commit_policy,commit_msg,commit_hook}.py
  scripts/bash/commit-msg.sh
  tests/unit/{test_guard,test_doctor,test_commit_msg,test_commit_hook}.py
  scripts/conformance/{commit-msg,review}.sh
  commands/doctor.md
  README.md
presets/default/commands/doctor.md
README.md
```

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Wrap or append arbitrary consumer hooks | Control flow and manager regeneration make preservation unverifiable. |
| Separate Husky/Lefthook adapters for older Git | Duplicates composition Git now owns and expands maintenance. |
| Call the review CLI from commit-msg | Initializes unrelated configuration and external prerequisites. |
| Copy the regex into a shell hook | Duplicates policy and makes equivalence harder to maintain. |

## Product handoff

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean Spec Kit analysis | Run after the task ledger is complete. | Pending |
| Technical approval of plan and tasks | Human review of this PR, including Git 2.54+ prerequisite. | Pending |
| Reviewed Linear dry-run and synchronization | Project at plan; task Issues after tasks. | Pending |
| Every executable task individually assignable and assigned | One Issue per task; assignment is a human decision. | Pending |
