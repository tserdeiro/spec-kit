#!/usr/bin/env python3
"""task-base: per-task branch setup -- refresh, task, and work-item modes.

Direct translations of today's first-task-refresh, task-base, and
work-item-branch shell blocks. Every mode that creates a branch ends by
reconciling Linear (push --hook) when the extension is installed; a
failing reconcile is a warning, never a failure of this script.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from _common import check_prerequisites, delivery_base, die, open_task_prs, reconcile_linear, run_git
from work_item_start import WorkItemContext, start as start_work_item

def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run_git(*args, cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result

def refresh(repo_root: Path) -> None:
    current_branch = _git(repo_root, "branch", "--show-current").stdout.strip()
    feature_branch = check_prerequisites(repo_root)["BRANCH"]
    if current_branch != feature_branch:
        die(f"expected feature branch {feature_branch}, found {current_branch}")
    base = delivery_base(repo_root)
    _git(repo_root, "check-ref-format", "--branch", base)
    _git(repo_root, "fetch", "origin")
    _git(repo_root, "merge", f"origin/{base}")
    _git(repo_root, "push", "origin", feature_branch)
    # No reconcile_linear() here: refresh fast-forwards an existing branch,
    # it never creates one, so there is nothing new for Linear to project.

def task(repo_root: Path, task_branch: str) -> None:
    feature_branch = check_prerequisites(repo_root)["BRANCH"]
    feature_number = feature_branch.rsplit("/", 1)[-1].split("-", 1)[0]
    feature_prs = open_task_prs(repo_root, feature_number, "headRefName,baseRefName,isDraft")
    draft = [pr["headRefName"] for pr in feature_prs if pr["isDraft"]]
    if draft:
        die("draft task PR still open: " + "\n".join(draft))
    heads = {pr["headRefName"] for pr in feature_prs}
    bases = {pr["baseRefName"] for pr in feature_prs}
    tops = sorted(heads - bases)
    if len(tops) > 1:
        die("two open task stacks: " + "\n".join(tops))
    base = tops[0] if tops else feature_branch
    _git(repo_root, "fetch", "origin")
    _git(repo_root, "switch", "-c", task_branch, f"origin/{base}")
    print(f"base={base}")
    reconcile_linear(repo_root)

def work_item(repo_root: Path, issue_key: str, title: str | None = None) -> WorkItemContext:
    context = start_work_item(repo_root, issue_key, title)
    base = delivery_base(repo_root)
    _git(repo_root, "check-ref-format", "--branch", base)
    _git(repo_root, "fetch", "origin")
    _git(repo_root, "switch", "-c", context.branch_name, f"origin/{base}")
    reconcile_linear(repo_root)
    print(json.dumps(asdict(context), ensure_ascii=False, sort_keys=True))
    return context

def main(argv: list[str]) -> int:
    if not argv:
        die("usage: task_base.py <refresh|task <branch>|work-item <issue-key> [title]>")
    repo_root = Path.cwd()
    mode, rest = argv[0], argv[1:]
    if mode == "refresh":
        refresh(repo_root)
    elif mode == "task":
        if not rest:
            die("usage: task_base.py task <NNN-T###-slug>")
        task(repo_root, rest[0])
    elif mode == "work-item":
        if not rest:
            die("usage: task_base.py work-item <issue-key> [title]")
        if len(rest) > 2:
            die("usage: task_base.py work-item <issue-key> [title]")
        work_item(repo_root, rest[0], rest[1] if len(rest) == 2 else None)
    else:
        die(f"unknown mode: {mode}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
