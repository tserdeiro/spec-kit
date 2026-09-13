---
description: Execute the task delivery loop — one branch and one draft pull request per task, scripted end to end.
scripts:
  sh: scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
  ps: scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
  py: scripts/python/check_prerequisites.py --json --require-tasks --include-tasks
---

# Spec Kit Implement

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Setup

1. If the user named a feature (`/speckit.implement 003` or `003-checkout-flow`), resolve it to exactly one `specs/<dir>/` directory (a unique prefix is enough; stop and list the candidates if it is ambiguous or matches nothing) and `export SPECIFY_FEATURE_DIRECTORY=specs/<dir>` in every shell where this feature's scripts run. Upstream persists that choice to `.specify/feature.json`, so later runs without an argument continue it; without an argument, the active feature applies as-is.
2. Run `{SCRIPT}` from the repository root; parse `FEATURE_DIR` and `AVAILABLE_DOCS`. Every path is absolute.
3. **Checklists, read-only** — when `FEATURE_DIR/checklists/` exists, scan each file's `- [ ]`/`- [x]` counts into a table (`Checklist | Total | Checked | Unchecked | Status`). Every checklist at 0 unchecked is `PASS`; otherwise display the table and ask whether to proceed anyway — "no" or "wait" halts, "yes" or "proceed" continues. Never edit a checklist file or its markers.
4. **Locate the artifacts** — `tasks.md` and `plan.md` (required); `data-model.md`, `contracts/`, `research.md`, `quickstart.md`, and `.specify/memory/constitution.md` when present. As orchestrator (below) read only `tasks.md`; the others travel to sub-agents as paths. Without sub-agents, load them all.
5. **Published product gate, before hooks** — run the installed `scripts/python/product_gate.py` with no arguments. It must observe an OPEN feature PR whose repository, full head ref, delivery base, advertised OID, and feature artifacts are coherent across the remote tree, `HEAD`, index, and worktree. It normalizes only task checkbox and Completion evidence progress. On exit 2, report its `product close pending` action and stop before any hook, refresh, branch, task, commit, push, PR, or Linear operation. A missing, closed, stale, ambiguous, or inconsistent gate is a human handoff decision; do not create or reopen a feature PR here. After it succeeds, verify the existing feature handoff table and `/speckit.linear.status` output: clean analysis, independent human technical approval, reviewed Linear synchronization, and an explicit native assignee for every executable task. Any pending check remains blocking and stops before hooks.
6. **Hooks, silently** — read `.specify/extensions.yml`'s `hooks.before_implement` (skip entirely, silently, on a missing file, a missing key, or invalid YAML). Among entries whose `enabled` is not explicitly `false` and whose `condition` is empty (a non-empty `condition` is left to the HookExecutor): invoke a **mandatory** hook (`optional: false`) as its own slash command — dots become hyphens, e.g. `speckit.git.commit` → `/speckit-git-commit` — and wait for it before continuing; run an **optional** hook the same way, silently, only when its own extension's configuration enables its event (check under `.specify/extensions/<extension>/`); skip every other optional hook, silently. Nothing about a hook is ever printed. The same rule governs `hooks.after_implement` — see "After hooks" below.

## The delivery loop

This distribution delivers **one branch and one draft PR per task**; wrap every task in the steps below.

**One task at a time.** Task lists here carry no parallel-task marker and no task ever runs in parallel. Exactly one task is in flight: one branch, one implementer, one draft PR. The next task starts only once the current one is `ready for review` (step 2). Tasks other developers deliver on their own branches are not this loop's concern.

Run every script below with the consumer's `.venv/bin/python` when it exists, else `python3` on PATH — the rule upstream's own `py` scripts follow.

## Orchestration

