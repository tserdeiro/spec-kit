#!/usr/bin/env python3
"""A fake ``ocr`` executable covering the surfaces this extension consumes.

**The output shapes below are derived from the contract's description of the
engine's output, not from a capture of the pinned binary.** The contract makes
that capture a prerequisite of the engine stage, and only a person can produce
it: agents never install ``ocr``. Until ``tests/conformance/test_real_ocr.py``
has been run against the real binary and its captured output has replaced these
fixtures, **both this fake and the parser it exercises are unverified against
upstream**, and that test is what settles it.

What *is* verified here is the adapter's behaviour: that it tolerates cosmetic
variation (bullets, emphasis, tables), that it refuses to guess when the shape is
unrecognizable, and that every failure mode maps to the documented exit code.

State file (``SPECKIT_CODE_REVIEW_FAKE_OCR_STATE``)::

    {
      "version": "ocr version v1.8.3",
      "missing_subcommands": ["delegate rule"],
      "files": [
        {"path": "src/module.py"},
        {"path": "docs/guide.md", "included": false, "reason": "documentation"}
      ],
      "rules": {"src/module.py": ["Validate every input."]},
      "preview_failure": "exit-1" | "empty" | "unknown-format" | "no-file-section",
      "rule_failure": "exit-1" | "empty" | "unrelated",
      "style": "list" | "table",
      "record_invocations": "/path/to/log.txt"
    }
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


STATE_ENV = "SPECKIT_CODE_REVIEW_FAKE_OCR_STATE"
DEFAULT_VERSION = "ocr version v1.8.3"


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
    """Everything after the flags: the paths ``delegate rule`` was asked about."""

    paths: list[str] = []
    skip = False
    for index, argument in enumerate(argv):
        if skip:
            skip = False
            continue
        if argument.startswith("--"):
            skip = argument in ("--repo", "--rule", "--from", "--to", "--exclude")
            continue
        if index < 2:  # "delegate", "preview"/"rule"
            continue
        paths.append(argument)
    return paths


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
    if failure == "no-file-section":
        sys.stdout.write("# Delegate preview\n\n- **Mode**: range\n- **From**: abc\n- **To**: def\n")
        return 0

    files = state.get("files")
    if files is None:
        files = [{"path": "src/module.py"}]
    reviewable = sum(1 for entry in files if entry.get("included", True))
    # The shape v1.8.3 actually prints, captured from the real binary and
    # transcribed here (see tests/conformance/evidence/real-ocr.md):
    #
    #     # Files (1 reviewable / 2 total)
    #
    #     - mode: range
    #     - from: HEAD~1
    #     ...
    #
    #     ~~- `docs/guide.md` [modified] +1/-0 (excluded: unsupported_ext)~~
    #       - `src/m.py` [modified] +1/-0
    #
    # Excluded entries are struck through, wrapper including the dash; included
    # entries are indented two spaces; the metadata are list items inside the
    # same section.
    lines = [
        f"# Files ({reviewable} reviewable / {len(files)} total)",
        "",
        f"- mode: {'range' if _flag(argv, '--from') else 'workspace'}",
    ]
    if _flag(argv, "--from"):
        lines.append(f"- from: {_flag(argv, '--from')}")
        lines.append(f"- to: {_flag(argv, '--to')}")
        lines.append(f"- merge_base: {_flag(argv, '--from')}")
    lines.extend(["- total_insertions: 2", "- total_deletions: 0", ""])

    if state.get("style") == "table":
        # Not a shape the real binary emits: kept as the adapter's tolerance
        # test, which is why it is opt-in rather than the default.
        lines.extend(["| File | State | Reason |", "| --- | --- | --- |"])
        for entry in files:
            included = entry.get("included", True)
            reason = entry.get("reason", "") if not included else ""
            lines.append(f"| {entry['path']} | {'included' if included else 'excluded'} | {reason} |")
    else:
        excludes = [item for item in (_flag(argv, "--exclude") or "").split(",") if item]
        for entry in files:
            path = entry["path"]
            status = entry.get("status", "modified")
            counts = entry.get("counts", "+1/-0")
            included = entry.get("included", True) and path not in excludes
            if included:
                lines.append(f"  - `{path}` [{status}] {counts}")
            else:
                reason = "user_exclude" if path in excludes else entry.get("reason", "unsupported_ext")
                lines.append(f"~~- `{path}` [{status}] {counts} (excluded: {reason})~~")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _rule(state: dict, argv: list[str]) -> int:
    failure = state.get("rule_failure")
    if failure == "exit-1":
        sys.stderr.write("delegate rule failed: the engine says no\n")
        return 1
    if failure == "empty":
        return 0
    if failure == "unrelated":
        sys.stdout.write("# Resolved rules\n\n## some/other/file.py\n\n- A rule for a file nobody asked about.\n")
        return 0

    paths = _positional_paths(argv)
    mapping = state.get("rules") or {}
    # The shape v1.8.3 actually prints: one numbered group per rule, the paths
    # it applies to, and the rule text under its own `#### Content` heading --
    # text that itself contains headings and list items, which is why the group
    # structure has to be read rather than sliced around.
    lines: list[str] = []
    groups: list[tuple[str, list[str]]] = []
    for path in paths:
        rules = mapping.get(path, ["Review this file against the repository's default expectations."])
        key = "\n".join(rules)
        for existing_key, members in groups:
            if existing_key == key:
                members.append(path)
                break
        else:
            groups.append((key, [path]))
    for number, (key, members) in enumerate(groups, start=1):
        lines.append(f"### Rule Group {number}: custom / {members[0]}")
        lines.append("")
        lines.append("Applies to:")
        for member in members:
            lines.append(f"- {member}")
        lines.append("")
        lines.append("#### Content")
        lines.append("")
        lines.append("## User-Specific Rules (Mandatory)")
        lines.append("")
        for rule in key.split("\n"):
            lines.append(rule)
        lines.append("")
    sys.stdout.write("\n".join(lines) + "\n")
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
