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
bash "$CR" review --findings ./findings.json --session <session> [--publish]

bash "$CR" doctor [--fix]
bash "$CR" completions bash|zsh
```

Universal flags: `--help`, `--json`, `--quiet`, `--verbose`, `--config PATH`,
`--root PATH`.

`review` detects its context. With no candidate it reviews the working tree and
is advisory: no immutable candidate, no session, no publishable verdict. With a
pull request it reviews the anchored candidate `(merge_base, head_commit)`,
identified by `candidate_id = sha256("<merge_base>\n<head_commit>\n")`.

An anchored review runs in two internal invocations — a CLI cannot wait for the
agent to read a packet, because the agent is what invokes it. The agent-facing
command file (`commands/code-review.md`) drives both, so a person runs one
command. The first writes the review packet and opens a session; the second
takes the agent's `findings.json`, validates it against the candidate, derives
the verdict, withdraws the environment, and closes the session.

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
- **No approval.** The verdict is `no-blocking-findings`, `changes-requested` or
  `inconclusive`. `APPROVE` and merging are unreachable by construction.
- **Two writes to GitHub, both behind `--publish`**: creating a review with
  event `COMMENT` or `REQUEST_CHANGES`, and adding the summary comment. Every
  other operation fails closed against the allowlist in `allowlist.py`.
- **Fail closed on the engine.** The pinned digest is re-verified before every
  invocation, and an output shape the adapter does not recognize is exit code 9,
  never a guessed scope.
- **One command installs, and only the pinned engine.** `doctor --fix` installs
  `ocr` into this distribution's data root and verifies it against the lock
  before leaving it on disk. Every other command, `review` included, installs,
  downloads and updates nothing.
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
| `speckit-code-review.yml` | yes | shared policy: engine, packet, budget, publish ceiling |
| `speckit-code-review.local.yml` | no (gitignored) | machine preferences: evidence root, verbosity |
| `.speckit-code-review.env` | no (gitignored) | `SPECKIT_CODE_REVIEW_*` values for this repository |
| `${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env` | n/a | the operator's own, trusted values |
| `.opencodereview/rule.json` | yes | the review rules, in the engine's native format |

Resolution order for the shared configuration: `--config PATH`, then
`SPECKIT_CODE_REVIEW_CONFIG`, then `<repo>/speckit-code-review.yml`.
`doctor --fix` creates the first three when they are absent.

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

Everything else installs nothing, on any path. `review` resolves, re-verifies
and refuses.

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

The conformance scripts drive the *installed* extension in a temporary Spec Kit
consumer, with this repository's own fakes for `ocr` and `gh`. Verifying the
**real** binary is a separate step (`tests/conformance/test_real_ocr.py`); it
uses whatever `doctor --fix` installed at the canonical path, and skips loudly
rather than passing quietly when the pinned version is not there.

Install into a temporary consumer with
`specify extension add /path/to/spec-kit-code-review --dev`. The installed copy
is self-contained: its launchers resolve their extension root at runtime, ship
their own `uv.lock`, and never reference this checkout.

## Relationship to the OCR agent plugin

`open-code-review` publishes its own slash commands and skills. Having both
installed is fine, but they are not the same thing: this extension always passes
an explicit `--rule` materialized from a specific commit, so a personal
`~/.opencodereview/rule.json` never takes part in a shared review.
