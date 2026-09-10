---
name: speckit-implement
description: Execute the task delivery loop — one branch and one draft pull request
  per task, scripted end to end.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: preset:default
---

# Speckit Implement Skill

# Spec Kit Implement

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Setup

1. If the user named a feature (`/speckit.implement 003` or `003-checkout-flow`), resolve it to exactly one `specs/<dir>/` directory (a unique prefix is enough; stop and list the candidates if it is ambiguous or matches nothing) and `export SPECIFY_FEATURE_DIRECTORY=specs/<dir>` in every shell where this feature's scripts run. Upstream persists that choice to `.specify/feature.json`, so later runs without an argument continue it; without an argument, the active feature applies as-is.
2. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from the repository root; parse `FEATURE_DIR` and `AVAILABLE_DOCS`. Every path is absolute.
3. **Checklists, read-only** — when `FEATURE_DIR/checklists/` exists, scan each file's `- [ ]`/`- [x]` counts into a table (`Checklist | Total | Checked | Unchecked | Status`). Every checklist at 0 unchecked is `PASS`; otherwise display the table and ask whether to proceed anyway — "no" or "wait" halts, "yes" or "proceed" continues. Never edit a checklist file or its markers.
4. **Load the artifacts** — `tasks.md` and `plan.md` (required); `data-model.md`, `contracts/`, `research.md`, `quickstart.md`, and `.specify/memory/constitution.md` when present.
5. **Hooks, silently** — read `.specify/extensions.yml`'s `hooks.before_implement` (skip entirely, silently, on a missing file, a missing key, or invalid YAML). Among entries whose `enabled` is not explicitly `false` and whose `condition` is empty (a non-empty `condition` is left to the HookExecutor): invoke a **mandatory** hook (`optional: false`) as its own slash command — dots become hyphens, e.g. `speckit.git.commit` → `/speckit-git-commit` — and wait for it before continuing; run an **optional** hook the same way, silently, only when its own extension's configuration enables its event (check under `.specify/extensions/<extension>/`); skip every other optional hook, silently. Nothing about a hook is ever printed. The same rule governs `hooks.after_implement` — see "After hooks" below.

## The delivery loop

This distribution delivers **one branch and one draft PR per task**; wrap every task in the steps below.

**Orchestrate when your host can.** If your host supports delegating to sub-agents (Claude Code's Task tool, OpenCode agents, or equivalent), run this loop as an orchestrator: implement each task in a **fresh sub-agent**, so no context carries one task's residue into the next, and keep for yourself only what the loop needs — state derivation, branches, commits, and the conversation with the human. Everything a sub-agent needs (spec, plan, tasks, checkboxes, branches, PRs) is observable from the repository, so hand it pointers, never your conversation. Without that capability, run the loop yourself as written.

**One task at a time.** Task lists here carry no parallel-task marker and no task ever runs in parallel. Exactly one task is in flight: one branch, one sub-agent, one draft PR. The next task starts only once the current one is `ready for review` (step 2). Tasks other developers deliver on their own branches are not this loop's concern.

Run every script below with the consumer's `.venv/bin/python` when it exists, else `python3` on PATH — the rule upstream's own `py` scripts follow.

## 0. The gate

Verify the **feature gate** — the draft feature PR on the feature branch (`NNN-slug`), the spec-review gate a human merge later closes:

```bash
gh pr view <feature-branch> --json url,isDraft,state 2>/dev/null
```

Only an OPEN pull request counts. When none exists, run the `/speckit.pr` routine's **feature-PR variant** — from the feature branch, with the feature's artifacts committed — before the first task: it opens the canonical draft gate, and the loop continues. When it is open, report its URL and never open another. When it is CLOSED or MERGED, stop and tell the human — a closed gate is a decision, not a gap. The gate is where a human approves the spec and plan; the loop never delivers a task against a feature with no gate open.

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

Before opening the PR, run the budget stop:

```bash
python3 .specify/presets/default/scripts/python/budget_stop.py <T###> <base>
```

(`base` is what step 1 printed.) It stops the task — no PR opens — when the authored executable lines pass the smaller of twice the task's `Delivery` forecast and 400, naming what does not fit. **A forecast or a budget is never amended in the PR that exceeds it**: a human changes it in the ledger, on the feature branch, outside that PR — or grants an explicit exception in the conversation, recorded in the PR's evidence, letting the PR open as is.

Run `/speckit.pr`: it guarantees the branch invariant and opens the draft PR with the canonical body. Self-review it next: the fresh reviewer's brief is fixed text, the packet path (or the diff and PR body, below) prepended:

> Verify the implementer's claims in the packet's evidence instead of
> repeating its experiments. Before asking for an edge case, ask
> whether the mechanism is needed at all — a simpler design that meets
> the requirement is a `major` finding, a new runtime dependency is
> `blocking`, per the repository's review rules. A packet over 100 KB
> (`wc -c`) is reviewed one file at a time, findings consolidated at
> the end. Write `findings.json` inside the review session directory
> when there is one; otherwise, return the findings directly to the
> orchestrator.

- **With `code-review` in the set**, review it with `/speckit.code-review <PR number>` — only the PR form opens a review session — orchestrated like the tasks: on hosts with sub-agents, open the review session but neither read the packet nor write the findings yourself — hand the packet path and the brief, nothing else, to a **fresh sub-agent** with no implementation residue, which reads the packet in full, reviews the candidate, and writes `findings.json` **inside the review session directory**; close the review with that file. Without sub-agents, run the review yourself — findings still written inside the session directory, fresh per review, never copied from an earlier one.
- **Without `code-review`**, hand a fresh sub-agent (or, without one, a fresh context) the PR's diff and body — `gh pr diff <n>` and `gh pr view <n>` — and the brief, nothing else carried over. It returns its findings; post them as one PR comment (`gh pr comment <n>`) — no session, no verdict, the degraded mode — and name that comment in the Completion evidence.

That independence is what makes the verdict worth anything: a reused findings file is not a review. Fix what it finds on the task branch, whichever path produced it.

**Carrying a fix through the stack.** Whenever a commit lands on a task branch that has open task PRs stacked on it — a review fix on an earlier task, a reviewer's comment fixed later:

```bash
python3 .specify/presets/default/scripts/python/stack_propagate.py <fixed_branch>
```

It merges the fix into every branch stacked above, in order, and pushes each; a conflict stops it there, naming the branch, without touching the branches above; an empty chain is reported and changes nothing.

Then, in the PR's **final commit**, check the task's box and fill its **Completion evidence** (a task split into stacked PRs checks it in the stack's last PR), push, and run the budget stop again — the branch may have grown during review. Then the ledger gate:

```bash
python3 .specify/presets/default/scripts/python/ledger_check.py <T###>
```

It exits 2 naming exactly what's missing — the checkbox, the evidence, or both — before the PR can be marked ready; once it passes, `gh pr ready <n>`. The checked box travels inside the task PR, reaching the feature branch only through the human merge; a reviewer's comment is fixed on this same PR, the box stays checked. Ready for review is what frees you to start the next task (step 1).

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
