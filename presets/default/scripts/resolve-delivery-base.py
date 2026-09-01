#!/usr/bin/env python3
"""Resolve and validate the repository delivery base."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(".specify/extensions/git/git-config.yml")
REEXEC_MARKER = "SPECKIT_DELIVERY_BASE_REEXEC"


class ResolutionError(Exception):
    """A user-actionable delivery-base error."""


def _load_yaml_module() -> Any:
    try:
        import yaml

        return yaml
    except ModuleNotFoundError as error:
        if os.environ.get(REEXEC_MARKER):
            raise ResolutionError(
                "the Specify runtime does not provide the required PyYAML dependency"
            ) from error
        specify = shutil.which("specify")
        if specify is None:
            raise ResolutionError(
                "PyYAML is unavailable and the Specify executable was not found"
            ) from error
        try:
            launcher = Path(specify).read_text(encoding="utf-8").splitlines()[0]
            interpreter = shlex.split(launcher.removeprefix("#!"))
        except (OSError, UnicodeError, IndexError, ValueError) as launcher_error:
            raise ResolutionError(
                f"cannot resolve the Specify Python runtime from {specify}: {launcher_error}"
            ) from launcher_error
        if not launcher.startswith("#!") or not interpreter:
            raise ResolutionError(f"the Specify executable has no usable shebang: {specify}")
        environment = os.environ.copy()
        environment[REEXEC_MARKER] = "1"
        try:
            os.execvpe(
                interpreter[0],
                [*interpreter, str(Path(__file__).resolve())],
                environment,
            )
        except OSError as exec_error:
            raise ResolutionError(
                f"cannot start the Specify Python runtime: {exec_error}"
            ) from exec_error
        raise AssertionError("os.execvpe returned unexpectedly")


try:
    yaml = _load_yaml_module()
except ResolutionError as error:
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(2) from error
BaseResolver = yaml.resolver.BaseResolver


class UniqueSafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ResolutionError("configuration mapping keys must be scalar") from error
        if duplicate:
            raise ResolutionError(f"duplicate configuration key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueSafeLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _load_config() -> Mapping[Any, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        payload = yaml.load(
            CONFIG_PATH.read_text(encoding="utf-8"), Loader=UniqueSafeLoader
        )
    except (OSError, UnicodeError, yaml.YAMLError, ResolutionError) as error:
        raise ResolutionError(f"cannot read {CONFIG_PATH}: {error}") from error
    if not isinstance(payload, Mapping):
        raise ResolutionError(f"{CONFIG_PATH} must contain a YAML mapping at its root")
    return payload


def _run(argv: list[str], label: str) -> str:
    try:
        result = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
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
    config = _load_config()
    trunk = config.get("trunk")
    if trunk is not None and not isinstance(trunk, str):
        raise ResolutionError(f"{CONFIG_PATH} key 'trunk' must be a string or null")
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
