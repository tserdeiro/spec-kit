#!/usr/bin/env python3
"""Resolve and validate the repository delivery base."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as error:
    yaml = None
    YAML_IMPORT_ERROR = error
else:
    YAML_IMPORT_ERROR = None

CONFIG_PATH = Path(".specify/extensions/git/git-config.yml")
BOOTSTRAP_MARKER = "SPECKIT_DELIVERY_BASE_BOOTSTRAPPED"


class ResolutionError(Exception):
    """A user-actionable delivery-base error."""


def _specify_python() -> Path:
    specify = shutil.which("specify")
    if specify is None:
        raise ResolutionError(
            "PyYAML is unavailable and specify is not on PATH; install the pinned Specify CLI"
        )
    try:
        launcher = Path(specify).resolve(strict=True)
        with launcher.open("rb") as stream:
            first_line = stream.readline(4097)
    except OSError as error:
        raise ResolutionError(f"cannot inspect Specify launcher {specify}: {error}") from error
    if len(first_line) > 4096 or not first_line.startswith(b"#!"):
        raise ResolutionError(f"Specify launcher {launcher} has no safe Python shebang")
    try:
        shebang = first_line[2:].strip().decode("utf-8")
    except UnicodeError as error:
        raise ResolutionError(f"Specify launcher {launcher} has an invalid shebang") from error
    interpreter = Path(shebang)
    if (
        not interpreter.is_absolute()
        or re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", interpreter.name) is None
        or not interpreter.is_file()
        or not os.access(interpreter, os.X_OK)
    ):
        raise ResolutionError(f"Specify launcher {launcher} has no safe Python shebang")
    return interpreter


def _require_yaml() -> Any:
    if yaml is not None:
        return yaml
    if os.environ.get(BOOTSTRAP_MARKER) == "1":
        raise ResolutionError(
            f"the pinned Specify Python cannot import PyYAML: {YAML_IMPORT_ERROR}"
        )
    interpreter = _specify_python()
    environment = os.environ.copy()
    environment[BOOTSTRAP_MARKER] = "1"
    try:
        os.execve(
            str(interpreter),
            [str(interpreter), str(Path(__file__).resolve()), *sys.argv[1:]],
            environment,
        )
    except OSError as error:
        raise ResolutionError(f"cannot start the pinned Specify Python: {error}") from error
    raise AssertionError("os.execve returned unexpectedly")


def _load_trunk() -> str | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        source = CONFIG_PATH.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ResolutionError(f"cannot read {CONFIG_PATH}: {error}") from error

    yaml_module = _require_yaml()

    class UniqueKeySafeLoader(yaml_module.SafeLoader):
        def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
            self.flatten_mapping(node)
            result: dict[Any, Any] = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in result
                except TypeError as error:
                    raise yaml_module.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        "found an unhashable key",
                        key_node.start_mark,
                    ) from error
                if duplicate:
                    raise yaml_module.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key {key!r}",
                        key_node.start_mark,
                    )
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        document = yaml_module.load(source, Loader=UniqueKeySafeLoader)
    except yaml_module.YAMLError as error:
        raise ResolutionError(f"invalid YAML in {CONFIG_PATH}: {error}") from error
    if not isinstance(document, dict):
        raise ResolutionError(f"{CONFIG_PATH} root must be a mapping")
    trunk = document.get("trunk")
    if trunk is None or trunk == "":
        return None
    if not isinstance(trunk, str):
        raise ResolutionError(f"{CONFIG_PATH} key 'trunk' must be a string, null, or empty")
    return trunk


def _single_output_record(value: str) -> str | None:
    match = re.fullmatch(r"([^\r\n]+)(?:\r\n|\r|\n)?", value)
    return match.group(1) if match else None


def _run(argv: list[str], label: str) -> str:
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True)
    except OSError as error:
        raise ResolutionError(f"cannot run {label}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise ResolutionError(f"{label} failed: {detail}")
    output = _single_output_record(result.stdout)
    if output is None:
        raise ResolutionError(f"{label} must return exactly one non-empty branch name")
    return output


def _validate(base: str, source: str) -> str:
    if re.fullmatch(r"@\{-[1-9][0-9]*\}", base):
        raise ResolutionError(f"{source} must not use Git reflog shorthand: {base!r}")
    try:
        result = subprocess.run(
            ["git", "check-ref-format", "--branch", base],
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError) as error:
        raise ResolutionError(f"cannot validate {source}: {error}") from error
    if result.returncode != 0:
        detail = f": {result.stderr.strip()}" if result.stderr.strip() else ""
        raise ResolutionError(f"{source} is not a valid Git branch name: {base!r}{detail}")
    if _single_output_record(result.stdout) != base:
        raise ResolutionError(f"{source} is not a literal Git branch name: {base!r}")
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
        _require_yaml()
        print(resolve())
    except ResolutionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
