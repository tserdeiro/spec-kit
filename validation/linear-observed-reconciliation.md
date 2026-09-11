# Round 005 acceptance — an observed Linear reconciliation, live

**Status: PERFORMED. Date: 2026-09-11.** The published distribution drove a
throwaway consumer against the real Linear team `TDS` (workspace
`tserdeiro`, team name *Personal*). Every state below was read back twice:
once through the extension's own `status --current --json`, once through an
independent `POST https://api.linear.app/graphql` call that does not use the
extension. No fixture, no mock, no endpoint override.

## Environment

| Item | Value |
| --- | --- |
| Specify CLI | 1.0.4 (Python 3.14.6, Darwin arm64) |
| Catalogs | the three published `catalog/*.json` on `main` |
| Bundle | `developer` 0.16.0 (5 components) |
| Extension | `linear` **0.13.0** (`.specify/extensions/linear/extension.yml`) |
| Extension | `code-review` **0.5.0** |
| Preset | `default` **0.10.0** |
| Consumer | `…/scratchpad/linear-acceptance/consumer`, HEAD `1cf8235`, branch `001-acceptance-probe` |
| Remote | local bare repository `…/linear-acceptance/origin.git` (GitHub deliberately out of scope) |
| Dispatcher interpreter | `python3` (3.9.6); no `.venv` was pinned by the wiring, so none was created |
| Linear binding | team `TDS` `8e432d46-3172-4201-bb1a-62d959c282d2`, slug `accept-2026-09-11-consumer` |

Team workflow states present: `Todo` (unstarted), `In Progress` (started),
`Done` (completed), plus Backlog/Canceled/Duplicate. **No `In Review`
state** — the `review` projection was therefore unconfigured for the whole
run, as `onboard` warned.

## Step 1 — Build the consumer from the published release

```bash
git init -b main && git remote add origin …/origin.git   # bare local origin
specify init --here --force --integration claude --ignore-agent-tools
specify extension catalog add https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/extensions.json --name tserdeiro-spec-kit --priority 1 --install-allowed
specify preset catalog add    https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/presets.json    --name tserdeiro-spec-kit --priority 1 --install-allowed
specify bundle catalog add    https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog/bundles.json    --id   tserdeiro-spec-kit --priority 1
specify bundle install developer        # -> "Installed 'developer' (5 added, 0 already present)."
```

**Finding A-1 (blocking for a new consumer, reproduced here).**
`specify bundle install developer` on a clean consumer did **not** wire the
runtime events: after it, `.specify/events.py` did not exist and
`.claude/settings.json` did not exist, while `specify extension list`
already reported `linear v0.13.0 … Hooks: 2`. This contradicts
`docs/dx.md` ("Verificación previa a la spec", item 3: *`bundle install
developer` en un consumidor limpio cablea los eventos sin ningún paso
manual*). The documented repair from dogfooding entry 102 fixed it in one
step:

```bash
specify extension disable linear && specify extension enable linear
```

after which `.specify/events.py` exists (13617 bytes, `0755`) and
`.claude/settings.json` carries the three `__speckit_event__` markers
(`PreToolUse` matcher `Bash|Edit|Write`, `SessionStart`, `PostToolUse`
matcher `Bash`). Every observation below was made with that wiring.

**Note A-2.** The generated hook commands pin `python3`, not
`.venv/bin/python`, because the consumer has no `.venv`. On this machine
`python3` is 3.9.6 while the extension requires 3.11+; the dispatcher runs
fine on 3.9.6 because `run.sh` re-enters through `uv run --project`, which
resolves its own interpreter. No `uv venv` / `uv sync` was needed.

Scaffold committed: `d3c152c chore(scaffold): install the developer bundle`.

## Step 2 — Onboard and the two doctors

```bash
bash .specify/extensions/linear/scripts/bash/run.sh onboard --team-key TDS \
  --repository accept-2026-09-11-consumer --apply     # exit 0
```

**Note A-3.** `--repository ACCEPT-2026-09-11-consumer` is rejected:
`error: --repository must use lowercase letters, numbers, and hyphens`. The
slug is therefore lowercase; Project and Issue titles keep the uppercase
`ACCEPT-2026-09-11` marker.

`onboard` created three resources and wrote `speckit-linear.yml`
(committed, `97a553e`):

| Resource | Identifier | createdAt |
| --- | --- | --- |
| Project Label `accept-2026-09-11-consumer` (under the pre-existing `Repository` group) | `9959951a-dae1-45a3-8a06-9da3fc999fc4` | 2026-09-11T18:07:33.157Z |
| Shared View `accept-2026-09-11-consumer / Features` (Project) | `47a28798-8730-4d47-b10d-c0251d975f9b` | 2026-09-11T18:07:33.472Z |
| Shared View `accept-2026-09-11-consumer / Work` (Issue) | `92069c05-b269-4c7a-bb15-05ac2a442ff9` | 2026-09-11T18:07:33.774Z |

