#!/usr/bin/env python3
"""Resolve and validate the repository delivery base."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(".specify/extensions/git/git-config.yml")
YAML_NULLS = {"null", "Null", "NULL", "~"}
YAML_BOOLEANS = {
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "y",
    "n",
}
YAML_NUMBER = re.compile(
    r"[-+]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?(?:e[-+]?[0-9]+)?|\.(?:inf|nan))",
    re.IGNORECASE,
)
YAML_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ResolutionError(Exception):
    """A user-actionable delivery-base error."""


def _quoted_tail_is_valid(tail: str) -> bool:
    return not tail or (tail[0].isspace() and tail.lstrip().startswith("#"))


def _decode_double_quoted(raw: str) -> str:
    try:
        value, end = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError as error:
        raise ResolutionError(f"invalid double-quoted trunk string: {error.msg}") from error
    if not isinstance(value, str) or not _quoted_tail_is_valid(raw[end:]):
        raise ResolutionError("trunk must contain one quoted string")
    return value


def _decode_single_quoted(raw: str) -> str:
    value: list[str] = []
    index = 1
    while index < len(raw):
        if raw[index] != "'":
            value.append(raw[index])
            index += 1
            continue
        if index + 1 < len(raw) and raw[index + 1] == "'":
            value.append("'")
            index += 2
            continue
        if not _quoted_tail_is_valid(raw[index + 1 :]):
            raise ResolutionError("trunk must contain one quoted string")
        return "".join(value)
    raise ResolutionError("invalid single-quoted trunk string: closing quote is missing")


def _decode_plain(raw: str) -> str | None:
    for index, character in enumerate(raw):
        if character == "#" and (index == 0 or raw[index - 1].isspace()):
            raw = raw[:index]
            break
    value = raw.strip()
    if not value or value in YAML_NULLS:
        return None
    if value.lower() in YAML_BOOLEANS or YAML_NUMBER.fullmatch(value) or YAML_DATE.fullmatch(value):
        raise ResolutionError("numeric-, date-, and boolean-looking trunk values must be quoted")
    if value[0] in "!&*|>{[" or value[0] in "\"'":
        raise ResolutionError("trunk must be one plain or quoted string")
    return value


def _decode_trunk(raw: str) -> str | None:
    value = raw.lstrip()
    if value.startswith('"'):
        return _decode_double_quoted(value)
    if value.startswith("'"):
        return _decode_single_quoted(value)
    return _decode_plain(value)


def _load_trunk() -> str | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ResolutionError(f"cannot read {CONFIG_PATH}: {error}") from error
    trunk: str | None = None
    found = False
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[0].isspace():
            continue
        if stripped.startswith(("[", "{", "-")):
            raise ResolutionError(f"{CONFIG_PATH}:{number} must be a top-level mapping entry")
        key, separator, raw = line.partition(":")
        if not separator:
            raise ResolutionError(f"{CONFIG_PATH}:{number} must be a top-level mapping entry")
        if key.strip() != "trunk":
            continue
        if found:
            raise ResolutionError(f"duplicate configuration key: 'trunk' at line {number}")
        found = True
        trunk = _decode_trunk(raw)
    return trunk


def _run(argv: list[str], label: str) -> str:
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True)
    except OSError as error:
        raise ResolutionError(f"cannot run {label}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise ResolutionError(f"{label} failed: {detail}")
    lines = result.stdout.splitlines()
    if len(lines) != 1 or not lines[0]:
        raise ResolutionError(f"{label} must return exactly one non-empty branch name")
    return lines[0]


def _validate(base: str, source: str) -> str:
    try:
        result = subprocess.run(
            ["git", "check-ref-format", "--branch", base],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise ResolutionError(f"cannot validate {source}: {error}") from error
    if result.returncode != 0:
        raise ResolutionError(f"{source} is not a valid Git branch name: {base!r}")
    return base


def resolve() -> str:
    trunk = _load_trunk()
    if trunk:
        return _validate(trunk, f"{CONFIG_PATH} key 'trunk'")
    fallback = _run(
        ["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"],
        "GitHub default-branch lookup",
    )
    return _validate(fallback, "GitHub default branch")


def main() -> int:
    try:
        base = resolve()
    except ResolutionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
