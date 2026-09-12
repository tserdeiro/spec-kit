
## Phase close (tserdeiro/spec-kit)

This distribution keeps every product phase as a local draft until one explicit
product approval — **where the hook and report rules above differ, these rules
win**:

- **Hooks are acted on, never announced.** Wherever the core text above
  says to print an "Optional Hook" / "Optional Pre-Hook" block, print
  nothing. A product-phase `git.commit` hook is suppressed silently in every
  configuration, including mandatory and default-enabled configurations.
  Mandatory hooks for other extensions, including Linear, behave exactly as
  the core text says. An optional non-`git.commit` hook whose own extension
  enables its event is executed silently; every other optional hook is skipped
  silently.
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
  `specs/<feature-directory>/`, verifies that no unrelated staged path is
  included, and performs the authorized commit, push, and canonical draft PR
  publication. An edit after approval requires fresh analysis and approval.
