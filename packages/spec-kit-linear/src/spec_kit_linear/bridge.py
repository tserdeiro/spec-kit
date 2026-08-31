"""Safe composition of descriptions containing bridge-owned HTML comments."""

from __future__ import annotations

import re

from .errors import AppError, Diagnostic


# A marker line: an identity, optionally followed by a ` hash:HHHH` suffix.
# Matches both a block's open tag and a lone marker line with no close tag
# (see merge_managed_block's migration case). A marker identity never itself
# contains a space (it's built only from feature/task ids), so stopping the
# capture at the first space safely separates it from an optional hash
# suffix.
_MARKER_LINE_RE = re.compile(r"<!-- (?P<marker>speckit-linear:[^>\n ]+)(?: hash:[0-9a-f]{12})? -->")

_BLOCK_RE = re.compile(
    r"<!-- (?P<marker>speckit-linear:[^>\n ]+)(?: hash:[0-9a-f]{12})? -->\n?(?P<body>.*?)<!-- /speckit-linear -->",
    re.DOTALL,
)


def merge_managed_block(existing: str, marker: str, replacement: str) -> str:
    """Replace ``marker``'s bounded block, preserving all exterior text.

    The open tag is matched with or without a ` hash:HHHH` suffix, so this
    replaces a block composed under either hash-gated or plain layout.

    Migration: a lone marker line for this identity with no
    `<!-- /speckit-linear -->` anywhere in the text is not an error -- it is
    the closing-tag-less shape a previous release left behind (or a human
    who deleted the close tag). Everything from the very start of the text
    through that marker line is replaced with ``replacement``; everything
    below survives untouched, becoming (or staying) human space below the
    new bounded block.
    """

    bounded_matches = [match for match in _BLOCK_RE.finditer(existing) if match.group("marker") == marker]
    if len(bounded_matches) > 1:
        raise _duplicate_marker_error()
    if bounded_matches:
        match = bounded_matches[0]
        return f"{existing[:match.start()]}{replacement}{existing[match.end():]}"

    marker_matches = [match for match in _MARKER_LINE_RE.finditer(existing) if match.group("marker") == marker]
    if len(marker_matches) > 1:
        raise _duplicate_marker_error()
    if marker_matches:
        match = marker_matches[0]
        return f"{replacement}{existing[match.end():]}"

    if not existing:
        return replacement
    separator = "" if existing.endswith("\n") else "\n"
    return f"{existing}{separator}{replacement}"


def marker_present(existing: str, marker: str) -> bool:
    """Whether ``marker``'s identity appears anywhere in ``existing``.

    Matches a bounded block's open tag and a lone marker line alike, with or
    without its ` hash:...` suffix -- so a remote resource is recognized as
    adopted regardless of which format its description is currently in.
    """

    return any(match.group("marker") == marker for match in _MARKER_LINE_RE.finditer(existing))


def block_bounded(existing: str, marker: str) -> bool:
    """Whether ``marker``'s region is a properly bounded open/close block.

    A lone marker line with no close tag -- the shape a previous release
    left behind -- is present but not bounded. The planner uses this to
    force a migrating rewrite even when the body hash matches: the hash
    covers only the body, so a format change alone never moves it.
    """

    return any(match.group("marker") == marker for match in _BLOCK_RE.finditer(existing))


def _duplicate_marker_error() -> AppError:
    return AppError(
        "multiple bridge-owned description blocks have the same marker",
        code=6,
        category="remote_identity",
        diagnostics=[Diagnostic("description_marker_duplicate", "refusing ambiguous bridge description ownership")],
    )
