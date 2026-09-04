
## Task delivery loop (tserdeiro/spec-kit)

This distribution delivers **one branch and one draft PR per task**, and
this loop is its delivery contract: **where the core rules above differ,
this loop wins.** Wrap every task in it as you implement:

**Hooks are acted on, never announced.** Wherever the core text above
says to print an "Optional Hook" / "Optional Pre-Hook" block, print
nothing. An optional hook whose own extension configuration enables its
event (check under `.specify/extensions/<extension>/`) runs silently;
every other optional hook is skipped silently. Mandatory hooks behave
exactly as the core text says.

**Orchestrate when your host can.** If your host supports delegating to
sub-agents (Claude Code's Task tool, OpenCode agents, or equivalent), run
this loop as an orchestrator: implement each task in a **fresh sub-agent**,
so no context carries one task's residue into the next, and keep for
yourself only what the loop needs — state derivation, branches, commits,
and the conversation with the human. Everything a sub-agent needs (spec,
plan, tasks, checkboxes, branches, PRs) is observable from the repository,
so hand it pointers, never your conversation. Without that capability, run
the loop yourself as written.

**One task at a time.** Task lists here carry no `[P]` markers and no
task ever runs in parallel. Exactly one task is in flight: one branch,
one sub-agent, one draft PR. The next task starts only once the current
one is `ready for review` (step 2). Tasks other developers deliver on
their own branches are not this loop's concern.

0. **Feature selection** — if the user named a feature in the command
   (`/speckit.implement 003` or `003-checkout-flow`), resolve it to
   exactly one `specs/<dir>/` directory (a unique prefix is enough; if it
   is ambiguous or matches nothing, stop and list the candidates) and
   `export SPECIFY_FEATURE_DIRECTORY=specs/<dir>` in every shell where
   you run this feature's scripts. Upstream persists that choice to
   `.specify/feature.json` — per-checkout local state the CLI keeps
   gitignored — so later runs without an argument continue it. Without
   an argument, the active feature applies as-is.
   Then verify the **feature gate** — the draft feature PR on the
   feature branch (`NNN-slug`), the spec-review gate a human merge
   later closes — with `gh pr view <feature-branch> --json
   url,isDraft,state 2>/dev/null`. Only an OPEN pull request counts.
   When none exists, execute the `/speckit.pr` routine's
   **feature-PR variant** — from the feature branch, with the
   feature's artifacts committed — before the first task: it opens
   the canonical draft gate, and the loop continues. When it is
   open, report its URL and never open another. When it is CLOSED
   or MERGED, stop and tell the human — a closed gate is a
   decision, not a gap. The gate is where a human approves the spec
   and plan; the loop never delivers a task against a feature with
   no gate open.
   Then fix this run's **tooling set** once, from the feature branch —
   `[ -d .specify/extensions/linear ]` and `[ -d
   .specify/extensions/code-review ]` — and report it in one line, for
   example `Tooling: linear, code-review` or `Tooling: none —
   reconciliation omitted, reviews by diff`. Every `/speckit.linear.push`
   call in this loop, `--hook` or `--apply`, runs only when `linear` is
   in the set and is silently omitted otherwise. A task never installs or
   removes an extension — that is a trunk chore, never a feature task.
   When `linear` is in the set, reconcile once with
   `/speckit.linear.push --hook`
   (when slash commands are unavailable, agents run
   `bash .specify/extensions/linear/scripts/bash/run.sh push --current
   --hook`): it catches state changes that happened while no session
   ran — overnight merges — applies without asking under the
   extension's lifecycle gates, and is a silent clean no-op when Linear
   is not configured. A reconcile failure is reported once and never
   blocks delivery — tracking waits for the next run.
1. **Starting a task** — before touching any code for `T###`:
   - On the **first task of the feature**, bring the repository's
     up-to-date delivery base into the feature branch (`NNN-slug`) with
     this single shell invocation:

     ```bash
     # first-task-refresh:start
     set -e
     current_branch=$(git branch --show-current)
     paths=$(bash .specify/scripts/bash/check-prerequisites.sh --paths-only)
     feature_branch=$(printf '%s\n' "$paths" | sed -n 's/^BRANCH: //p')
     [ "$current_branch" = "$feature_branch" ] ||
       { printf 'error: expected feature branch %s, found %s\n' \
         "$feature_branch" "$current_branch" >&2; exit 2; }
     trunk=$(sed -nE '/^trunk:/{s/^trunk:[[:space:]]*["'"'"']?([^"'"'"'#[:space:]]*)["'"'"']?.*$/\1/p;q;}' \
       .specify/extensions/git/git-config.yml 2>/dev/null || true)
     delivery_base=${trunk:-$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)}
     git check-ref-format --branch "$delivery_base" >/dev/null
     remote=origin
     git fetch "$remote"
     git merge "$remote/$delivery_base"
     git push "$remote" "$feature_branch"
     # first-task-refresh:end
     ```

     The delivery base resolves the same way `speckit.pr`'s feature PR
     does (see there for the exact rule). Do not run this refresh on
     later tasks; later delivery-base refreshes are the developer's duty.
   - Create the task branch **from the top of the open task stack**: run
     the block below, replacing only the `task_branch` literal (`pr.md`'s
     `pr-create` block replaces its own literal the same way). It
     resolves the feature branch, reads this feature's open, non-draft
     task PRs, and switches `task_branch` onto the one none of them uses
     as a base — or onto the feature branch when none is open, including
     when the human merged the stack root-first between tasks. A draft
     task PR means one is still in flight and stops the loop; two heads
     with nothing stacked on either is two stacks and also stops the
     loop. **Depends on** documents delivery order; it never chooses the
     base. Name the base the block prints in the PR body's `Stack:` line.

     ```bash
     # task-base:start
     set -e
     task_branch="<NNN-T###-short-slug>"
     paths=$(bash .specify/scripts/bash/check-prerequisites.sh --paths-only)
     feature_branch=$(printf '%s\n' "$paths" | sed -n 's/^BRANCH: //p')
     feature_number=${feature_branch##*/}
     feature_number=${feature_number%%-*}
     prs=$(mktemp)
     gh pr list --state open --limit 100 --json headRefName,baseRefName,isDraft \
       --jq ".[] | select(.headRefName | startswith(\"$feature_number-T\")) | \"\(.headRefName) \(.baseRefName) \(.isDraft)\"" \
       > "$prs"
     draft=$(awk '$3 == "true" { print $1 }' "$prs")
     [ -z "$draft" ] ||
       { printf 'error: draft task PR still open: %s\n' "$draft" >&2; exit 2; }
     tops=$(awk '{ head[$1]=1; used[$2]=1 } END { for (h in head) if (!(h in used)) print h }' "$prs")
     top_count=$(printf '%s\n' "$tops" | grep -c .) || true
     if [ "$top_count" -gt 1 ]; then
       printf 'error: two open task stacks: %s\n' "$tops" >&2
       exit 2
     elif [ "$top_count" -eq 1 ]; then
       base="$tops"
     else
       base="$feature_branch"
     fi
     git fetch origin
     git switch -c "$task_branch" "origin/$base"
     printf 'base=%s\n' "$base"
     # task-base:end
     ```
   - **The stack is derived, never invented**: when the task or the
     plan's `## Documentation` section defines stack or documentation
     links, they rule. Otherwise read the real manifests
     (`package.json`, lockfiles, etc.) and the neighboring code, and
     reuse what is installed. Never add a dependency and never
     reimplement what an installed library already covers — both are
     human decisions to ask for. An API you are not certain of is
     verified against the linked or official documentation before use,
     never guessed.
   The branch is what projects the task to *In Progress* in Linear —
   once it exists and `linear` is in the set, reconcile with
   `/speckit.linear.push --hook`.
2. **Finishing a task** — before opening the PR, run the **budget
   stop**: replacing only the `task_id` and `base` literals (`base` is
   what `task-base` printed), it reads the forecast from the task's
   `Delivery` line (`~N authored lines`; absent defaults to 400), sums
   the added lines of `git diff --numstat <base>...HEAD` over the files
   the review budget counts, and stops at the smaller of twice the
   forecast and 400.

   ```bash
   # budget-stop:start
   set -e
   task_id="<T###>"
   base="<the base the task-base block printed>"
   paths=$(bash .specify/scripts/bash/check-prerequisites.sh --paths-only)
   tasks_file=$(printf '%s\n' "$paths" | sed -n 's/^FEATURE_DIR: //p')/tasks.md
   forecast=$(awk -v id="$task_id" '
     in_fence {
       i=0; while (substr($0,i+1,1)==" ") i++
       c=substr($0,i+1); sub(/[ \t]+$/, "", c)
       ok=(i<=3 && length(c)>=mlen)
       if (ok) for (j=1;j<=length(c);j++) if (substr(c,j,1)!=marker) { ok=0; break }
       if (ok) in_fence=0
       next
     }
     {
       i=0; while (substr($0,i+1,1)==" ") i++
       r=substr($0,i+1); ch=substr(r,1,1)
       if (i<=3 && (ch=="`" || ch=="~")) {
         n=0; while (substr(r,n+1,1)==ch) n++
         if (n>=3 && (ch!="`" || !index(substr(r,n+1),"`"))) { in_fence=1; marker=ch; mlen=n; next }
       }
       if (header) {
         if ($0 ~ /^- \[[ xX]\] T[0-9][0-9][0-9]/) exit
         if (/\*\*Delivery\*\*:/) {
           if (match($0, /~[0-9]+/)) print substr($0, RSTART + 1, RLENGTH - 1)
           exit
         }
       }
       if ($0 ~ "^- \\[[ xX]\\] " id " ") header = 1
     }
   ' "$tasks_file")
   [ -n "$forecast" ] || forecast=400
   numstat=$(mktemp)
   git diff --numstat "$base...HEAD" > "$numstat"
   listing=$(mktemp)
   added=$(awk -v listing="$listing" '
     {
       lines = $1; path = $3
       if (lines == "-" || $2 == "-") next
       n = split(path, parts, "/"); name = parts[n]
       if (name == "uv.lock" || name == "package-lock.json" || name == "poetry.lock" || name == "Cargo.lock") next
       m = split(name, nparts, "."); suffix = ""
       if (m > 1) suffix = tolower("." nparts[m])
       if (suffix == ".md" || suffix == ".rst" || suffix == ".txt" || suffix == ".lock" ||
           suffix == ".svg" || suffix == ".png" || suffix == ".jpg" || suffix == ".jpeg" ||
           suffix == ".gif" || suffix == ".ico" || suffix == ".pdf") next
       sum += lines
       print lines, path > listing
     }
     END { print sum + 0 }
   ' "$numstat")
   stop=$((2 * forecast))
   [ "$stop" -le 400 ] || stop=400
   if [ "$added" -gt "$stop" ]; then
     printf 'error: %s added %d lines against a stop of %d (forecast ~%d)\n' \
       "$task_id" "$added" "$stop" "$forecast" >&2
     sort -rn "$listing" | head -n 10 >&2
     exit 2
   fi
   printf 'budget: %d/%d (forecast ~%d)\n' "$added" "$stop" "$forecast"
   # budget-stop:end
   ```

   The loop runs this again before marking the PR `ready for review`, in
   case the branch grew during the review. On a stop, the task returns
   to the human with the diagnosis above — what does not fit and a
   proposed split — and no PR opens as-is. **A forecast or budget is
   never amended in the PR that exceeds it**: a human changes it in the
   ledger, on the feature branch, outside that PR.

   Run `/speckit.pr`: it guarantees the branch invariant and opens the
   draft PR with the canonical body. Self-review it next: the fresh
   reviewer's brief is fixed text, the packet path (or the diff and PR
   body, below) prepended:

   > Verify the implementer's claims in the packet's evidence instead of
   > repeating its experiments. Before asking for an edge case, ask
   > whether the mechanism is needed at all — a simpler design that meets
   > the requirement is a `major` finding, a new runtime dependency is
   > `blocking`, per the repository's review rules. A packet over 100 KB
   > (`wc -c`) is reviewed one file at a time, findings consolidated at
   > the end. Write `findings.json` inside the review session directory
   > when there is one; otherwise, return the findings directly to the
   > orchestrator.

   - **With `code-review` in the set**, review it with
     `/speckit.code-review <PR number>` — only the PR form opens a
     review session — orchestrated like the tasks: on hosts with
     sub-agents, open the review session but neither read the packet nor
     write the findings yourself — hand the packet path and the brief,
     nothing else, to a **fresh sub-agent** with no implementation
     residue, which reads the packet in full, reviews the candidate, and
     writes `findings.json` **inside the review session directory**;
     close the review with that file. Without sub-agents, run the review
     yourself — findings still written inside the session directory,
     fresh per review, never copied from an earlier one.
   - **Without `code-review`**, hand a fresh sub-agent (or, without one,
     a fresh context) the PR's diff and body — `gh pr diff <n>` and
     `gh pr view <n>` — and the brief, nothing else carried over. It
     returns its findings; post them as one PR comment
     (`gh pr comment <n>`) — no session, no verdict, the degraded
     mode — and name that comment in the Completion evidence.
   That independence is what makes the verdict worth anything: a reused
   findings file is not a review. Fix what it finds on the task branch,
   whichever path produced it.

   **Carrying a fix through the stack.** Whenever a commit lands on
   a task branch that has open task PRs stacked on it — a review fix
   on an earlier task, a reviewer's comment fixed later — run the
   block below from that branch, replacing only the `fixed_branch`
   literal. It reads this feature's open task PRs (the same query as
   `task-base`) and walks the chain upward: the PR whose base is
   `fixed_branch`, then the PR whose base is that head, and so on —
   one linear stack, each `T###` read from the branch's `NNN-T###-`
   prefix with `sed`. For every branch in that order it runs
   `git switch`, `git merge --no-ff -m "merge(task): carry the <T###
   of fixed_branch> fix into <T### of that branch>" <previous
   branch>`, then `git push origin <branch>`. A merge failure runs
   `git merge --abort`, prints the branch it stopped at, and exits 2
   without touching the branches above it; an empty chain prints
   that nothing is stacked and exits 0. Once every stacked branch is
   merged and pushed, it switches back to `fixed_branch`. No
   rewrite, no rebase, no force — merge commits only, the subject
   form the conventions check accepts.

   ```bash
   # stack-propagate:start
   set -e
   fixed_branch="<NNN-T###-short-slug>"
   feature_number=${fixed_branch%%-*}
   prs=$(mktemp)
   gh pr list --state open --limit 100 --json headRefName,baseRefName,isDraft \
     --jq ".[] | select(.headRefName | startswith(\"$feature_number-T\")) | \"\(.headRefName) \(.baseRefName) \(.isDraft)\"" \
     > "$prs"
   fixed_task=$(printf '%s\n' "$fixed_branch" | sed -nE 's/^[0-9]+-(T[0-9]{3})-.*/\1/p')
   previous="$fixed_branch"
   current=$(awk -v base="$fixed_branch" '$2 == base { print $1; exit }' "$prs")
   if [ -z "$current" ]; then
     printf 'nothing stacked on %s\n' "$fixed_branch"
     exit 0
   fi
   while [ -n "$current" ]; do
     current_task=$(printf '%s\n' "$current" | sed -nE 's/^[0-9]+-(T[0-9]{3})-.*/\1/p')
     git switch "$current"
     if ! git merge --no-ff -m "merge(task): carry the $fixed_task fix into $current_task" "$previous"; then
       git merge --abort || true
       printf 'error: merge conflict carrying the fix into %s\n' "$current" >&2
       exit 2
     fi
     git push origin "$current"
     previous="$current"
     current=$(awk -v base="$previous" '$2 == base { print $1; exit }' "$prs")
   done
   git switch "$fixed_branch"
   # stack-propagate:end
   ```

   Then, in the PR's **final commit**, check
   the task's box and fill its **Completion evidence** (the PR and the
   verification results; a task split into stacked PRs checks it in the
   stack's last PR), push, and mark the PR `ready for review`, then, when
   `linear` is in the set, reconcile with `/speckit.linear.push --hook`
   so the issue shows its review state. The checked box travels inside
   the task PR, so it reaches the feature branch only through the human
   merge; reviewer comments are fixed on this same PR, the box stays
   checked. Ready for review is what frees you to start the next task
   (step 1).
3. **Between tasks** — a task is finished when a human merged its PR:
   the merge is what lands its checked box and evidence on the feature
   branch, so there `[x]` means merged, by construction.
   `/speckit.linear.status` shows every task's derived state and its
   suggested next action (an open PR outranks the checkbox in the
   projection, so a task in review never reads as done).

   **The loop never merges.** A run ends with every task PR `ready for
   review` and its fresh review closed; merging is the human's
   decision, made **root-first** — the first PR of the stack into the
   feature branch, then the next — because retargeting the PR above is
   GitHub's `edited` event, which re-runs no tests or conformance (only
   the naming check listens to it), while merging leaf-first
   synchronizes every open PR still stacked below and re-runs every
   check at every step.
   Only when the human explicitly asks the agent to merge, in the
   conversation, does it act: `git worktree prune` first — a stale
   worktree blocks branch deletion — then `gh pr merge <n> --merge
   --delete-branch` for each PR, root-first; then, when `linear` is in
   the set, reconcile with `/speckit.linear.push --apply`.
4. **Closing the feature** — when every box on the feature branch is
   checked — every task PR merged — mark the **feature PR** (the draft
   gate, whether the product phase or step 0 opened it)
   `ready for review`: it now shows the whole
   feature, composed of task PRs a human already reviewed one by one.
   Approving and merging are never yours — a human merges it into the
   delivery base with a **merge commit** (no squash: the task history
   must survive). After that merge, run `git worktree prune` — a stale
   worktree blocks branch deletion — then delete your local feature
   branch (GitHub deletes the remote when the repository auto-deletes
   merged branches); when `linear` is in the set, reconcile with
   `/speckit.linear.push --apply`.

**Reverting a delivered task.** Undoing a delivered change is a ledger
task the human adds, delivered through this loop like any other: its
own branch, PR, fresh review, and `ready for review`. Its commit is
never the tool's default subject, which fails the conventions check:
run `git revert --no-commit <sha>` (`-m 1` for a merge), then commit it
yourself with `git commit -m "revert(scope): <subject>"`.
