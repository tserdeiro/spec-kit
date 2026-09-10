#!/usr/bin/env python3
"""pr-create: resolve and print the PR base for a delivery kind.

Prints ``base=<name>`` only and never runs ``gh pr create`` itself -- the
command composes the title and body and runs that call with the base
this script printed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from _common import check_prerequisites, delivery_base, die, first_unchecked, open_task_prs, parse_ledger, run_git

def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run_git(*args, cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result

def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return run_git("merge-base", "--is-ancestor", ancestor, descendant, cwd=repo_root).returncode == 0

def feature_or_work_item(repo_root: Path) -> str:
    base = delivery_base(repo_root)
    _git(repo_root, "check-ref-format", "--branch", base)
    return base

def task(repo_root: Path, named_task: str) -> str:
    paths = check_prerequisites(repo_root)
    feature_branch = paths["BRANCH"]
    feature_number = feature_branch.rsplit("/", 1)[-1].split("-", 1)[0]
    current = _git(repo_root, "branch", "--show-current").stdout.strip()
    match = re.match(r"^[0-9]+-(T[0-9]{3})-", current.rsplit("/", 1)[-1])
    branch_task = match.group(1) if match else ""
    tasks_file = Path(paths["FEATURE_DIR"]) / "tasks.md"
    full_path = repo_root / tasks_file
    if not full_path.is_file():
        die(f"task ledger not found: {tasks_file}")
    unchecked = first_unchecked(parse_ledger(full_path.read_text(encoding="utf-8")))
    expected_task = named_task or (unchecked.id if unchecked else "")
    if not expected_task:
        die(f"no unchecked task found in {tasks_file}")
    if branch_task != expected_task:
        die(f"branch {current} delivers {branch_task} but the task to deliver is {expected_task}")
    _git(repo_root, "fetch", "origin")
    prs = open_task_prs(repo_root, feature_number, "headRefName,baseRefName,isDraft")
    heads = [pr["headRefName"] for pr in prs if not pr["isDraft"]]
    base = feature_branch
    for head in heads:
        if not _is_ancestor(repo_root, f"origin/{head}", "HEAD"):
            continue
        if base == feature_branch or _is_ancestor(repo_root, f"origin/{base}", f"origin/{head}"):
            base = head
    return base

def main(argv: list[str]) -> int:
    if not argv:
        die("usage: pr_create.py <feature|task|work-item> [named-task]")
    kind, rest = argv[0], argv[1:]
    repo_root = Path.cwd()
    if kind in ("feature", "work-item"):
        base = feature_or_work_item(repo_root)
    elif kind == "task":
        base = task(repo_root, rest[0] if rest else "")
    else:
        die(f"unknown delivery kind: {kind}")
    print(f"base={base}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
