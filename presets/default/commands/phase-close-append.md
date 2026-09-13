
## Phase close (tserdeiro/spec-kit)

This distribution keeps every product phase as a local draft until one explicit
product approval — **where the hook and report rules above differ, these rules
win**:

- **Hooks are acted on, never announced.** Wherever the core text above
  says to print an "Optional Hook" / "Optional Pre-Hook" block, print
  nothing. A product-phase `git.commit` hook is suppressed silently in every
  configuration, including mandatory and default-enabled configurations.
  Mandatory hooks for other extensions, including Linear, behave exactly as
  the core text says. Optional non-`git.commit` hooks are skipped silently.
- **The resolved template rules the phase's own sections and files** —
  only what the resolved template defines, at the density of the
  precedent, never a heavier structure the core text's own generic
  example might suggest.
- **The phase remains local.** After this command's own report, leave the
  active feature artifacts in the worktree. Do not stage, commit, push, or
  create or update a feature PR from a product phase. This includes
  `specify`, `clarify`, `plan`, and `analyze`; analysis itself is read-only.
- **Approved closure is separate.** After clean analysis, present the exact
  spec, plan, tasks, analysis result, and unresolved handoff prerequisites.
  Wait for explicit human approval of those concrete artifacts. Only after
  that decision, invoke the feature variant of `/speckit.pr`; it stages only
  `specs/<feature-directory>/`, uses `git commit --only` so unrelated staged
  content remains outside the commit, and performs the authorized commit,
  push, and canonical draft PR publication. The PR command observes the local
  head, remote head, and existing PR before each write, reuses only an OPEN
  gate, and reads back an ambiguous commit, push, create, or body update before
  retrying it. An edit after approval that changes material product scope, acceptance,
  plan decisions, task definitions, or stable IDs requires fresh analysis and
  approval; completion checkboxes and completion evidence alone preserve the
  approved handoff.
- **Handoff status remains honest.** After publication, use the existing Linear
  preview/apply/status commands and report synchronization and native task
  assignments as prerequisites. An incomplete projection or unassigned task
  keeps development pending. Technical approval of the plan and tasks is
  separate from permission to publish, and this close never assigns users or
  invents readiness.
