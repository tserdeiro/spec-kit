
## Task delivery loop (tserdeiro/spec-kit)

This distribution delivers **one branch and one draft PR per task**, and
this loop is its delivery contract: **where the core rules above differ,
this loop wins.** Wrap every task in it as you implement:

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
1. **Starting a task** — before touching any code for `T###`:
   - On the **first task of the feature**, bring the repository's
     up-to-date delivery base into the feature branch (`NNN-slug`) with
     this single shell invocation:

     ```bash
     # first-task-refresh:start
     # delivery-base-resolution:start
     trunk_config=.specify/extensions/git/git-config.yml
     trunk_error() {
       printf 'error: invalid trunk in %s: %s\n' "$trunk_config" "$1" >&2
       exit 2
     }
     trunk_raw=$(awk '/^trunk:([[:space:]]|$)/ { sub(/^trunk:[[:space:]]*/, ""); sub(/[[:space:]]*$/, ""); print; exit }' \
       "$trunk_config" 2>/dev/null || true)
     trunk_quoted=false
     case "$trunk_raw" in
       \"*) trunk_quote='"'; trunk_quoted=true ;;
       \'*) trunk_quote="'"; trunk_quoted=true ;;
     esac
     if [ "$trunk_quoted" = true ]; then
       delivery_base=$(printf '%s\n' "$trunk_raw" | awk -v quote="$trunk_quote" '
         {
           line=substr($0, 2); closing=index(line, quote)
           if (closing == 0) exit 1
           value=substr(line, 1, closing - 1); tail=substr(line, closing + 1)
           if (tail !~ /^[[:space:]]*$/ && tail !~ /^[[:space:]]+#/) exit 1
           print value; valid=1
         }
         END { if (!valid) exit 1 }
       ') || trunk_error 'quotes must match and enclose one simple string'
     else
       delivery_base=$(printf '%s\n' "$trunk_raw" | sed 's/^#.*$//; s/[[:space:]][[:space:]]*#.*$//; s/[[:space:]]*$//')
       case "$delivery_base" in
         *\\*) trunk_error 'escapes are not supported' ;;
         *\"*|*\'*) trunk_error 'quotes must match and enclose the whole value' ;;
       esac
       case "$delivery_base" in
         "") ;;
         null|Null|NULL|\~) delivery_base="" ;;
         [Tt][Rr][Uu][Ee]|[Ff][Aa][Ll][Ss][Ee]|[Yy][Ee][Ss]|[Nn][Oo]|[Oo][Nn]|[Oo][Ff][Ff]|[Yy]|[Nn])
           trunk_error 'plain YAML booleans are not branch-name strings' ;;
         \!*|\&*|\**|\|*|\>*|\[*|\{*) trunk_error 'YAML tags, anchors, aliases, block, and flow values are not supported' ;;
         *[[:space:]]*) trunk_error 'the value must be one simple branch-name string' ;;
         [A-Za-z_]*) ;;
         *) trunk_error 'unquoted branch names must start with an ASCII letter or underscore; quote numeric-looking names' ;;
       esac
     fi
     case "$delivery_base" in
       *[!A-Za-z0-9._/-]*) trunk_error 'branch names may contain only ASCII letters, digits, dot, underscore, slash, and hyphen' ;;
     esac
     if [ -n "$delivery_base" ] && ! git check-ref-format --branch "$delivery_base" >/dev/null 2>&1; then
       trunk_error "'$delivery_base' is not a valid branch name"
     fi
     if [ -z "$delivery_base" ]; then
       delivery_base=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
     fi
     # delivery-base-resolution:end
     git fetch
     git merge "origin/$delivery_base"
     git push
     # first-task-refresh:end
     ```

     An explicit non-empty `trunk:` wins; otherwise the GitHub default
     applies. Do not run this refresh on later tasks; later delivery-base
     refreshes are the developer's duty.
   - Create the task branch **from the up-to-date feature branch**:
     `git switch -c NNN-T###-short-slug`. One exception stacks: when the
     task's **Depends on** names a task whose PR is not merged yet,
     branch from that task's branch instead and name it in the PR body's
     `Stack:` line — never wait idle for that merge; when it lands,
     GitHub retargets the stacked PR to the feature branch by itself.
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
   with `/speckit.code-review` and fix what it finds. Then, in the PR's
   **final commit**, check the task's box and fill its **Completion
   evidence** (the PR and the verification results; a task split into
   stacked PRs checks it in the stack's last PR), push, and mark the PR
   `ready for review`. The checked box travels inside the task PR, so it
   reaches the feature branch only through the human merge; reviewer
   comments are fixed on this same PR, the box stays checked. Ready for
   review is what frees you to start the next task (step 1).
3. **Between tasks** — a task is finished when a human merged its PR:
   the merge is what lands its checked box and evidence on the feature
   branch, so there `[x]` means merged, by construction.
   `/speckit.linear.status` shows every task's derived state and its
   suggested next action (an open PR outranks the checkbox in the
   projection, so a task in review never reads as done).
4. **Closing the feature** — when every box on the feature branch is
   checked — every task PR merged — mark the **feature PR** (the draft
   opened when the product phase closed) `ready for review`: it now
   shows the whole
   feature, composed of task PRs a human already reviewed one by one.
   Approving and merging are never yours — a human merges it into the
   delivery base with a **merge commit** (no squash: the task history
   must survive). After that merge, delete your local feature branch
   (GitHub deletes the remote when the repository auto-deletes merged
   branches) and reconcile with `/speckit.linear.push --apply`.
