"""Shared helpers the preset's Python scripts import as ``import _common``."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

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

def delivery_base(repo_root: Path, *, observed_default: str | None = None) -> str:
    """Explicit non-empty trunk: else the GitHub default branch."""
    config = repo_root / ".specify" / "extensions" / "git" / "git-config.yml"
    try:
        text = config.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    trunk = next((m.group(1) for line in text.splitlines() if (m := _TRUNK_RE.match(line))), "")
    if trunk:
        return trunk
    if observed_default is not None:
        return observed_default
    result = run_gh("repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name", cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or "gh repo view failed")
    return result.stdout.strip()

def check_prerequisites(repo_root: Path) -> dict[str, str]:
    """Run check-prerequisites.sh --paths-only; parse its "KEY: value" lines."""
    result = subprocess.run(
        ["bash", ".specify/scripts/bash/check-prerequisites.sh", "--paths-only"],
        cwd=repo_root, text=True, capture_output=True,
    )
    if result.returncode != 0:
        die(result.stderr.strip() or "check-prerequisites.sh failed")
    paths: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition(": ")
        if sep:
            paths[key] = value
    return paths

def run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)

def run_gh(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], cwd=cwd, text=True, capture_output=True)

def run_gh_json(*args: str, cwd: Path | None = None) -> Any:
    """Run a `gh ... --json <fields>` call; parse stdout, `die` on either failure."""
    result = run_gh(*args, cwd=cwd)
    if result.returncode != 0:
        die(result.stderr.strip() or f"gh {' '.join(args)} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        die(f"gh {' '.join(args)} returned invalid JSON: {error}")

_TASK_PR_LIMIT = 1000

def open_task_prs(repo_root: Path, feature_number: str, fields: str) -> list[dict[str, Any]]:
    """The feature's open task PRs (heads `<feature_number>-T…`), from the whole repository.

    `gh` paginates up to `--limit`; a saturated result may be truncated, and
    acting on a partial stack yields a wrong base, an empty propagation, or
    a false "nothing to merge", so that case dies instead.
    """
    prs = run_gh_json("pr", "list", "--state", "open", "--limit", str(_TASK_PR_LIMIT), "--json", fields, cwd=repo_root)
    if len(prs) >= _TASK_PR_LIMIT:
        die(f"gh pr list hit its {_TASK_PR_LIMIT}-PR limit; the result may be truncated")
    return [pr for pr in prs if pr["headRefName"].startswith(f"{feature_number}-T")]

def reconcile_linear(repo_root: Path) -> None:
    """Reconcile Linear after work `post_tool_use` cannot see: `push --hook`
    when the extension is installed, a silent no-op without it, and a
    warning -- never a failure of the calling script -- if that call fails.
    """
    run_sh = repo_root / ".specify" / "extensions" / "linear" / "scripts" / "bash" / "run.sh"
    if not run_sh.is_file():
        return
    result = subprocess.run(["bash", str(run_sh), "push", "--hook"], cwd=repo_root, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        print(f"warning: linear reconcile failed: {detail}", file=sys.stderr)

def die(message: str) -> NoReturn:
    """Today's shell diagnostic, unchanged: "error: ..." on stderr, exit 2."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)
