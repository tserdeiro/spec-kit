"""Shared helpers the preset's Python scripts import as ``import _common``."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

DEFAULT_FORECAST = 400  # no "~N" on the Delivery line: today's shell default

_TASK_RE = re.compile(r"^\s*-\s+\[([ xX])\]\s+(T[0-9]{3})\b")
_DELIVERY_RE = re.compile(r"\*\*Delivery\*\*:\s*(.*)$")
_FORECAST_RE = re.compile(r"~([0-9]+)")
_EVIDENCE_RE = re.compile(r"\*\*Completion evidence\*\*:\s*(.*)$")
_TRUNK_RE = re.compile(r"""^trunk:\s*["']?([^"'#\s]*)""")

@dataclass(frozen=True)
class Task:
    """One ledger task: id, checkbox, Delivery forecast, Completion evidence."""

    id: str
    checked: bool
    forecast: int
    completion_evidence: str

# _fence_start/_fence_end equal spec_kit_linear.parser's; a test enforces it.
def _fence_start(line: str) -> tuple[str, int] | None:
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3 or not stripped:
        return None
    marker = stripped[0]
    if marker not in ("`", "~"):
        return None
    length = len(stripped) - len(stripped.lstrip(marker))
    if length < 3:
        return None
    if marker == "`" and marker in stripped[length:]:
        return None
    return marker, length

def _fence_end(line: str, marker: str, opening_length: int) -> bool:
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    candidate = stripped.rstrip(" \t")
    return len(candidate) >= opening_length and candidate == marker * len(candidate)

def parse_ledger(text: str) -> list[Task]:
    """Parse tasks.md fence-aware: a fenced sample is never a task."""
    tasks: list[Task] = []
    fence: tuple[str, int] | None = None
    task_id: str | None = None
    checked, forecast, evidence = False, DEFAULT_FORECAST, ""
    for line in text.splitlines():
        if fence is not None:
            if _fence_end(line, *fence):
                fence = None
            continue
        started = _fence_start(line)
        if started is not None:
            fence = started
            continue
        header = _TASK_RE.match(line)
        if header:
            if task_id is not None:
                tasks.append(Task(task_id, checked, forecast, evidence))
            task_id, checked = header.group(2), header.group(1) in "xX"
            forecast, evidence = DEFAULT_FORECAST, ""
            continue
        if task_id is None:
            continue
        delivery = _DELIVERY_RE.search(line)
        if delivery:
            found = _FORECAST_RE.search(delivery.group(1))
            forecast = int(found.group(1)) if found else forecast
            continue
        completion = _EVIDENCE_RE.search(line)
        if completion:
            evidence = completion.group(1).strip()
    if task_id is not None:
        tasks.append(Task(task_id, checked, forecast, evidence))
    return tasks

def first_unchecked(tasks: list[Task]) -> Task | None:
    return next((task for task in tasks if not task.checked), None)

def delivery_base(repo_root: Path) -> str:
    """Explicit non-empty trunk: else the GitHub default branch."""
    config = repo_root / ".specify" / "extensions" / "git" / "git-config.yml"
    try:
        text = config.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    trunk = next((m.group(1) for line in text.splitlines() if (m := _TRUNK_RE.match(line))), "")
    if trunk:
        return trunk
    result = run_gh("repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name", cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or "gh repo view failed")
    return result.stdout.strip()

def run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)

def run_gh(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], cwd=cwd, text=True, capture_output=True)

def die(message: str) -> NoReturn:
    """Today's shell diagnostic, unchanged: "error: ..." on stderr, exit 2."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)
