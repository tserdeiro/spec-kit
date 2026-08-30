"""Safe composition of descriptions containing bridge-owned HTML comments."""

from __future__ import annotations

import re

from .errors import AppError, Diagnostic


_BLOCK_RE = re.compile(r"<!-- (?P<marker>speckit-linear:[^>\n]+) -->\n?(?P<body>.*?)<!-- /speckit-linear -->", re.DOTALL)

# The new single-line head marker: an identity, optionally followed by a
# ` hash:HHHH` suffix. A marker identity never itself contains a space (it's
# built only from feature/task ids), so stopping the capture at the first
# space safely separates the identity from an optional hash suffix -- and
# this same pattern matches a legacy open tag too, since "no hash suffix" is
# exactly what one looks like.
_HEAD_MARKER_RE = re.compile(r"<!-- (?P<marker>speckit-linear:[^>\n ]+)(?: hash:[0-9a-f]{12})? -->")


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
        raise _duplicate_marker_error()
    if matches:
        match = matches[0]
        return f"{existing[:match.start()]}{replacement}{existing[match.end():]}"
    if not existing:
        return replacement
    separator = "" if existing.endswith("\n") else "\n"
    return f"{existing}{separator}{replacement}"


def marker_present(existing: str, marker: str) -> bool:
    """Whether ``marker``'s identity appears anywhere in ``existing``.

    Matches a legacy bounded-block open tag and a new-format head marker
    line alike, with or without its ` hash:...` suffix -- so a remote
    resource is recognized as adopted regardless of which format its
    description is currently in.
    """

    return any(match.group("marker") == marker for match in _HEAD_MARKER_RE.finditer(existing))


def merge_managed_head(existing: str, marker: str, replacement_head: str) -> str:
    """Replace the bridge-owned HEAD of ``existing`` with ``replacement_head``.

    Ownership here is not a bounded block: it is everything from the very
    start of the text through ``marker``'s own single-line marker -- its
    last line, carrying the identity and (for a hash-gated block) the body
    hash together, the one visible line Linear's issue view renders an HTML
    comment as. Everything below that line is human space, preserved
    verbatim on every rewrite.

    Trade-off: text a human inserts ABOVE the marker line sits inside the
    owned region and is silently replaced the next time the source artifact
    (the task's own body, or the spec) changes -- only text strictly below
    the marker line is guaranteed to survive a rewrite.

    A legacy bounded block (`<!-- marker -->` ... `<!-- /speckit-linear -->`)
    for this identity is a one-time migration: it is replaced in place,
    preserving text on both sides, exactly like `merge_managed_block`. After
    that rewrite the resource is in the new head format for good.
    """

    legacy_matches = [match for match in _BLOCK_RE.finditer(existing) if match.group("marker") == marker]
    if len(legacy_matches) > 1:
        raise _duplicate_marker_error()
    if legacy_matches:
        match = legacy_matches[0]
        return f"{existing[:match.start()]}{replacement_head}{existing[match.end():]}"

    head_matches = [match for match in _HEAD_MARKER_RE.finditer(existing) if match.group("marker") == marker]
    if len(head_matches) > 1:
        raise _duplicate_marker_error()
    if head_matches:
        match = head_matches[0]
        return f"{replacement_head}{existing[match.end():]}"

    if not existing:
        return replacement_head
    return f"{replacement_head}\n{existing}"


def _duplicate_marker_error() -> AppError:
    return AppError(
        "multiple bridge-owned description blocks have the same marker",
        code=6,
        category="remote_identity",
        diagnostics=[Diagnostic("description_marker_duplicate", "refusing ambiguous bridge description ownership")],
    )
