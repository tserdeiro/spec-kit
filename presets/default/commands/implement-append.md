
## Task delivery loop (tserdeiro/spec-kit)

This distribution delivers **one branch and one draft PR per task**. As you
implement, wrap every task in this loop:

**Orchestrate when your host can.** If your host supports delegating to
sub-agents (Claude Code's Task tool, OpenCode agents, or equivalent), run
this loop as an orchestrator: implement each task in a **fresh sub-agent**,
so no context carries one task's residue into the next, and keep for
yourself only what the loop needs — state derivation, branches, commits,
and the conversation with the human. Everything a sub-agent needs (spec,
plan, tasks, checkboxes, branches, PRs) is observable from the repository,
so hand it pointers, never your conversation. Without that capability, run
the loop yourself as written.

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
1. **Starting a task** — before touching any code for `T###`:
   - On the **first task of the feature**, bring the repository's
     up-to-date default branch into the feature branch (`NNN-slug`):
     `git fetch`, then on the feature branch
     `git merge origin/<default>` — resolve the default branch with
     `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` —
     and push. Later refreshes from the default branch are the
     developer's duty, not this loop's.
   - Create the task branch **from the up-to-date feature branch** — or
     from the previous task's branch when this task stacks:
     `git switch -c NNN-T###-short-slug`.
   - **The stack is derived, never invented**: when the task or the
     plan's `## Documentation` section defines stack or documentation
     links, they rule. Otherwise read the real manifests
     (`package.json`, lockfiles, etc.) and the neighboring code, and
     reuse what is installed. Never add a dependency and never
     reimplement what an installed library already covers — both are
     human decisions to ask for. An API you are not certain of is
     verified against the linked or official documentation before use,
     never guessed.
   The branch is what projects the task to *In Progress* in Linear.
2. **Finishing a task** — run `/speckit.pr`: it guarantees the branch
   invariant and opens the draft PR with the canonical body. Self-review
   with `/speckit.code-review`, fix what it finds, then mark the PR
   `ready for review`.
3. **Between tasks** — `/speckit.linear.status` shows every task's derived
   state and its suggested next action. A task is finished when a human
   merged its PR and its checkbox records the completion evidence.
4. **Closing the feature** — when every task is checked with its
   completion evidence, mark the **feature PR** (the draft opened when
   the product phase closed) `ready for review`: it now shows the whole
   feature, composed of task PRs a human already reviewed one by one.
   Approving and merging are never yours — a human merges it into the
   default branch with a **merge commit** (no squash: the task history
   must survive). After that merge, delete your local feature branch
   (GitHub deletes the remote when the repository auto-deletes merged
   branches) and reconcile with `/speckit.linear.push --apply`.
