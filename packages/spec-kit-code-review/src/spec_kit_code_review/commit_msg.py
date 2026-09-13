"""Native Git ``commit-msg`` entry point with no review setup side effects."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from .commit_policy import is_valid_commit_subject


def _first_line(path: Path) -> str:
    text = path.read_bytes().decode("utf-8", errors="replace")
    return text.splitlines()[0] if text else ""


def main(argv: Sequence[str] | None = None) -> int:
    """Validate Git's one message file, preserving it byte-for-byte."""

    if sys.version_info < (3, 11):
        print(
            "Spec Kit commit-msg requires Python 3.11+; install it or create .venv/bin/python, then retry",
            file=sys.stderr,
        )
        return 4

    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print(
            "Spec Kit commit-msg requires exactly one Git message file; repair the hook command and retry",
            file=sys.stderr,
        )
        return 4

    path = Path(arguments[0])
    try:
        subject = _first_line(path)
    except (OSError, ValueError) as error:
        print(
            f"Spec Kit commit-msg cannot read Git's message file {path}: {error}; restore a readable file and retry",
            file=sys.stderr,
        )
        return 4

    if not is_valid_commit_subject(subject):
        print(
            f"commit rejected: subject `{subject}` does not match type(scope): subject; use type(scope): subject",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
