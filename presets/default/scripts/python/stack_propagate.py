#!/usr/bin/env python3
"""stack-propagate: carry a fix through every open task PR stacked on it.

Direct translation of today's stack-propagate shell block: walks the
feature's open task-PR chain above ``fixed_branch``, in stack order,
merging each with a "carry the fix" subject and pushing it; a conflict
aborts and names the branch, an empty chain is reported without
touching git. Every branch pushed is reconciled into Linear (push
--hook) when the extension is installed, same rule as task_base.py --
also when a later hop conflicts, since the pushes already made are
real; a failing reconcile is a warning, never a failure of this script,
and an empty chain reconciles nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import die, open_task_prs, reconcile_linear, run_git

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
    feature_prs = open_task_prs(repo_root, feature_number, "headRefName,baseRefName,isDraft")
    fixed_task = _task_id(fixed_branch)
    previous = fixed_branch
    current = _child(feature_prs, previous)
    if current is None:
        print(f"nothing stacked on {fixed_branch}")
        return 0
    pushed = 0
    try:
        while current is not None:
            current_task = _task_id(current)
            _git(repo_root, "switch", current)
            subject = f"merge(task): carry the {fixed_task} fix into {current_task}"
            merge = run_git("merge", "--no-ff", "-m", subject, previous, cwd=repo_root)
            if merge.returncode != 0:
                run_git("merge", "--abort", cwd=repo_root)
                die(f"merge conflict carrying the fix into {current}")
            _git(repo_root, "push", "origin", current)
            pushed += 1
            previous = current
            current = _child(feature_prs, previous)
        _git(repo_root, "switch", fixed_branch)
    finally:
        if pushed:
            reconcile_linear(repo_root)
    return 0

def main(argv: list[str]) -> int:
    if len(argv) != 1:
        die("usage: stack_propagate.py <fixed_branch>")
    return propagate(Path.cwd(), argv[0])

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
