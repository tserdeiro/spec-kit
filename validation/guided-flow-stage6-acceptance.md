# Stage 6 acceptance — the guided flow, dogfooded

**Status: PERFORMED. Dates: 2026-08-06.** The first feature delivered
through the product's own seven-step workflow, one task per point, one
branch and one human-merged PR each (PRs #1, #3, #4, #5, #6), every state
visible in Linear (WOR-18..22), every PR self-reviewed before ready.

| Point | Delivered | Dogfood proof |
| --- | --- | --- |
| 6.1 branch at task start | PR #1 | every later task branched first |
| 6.2 `/speckit.pr` | PR #4 | its own PR was opened by following the command verbatim |
| 6.3 `NEXT` column | PR #3 | guided every subsequent hand-off ("await the final review…") |
| 6.4 `/speckit.doctor` | PR #5 | remediations surfaced verbatim in a live consumer |
| 6.5 `publish.sh` | PR #6 | one invocation released this very feature (linear 0.2.0, code-review 0.1.1, bundles 0.2.0); second dry-run reports nothing pending |

The flow also caught and fixed one of its own bugs mid-delivery through
the bug short path: WOR-31 (`.specify/bugs/session-root-redaction/`,
PR #2) — phase 2 of the review refused every session in a repository
under the home directory. Frictions recorded for future work: the
upstream `before_specify` hook prefers feature branches over our
task branches; workspace Issues are adopted by feature-number identity
across repository rebirths; the preset still carries the legacy
"Product handoff" template section.

Live re-verification: a fresh consumer installed `developer v0.2.0` from
the published catalogs — 5 components, `speckit-pr` and `speckit-doctor`
registered as agent skills.
