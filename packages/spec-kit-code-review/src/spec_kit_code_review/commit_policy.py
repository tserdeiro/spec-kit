"""The shared commit-subject policy used by agent and native Git checks."""

from __future__ import annotations

import re


_COMMIT_SUBJECT_RE = re.compile(r"^[a-z]+\([a-z0-9-]+\): .+$")


def is_valid_commit_subject(subject: str) -> bool:
    """Return whether ``subject`` follows the repository's current rule."""

    return _COMMIT_SUBJECT_RE.match(subject) is not None
