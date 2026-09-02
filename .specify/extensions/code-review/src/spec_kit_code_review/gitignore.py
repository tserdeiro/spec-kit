"""Additive, non-destructive ``.gitignore`` entry management for consumers.

Only this extension's genuinely operator-local files are ever added:
``speckit-code-review.local.yml`` and ``.speckit-code-review.env``. The shared
``speckit-code-review.yml`` is a committed artifact -- it holds no secret and no
operator identity -- and is never added here, and neither is the evidence root,
which lives outside the repository by construction.

Every edit is additive and idempotent: an existing file is read verbatim, only
the owned entries that are missing are appended, and every other line is
preserved untouched. Nothing is ever removed, reordered, or rewritten.
"""

from __future__ import annotations

from pathlib import Path

from .config import LOCAL_CONFIG_FILENAME
from .env_files import REPO_ENV_FILENAME


SECTION_HEADER = "# spec-kit-code-review: operator-local files"
MANAGED_ENTRIES: tuple[str, ...] = (LOCAL_CONFIG_FILENAME, REPO_ENV_FILENAME)


def missing_entries(path: Path, entries: tuple[str, ...] = MANAGED_ENTRIES) -> list[str]:
    """Which of ``entries`` the ``.gitignore`` at ``path`` does not list yet."""

    existing_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    existing_lines = {line.strip() for line in existing_text.splitlines()}
    return [entry for entry in entries if entry not in existing_lines]


def ensure_entries(path: Path, entries: tuple[str, ...] = MANAGED_ENTRIES) -> list[str]:
    """Append any missing owned entries; returns what was actually added."""

    missing = missing_entries(path, entries)
    if not missing:
        return []
    existing_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    existing_lines = {line.strip() for line in existing_text.splitlines()}

    lines_to_append: list[str] = []
    if existing_text and not existing_text.endswith("\n"):
        lines_to_append.append("")
    if SECTION_HEADER not in existing_lines:
        lines_to_append.append(SECTION_HEADER)
    lines_to_append.extend(missing)

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines_to_append) + "\n")
    return missing
