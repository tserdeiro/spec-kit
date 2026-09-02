"""The review budget: one count, one warning, no subsystem.

`spec-kit.plan.md` states the convention -- a reviewed pull request stays under
~400 authored executable lines, and larger work splits into stacked pull
requests. This module counts and warns. It never fails a review: accepting a
large pull request is a human decision.

Binary files contribute nothing (``git diff --numstat`` reports ``-`` for them,
because there are no authored lines to count), and documentation, lockfiles and
snapshots are not executable. Everything else counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .errors import EXIT_CANDIDATE, AppError, Diagnostic
from .git import Git


DEFAULT_LIMIT = 400

# Deliberately built in rather than configurable: a per-repository glob cascade
# was a subsystem, and the budget is a convention with a warning attached.
NON_EXECUTABLE_SUFFIXES: frozenset[str] = frozenset(
    {".md", ".rst", ".txt", ".lock", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf"}
)
NON_EXECUTABLE_NAMES: frozenset[str] = frozenset({"uv.lock", "package-lock.json", "poetry.lock", "Cargo.lock"})


def is_executable_path(path: str) -> bool:
    """Whether a changed file's added lines count towards the budget."""

    name = path.rsplit("/", 1)[-1]
    if name in NON_EXECUTABLE_NAMES:
        return False
    suffix = name[name.rfind(".") :].lower() if "." in name else ""
    return suffix not in NON_EXECUTABLE_SUFFIXES


@dataclass(frozen=True)
class FileBudget:
    """One changed file and what it contributes."""

    path: str
    added: int | None
    counted: int
    binary: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "added": self.added, "counted": self.counted, "binary": self.binary}


@dataclass
class BudgetReport:
    """The budget observation for one review."""

    entries: tuple[FileBudget, ...]
    limit: int = DEFAULT_LIMIT
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def counted(self) -> int:
        return sum(entry.counted for entry in self.entries)

    @property
    def over_budget(self) -> bool:
        return self.counted > self.limit

    @property
    def message(self) -> str:
        return (
            f"{self.counted} authored executable lines added against a budget of {self.limit}. "
            "Split the work into stacked pull requests that each stay inside the budget. "
            "Accepting a larger pull request is a human decision, not one this review can make."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "counted": self.counted,
            "over_budget": self.over_budget,
            "files": [entry.as_dict() for entry in self.entries],
        }


def compute(git: Git, *, merge_base: str, head_commit: str, limit: int = DEFAULT_LIMIT) -> BudgetReport:
    """Count the candidate's authored executable lines over its own range."""

    # Renames are detected, not suppressed: a pure rename of 500 lines is zero
    # authored lines. The `-z` form reports the old and the new path as separate
    # NUL-separated fields, so a path can carry anything but NUL and be read
    # exactly.
    result = git.run(
        "-c",
        "core.quotePath=false",
        "diff",
        "--numstat",
        "-z",
        "--end-of-options",
        f"{merge_base}..{head_commit}",
    )
    if not result.ok:
        raise AppError(
            f"could not read the diff statistics between {merge_base} and {head_commit}",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("numstat_unreadable", result.stderr.strip() or "git diff --numstat failed")],
        )
    return _finalize(_entries_from_numstat(result.stdout), limit=limit)


def compute_working_tree(git: Git, root: Path, *, limit: int = DEFAULT_LIMIT) -> BudgetReport:
    """Count the uncommitted work in the operator's own tree, untracked included.

    ``git diff`` cannot see untracked files and the standard trick --
    ``git add --intent-to-add`` -- writes to the index, which this command must
    never do. So their lines are counted by reading them.
    """

    # `diff.autoRefreshIndex=false`: reading the working tree must not *write* to
    # it, and a plain `git diff` rewrites `.git/index` whenever a file's stat
    # info moved without its content changing.
    result = git.run(
        "-c",
        "core.quotePath=false",
        "-c",
        "diff.autoRefreshIndex=false",
        "diff",
        "--numstat",
        "-z",
        "--end-of-options",
        "HEAD",
    )
    if not result.ok:
        raise AppError(
            "could not read the working tree's diff statistics against HEAD",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("numstat_unreadable", result.stderr.strip() or "git diff --numstat failed")],
        )
    entries = _entries_from_numstat(result.stdout)
    entries.extend(_untracked_entries(git, root))
    entries.sort(key=lambda entry: entry.path)
    return _finalize(entries, limit=limit)


def parse_numstat_z(stdout: str) -> list[tuple[str, str, str]]:
    """Read ``git diff --numstat -z`` into ``(added, removed, path)``.

    Two record shapes share the stream: an ordinary change is
    ``added\tremoved\tpath\0`` and a rename or copy is
    ``added\tremoved\t\0old\0new\0``. Reading it as fields rather than as lines
    is the whole point of ``-z``: it is the only form in which a path containing
    a newline, a quote or a tab survives intact.
    """

    fields = stdout.split("\0")
    records: list[tuple[str, str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        if not field:
            index += 1
            continue
        parts = field.split("\t")
        if len(parts) < 3:
            index += 1
            continue
        added, removed, remainder = parts[0], parts[1], "\t".join(parts[2:])
        if remainder == "":
            # A rename or a copy: the two paths are the next two fields.
            new_path = fields[index + 2] if index + 2 < len(fields) else ""
            records.append((added, removed, new_path))
            index += 3
            continue
        records.append((added, removed, remainder))
        index += 1
    return records


def _entries_from_numstat(stdout: str) -> list[FileBudget]:
    entries: list[FileBudget] = []
    for added_raw, removed_raw, path in parse_numstat_z(stdout):
        if added_raw == "-" or removed_raw == "-":
            entries.append(FileBudget(path=path, added=None, counted=0, binary=True))
            continue
        added = int(added_raw)
        entries.append(FileBudget(path=path, added=added, counted=added if is_executable_path(path) else 0))
    return entries


def _untracked_entries(git: Git, root: Path) -> list[FileBudget]:
    result = git.run("-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard", "-z")
    if not result.ok:
        return []
    entries: list[FileBudget] = []
    for path in (item for item in result.stdout.split("\0") if item):
        try:
            data = (root / path).read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            entries.append(FileBudget(path=path, added=None, counted=0, binary=True))
            continue
        added = len(data.decode("utf-8", "replace").splitlines())
        entries.append(FileBudget(path=path, added=added, counted=added if is_executable_path(path) else 0))
    return entries


def _finalize(entries: Sequence[FileBudget], *, limit: int) -> BudgetReport:
    report = BudgetReport(entries=tuple(entries), limit=limit)
    if report.over_budget:
        report.diagnostics = [Diagnostic("budget_exceeded", report.message, severity="warning")]
    return report
