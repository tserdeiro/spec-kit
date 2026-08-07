# Spec Kit Linear

A Spec Kit extension that projects a repository's delivery state into Linear:
a **Project** per feature, an **Issue** per `Txxx` task, and each Issue's
workflow state — including the bugs and chores a human filed directly in
Linear — derived from what the repository can observe.

The repository is the sole authority. Linear is a projection and never writes
a feature artifact. Every remote write goes through one named, allowlisted
GraphQL mutation, preceded by a fresh read of the exact resources it touches.
Zero runtime dependencies: stdlib HTTP, cursor pagination, bounded retries,
sanitized diagnostics.

## Commands

| Command | What it does |
| --- | --- |
| `onboard` | Binds the repository to a Linear team, resolving every ID, and completes the team's PR-automation mapping (its one remote write: additive, never overwrites). The only setup path. |
| `push` | Projects the current feature state. Preview by default, `--apply` writes. Idempotent. |
| `status` | Reports the local feature state and its Linear projection. Never writes. |
| `doctor` | Diagnoses prerequisites, with `--fix` for the mechanical ones. |
| `completions` | Prints a bash or zsh completion script. |

Flags, in full:

- shared by `onboard`/`push`/`status`/`doctor`: `--json`, `--quiet`,
  `--config PATH`, `--root PATH`
- `onboard`: `--team-id`, `--team-key`, `--repository`, `--dry-run`, `--apply`
- `push`: `--feature NNN`, `--current`, `--all`, `--dry-run`, `--apply`,
  `--hook`
- `status`: `--feature NNN`, `--current`, `--all`
- `doctor`: `--offline`, `--fix`

`--hook` is not for manual use: the two lifecycle-hook entries in
`extension.yml` (`after_plan` and `after_tasks` — the moments the Project
and the Issues are created, which nothing native can do) pass it so a hook
invocation degrades to a clean no-op when there is no configuration yet,
and honors the `hooks.*` gates. Every later state transition is Linear's
native GitHub integration's job; `push` remains the idempotent reconciler.

## Getting started

```bash
LINEAR_API_KEY=... spec-kit-linear onboard --team-key WOR --repository my-repo
spec-kit-linear doctor
spec-kit-linear push --current            # preview
spec-kit-linear push --current --apply    # write
```

`onboard` resolves the `Repository` Project Label group, its `<slug>` child
label, the `<slug> / Features` and `<slug> / Work` Shared Views, and four
Team workflow states — `completed`, `unstarted`, and the two `started` states
named `In Progress` and `In Review` — all by name. A binding that resolves
to nothing is **created** (label group, child label, and both views, in
dependency order); a name that resolves ambiguously still aborts, and a
missing workflow state stays a human decision (states shape the team's
whole workflow, not just this binding).

It also performs its one remote write: the team's PR-automation mapping for
Linear's native GitHub integration (`draft` → *In Progress*, `start` →
*In Review*, `merge` → *Done*). Additive and idempotent — missing mappings
are created, an existing different mapping is warned about and left
untouched, branch-scoped rules are never touched. Connecting the GitHub
integration itself is a one-time human step per workspace (Linear Settings →
Integrations → GitHub); without it, onboard warns and the mapping stays
dormant until an admin connects it.

## Task states

Every `push` and every `status` re-derives each task's state from what can be
observed right now. Nothing is remembered between runs and no event is
listened for, so a missed webhook cannot desynchronize anything.

| Observed | Derived state | Linear state |
| --- | --- | --- |
| `[x]` in `tasks.md`, or a merged PR | `completed` | `completed_state_id` |
| An open, ready-for-review PR | `review` | `review_state_id` |
| An open draft PR, or a branch | `started` | `started_state_id` |
| Nothing | `unstarted` | `open_state_id` |

The first row that applies wins. Branches and pull requests count only when
they follow the convention `NNN-Txxx`, optionally with a `-suffix`
(`001-T004`, `001-T004-add-parser`); several PRs on one task — stacked PRs —
report the furthest that task reached.

Branches are read from the refs Git already has (`refs/heads` and
`refs/remotes/origin`): no fetch, no network. Pull requests are read with one
`gh pr list` per invocation. GitHub is optional: with no `gh`, no
authentication, or unreadable output, `push` and `status` warn once and
derive from the checkbox and branches alone. A workflow state the Team does
not have is left unconfigured, and the tasks that derive to it keep the state
they have — a `review` with no `In Review` falls back to `In Progress`.

## Bugs and chores

A bug or a chore is an Issue a person files in Linear; it has no spec, no
plan, and no `tasks.md` row. This extension never creates one and never edits
its content — the only thing it projects is its workflow state, from the same
two observations, on the same map minus the checkbox row:

