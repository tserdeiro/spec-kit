#!/usr/bin/env python3
"""stack-propagate: carry a fix through every open task PR stacked on it.

Direct translation of today's stack-propagate shell block: walks the
feature's open task-PR chain above ``fixed_branch``, in stack order,
merging each with a "carry the fix" subject and pushing it; a conflict
aborts and names the branch, an empty chain is reported without
touching git.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import die, run_gh_json, run_git

_TASK_RE = re.compile(r"^[0-9]+-(T[0-9]{3})-")

def _git(repo_root: Path, *args: str) -> None:
    result = run_git(*args, cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or f"git {' '.join(args)} failed")

def _task_id(branch: str) -> str:
    match = _TASK_RE.match(branch)
    return match.group(1) if match else ""

def _child(prs: list[dict[str, Any]], base: str) -> str | None:
    return next((pr["headRefName"] for pr in prs if pr["baseRefName"] == base), None)

def propagate(repo_root: Path, fixed_branch: str) -> int:
    feature_number = fixed_branch.split("-", 1)[0]
    prs = run_gh_json(
        "pr", "list", "--state", "open", "--limit", "100",
        "--json", "headRefName,baseRefName,isDraft", cwd=repo_root,
    )
    feature_prs = [pr for pr in prs if pr["headRefName"].startswith(f"{feature_number}-T")]
    fixed_task = _task_id(fixed_branch)
    previous = fixed_branch
    current = _child(feature_prs, previous)
    if current is None:
        print(f"nothing stacked on {fixed_branch}")
        return 0
    while current is not None:
        current_task = _task_id(current)
        _git(repo_root, "switch", current)
        subject = f"merge(task): carry the {fixed_task} fix into {current_task}"
        merge = run_git("merge", "--no-ff", "-m", subject, previous, cwd=repo_root)
        if merge.returncode != 0:
            run_git("merge", "--abort", cwd=repo_root)
            die(f"merge conflict carrying the fix into {current}")
        _git(repo_root, "push", "origin", current)
        previous = current
        current = _child(feature_prs, previous)
    _git(repo_root, "switch", fixed_branch)
    return 0

def main(argv: list[str]) -> int:
    if len(argv) != 1:
        die("usage: stack_propagate.py <fixed_branch>")
    return propagate(Path.cwd(), argv[0])

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
