#!/usr/bin/env python3
"""budget-stop: stop a task before its authored lines pass the budget.

Direct translation of today's budget-stop shell block: the forecast comes
from the task's Delivery line (fence-aware; absent or without a "~N" marker
defaults to 400), the diff sums ``git diff --numstat --no-renames
<base>...HEAD`` excluding binary rows, the four lockfiles, and eleven
suffixes (case-insensitive), and the stop is the smaller of twice the
forecast and 400.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _common import DEFAULT_FORECAST, check_prerequisites, die, parse_ledger, run_git

_LOCKFILES = {"uv.lock", "package-lock.json", "poetry.lock", "Cargo.lock"}
_EXCLUDED_SUFFIXES = {
    ".md", ".rst", ".txt", ".lock", ".svg", ".png",
    ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
}
_MAX_STOP = 400
_LISTED_FILES = 10

def _counted_lines(numstat: str) -> tuple[int, list[tuple[int, str]]]:
    """Sum the added lines the review budget counts. A binary row (either
    count is "-"), a lockfile, or an excluded suffix contributes nothing."""
    total = 0
    listing: list[tuple[int, str]] = []
    for line in numstat.splitlines():
        added, removed, path = line.split("\t", 2)
        if added == "-" or removed == "-":
            continue
        name = path.rsplit("/", 1)[-1]
        if name in _LOCKFILES:
            continue
        parts = name.split(".")
        suffix = f".{parts[-1].lower()}" if len(parts) > 1 else ""
        if suffix in _EXCLUDED_SUFFIXES:
            continue
        lines = int(added)
        total += lines
        listing.append((lines, path))
    return total, listing

def check_budget(repo_root: Path, task_id: str, base: str) -> int:
    feature_dir = check_prerequisites(repo_root)["FEATURE_DIR"]
    tasks_file = Path(feature_dir) / "tasks.md"
    full_path = repo_root / tasks_file
    if not full_path.is_file():
        die(f"task ledger not found: {tasks_file}")
    tasks = parse_ledger(full_path.read_text(encoding="utf-8"))
    forecast = next((task.forecast for task in tasks if task.id == task_id), DEFAULT_FORECAST)
    result = run_git("diff", "--numstat", "--no-renames", f"{base}...HEAD", cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or "git diff failed")
    added, listing = _counted_lines(result.stdout)
    stop = min(2 * forecast, _MAX_STOP)
    if added > stop:
        print(f"error: {task_id} added {added} lines against a stop of {stop} (forecast ~{forecast})",
              file=sys.stderr)
        for lines, path in sorted(listing, key=lambda item: item[0], reverse=True)[:_LISTED_FILES]:
            print(f"{lines} {path}", file=sys.stderr)
        return 2
    print(f"budget: {added}/{stop} (forecast ~{forecast})")
    return 0

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        die("usage: budget_stop.py <task_id> <base>")
    return check_budget(Path.cwd(), argv[0], argv[1])

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
