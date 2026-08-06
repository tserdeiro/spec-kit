
## Task delivery loop (tserdeiro/spec-kit)

This distribution delivers **one branch and one draft PR per task**. As you
implement, wrap every task in this loop:

1. **Starting a task** — before touching any code for `T###`, create its
   branch from an up-to-date `main`: `git switch -c NNN-T###-short-slug`.
   The branch is what projects the task to *In Progress* in Linear.
2. **Finishing a task** — run `/speckit.pr`: it guarantees the branch
   invariant and opens the draft PR with the canonical body. Self-review
   with `/speckit.code-review`, fix what it finds, then mark the PR
   `ready for review`.
3. **Between tasks** — `/speckit.linear.status` shows every task's derived
   state and its suggested next action. A task is finished when a human
   merged its PR and its checkbox records the completion evidence.
