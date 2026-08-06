
## Task delivery loop (tserdeiro/spec-kit)

This distribution delivers **one branch and one draft PR per task**. As you
implement, wrap every task in this loop:

0. **Feature selection** — if the user named a feature in the command
   (`/speckit.implement 003` or `003-checkout-flow`), resolve it to
   exactly one `specs/<dir>/` directory (a unique prefix is enough; if it
   is ambiguous or matches nothing, stop and list the candidates) and
   `export SPECIFY_FEATURE_DIRECTORY=specs/<dir>` in every shell where
   you run this feature's scripts. Upstream persists that choice to
   `.specify/feature.json`, making it the locally active feature — later
   runs without an argument continue it. That persisted change is local
   convenience: **never include `.specify/feature.json` in a task
   commit**. Without an argument, the active feature applies as-is.
1. **Starting a task** — before touching any code for `T###`, create its
   branch from the repository's up-to-date **default branch** — resolve it
   with `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` —
   or from the previous PR's branch when this task stacks:
   `git switch -c NNN-T###-short-slug`.
   The branch is what projects the task to *In Progress* in Linear.
2. **Finishing a task** — run `/speckit.pr`: it guarantees the branch
   invariant and opens the draft PR with the canonical body. Self-review
   with `/speckit.code-review`, fix what it finds, then mark the PR
   `ready for review`.
3. **Between tasks** — `/speckit.linear.status` shows every task's derived
   state and its suggested next action. A task is finished when a human
   merged its PR and its checkbox records the completion evidence.
