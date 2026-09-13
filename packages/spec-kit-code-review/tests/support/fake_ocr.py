#!/usr/bin/env python3
"""A fake ``ocr`` executable covering the surfaces this extension consumes.

**The JSON shapes below are captured from the real pinned binary**, open-code-
review v1.12.0 (494bf1c8d), run against a temporary repository with
``delegate preview --format json`` and ``delegate rule --format json`` --
see ``tests/conformance/evidence/real-ocr.md``. What is *not* verified is
whether every field this fake omits or defaults (e.g. ``background``) is
always present on the real binary's output; the adapter never depends on a
field this fake does not exercise.

State file (``SPECKIT_CODE_REVIEW_FAKE_OCR_STATE``)::

    {
      "version": "open-code-review v1.12.0 (494bf1c8d)",
      "missing_subcommands": ["delegate rule"],
      "files": [
        {"path": "src/module.py"},
        {"path": "docs/guide.md", "included": false, "reason": "documentation"}
      ],
      "rules": {"src/module.py": ["Validate every input."]},
      "preview_failure": "exit-1" | "empty" | "unknown-format" | "bad-schema",
      "rule_failure": "exit-1" | "empty" | "unrelated" | "bad-schema",
      "record_invocations": "/path/to/log.txt"
    }
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


STATE_ENV = "SPECKIT_CODE_REVIEW_FAKE_OCR_STATE"
DEFAULT_VERSION = "open-code-review v1.12.0 (494bf1c8d)"


def _state() -> dict:
    """The state file, found beside this executable or named by the env var.

    The sibling file is what makes this work under the deliberately minimal
    environment the extension runs the engine in: only a handful of enumerated
    variables are passed through, and a test fixture's own is not one of them.
    """

    candidates = [os.environ.get(STATE_ENV), str(Path(__file__).resolve().parent / "ocr-state.json")]
    for path in candidates:
        if not path:
            continue
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _record(state: dict, argv: list[str]) -> None:
    """Note the invocation, so a test can prove the engine was never run."""

    destination = state.get("record_invocations")
    if not destination:
        return
    try:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(" ".join(argv) + "\n")
    except OSError:
        pass


def _flag(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def _positional_paths(argv: list[str]) -> list[str]:
    """Everything after ``--``: the paths ``delegate rule`` was asked about.

    The real invocation, and this extension's own, always closes the flag list
    with ``--`` before the paths -- that is what stops a file named ``--rule``
    from being read as a second flag -- so a fake that only understands that
    shape is exercising the actual contract, not a more permissive one.
    """

    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def _preview(state: dict, argv: list[str]) -> int:
    failure = state.get("preview_failure")
    if failure == "exit-1":
        sys.stderr.write("delegate preview failed: the engine says no\n")
        return 1
    if failure == "empty":
        return 0
    if failure == "unknown-format":
        sys.stdout.write("Delegate preview complete. 3 changed entries were considered.\n")
        return 0
    if failure == "bad-schema":
        sys.stdout.write(
            json.dumps({"schema_version": "99", "mode": "range", "reviewable_files": [], "excluded_files": []}) + "\n"
        )
        return 0

    files = state.get("files")
    if files is None:
        files = [{"path": "src/module.py"}]

    reviewable_files: list[dict] = []
    excluded_files: list[dict] = []
    total_insertions = 0
    total_deletions = 0
    for entry in files:
        insertions = entry.get("insertions", 1)
        deletions = entry.get("deletions", 0)
        total_insertions += insertions
        total_deletions += deletions
        item = {
            "path": entry["path"],
            "status": entry.get("status", "modified"),
            "insertions": insertions,
            "deletions": deletions,
        }
        if entry.get("included", True):
            reviewable_files.append(item)
        else:
            item["exclude_reason"] = entry.get("reason", "unsupported_ext")
            excluded_files.append(item)

    payload = {
        "schema_version": "1",
        "mode": "range" if _flag(argv, "--from") else "workspace",
        "repository": _flag(argv, "--repo") or "",
        "total_files": len(files),
        "reviewable_count": len(reviewable_files),
        "excluded_count": len(excluded_files),
        "total_insertions": total_insertions,
        "total_deletions": total_deletions,
        "reviewable_files": reviewable_files,
        "excluded_files": excluded_files,
    }
    if _flag(argv, "--from"):
        payload["from"] = _flag(argv, "--from")
        payload["to"] = _flag(argv, "--to")
        payload["merge_base"] = _flag(argv, "--from")

    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


_DEFAULT_RULE = "Review this file against the repository's default expectations."


def _rule(state: dict, argv: list[str]) -> int:
    failure = state.get("rule_failure")
    if failure == "exit-1":
        sys.stderr.write("delegate rule failed: the engine says no\n")
        return 1
    if failure == "empty":
        return 0
    if failure == "unrelated":
        sys.stdout.write(
            json.dumps(
                {
                    "schema_version": "1",
                    "groups": [
                        {
                            "group_id": 1,
                            "source": "custom",
                            "pattern": "**/*",
                            "files": ["some/other/file.py"],
                            "rule": "A rule for a file nobody asked about.",
                        }
                    ],
                }
            )
            + "\n"
        )
        return 0
    if failure == "bad-schema":
        sys.stdout.write(json.dumps({"schema_version": "99", "groups": []}) + "\n")
        return 0

    paths = _positional_paths(argv)
    mapping = state.get("rules") or {}

    # One group per distinct rule text, covering every requested path whose
    # mapping includes it -- the same content-based grouping the real engine
    # does, and the reason a path can end up in more than one group.
    order: list[str] = []
    files_by_text: dict[str, list[str]] = {}
    for path in paths:
        for rule_text in mapping.get(path) or [_DEFAULT_RULE]:
            if rule_text not in files_by_text:
                files_by_text[rule_text] = []
                order.append(rule_text)
            files_by_text[rule_text].append(path)

    groups = [
        {
            "group_id": index,
            "source": "custom",
            "pattern": "**/*",
            "files": files_by_text[rule_text],
            "rule": rule_text,
        }
        for index, rule_text in enumerate(order, start=1)
    ]
    sys.stdout.write(json.dumps({"schema_version": "1", "groups": groups}) + "\n")
    return 0


def _rules_check(state: dict, argv: list[str]) -> int:
    """``rules check``. **Unverified**: the real flag shape is unknown.

    The contract names the surface but not its flags, so this mirrors the
    ``--repo``/``--rule`` convention of the delegation subcommands. Whether the
    pinned binary accepts ``--repo`` here at all is one of the things the
    real-binary conformance test settles.
    """

    if state.get("rules_check_failure"):
        sys.stderr.write("rules check failed\n")
        return 1
    paths = _positional_paths(argv)
    lines = ["# Rule cascade", ""]
    for path in paths:
        lines.append(f"## {path}")
        lines.append("- layer: repository (--rule)")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main(argv: list[str]) -> int:
    state = _state()
    _record(state, argv)

    if argv[:1] == ["--version"]:
        sys.stdout.write(f"{state.get('version', DEFAULT_VERSION)}\n")
        return int(state.get("version_exit_code", 0))

    if len(argv) >= 3 and argv[0] == "delegate" and argv[2] == "--help":
        subcommand = f"delegate {argv[1]}"
        if subcommand in (state.get("missing_subcommands") or []):
            sys.stderr.write(f'unknown command "{argv[1]}" for "ocr delegate"\n')
            return 1
        sys.stdout.write(f"Usage: ocr {subcommand} [flags]\n")
        return 0

    if argv[:2] == ["delegate", "preview"]:
        if "--background" in argv or "-B" in argv:
            sys.stderr.write("the review must never run in the background\n")
            return 1
        return _preview(state, argv)

    if argv[:2] == ["delegate", "rule"]:
        return _rule(state, argv)

    if argv[:2] == ["rules", "check"]:
        return _rules_check(state, argv)

    sys.stderr.write(f"fake ocr: unsupported invocation: {' '.join(argv)}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
