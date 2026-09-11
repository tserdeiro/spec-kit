"""Protected paths: a deterministic contract-protection finding (FR-010, plan D1).

A task pull request -- its base branch's final path segment matching
``^[0-9]+-`` -- may not touch the paths the product contract lives in.
Working-tree reviews and trunk-based candidates are exempt by construction.
The generated entries join the agent's own findings before normalization, so
they are validated, ordered, verdicted and published like any other finding.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any, Sequence

from .anchors import HunkMap
from .git import Git


_TASK_BASE_RE = re.compile(r"^[0-9]+-")
TITLE = "Protected path changed in a task pull request"


def is_task_base(base_branch: str | None) -> bool:
    """A numeric final path segment marks the base as a task, not the trunk."""

    if not base_branch:
        return False
    return bool(_TASK_BASE_RE.match(base_branch.rsplit("/", 1)[-1]))


def matches_protected_path(path: str, protected_paths: Sequence[str]) -> str | None:
    """The first ``protected_paths`` glob ``path`` matches, or ``None``.

    Shared by the after-the-fact finding below and the `pre_tool_use` guard
    (FR-008): one glob rule, never two.
    """

    return next((item for item in protected_paths if fnmatch.fnmatch(path, item)), None)


def protected_path_findings(
    *,
    base_branch: str | None,
    protected_paths: Sequence[str],
    git: Git,
    hunks: HunkMap,
    merge_base: str,
    head_commit: str,
) -> list[dict[str, Any]]:
    """One generated ``blocking``/``contract`` finding per touched protected path."""

    if not is_task_base(base_branch):
        return []
    entries: list[dict[str, Any]] = []
    for path in git.changed_paths(merge_base, head_commit):
        pattern = matches_protected_path(path, protected_paths)
        if pattern is None:
            continue
        content = (
            f"`{path}` matches the protected path `{pattern}`. A task pull request (base "
            f"`{base_branch}`) may not change the product contract; this belongs in the feature "
            "pull request instead."
        )
        right_hunks = hunks.for_path(path)
        if right_hunks:
            entries.append(_entry(path, "RIGHT", right_hunks[0].start, right_hunks[0].end, content))
        else:
            # No RIGHT hunk: whether the file was removed whole or just some
            # of its lines were, the base file always has a line 1 to anchor.
            entries.append(_entry(path, "LEFT", 1, 1, content))
    return entries


def _entry(path: str, side: str, start_line: int, end_line: int, content: str) -> dict[str, Any]:
    return {
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "side": side,
        "severity": "blocking",
        "category": "contract",
        "title": TITLE,
        "content": content,
    }
