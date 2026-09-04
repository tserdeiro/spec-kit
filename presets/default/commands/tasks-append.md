
## One task at a time (tserdeiro/spec-kit)

This distribution delivers tasks strictly one at a time, one branch and
one draft PR each — **where the core guidance above differs, this rule
wins**: emit no `[P]` markers and no parallel-execution examples. Order
every task by its dependencies alone (`Depends on`), so the list reads
as the sequence one developer follows. Who takes which task is decided
by assignment in Linear, never by markers in this file.

Tasks form one chain in file order: **Depends on** documents that order
and never chooses the base — delivery always stacks the next task on the
open, ready task PR, or starts from the feature branch when none is
open, so the ledger accumulates every checked box on one stack.

## Phase close (tserdeiro/spec-kit)

This distribution closes every product phase silent and committed —
**where the hook and report rules above differ, these rules win**:

- **Hooks are acted on, never announced.** Wherever the core text above
  says to print an "Optional Hook" / "Optional Pre-Hook" block, print
  nothing. An optional hook whose own extension configuration enables its
  event (check under `.specify/extensions/<extension>/`) is executed
  silently; every other optional hook is skipped silently. Mandatory
  hooks behave exactly as the core text says.
- **The phase ends committed.** After this command's own report, commit
  the feature's artifacts: stage only `specs/<feature-directory>/` — the
  active feature's directory, never anything outside it, however dirty
  the rest of the tree is — and commit with a `type(scope): subject`
  message in English naming the phase's artifact (e.g.
  `docs(specs): <feature> — implementation plan`). When those paths hold
  no changes, skip the commit silently. No reminders and no announcement
  beyond the commit appearing in the report's evidence, if this command
  reports any.
