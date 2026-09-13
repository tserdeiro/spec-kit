# Spec Kit Code Review

A Spec Kit extension with **one review command**. It wraps
[open-code-review](https://github.com/alibaba/open-code-review) (OCR), pinned by
version and digest, and reviews against the repository's versioned rules and its
Spec Kit artifacts — without ever modifying what it reviews.

## Commands

```bash
CR=".specify/extensions/code-review/scripts/bash/run.sh"

bash "$CR" review                    # the pending diff of the working tree (advisory)
bash "$CR" review 128                # an anchored pull-request candidate
bash "$CR" review --base main --head feature
bash "$CR" review --findings <session>/findings.json --session <session> [--publish]

bash "$CR" doctor [--fix]
```

Universal flags: `--help`, `--json`, `--quiet`, `--verbose`, `--config PATH`,
`--root PATH`.

### Native commit-message validation

`doctor` reports Git's effective `commit-msg` hooks path, native registration
scope, payload, and state. Automatic repair requires Git 2.54+ and
`git hook list`; the review command's minimum remains Git 2.41. With
`doctor --fix`, the extension registers one named native hook when the
arrangement is safe:

```ini
[hook "speckit-commit-message"]
    command = sh .specify/extensions/code-review/scripts/bash/commit-msg.sh
    event = commit-msg
```

The local scope uses the repository-shared config path. When
`extensions.worktreeConfig` is enabled, registration is local to the current
worktree in Git's resolved `config.worktree` path. Otherwise it is in the
shared config path and applies to every linked worktree; the installed
payload must exist in each of them. The command resolves the installed
checkout at runtime. The payload is `scripts/bash/commit-msg.sh` plus
`__init__.py`, `commit_msg.py`, and `commit_policy.py` under
`src/spec_kit_code_review/`.
Custom `core.hooksPath`, traditional hooks, and Husky or Lefthook dispatchers
remain untouched and keep their bytes, modes, arguments, order, and rejection
behavior. A successful retry is idempotent and leaves one effective
registration.

States are `missing`, `installed`, `disabled`, and `unverifiable`, with
partial, duplicate, foreign-scope, conflict, payload, lock, permission,
concurrency, write, and readback diagnostics also reported. The doctor keeps
the affected path and the diagnostic's available next action in every finding.
A missing or
unreadable payload requires reinstalling this extension and rerunning
`doctor --fix`; a disabled or foreign entry requires explicit manual repair.
The repair takes a cooperative exclusive lock and checks the diagnosed bytes,
mode, and effective snapshot before preparing its temporary file. Writers that
honor Git's lock cannot edit concurrently. A direct writer that ignores the
lock can race after that snapshot; no atomic compare-and-swap guarantee is
made. The temporary file is edited through Git, atomically replaces the
destination, and is checked by effective-config and hook-list readback. If
readback fails, restoration of the diagnosed bytes and mode is attempted. A
restoration failure requires manual inspection of the reported config path and
the owned-section rollback below. A `git_hooks_write_failed` diagnostic (`native
registration was not completed ...; retry doctor`) is generic: it can mean a
pre-replacement write failure or a replacement followed by failed restoration.
Inspect the path before retrying; the diagnostic cannot always say which
outcome occurred.

To roll back, confirm the scope reported by `doctor` and remove only the owned
section with the matching command:

```bash
git config --local --remove-section hook.speckit-commit-message
git config --worktree --remove-section hook.speckit-commit-message
```

This does not edit consumer hook files or manager configuration. Local
validation remains bypassable with `git commit --no-verify` or per-event
disabling, and a later traditional hook may rewrite the message after the
native validator observes it; GitHub and CI enforcement remain separate.

`review` detects its context. With no candidate it reviews the working tree and
is advisory: no immutable candidate, no session, no publishable verdict. With a
pull request it reviews the anchored candidate `(merge_base, head_commit)`,
identified by `candidate_id = sha256("<merge_base>\n<head_commit>\n")`.

An advisory response reports `advisory_evidence.coverage_path` beside the
packet. After reading the packet, the host may write `coverage.json` there with
the packet and inventory digests, working-tree source hashes, exact inclusive
line-range receipts, and scope-linked assessments. Compare those source hashes
before reporting; compare the complete reviewed-path set in
`context-inventory.json` as well, including new, deleted, and unavailable
paths. A tracked deletion remains valid while the path stays absent; an
unavailable or symlinked path is an explicit gap. Recompute membership with
`git -c diff.autoRefreshIndex=false diff -z --no-renames --name-only
--end-of-options HEAD` plus `git ls-files --others --exclude-standard -z`.
The NUL-delimited results are unioned: the first covers staged and unstaged
tracked changes against `HEAD`, and the second adds untracked paths. Any changed, added, or removed
source requires a fresh packet. This evidence is host-reported and advisory only. It is never reusable for pull-request
coverage, which uses the session findings envelope below.

An anchored review runs in two internal invocations — a CLI cannot wait for the
agent to read a packet, because the agent is what invokes it. The agent-facing
command file (`commands/code-review.md`) drives both, so a person runs one
command. The first writes the review packet and opens a session; the second
takes the agent's `<session>/findings.json`, validates it against the candidate,
derives the verdict, withdraws the environment, and closes the session. A
findings path outside that session is a usage error.

### findings.json

```json
{
  "findings": [
    {
      "path": "src/module.py",
      "start_line": 42,
      "end_line": 44,
      "severity": "blocking",
      "category": "correctness",
      "title": "…",
      "content": "…"
    }
  ],
  "coverage": {
    "candidate_id": "<candidate_id>",
    "packet_sha256": "<packet_sha256>",
    "inventory_sha256": "<inventory_sha256>",
    "reads": [{"path": "specs/003-example/spec.md", "version": "<head_commit>", "start_line": 1, "end_line": 20, "sha256": "<exact-range-sha256>", "assessment": "How this range affects the reviewed scope", "scope": "FR-014"}]
  }
}
```

When a category is invalid, edit only that field and rerun the same close
command. Use the generated category catalog in the packet; an ambiguous
meaning remains unresolved until the reviewer selects a meaningful supported
category. The original submission is preserved byte-for-byte at
`finding-corrections/<findings_attempt_id>/original.json`, with each attempted
correction recorded beside it. Partial corrections stay open. A validated
correction record is evidence of the category change, not approval, closure, or
publication; the normal verdict still applies. A blocking finding remains
`changes-requested`, and coverage or engine gaps remain `inconclusive`.
Substantive edits require a fresh review and new analysis.

Severities: `blocking`, `major`, `minor`, `nit`, `info`. Categories are listed
in the packet's generated catalog; any other value refuses the whole file.

## Guards

Configured on an agent with runtime-event support (Claude Code, Codex,
Cursor), this extension also runs as a `pre_tool_use` handler and blocks,
before it takes effect (exit 2, the fix on stderr):

- a `git commit` whose subject — however the message is given (`-m`,
  `--message`, `-F`/`--file`, or a heredoc) — does not follow
  `type(scope): subject`;
- any form of `git push --force`, including a `+refspec` or `--mirror`;
- a `gh pr merge` carrying `--delete-branch`;
- an `Edit`/`Write` to a `protected_paths` glob while on a task branch
  (`NNN-T###-...`); a feature branch is exempt.

Every other tool, command, or branch — and any malformed payload or internal
failure — is a silent no-op, exit 0.

## Invariants

- **Nothing in the candidate tree governs execution.** Configuration, the
  repository env file, executable paths, and (in the fail-closed cases) the rule
  file are read from the operator's own ref, before anything is materialized.
- **The candidate never touches your checkout.** It is materialized in a
  temporary worktree under the evidence root, withdrawn when the review ends. A
  worktree holding uncommitted content is kept and reported, never forced.
- **The candidate does not write the criteria it is judged by.** When it is
  cross-repository, or when its own diff touches `.opencodereview/`, the rules
  come from the merge base and the proposed ones travel in the packet as data.
- **The candidate does not edit the contract it is judged by.** A task pull
  request (base branch `NNN-…`) that touches a `protected_paths` entry gets an
  automatic `blocking` finding and `changes-requested`, whatever the agent
  found; the feature pull request, based on the trunk, is exempt.
- **No approval.** The verdict is `no-blocking-findings`, `changes-requested` or
  `inconclusive`. `APPROVE` and merging are unreachable by construction.
- **Two writes to GitHub, both behind `--publish`**: creating a review with
  event `COMMENT` or `REQUEST_CHANGES`, and adding the summary comment. Every
  other operation fails closed against the allowlist in `allowlist.py`.
- **Fail closed on the engine.** The pinned digest is re-verified before every
  invocation, and an output shape the adapter does not recognize is exit code 9,
  never a guessed scope.
- **Doctor performs only its bounded installs.** `doctor --fix` installs `ocr`
  into this distribution's data root, verifies it against the lock, and can
  register the named native commit hook in the consumer's Git configuration.
  Every other command, `review` included, installs, downloads and updates
  nothing.
- **No new credential, zero runtime dependencies.** GitHub authentication is the
  operator's own `gh`; OCR runs in delegation mode, so no model provider is
  introduced. Standard library only.

## Review budget

A reviewed pull request stays under ~400 authored executable lines. Over that,
the review emits a warning and suggests stacked pull requests. It is a
convention with a warning attached, never a failure: accepting a larger pull
request is a human decision. `budget.limit` sets the number.

## Configuration

| File | Committed? | Purpose |
| --- | --- | --- |
| `speckit-code-review.yml` | yes | shared policy: engine, packet, budget, publish ceiling, protected paths |
| `speckit-code-review.local.yml` | no (gitignored) | machine preferences: evidence root, verbosity |
| `.speckit-code-review.env` | no (gitignored) | `SPECKIT_CODE_REVIEW_*` values for this repository |
| `${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env` | n/a | the operator's own, trusted values |
| `.opencodereview/rule.json` | yes | the review rules, in the engine's native format |

Resolution order for the shared configuration: `--config PATH`, then
`SPECKIT_CODE_REVIEW_CONFIG`, then `<repo>/speckit-code-review.yml`.
`doctor --fix` creates the first three when they are absent. It also registers
the named native commit hook described above when Git and the hook arrangement
are safe. For a
repository with no rule file, it also writes `.opencodereview/rule.json`
with a starting `**/*` rule stating the engineering principles —
over-engineering and speculative abstraction are `major` findings, a new
runtime dependency is `blocking` — ahead of the shipped `**/*.py` rule; a
repository with an existing rule file merges the `**/*` rule in by hand.

`protected_paths` (default `specs/*/spec.md` and `.specify/memory/constitution.md`)
names the paths a task pull request may not touch; see Invariants above.

A repository env file can never define an executable path:
`SPECKIT_CODE_REVIEW_OCR_BIN` and `SPECKIT_CODE_REVIEW_GH_BIN` are honored only
from the real process environment or from the operator's own file. One
**tracked** in the candidate's head rejects the review outright (exit 3).

## Per-user paths, and where the engine lives

```text
${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env       operator configuration
${XDG_DATA_HOME:-~/.local/share}/tserdeiro/spec-kit/tools/<tool>/<version>/
                                                            pinned external binaries
${XDG_STATE_HOME:-~/.local/state}/tserdeiro/spec-kit/code-review/
                                                            session evidence, 0700
```

The separation is deliberate: the evidence carries diffs of the code under
review, and `XDG_STATE_HOME` is for what should not be synced or backed up.
`doctor` prints all three resolved.

### Installing `ocr`

```bash
bash "$CR" doctor --fix          # installs the pinned engine if it is absent
```

`doctor --fix` runs the `npm install` itself, by argv and never through a shell,
into the data root, one directory per version — **never global**, because a tool
this extension pins must not outlive its uninstall, and **never per-project**,
because the executable guard refuses (exit 4) any binary resolving inside the
tree under review. What it installs is verified against the lock's per-platform
digest **before it is left on disk**: a mismatch removes the whole directory and
fails. `doctor` also prints the equivalent command for a person who prefers to
run it themselves.

The `review` command installs nothing on any path; it only resolves and
re-verifies the engine.

### Which `ocr` runs

1. `SPECKIT_CODE_REVIEW_OCR_BIN`, from the process environment or the operator's
   own env file — an explicit choice, verified like anything else;
2. otherwise the canonical pinned path above, for the tag the lock pins.

`PATH` is not consulted: the npm package puts a JS shim named `ocr` there, and
its digest is never the pinned one. Nothing has to be exported for the normal
path to work.

## Exit codes

```text
0   success                     6   candidate not resolvable or ambiguous
1   changes-requested           7   environment not preparable/withdrawable
2   usage                       8   drift (head or merge base moved)
3   configuration               9   engine failure
4   missing prerequisite        10  publication failure
5   GitHub authentication       130 interrupted, environment restored
```

## Local development

```bash
uv sync --frozen
uv run pytest packages/spec-kit-code-review/tests
bash packages/spec-kit-code-review/scripts/conformance/review.sh
bash packages/spec-kit-code-review/scripts/conformance/publish.sh
uv run pytest packages/spec-kit-code-review/tests/conformance -v   # the real binary
```

`review.sh` is fake-tool conformance evidence: it drives the *installed*
extension in a temporary consumer and checks late-task, shared multi-task,
full-feature, ledger-free short-path, receipt, packet-limit, and checkout
invariants with the repository's fake `ocr` and `gh`. This does not establish
entry 23 live-host acceptance. The separate `tests/conformance/test_real_ocr.py`
checks the pinned binary installed by `doctor --fix` and skips loudly when
that binary is unavailable.

Install into a temporary consumer with
`specify extension add /path/to/spec-kit-code-review --dev`. The installed copy
is self-contained: its launchers resolve their extension root at runtime, ship
their own `uv.lock`, and never reference this checkout.

## Relationship to the OCR agent plugin

`open-code-review` publishes its own slash commands and skills. Having both
installed is fine, but they are not the same thing: this extension always passes
an explicit `--rule` materialized from a specific commit, so a personal
`~/.opencodereview/rule.json` never takes part in a shared review.