| Observed | Derived state |
| --- | --- |
| A merged PR | `completed` |
| An open, ready-for-review PR | `review` |
| An open draft PR, or a branch | `started` |
| Nothing | *left untouched* |

The convention is the Issue key itself: a branch (local or `origin/`) named
`<team key>-<number>`, optionally with a `-suffix` and optionally behind a
single-level prefix — Linear's own "Copy git branch name" format
(`<username>/wor-123-slug`) — references that Issue: `wor-123-fix-crash`,
`WOR-45`, `devs/wor-45-fix`. The team key comes from `linear.team_key` in
the configuration and the match is case-insensitive. The last row is the
difference that matters: an Issue nobody has started is never observed, so a
backlog is never rewritten.

Every `push` reconciles every observed work item — with `--feature`, with
`--all`, and in a repository that has no feature directory at all. The
feature selectors scope the `Txxx` tasks and nothing else. All observed keys
are resolved in one batched query per push; a branch naming an Issue that
does not exist is a warning, never an operation. `status` lists the same
items under **Work items** (`status.work_items` in `--json`).

## Configuration

`speckit-linear.yml` at the repository root, written by `onboard` and
**committed**: it carries no secrets, so teammates and CI inherit the binding
from Git. See [`config/speckit-linear.template.yml`](config/speckit-linear.template.yml)
for the full schema. `--config PATH` or `SPECKIT_LINEAR_CONFIG` override the
location.

Optional sections: `lifecycle` (the four workflow state IDs a derived state
is written to) and `hooks` (`lifecycle_enabled`/`auto_apply`, both default
`true`).

## Credentials

GitHub is never authenticated here: the optional pull-request signal goes
through the `gh` binary, which owns its own credential.

Set exactly one of `LINEAR_API_KEY` or `LINEAR_OAUTH_ACCESS_TOKEN`. They are
read from the process environment, from `.speckit-linear.env` at the
repository root (gitignored; `onboard` and `doctor --fix` add the entry), or
from `~/.config/speckit-linear/env`. The real environment always wins.
Credentials never appear in output, in the configuration, or in Git.

## Choosing the GraphQL destination

Without an override, every command that talks to Linear reaches the
production workspace of whoever runs it. `SPECKIT_LINEAR_GRAPHQL_ENDPOINT`
overrides that destination — and only the destination.

- It must be an absolute `http`/`https` URL. Plain `http` is accepted only
  against `localhost`, `127.0.0.1` or `::1`; anything else is exit code 3, as
  is an empty or malformed value. The string is used verbatim.
- It cannot come from configuration. An endpoint-shaped key in the committed
  config is exit code 3, never a warning: a per-repository committed file able
  to redirect a whole team's reads and writes is a redirection vector, not a
  preference.
- When the effective endpoint is not production, every command that can reach
  Linear says so prominently on stderr and adds an `endpoint` object to its
  JSON result. No flag silences it, `--quiet` included.
- A redirect from the configured endpoint is refused rather than followed, so
  the credential is never sent to a host the validator did not approve.

## What push will never do

Delete or archive anything; create sub-issues or checklists; assign anyone
(assignment is native Linear: the UI or the official Linear MCP acting as
the human); touch a project lead, project members, or human comments;
rewrite content outside its own `<!-- speckit-linear:... -->` managed
block; create a bug or chore Issue, or change anything about one except
its workflow state; or touch any file under `specs/`. The complete write
surface is nine operation kinds with an enumerated input field list each
— see [`src/spec_kit_linear/allowlist.py`](src/spec_kit_linear/allowlist.py).

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Usage error |
| 3 | Configuration error |
| 4 | Missing prerequisite |
| 5 | Authentication or authorization |
| 6 | Remote drift, ambiguous identity, or a forbidden mutation |
| 8 | Transport or service unavailable |
| 9 | GraphQL or protocol error |
| 10 | Post-apply verification failed |

## Local development

```bash
uv sync --frozen
uv run pytest tests
PYTHONPATH=src uv run --frozen python -m spec_kit_linear.cli doctor --offline --root /path/to/consumer
PYTHONPATH=src uv run --frozen python -m spec_kit_linear.cli push --dry-run --json --root /path/to/consumer --feature 001
```

`scripts/conformance/installed-artifact.sh` installs the extension into a
throwaway consumer repository and asserts that the installed artifact
materializes its commands, never references its source checkout, resolves its
configuration, fails closed (exit 8) when it cannot reach its endpoint, and
announces a non-production endpoint on every invocation. It pins the endpoint
override to a loopback destination and refuses to run if the effective
endpoint would be production, so credentials on a machine cannot change what
conformance touches.

## Shell completions

```bash
eval "$(spec-kit-linear completions bash)"   # or: zsh
```

The script is generated from the argparse tree itself, so it can never drift
from the real command surface.