It performed **no** team-level write: the team's `gitAutomationStates`
already held `draft → In Progress` and `merge → Done`, both created
2026-08-30T11:59:20Z by the earlier `spec-kit` binding, and a re-run of
`onboard --dry-run --json` reports `"automation_operations": []` with
`"missing_remote_resources": ["review_state"]`. `start → In Review` stays
unmapped because the team has no `In Review` state.

Doctors, read-only, both exit `0`:

```bash
bash .specify/extensions/linear/scripts/bash/run.sh doctor        # "online doctor checks passed"
bash .specify/extensions/code-review/scripts/bash/run.sh doctor   # "doctor completed with no blocking problems" + 4 warnings
```

The code-review warnings are the expected absent-configuration ones
(`speckit-code-review.yml`, `.local.yml`, gitignore entries,
`.opencodereview/rule.json`); `--fix` was not run.

## Step 3 — A hand-written feature

Branch `001-acceptance-probe`; `specs/001-acceptance-probe/{spec,plan,tasks}.md`
in the `default` preset's shape, two tasks with `Delivery` forecasts, plus
`.specify/feature.json`. Commit `fa02c97`.

`status --current --json` before any push: `missing:
["feature_project", "task:001:T001", "task:001:T002"]`,
`remote_project_count: 0`, both tasks `derived_state: unstarted`,
`remote_operations: {"mode": "query-only", "writes": 0}`.

## Step 4 — The observations

Every row was confirmed by the independent GraphQL query
`issues(filter: {project: {id: {eq: "86ef307f-…"}}}, includeArchived: true)`
plus `project(id: …) { name archivedAt }`.

### 4a. Create — `push --current --apply`

```
push applied 3 operation(s)
  project.create         feature:001     001: ACCEPT-2026-09-11-acceptance-probe
  issue.create           task:001:T001   T001 ACCEPT-2026-09-11 probe the started transition …
  issue.create           task:001:T002   T002 ACCEPT-2026-09-11 probe the archive and restore path …
warning: `gh pr list` failed (no GitHub remote, or not authenticated); pull-request states are not derived.
```

| Resource | Identifier | Observed state |
| --- | --- | --- |
| Project | `86ef307f-bb51-4e5a-9143-892b78c45473` | `001: ACCEPT-2026-09-11-acceptance-probe`, `archivedAt: null` |
| Issue T001 | **TDS-77** (`e1a57dee-e211-4133-892b-57e0895892ea`) | **Todo** (`unstarted`) |
| Issue T002 | **TDS-78** (`15ac4c68-9e67-4bdc-8d2c-7493d4f827eb`) | **Todo** (`unstarted`) |

The `gh` warning is expected and is the reason the PR-derived rows of the
state table were never exercised (see the final table).

### 4b. The real `session_start` handler, on the feature branch

```bash
python3 .specify/events.py session-start session_start 60 < /dev/null
```

exit `0`, stderr empty, stdout exactly:

```
Linear: 001 on 001-acceptance-probe — next T001 (unchecked); next: /speckit.implement 001
```

Linear unchanged afterwards: TDS-77 `Todo`, TDS-78 `Todo`, project
unarchived; `status` reports `writes: 0` and `operations: []`.

### 4c. The real `post_tool_use` handler, after a real push

```bash
git switch -c 001-T001-probe && git push -u origin 001-T001-probe   # real push to the bare origin
printf '{"tool_name":"Bash","tool_input":{"command":"git push -u origin 001-T001-probe"}}' \
  | python3 .specify/events.py post-tool-use post_tool_use 60
```

Handler: exit `0`, stdout empty, stderr empty — silent by contract.
Linear afterwards:

| Issue | Observed state | `state_source` |
| --- | --- | --- |
| **TDS-77** | **In Progress** (`started`) | `branch` |
| TDS-78 | Todo (`unstarted`) | `none` |

`status` next action for T001 became `/speckit.pr`. This is the first time
the shipped `post_tool_use` handler has been observed writing a real Linear
state.

### 4d. Checkbox + Completion evidence → completed

On the feature branch: `- [x] T001 …` and a filled `**Completion
evidence**` (commit `19de88b`), then the task branch was removed locally
and on the remote, so no live branch remained:

```bash
git branch -D 001-T001-probe && git push origin --delete 001-T001-probe
bash .specify/extensions/linear/scripts/bash/run.sh push --current --apply
```

```
push applied 2 operation(s)
  issue.update           task:001:T001
  issue.lifecycle.update task:001:T001
```

| Issue | Observed state | `state_source` |
| --- | --- | --- |
| **TDS-77** | **Done** (`completed`) | `checkbox` |
| TDS-78 | Todo (`unstarted`) | `none` |

### 4e. Remove a task → archive; restore → unarchive

T002's block deleted from `tasks.md` (commit `8d42fde`):

```
push preview: 1 operation(s)
  issue.archive          task:001:T002
```

State unchanged after the dry-run (verified). Then `--apply`:

