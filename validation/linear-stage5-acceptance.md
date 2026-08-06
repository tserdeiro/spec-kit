# Stage 5 acceptance — the bug short path, live

**Status: PERFORMED. Date: 2026-08-04.** A real bug (the double-applied
retry that `/speckit.code-review` flagged on PR #2 and Stage 3 merged
knowingly) driven through the vision's short path with `spec-kit-linear`
0.5.0 against the authorized workspace:

| Short-path step | Real action | WOR-30 (verified live) |
| --- | --- | --- |
| Issue born in Linear | created by the operator via the API | Todo |
| Issue-key branch | `wor-30-retry-double-run` | **In Progress** (source: branch) |
| Triage trio + fix | `.specify/bugs/retry-double-run/{assessment,fix,test}.md` + the fix | — |
| Draft PR | #3, evidence in the body | In Progress (source: pr, 0 spurious ops) |
| Self-review + ready | `no-blocking-findings — a recommendation, not an approval` | **In Review** |
| Human merge | squash ordered by the owner | **Done**; next dry-run plans 0 operations |

The batch issue lookup (`number: in` + team filter) ran against the real
Linear API for the first time and behaved as designed. Chores follow the
same path minus the triage trio (documented in `docs/guide.md`).

**Live re-verification of the published artifacts (2026-08-04):** a fresh
consumer following the guide installed `developer v1.1.0` from the live
catalogs — 5 components including the `bug` extension and `linear 0.5.0`.
