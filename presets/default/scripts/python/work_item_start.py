#!/usr/bin/env python3
"""Resolve a Linear Issue and validate the branch before Git setup."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _common import die, run_git


KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[0-9]+$")
RESERVED_RE = re.compile(r"^[0-9]{3}(?:-T[0-9]{3})?-[^/]+$")


@dataclass(frozen=True)
class WorkItemContext:
    issue_key: str
    title: str
    description: str
    branch_name: str
    url: str = ""
    configured: bool = False


def _issue_key(value: str) -> str:
    key = value.strip()
    if not KEY_RE.fullmatch(key):
        die("Issue key must match TEAM-number")
    return key


def _resolver_script(repo_root: Path) -> Path | None:
    path = repo_root / ".specify" / "extensions" / "linear" / "scripts" / "python" / "resolve_work_item.py"
    return path if path.is_file() else None


def _main_root(repo_root: Path) -> Path | None:
    result = run_git("rev-parse", "--git-common-dir", cwd=repo_root)
    if result.returncode != 0:
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = repo_root / common
    return common.resolve().parent if common.name == ".git" else None


def _selected_config(repo_root: Path) -> bool:
    main_root = _main_root(repo_root)
    process_value = os.environ.get("SPECKIT_LINEAR_CONFIG")
    if process_value is not None:
        if process_value.strip():
            return True
        config = repo_root / "speckit-linear.yml"
        return os.path.lexists(config) or bool(main_root and os.path.lexists(main_root / "speckit-linear.yml"))
    repo_env = repo_root / ".speckit-linear.env"
    if not repo_env.exists() and main_root is not None:
        repo_env = main_root / ".speckit-linear.env"
    env_paths = [repo_env, Path.home() / ".config/speckit-linear/env"]
    for path in env_paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            continue
        selected = None
        for raw in lines:
            key, separator, value = raw.strip().partition("=")
            key = key.strip()
            if key != "SPECKIT_LINEAR_CONFIG":
                continue
            if not separator:
                die("selected Linear configuration is malformed")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            selected = value
        if selected is not None:
            if selected:
                return True
            break
    config = repo_root / "speckit-linear.yml"
    if os.path.lexists(config):
        return True
    return bool(main_root and os.path.lexists(main_root / "speckit-linear.yml"))


def _configured(repo_root: Path) -> bool:
    selected = _selected_config(repo_root)
    extension = repo_root / ".specify" / "extensions" / "linear"
    source = extension / "src"
    if not source.is_dir():
        return selected
    try:
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        from spec_kit_linear.config import resolve_config_path
        from spec_kit_linear.env_files import load_dotenv_files

        environment = dict(os.environ)
        load_dotenv_files(repo_root, environment)
        selected_path = environment.get("SPECKIT_LINEAR_CONFIG")
        return bool(selected_path) or os.path.lexists(resolve_config_path(repo_root, selected_path))
    except Exception:
        die("cannot inspect installed Linear configuration")


def _diagnostic(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        details = payload.get("diagnostics")
        if isinstance(details, list):
            messages = [item.get("message") for item in details if isinstance(item, dict)]
            if any(isinstance(message, str) and message.strip() for message in messages):
                return "; ".join(message.strip() for message in messages if isinstance(message, str) and message.strip())
    return fallback


def _native(repo_root: Path, script: Path, issue_key: str) -> WorkItemContext | None:
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(repo_root)],
        cwd=repo_root,
        input=json.dumps({"issue_key": issue_key}),
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("configured Linear work-item resolver returned invalid JSON")
    if result.returncode != 0:
        die(f"configured Linear work-item resolution failed: {_diagnostic(payload, 'resolver failed')}")
    status = payload.get("status") if isinstance(payload, dict) else None
    if status == "absent":
        return None
    if status != "resolved" or not isinstance(payload, dict):
        die(f"configured Linear work-item resolution failed: {_diagnostic(payload, 'resolver returned no Issue')}")
    resolution = payload.get("resolution")
    if not isinstance(resolution, dict):
        die("configured Linear work-item resolution returned no Issue context")
    branch = resolution.get("branch_name")
    title = resolution.get("title")
    description = resolution.get("description")
    identifier = resolution.get("identifier")
    url = resolution.get("url", "")
    if not all(isinstance(value, str) and value.strip() for value in (branch, title, identifier)):
        die("configured Linear work-item resolution returned incomplete Issue context")
    if not isinstance(description, str) or not isinstance(url, str):
        die("configured Linear work-item resolution returned malformed Issue context")
    return WorkItemContext(identifier, title, description, branch, url, True)


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")


def _validate_branch(repo_root: Path, branch: str) -> None:
    if not branch or branch == "HEAD" or branch.startswith("-"):
        die("Issue branch name is invalid: HEAD and leading-dash names are not allowed")
    if RESERVED_RE.fullmatch(branch):
        die(f"Issue branch name collides with a reserved feature/task name: {branch}")
    checked = run_git("check-ref-format", "--branch", branch, cwd=repo_root)
    if checked.returncode != 0 or checked.stdout.strip() != branch:
        die(f"Issue branch name is not a valid Git branch: {branch}")
    ref_checked = run_git("check-ref-format", f"refs/heads/{branch}", cwd=repo_root)
    if ref_checked.returncode != 0:
        die(f"Issue branch name is not a valid Git ref: {branch}")


def start(
    repo_root: Path,
    issue_key: str,
    title: str | None = None,
    description: str = "",
) -> WorkItemContext:
    """Return native Issue context or derive an unconfigured default branch."""
    key = _issue_key(issue_key)
    script = _resolver_script(repo_root)
    context = _native(repo_root, script, key) if script else None
    if context is None and script is None and _configured(repo_root):
        die("Linear is configured but its installed work-item resolver is unavailable; reinstall the Linear extension")
    if context is None:
        if not isinstance(title, str) or not title.strip():
            die("Linear configuration is absent; provide the Issue title to derive the work-item branch")
        slug = _slug(title)
        if not slug:
            die("Issue title must contain letters or numbers to derive the work-item branch")
        context = WorkItemContext(key, title.strip(), description, f"{key.casefold()}-{slug}")
    _validate_branch(repo_root, context.branch_name)
    return context


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or len(values) > 2:
        die("usage: work_item_start.py <issue-key> [title]")
    context = start(Path.cwd(), values[0], values[1] if len(values) == 2 else None)
    print(json.dumps(asdict(context), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