When your host can delegate to sub-agents (Claude Code's Task tool, OpenCode agents, or equivalent), run this loop as an orchestrator: each task is implemented in its own sub-agent, so no context carries one task's residue into the next. Without that capability, run the loop yourself as written.

- **Working state.** Keep five facts — task id, branch, head SHA, current step, next action — and pointers: PR number, session path, packet path. Never contents.
- **Never read** packets, diffs, test logs, findings files, plan or spec bodies, or full JSON documents. Consume exit codes, the scripts' one-line results, the review command's compact JSON, and the sub-agents' return lines. What you must know about the code, a sub-agent finds out for you.
- **Implementer brief**, fixed: the task block copied verbatim from `tasks.md`; plan sections by path and heading, never pasted; files and boundaries; the task's Evidence commands; branch and base; the exit condition — evidence commands pass, changes committed with a conventional subject, ledger filled as step 2 says; the delegation budget below; and the return format: at most fifteen lines — head SHA, files changed, each evidence command with its result line, deviations or open questions. Nothing else comes back.
- **Reviewer brief**: the packet path and step 2's fixed brief. It returns one line, `findings written at <path>: N (blocking/major/minor/nit/info)`. Finding contents never reach you; the close command's `delivery` decision is what you act on.
- **Waiting.** Wait on the host's completion notification: no polling, no status message, no file read, no remote query while waiting, unless there is a new reason. A host that requires a periodic update gets one line — no new investigation, no re-sent instructions. Silence is not a block: before interrupting, check one piece of evidence once (did the branch head move, did the PR appear).
- **Delegation budget.** One attempt, plus one recovery after a diagnosed cause; the recovery brief carries only the verified progress (head SHA, what is done) and the blocker. When the recovery is spent: keep the work on the branch, report the blocker to the human, stop. Exhaustion is never success.
- **Resume from native state**, never from conversation summaries: the branch, `gh pr view`, the ledger, the session directory. Adopt what exists before doing anything; verify an uncertain remote result — a push, a PR creation, a comment — before repeating the write.
- **Effort.** Respect the user's model selection. Where the host sets effort per delegation, mechanical steps — waiting, state derivation, follow-up verification — take the lower setting; complex decisions and the final feature audit keep the higher one.
- **Communication.** Report findings, decisions and blockers. The completion report below stays as it is.

## 0. The gate

Verify the **feature gate** — the draft feature PR on the feature branch (`NNN-slug`), the spec-review gate a human merge later closes:

```bash
gh pr view <feature-branch> --json url,isDraft,state 2>/dev/null
```

Only an OPEN pull request counts. The product gate helper observes it before any hook or task mechanics. When none exists, stop with product closure pending; do not run `/speckit.pr`, create a gate, or publish artifacts from implementation. When it is CLOSED or MERGED, stop and tell the human — a closed gate is a decision, not a gap. The gate is where a human approves the spec and plan; the loop never delivers a task against a feature with no gate open.

Report the tooling once, from the feature branch: `[ -d .specify/extensions/code-review ]` decides the review path of step 2 below — `Tooling: code-review` or `Tooling: none — reviews by diff`. Linear's own state-syncing runs outside this loop — in `task_base.py`'s branch creation and, where the linear extension's session and tool-use handlers are installed, in those handlers; the loop carries no instruction for it. A task never installs or removes an extension — that is a trunk chore, never a feature task.

## 1. Starting a task

Before touching any code for `T###`:

- On the **first task of the feature**, bring the delivery base into the feature branch, once:

  ```bash
  python3 .specify/presets/default/scripts/python/task_base.py refresh
  ```

  Do not run this on later tasks; later delivery-base refreshes are the developer's duty.
- Create the task branch from the top of the open task stack:

  ```bash
  python3 .specify/presets/default/scripts/python/task_base.py task <NNN-T###-short-slug>
  ```

  It prints `base=<name>` — name it in the PR body's `Stack:` line — and projects the branch to Linear itself once it exists. A draft task PR still open, or two open stacks, stops the loop with the script's own diagnosis; **Depends on** in the ledger documents delivery order, it never chooses the base.
- **The stack is derived, never invented**: when the task or the plan's `## Documentation` section defines stack or documentation links, they rule. Otherwise read the real manifests (`package.json`, lockfiles, etc.) and the neighboring code, and reuse what is installed. Never add a dependency and never reimplement what an installed library already covers — both are human decisions to ask for. An API you are not certain of is verified against the linked or official documentation before use, never guessed.

## 2. Finishing a task

**Close the candidate.** With the implementation done and the task's Evidence commands run on the branch, check the task's box and fill its **Completion evidence** — the commands run and their result lines — **in the same commit as the last code change** (a task split into stacked PRs checks it in the stack's last PR). The checked box means "implementation finished on this branch, with its evidence"; it never means "reviewed", and the evidence never names a review, a session or a SHA it cannot know yet. Every commit that changes the candidate carries its evidence update; evidence never travels alone. Push, then the ledger gate:

```bash
python3 .specify/presets/default/scripts/python/ledger_check.py <T###>
```

It exits 2 naming exactly what's missing — the checkbox, the evidence, or both — before the PR can open.

**Open the PR.** Run `/speckit.pr`: it guarantees the branch invariant and opens the draft PR with the canonical body, or reports the one already open. Its Verification evidence table is filled from the same run as the ledger, once.

**Review the candidate.** The reviewer's brief is fixed text, the packet path (or the diff and PR body, below) prepended:

> Verify the implementer's claims in the packet's evidence instead of
> repeating its experiments. Before asking for an edge case, ask
> whether the mechanism is needed at all — a simpler design that meets
> the requirement is a `major` finding, a new runtime dependency is
> `blocking`, per the repository's review rules. Read every changed
> range of your assigned files, and the contract ranges (spec, plan,
> tasks, frozen intent) you need to judge them; return your findings and
> the reading receipts for what you read.

- **With `code-review` in the set**, review it with `/speckit.code-review <PR number>` — only the PR form opens a review session — orchestrated like the tasks: on hosts with sub-agents, open the review session but neither read the packet nor write the findings yourself. Group the packet's in-scope files into groups of at most 10 related files (same package or directory, following the packet's rule groups); a group whose changed lines exceed the packet's per-artifact byte cap splits into one group per file. Hand each group's file list, the packet path and the brief, nothing else, to that group's **reviewer** (below) — a sub-agent with no implementation residue — which reads its files' changed ranges and the contract ranges it needs, and returns its findings and receipts with the one line the Orchestration section fixes; merge every reviewer's findings and receipts into the session's single `findings.json` **inside the review session directory**, close the review with that file and act on its `delivery` decision. Without sub-agents, run the review yourself — findings still written inside the session directory, one file per session, never copied from an earlier one. After the close, record the review in the PR as one comment — session path, head, verdict, `delivery.decision` — **never a commit**.
- **Without `code-review`**, hand the task's reviewer (or, without sub-agents, a fresh context) the PR's diff and body — `gh pr diff <n>` and `gh pr view <n>` — and the brief, nothing else carried over. It returns its findings; post them as one PR comment (`gh pr comment <n>`) — no session, no verdict, the degraded mode. The ledger never names that comment. The review rounds below apply with that comment as the previous findings and "no finding left" as `proceed`.

That independence is what makes the verdict worth anything: a reused findings file is not a review. Fix what it finds on the task branch, whichever path produced it: the fix commit carries its evidence update, push, and the new candidate is reviewed as the review rounds below say. Editing the PR body or commenting never creates a candidate: the session compares head and merge base only, so a PR-body correction — a count, a wording — is free and never triggers a review.

### Review rounds

- **One reviewer per group of files**, independent of the implementer, kept for the task's whole life; a candidate that fits one group has one reviewer. Its first review covers the whole group, groups findings by mechanism and checks every path of that mechanism — normal, error, recovery, cleanup — before answering, so variants of one defect surface once.
- **Follow-up by the same reviewer.** After a fix commit, when the host can continue a sub-agent (Claude Code: message the same agent), open the new session and send the fixed follow-up brief:

  > The candidate advanced from <reviewed sha> to <head sha>; previous
  > findings: <previous session>/findings.md. Verify each previous
  > finding is fixed or say why it is still open; review the delta
  > (`git diff <reviewed sha>..<head sha>`) and its effects on the rest
  > of the candidate; write `findings.json` in <new session> with
  > coverage receipts for the new head and the envelope of the new
  > session (its `candidate_id`, `packet_sha256`, `inventory_sha256`).
  > A range whose bytes did not change keeps the digest you already
  > computed, with the new head as its version; re-read every range the
  > delta touched.

  When the host cannot continue an agent, a fresh reviewer gets the same brief and the packet path, and reads the full packet as in the first round.
- **Every head has its own session, findings and receipts.** Reusing a digest for unchanged bytes is not reusing a finding: the close command validates every receipt against the new head's bytes. A `findings.json` is never copied between sessions, and a verdict never carries over to a new head.
- **Full review again** when the merge base moved, the file scope grew, or the reviewer's context was lost.
- **Two correction rounds at most** after the initial review. When the close after the second correction still returns `delivery.decision` `hold` with `blocking` or `major` findings, stop patching: write a short diagnosis as one PR comment and in the completion report — the pending findings and their common cause; which layer fails (implementation, task definition, review); one proposal (consolidate the fix, re-plan the task, request a bounded exception) — and hand the task to the human. Never mark ready with pending findings; never continue automatically.
- **Each round leaves one PR comment**: session path, head, verdict, `delivery.decision` — the durable record of the rounds and their duration.
- **The final feature audit** (the feature PR) keeps a fresh, independent context; reviewer continuity is per task only. It runs a second fresh pass with the first pass's findings as context, and closes once that pass adds nothing.

### Verification

- **Implementer**: focused tests while changing; at candidate close, the full suite of every package the task touched, with the commands the plan's verification table names, and conformance only when the task touches assets it covers. It records, per command, the command, its result line (passed/failed counts) and the head it ran on, in the ledger's Completion evidence and the PR table, from one run.
- **Orchestrator**: runs no tests. It checks that the implementer's returned result lines cover the task's Evidence commands and that each says pass; a missing or failing line is a blocker for the implementer, never a reason to run the suite itself.
- **Reviewer**: verifies the claims against the evidence and the diff; re-runs a command only to settle a concrete doubt it names in the finding. It never re-runs a suite because the evidence came from another agent.
- **CI is the required gate**: a local run never replaces reading its result (checks, once — below), and reading CI never requires a local re-run.
- **A full suite runs again only when** the head changed since the recorded run; the recorded result is missing or unverifiable; a different environment is required; a finding asks for it. "A different agent is looking" is never a reason.
- **Environment once**: the interpreter and dependencies are resolved before the first delegation (the project's install step, the doctor). A sub-agent that hits a cache or dependency failure reports it as a prerequisite failure — distinct from a test failure and from a test not run — and does not investigate the environment.

**Carrying a fix through the stack.** Whenever a commit lands on a task branch that has open task PRs stacked on it — a review fix on an earlier task, a reviewer's comment fixed later:

```bash
python3 .specify/presets/default/scripts/python/stack_propagate.py <fixed_branch>
```

It merges the fix into every branch stacked above, in order, and pushes each; a conflict stops it there, naming the branch, without touching the branches above; an empty chain is reported and changes nothing. A propagated fix is a new candidate on each stacked PR, reviewed before that PR is declared ready again.

**Checks, once.** Before marking ready, read `gh pr checks <n>` once: a failure is fixed on the branch — a new candidate; pending waits for the host's notification or one bounded wait, then one more read, never a polling loop; a repository with no checks is reported as such.

**Ready.** `gh pr ready <n>` when `delivery.decision` is `proceed` — without `code-review`, when the comment's findings are fixed — and no check failed. The checked box travels inside the task PR, reaching the feature branch only through the human merge; a reviewer's comment is fixed on this same PR, the box stays checked. Ready for review is what frees you to start the next task (step 1).

## 3. Between tasks

A task is finished when a human merged its PR — the merge is what lands its checked box and evidence on the feature branch, so `[x]` there means merged, by construction. `/speckit.linear.status` shows every task's derived state and its next command.

**The loop never merges.** Only when the human explicitly asks, in the conversation, does it act. Retargeting a PR onto the feature branch is GitHub's cheap `edited` event; merging leaf-first would instead re-run every check at every step, so the merge goes **root-first**:

```bash
python3 .specify/presets/default/scripts/python/merge_root_first.py
```

It prunes stale worktrees, then retargets and merges every open task PR root-first, and never requests branch deletion — the repository's auto-delete of merged branches does that cleanup on its own.

## 4. Closing the feature

When every box on the feature branch is checked — every task PR merged — mark the **feature PR** (the draft gate, whichever step opened it) `ready for review`: it now shows the whole feature, composed of task PRs a human already reviewed one by one. Approving and merging are never yours — a human merges it into the delivery base with a **merge commit** (no squash: the task history must survive). After that merge, run `git worktree prune`, then delete your local feature branch (GitHub deletes the remote when the repository auto-deletes merged branches).

## Reverting a delivered task

Undoing a delivered change is a ledger task the human adds, delivered through this loop like any other: its own branch, PR, fresh review, and `ready for review`. Its commit is never the tool's default subject, which fails the conventions check: run `git revert --no-commit <sha>` (`-m 1` for a merge), then commit it yourself with `git commit -m "revert(scope): <subject>"`.

## After hooks

Run `.specify/extensions.yml`'s `hooks.after_implement` by Setup step 5's own rule, once this run has nothing left to deliver — silently, mandatory hooks awaited, eligible optional hooks run quietly, every other one skipped.

## Completion report

Report what this run delivered: the tasks moved to `ready for review` (or merged, if the human acted), their PR links, and the loop's current position — the next task, or that the feature is waiting on the human.
