#!/usr/bin/env python3
"""ignore-entries: add the installer's cache and payload-venv directories
to .gitignore when git check-ignore does not already cover them."""

from __future__ import annotations

import sys
from pathlib import Path

from _common import die, run_git

_ENTRIES = (
    ".specify/extensions/.cache/", ".specify/presets/.cache/",
    ".specify/integrations/.cache/", ".specify/extensions/*/.venv/",
)
_HEADER = "# tserdeiro/spec-kit installer state"

def add_ignore_entries(repo_root: Path, fix: bool) -> int:
    gitignore = repo_root / ".gitignore"
    missing = [e for e in _ENTRIES if run_git("check-ignore", "-q", e.replace("*", "x"), cwd=repo_root).returncode != 0]
    if not missing:
        print("ignore: nothing to do")
        return 0
    if not fix:
        for entry in missing:
            print(f"ignore: {entry} is not covered by .gitignore -- run with --fix")
        return 0
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    header = "" if _HEADER in existing else (f"{_HEADER}\n" if not gitignore.is_file() else f"\n{_HEADER}\n")
    with gitignore.open("a", encoding="utf-8") as handle:
        handle.write(header + "".join(f"{entry}\n" for entry in missing))
    for entry in missing:
        print(f"ignore: added {entry} to .gitignore")
    return 0

def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("true", "false"):
        die("usage: ignore_entries.py <true|false>")
    return add_ignore_entries(Path.cwd(), argv[0] == "true")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
