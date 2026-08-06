"""Explicit and deterministic feature discovery for consumer repositories."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .errors import AppError, Diagnostic


FEATURE_RE = re.compile(r"^([0-9]{3})-(.+)$")
ID_RE = re.compile(r"^[0-9]{3}$")


def validate_feature_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise AppError(
            "feature must be a three-digit identifier such as 001",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("feature_id", "feature identifier must match NNN")],
        )
    return value


def discover_feature_directories(root: Path) -> dict[str, Path]:
    specs_root = root / "specs"
    if not specs_root.is_dir():
        raise AppError(
            "consumer repository has no specs directory",
            code=4,
            category="prerequisite",
            diagnostics=[Diagnostic("specs_missing", "expected specs/ directory", str(specs_root))],
        )
    result: dict[str, Path] = {}
    for child in sorted(specs_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        match = FEATURE_RE.fullmatch(child.name)
        if not match:
            continue
        identifier = match.group(1)
        if identifier in result:
            raise AppError(
                f"multiple directories use feature {identifier}",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("feature_duplicate", f"duplicate feature {identifier}", str(child))],
            )
        result[identifier] = child
    if not result:
        raise AppError(
            "no compatible feature directories were found under specs/",
            code=4,
            category="prerequisite",
            diagnostics=[Diagnostic("feature_missing", "expected specs/NNN-name/", str(specs_root))],
        )
    return result


def has_feature_directories(root: Path) -> bool:
    """True when the repository has at least one ``specs/NNN-slug/`` directory.

    Stage 5's short path (Issue -> branch -> PR -> review) needs no feature at
    all, so a repository that only tracks bugs and chores is a legitimate
    state, not a failure. ``push``/``status`` consult this before selecting a
    feature so they can reconcile work items in such a repository instead of
    exiting on a prerequisite that does not apply to it.
    """

    specs_root = root / "specs"
    if not specs_root.is_dir():
        return False
    return any(child.is_dir() and FEATURE_RE.fullmatch(child.name) for child in specs_root.iterdir())


def _feature_from_feature_json(root: Path) -> str | None:
    path = root / ".specify" / "feature.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(
            "could not parse .specify/feature.json",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("feature_json", str(error), str(path))],
        ) from error
    if not isinstance(data, dict):
        raise AppError(
            ".specify/feature.json must contain an object",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("feature_json", "expected an object", str(path))],
        )
    for key in ("feature", "feature_number", "number", "id"):
        value = data.get(key)
        if isinstance(value, str) and ID_RE.fullmatch(value):
            return value
    # Spec Kit's native scripts (.specify/scripts/bash/common.sh) persist a
    # "feature_directory" path such as "specs/001-repository-file-sync"
    # rather than a bare NNN identifier.
    directory = data.get("feature_directory")
    if isinstance(directory, str):
        segment = directory.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        match = FEATURE_RE.fullmatch(segment)
        if match:
            return match.group(1)
    return None


def _run_git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), *args], check=False, text=True, capture_output=True)
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _feature_from_git_ref(root: Path) -> str | None:
    """Doc "Descubrimiento de feature" step 3: branch/worktree con identificador valido.

    Tried only after ``.specify/feature.json`` and only when neither an
    explicit ``--feature`` nor ``--all`` was requested. Checks, in order:
    the current branch's final path segment (so both ``001-slug`` and
    ``feature/001-slug`` resolve), then the linked worktree's top-level
    directory name (Spec Kit can materialize one Git worktree per feature,
    named after it). Never touches the network; a detached HEAD, a bare
    repository, or a name that does not match ``NNN-slug`` all yield
    ``None`` rather than raising, since this is only one step of an
    implicit resolution chain that still has a further fallback.
    """

    candidates: list[str] = []
    branch = _run_git(root, "symbolic-ref", "--short", "-q", "HEAD")
    if branch:
        candidates.append(branch.rsplit("/", 1)[-1])
    worktree_root = _run_git(root, "rev-parse", "--show-toplevel")
    if worktree_root:
        candidates.append(Path(worktree_root).name)
    for candidate in candidates:
        match = FEATURE_RE.fullmatch(candidate)
        if match:
            return match.group(1)
    return None


def select_features(
    root: Path,
    *,
    explicit_feature: str | None,
    current: bool,
    all_features: bool,
) -> list[Path]:
    """Select feature directories without silently choosing an ambiguous one."""

    if sum(bool(item) for item in (explicit_feature, current, all_features)) > 1:
        raise AppError(
            "choose only one of --feature, --current, or --all",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("feature_selection", "feature selectors are mutually exclusive")],
        )
    available = discover_feature_directories(root)
    if explicit_feature:
        identifier = validate_feature_id(explicit_feature)
        if identifier not in available:
            raise AppError(
                f"feature {identifier} was not found",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("feature_unknown", f"no specs/{identifier}-*/ directory", str(root / "specs"))],
            )
        return [available[identifier]]
    if all_features:
        return [available[key] for key in sorted(available)]
    # Doc "Descubrimiento de feature": .specify/feature.json (step 2) before
    # branch/worktree (step 3), before the single-directory fallback (step 4).
    current_identifier = _feature_from_feature_json(root) or _feature_from_git_ref(root)
    if current or current_identifier:
        if current_identifier is None:
            raise AppError(
                "--current requires .specify/feature.json or a branch/worktree name matching NNN-slug",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("feature_current", "could not determine current feature", str(root / ".specify/feature.json"))],
            )
        if current_identifier not in available:
            raise AppError(
                f"current feature {current_identifier} was not found",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("feature_unknown", "current feature directory is missing", str(root / "specs"))],
            )
        return [available[current_identifier]]
    if len(available) == 1:
        return list(available.values())
    raise AppError(
        "feature selection is ambiguous; pass --feature NNN, --current, or --all",
        code=2,
        category="usage",
        diagnostics=[Diagnostic("feature_ambiguous", "multiple compatible feature directories", str(root / "specs"))],
    )