```
push applied 1 operation(s)
  issue.archive          task:001:T002
```

GraphQL with `includeArchived: true`: **TDS-78 `archivedAt:
2026-09-11T18:12:17.343Z`**, still `Todo`; the Project and TDS-77 untouched.

T002 restored verbatim (commit `1cf8235`), then `--apply`:

```
push applied 1 operation(s)
  issue.unarchive        task:001:T002
```

**TDS-78 `archivedAt: null`** again, state `Todo`. The Issue identifier was
preserved across archive and restore — no second Issue was created.

### 4f. Idempotence

```bash
bash .specify/extensions/linear/scripts/bash/run.sh push --current --apply   # push applied 0 operation(s)
bash .specify/extensions/linear/scripts/bash/run.sh push --current --apply   # push applied 0 operation(s)
```

Both exit `0`. Final `status --current --json`: `missing: []`, `drift: []`,
`remote_operations: {"mode": "query-only", "writes": 0}`.

## Step 5 — Cleanup

```graphql
mutation {
  a: issueArchive(id: "e1a57dee-…")   { success }   # TDS-77
  b: issueArchive(id: "15ac4c68-…")   { success }   # TDS-78
  c: projectArchive(id: "86ef307f-…") { success }
}
```

All three `success: true`, verified by re-reading with `includeArchived: true`:

| Resource | `archivedAt` |
| --- | --- |
| Project `001: ACCEPT-2026-09-11-acceptance-probe` | 2026-09-11T18:12:58.552Z |
| TDS-77 | 2026-09-11T18:12:58.252Z |
| TDS-78 | 2026-09-11T18:12:58.426Z |

**Blast radius.** The only TDS Issues updated in the window are TDS-77 and
TDS-78. The four pre-existing Projects (`002`–`005`) are untouched and
unarchived.

**Left behind for a human to remove** (`onboard` creates these; nothing
archives them, and deleting was out of scope):

- Project Label `accept-2026-09-11-consumer` — `9959951a-dae1-45a3-8a06-9da3fc999fc4`
- Shared View `accept-2026-09-11-consumer / Features` — `47a28798-8730-4d47-b10d-c0251d975f9b`
- Shared View `accept-2026-09-11-consumer / Work` — `92069c05-b269-4c7a-bb15-05ac2a442ff9`

Do **not** remove the `Repository` label group
(`8b20a0a6-7618-41f8-b61a-61448a70b17b`, created 2026-08-30): it is shared
with the live `spec-kit` binding.

## Observed vs not exercised

| Projection row | Verdict |
| --- | --- |
| `project.create` / `issue.create` at first push | **Observed** (TDS-77, TDS-78 in `Todo`) |
| Branch → `started` → *In Progress*, via the real `post_tool_use` handler | **Observed** (TDS-77) |
| `session_start` context line, zero writes | **Observed** |
| `[x]` checkbox (no live PR) → `completed` → *Done* | **Observed** (TDS-77, `state_source: checkbox`) |
| Task removed → `issue.archive`, previewed then applied | **Observed** (TDS-78, `archivedAt` set) |
| Task restored → `issue.unarchive`, same Issue | **Observed** (TDS-78, `archivedAt: null`) |
| Idempotence: repeated `--apply` plans 0 operations | **Observed** (twice) |
| Open draft PR → `started` | **Not exercised** — no GitHub remote; `gh pr list` warned on every push |
| Ready-for-review PR → `review` → *In Review* | **Not exercised**, and **not configurable**: team `TDS` has no `In Review` state |
| Merged PR → `completed` | **Not exercised** — no GitHub remote |
| Stacked PRs reporting the furthest state | **Not exercised** |
| Bugs / chores (work items by Issue-key branch) | **Not exercised** — `work_items: []` throughout |
| Team PR-automation mapping written by `onboard` | **Not exercised** — already complete from 2026-08-30; `automation_operations: []` |
| Codex runtime | **Not exercised** — consumer installed with `--integration claude` only |
| Claude Code agent actually firing the hooks | **Not exercised** — handlers were driven through `.specify/events.py` with the exact argv and stdin the generated `.claude/settings.json` uses |
| `pre_tool_use` guard | **Not exercised** — out of scope for this item |

## Findings to carry forward

1. **A-1**: `specify bundle install developer` left a clean consumer with no
   `.specify/events.py` and no `.claude/settings.json`. `docs/dx.md` claims
   the opposite. A new consumer that follows the README's "Primeros pasos"
   verbatim gets no session context line, no `post_tool_use` reconcile and
   no guard, silently — the handlers are silent by contract, so nothing
   says so. `specify extension disable linear && specify extension enable
   linear` repairs it. Candidate for the reliability round's doctor step 6.
2. **A-3**: `--repository` rejects uppercase, so a slug convention that
   includes uppercase cannot be used; the error message is clear.
3. `In Review` is absent from team `TDS`, so the `review` projection cannot
   be accepted in this workspace without a human creating that state.
