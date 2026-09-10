#!/usr/bin/env python3
"""task-base: per-task branch setup -- refresh, task, and work-item modes.

Direct translations of today's first-task-refresh, task-base, and
work-item-branch shell blocks. Every mode that creates a branch ends by
reconciling Linear (push --hook) when the extension is installed; a
failing reconcile is a warning, never a failure of this script.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _common import check_prerequisites, delivery_base, die, run_gh_json, run_git

def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run_git(*args, cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result

def _reconcile(repo_root: Path) -> None:
    run_sh = repo_root / ".specify" / "extensions" / "linear" / "scripts" / "bash" / "run.sh"
    if not run_sh.is_file():
        return
    result = subprocess.run(["bash", str(run_sh), "push", "--hook"], cwd=repo_root, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        print(f"warning: linear reconcile failed: {detail}", file=sys.stderr)

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
    # No _reconcile() here: refresh fast-forwards an existing branch, it
    # never creates one, so there is nothing new for Linear to project.

def task(repo_root: Path, task_branch: str) -> None:
    feature_branch = check_prerequisites(repo_root)["BRANCH"]
    feature_number = feature_branch.rsplit("/", 1)[-1].split("-", 1)[0]
    prs = run_gh_json(
        "pr", "list", "--state", "open", "--limit", "100",
        "--json", "headRefName,baseRefName,isDraft", cwd=repo_root,
    )
    feature_prs = [pr for pr in prs if pr["headRefName"].startswith(f"{feature_number}-T")]
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
    _reconcile(repo_root)

def work_item(repo_root: Path, branch: str) -> None:
    base = delivery_base(repo_root)
    _git(repo_root, "check-ref-format", "--branch", base)
    _git(repo_root, "fetch", "origin")
    _git(repo_root, "switch", "-c", branch, f"origin/{base}")
    _reconcile(repo_root)

def main(argv: list[str]) -> int:
    if not argv:
        die("usage: task_base.py <refresh|task <branch>|work-item <branch>>")
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
            die("usage: task_base.py work-item <branch-name>")
        work_item(repo_root, rest[0])
    else:
        die(f"unknown mode: {mode}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
