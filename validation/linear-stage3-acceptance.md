# Stage 3 acceptance — one feature through the seven vision steps

**Status: PERFORMED. Date: 2026-08-04.** Synthetic feature
`002-retry-hardening` (two tasks) in a consumer clone of
`tserdeiro/code-review-test`, bound to the authorized Wortise workspace,
driven end-to-end with `spec-kit-linear` 0.4.0 deriving every state from
observable reality (checkbox, `NNN-T###` branch, `gh pr list`).

| Vision step | Real action | Linear (verified live) |
| --- | --- | --- |
| 2–3 plan/tasks | `push --apply` | Project + WOR-28/WOR-29 in **Todo** |
| 4 implement | branch `002-T001-retry-pass` | WOR-28 → **In Progress** (source: branch) |
| 5 draft PR | PR #2 opened as draft | **In Progress** (source: pr), 0 spurious ops |
| 6 self-review + ready | `/speckit.code-review` found the planted blocking defect; `gh pr ready` | derived `review`; **In Review** once the team state existed (before that, the designed degradation kept In Progress with a warning) |
| 7 final review + merge | reviewer's review published (API-verified, anchored); human-ordered squash merge | WOR-28 → **Done** (source: pr) |

A second `push --dry-run` after every transition planned 0 operations.
The `In Review` team state was created by the owner mid-acceptance;
`onboard` resolved it on re-run and the ready PR projected to it with one
`issue.lifecycle.update`.

Defect found during the run (tracked separately): closing a review that
published leaves its temporary worktree registered; a close without
`--publish` withdraws it.
