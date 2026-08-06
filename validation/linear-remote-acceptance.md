# Linear remote acceptance — Etapa 3 (spec-kit-linear)

Date: 2026-07-27. Workspace: Wortise (team WOR), authorized by the repository
owner in-session. Credentials were provided exclusively through the
`LINEAR_API_KEY` environment variable (gitignored `.env`), never stored in
configuration or artifacts. All command output below is sanitized.

## Sequence and results

| Step | Command | Result |
|---|---|---|
| Bootstrap seed dry-run | `seed --dry-run --adopt-existing --strict --resources … --plan …` | Plan with 2 `project_label.create` ops (group `Repository`, label `spec-kit`); Shared Views emitted as manual instructions per contract |
| Expired-plan rejection | `seed --apply` with an expired plan | **Exit code 7** (`plan_expired`) — fail-closed, as specified |
| Seed apply (authorized) | `seed --apply --plan …` | 2 writes; post-apply snapshot verification passed |
| Seed idempotency | second `seed --dry-run --adopt-existing --strict` | **0 operations** |
| Binding validation | `doctor` / `status` / `pull` | Exit 0 after schema conformance fix (see below); `lifecycle_disabled` warning emitted as designed |
| Push dry-run (reviewed) | `push --dry-run --plan …` | 15 ops: 1 `project.create`, 4 `milestone.create`, 10 `issue.create`; no updates, no deletes, no assignee/lead/member inputs |
| Push apply (authorized) | `push --apply --plan …` | 15 writes, 0 recovered; post-apply read verification passed |
| Push idempotency | second `push --dry-run` | **0 operations** |
| Remote verification | direct read-only GraphQL | Feature Project `001: …repository file sync` carries label `spec-kit`, 4 Phase Milestones, issues WOR-18…WOR-27 |

## Schema conformance findings (fixed in code during acceptance)

The `BindingInspection` query had never run against the real schema; Linear
rejected it (HTTP 400). Fixes applied to `linear_client.py`, all covered by
regression tests using serializations captured verbatim from this workspace:

1. Root field `projectLabelGroup` does not exist — groups resolve through
   `projectLabel(id:)` (aliased to preserve the response shape).
2. `CustomView.type` does not exist — the field is `modelName`
   (aliased to `type`).
3. `team`/`projectLabel`/`customView` id arguments are `String!`, not `ID!`.
4. Saved-view filters are serialized by the UI with `and`/`or` wrappers and
   label **names** (`{"name": {"eq": …}}`), not the canonical
   `labels.some.id.eq` API form. View-filter validation now accepts either
   form anywhere in the filter tree; Issue views must still scope the label
   under `project` (a view pinned to a specific project id fails closed).

## Manual steps performed by the owner (per contract)

- Created Shared Views `spec-kit / Features` (Project) and `spec-kit / Work`
  (Issue) through the Linear UI, workspace-shared, filtered by the repository
  label. The Custom View GraphQL contract remains non-conformed, so `seed`
  emits these as manual instructions by design.

## Known leftovers for the owner

- A stray **Project** named `spec-kit / Features` (distinct from the Shared
  View of the same name) was created manually during view setup and carries
  the `spec-kit` label. It has no bridge marker, so reconcile ignores it, but
  it appears in the Features view. The extension never deletes; removal is a
  human action.
- The default `All issues` view was shared unintentionally and can be
  unshared.
- Issues were created in the team default state (`Backlog`) because the
  optional `lifecycle` config section is not set; completed `[x]` state in
  `tasks.md` will sync once `lifecycle.completed_state_id`/`open_state_id`
  are configured.

## Acceptance criteria of Etapa 3 (contract §Etapas de implementación)

- Dry-run reviewed: yes (both seed and push plans reviewed before apply).
- Human authorization: yes, explicit, per apply.
- Remote acceptance in the authorized workspace: yes.
- Second run with zero writes: yes (seed and push).
- No forbidden operations: yes — only allowlisted creates were issued.

## Addendum — v0.3.0 re-acceptance (2026-08-03)

Run with the pruned surface (five commands, no milestones, no persisted-plan
protocol) against the same authorized workspace: `push --feature 001
--dry-run` planned 10 `issue.update`, `--apply` executed all 10, and a second
dry-run planned 0 operations. Existing issues were matched by identity; no
creates, and no milestone mutation is admissible any longer.
