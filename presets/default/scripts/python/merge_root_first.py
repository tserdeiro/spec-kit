#!/usr/bin/env python3
"""merge-root-first: the human's explicit "yes, merge" for a task-PR stack.

Extracts today's prose-only "Between tasks" merge procedure: self-derives
the feature branch, prunes worktrees, then walks the feature's open task
PRs root-first, retargeting each to the feature branch by API before
merging it. Retargeting root-first is GitHub's cheap "edited" event,
where merging leaf-first would re-run every check at every step; the
head branch is never deleted here because doing so before GitHub's own
retarget can close the PR above instead of reopening it onto the new
base -- the repository's auto-delete of merged branches does that
cleanup on its own schedule. The script performs the mechanical steps
only; the human's "yes, merge" stays a conversation-level decision.
Every PR merged is reconciled into Linear (push --hook) when the
extension is installed, same rule as task_base.py -- also when a later
merge fails, since the merges already made are real; a failing reconcile
is a warning, never a failure of this script, and an empty stack
reconciles nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from _common import check_prerequisites, die, open_task_prs, reconcile_linear, run_gh, run_git

def _git(repo_root: Path, *args: str) -> None:
    result = run_git(*args, cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or f"git {' '.join(args)} failed")

def _gh(repo_root: Path, number: int, *args: str) -> None:
    result = run_gh(*args, cwd=repo_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"gh {' '.join(args)} failed"
        die(f"#{number}: {detail}")

def _base(repo_root: Path, number: int) -> str:
    result = run_gh("api", f"repos/{{owner}}/{{repo}}/pulls/{number}", "--jq", ".base.ref", cwd=repo_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"gh api pull request {number} failed"
        die(f"#{number}: {detail}")
    base = result.stdout.strip()
    if not base:
        die(f"#{number}: gh api returned an empty base branch")
    return base

def _child(prs: list[dict[str, Any]], base: str) -> dict[str, Any] | None:
    return next((pr for pr in prs if pr["baseRefName"] == base), None)

def merge_root_first(repo_root: Path) -> int:
    feature_branch = check_prerequisites(repo_root)["BRANCH"]
    feature_number = feature_branch.rsplit("/", 1)[-1].split("-", 1)[0]
    _git(repo_root, "worktree", "prune")
    feature_prs = open_task_prs(repo_root, feature_number, "number,headRefName,baseRefName,isDraft")
    order: list[dict[str, Any]] = []
    base = feature_branch
    pr = _child(feature_prs, base)
    while pr is not None:
        order.append(pr)
        base = pr["headRefName"]
        pr = _child(feature_prs, base)
    if not order:
        print(f"nothing to merge on {feature_branch}")
        return 0
    merged = 0
    try:
        for pr in order:
            number = pr["number"]
            current_base = _base(repo_root, number)
            if current_base != feature_branch:
                patch = run_gh("api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/pulls/{number}",
                               "-f", f"base={feature_branch}", cwd=repo_root)
                if patch.returncode != 0:
                    original_error = patch.stderr.strip() or f"gh api PATCH pull request {number} failed"
                    # GitHub may have retargeted the PR between the GET and PATCH.
                    # Accept the race only after proving the remote base is correct.
                    verify = run_gh("api", f"repos/{{owner}}/{{repo}}/pulls/{number}", "--jq", ".base.ref", cwd=repo_root)
                    if verify.returncode != 0 or verify.stdout.strip() != feature_branch:
                        die(f"#{number}: {original_error}")
            _gh(repo_root, number, "pr", "merge", str(number), "--merge")
            merged += 1
            print(f"merged #{number} {pr['headRefName']}")
    finally:
        if merged:
            reconcile_linear(repo_root)
    return 0

def main(argv: list[str]) -> int:
    if argv:
        die("usage: merge_root_first.py")
    return merge_root_first(Path.cwd())

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
