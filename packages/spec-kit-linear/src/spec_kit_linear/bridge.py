"""Safe composition of descriptions containing bridge-owned HTML comments."""

from __future__ import annotations

import re

from .errors import AppError, Diagnostic


_BLOCK_RE = re.compile(r"<!-- (?P<marker>speckit-linear:[^>\n]+) -->\n?(?P<body>.*?)<!-- /speckit-linear -->", re.DOTALL)


def merge_managed_block(existing: str, marker: str, replacement: str) -> str:
    """Replace only ``marker``'s bounded block, preserving all exterior text.

    An unclosed marker is ambiguous: replacing through the end could erase
    human text, so it is rejected instead of guessed at.
    """

    expected_open = f"<!-- {marker} -->"
    if expected_open in existing and not any(match.group("marker") == marker for match in _BLOCK_RE.finditer(existing)):
        raise AppError(
            "bridge-owned description marker is not safely bounded",
            code=6,
            category="remote_identity",
            diagnostics=[Diagnostic("description_marker_unbounded", "refusing to overwrite text after an unclosed bridge marker")],
        )

    matches = [match for match in _BLOCK_RE.finditer(existing) if match.group("marker") == marker]
    if len(matches) > 1:
        raise AppError(
            "multiple bridge-owned description blocks have the same marker",
            code=6,
            category="remote_identity",
            diagnostics=[Diagnostic("description_marker_duplicate", "refusing ambiguous bridge description ownership")],
        )
    if matches:
        match = matches[0]
        return f"{existing[:match.start()]}{replacement}{existing[match.end():]}"
    if not existing:
        return replacement
    separator = "" if existing.endswith("\n") else "\n"
    return f"{existing}{separator}{replacement}"
