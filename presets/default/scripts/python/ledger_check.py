#!/usr/bin/env python3
"""ledger-check: verify a task's ledger entry is ready for review.

Exits 0 with a confirmation line when the task's checkbox is ``[x]`` and
its Completion evidence is filled -- not empty, not "Pending"
(case-insensitive), and not the template's bracketed sample text (a
value starting with ``[`` and ending with ``]``); otherwise exits 2
naming exactly what is missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _common import check_prerequisites, die, parse_ledger

def _unfilled(evidence: str) -> bool:
    if not evidence or evidence.lower() == "pending":
        return True
    return evidence.startswith("[") and evidence.endswith("]")

def check_ledger(repo_root: Path, task_id: str) -> int:
    feature_dir = check_prerequisites(repo_root)["FEATURE_DIR"]
    tasks_file = Path(feature_dir) / "tasks.md"
    full_path = repo_root / tasks_file
    if not full_path.is_file():
        die(f"task ledger not found: {tasks_file}")
    tasks = parse_ledger(full_path.read_text(encoding="utf-8"))
    task = next((candidate for candidate in tasks if candidate.id == task_id), None)
    if task is None:
        die(f"task {task_id} not found in {tasks_file}")
    problems = []
    if not task.checked:
        problems.append("is not checked")
    if _unfilled(task.completion_evidence):
        problems.append("has no completion evidence")
    if problems:
        die(f"task {task_id} " + " and ".join(problems))
    print(f"ledger: {task_id} checked, completion evidence filled")
    return 0

def main(argv: list[str]) -> int:
    if len(argv) != 1:
        die("usage: ledger_check.py <task_id>")
    return check_ledger(Path.cwd(), argv[0])

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
