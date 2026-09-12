"""Resolve one configured Linear Issue for the internal JSON bridge."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path

from .config import load_config, resolve_config_path, team_binding
from .credentials import Credentials, load_credentials
from .endpoint import resolve_endpoint
from .env_files import load_dotenv_files
from .errors import AppError, Diagnostic
from .linear_client import LinearClient, RemoteIssueContext

KEY_RE = re.compile(r"^(?P<team>[A-Za-z][A-Za-z0-9]*)-(?P<number>[0-9]+)$")
FEATURE_RE = re.compile(r"^[0-9]{3}-[^/]+$")


def _error(
    code: str,
    message: str,
    *,
    category: str = "remote_identity",
    exit_code: int = 6,
) -> AppError:
    return AppError(
        message,
        code=exit_code,
        category=category,
        diagnostics=[Diagnostic(code, message)],
    )


def _input(message: str) -> AppError:
    return _error("work_item_input", message, category="usage", exit_code=2)


def _key(value: object, team_key: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _input(f"{source} must be a non-empty Issue key")
    match = KEY_RE.fullmatch(value.strip())
    if match is None:
        raise _input(f"{source} must match TEAM-number")
    if match.group("team").casefold() != team_key.casefold():
        raise _error(
            "work_item_wrong_team",
            f"{source} belongs to a different Linear Team",
        )
    return f"{team_key.upper()}-{int(match.group('number'))}"


def _validate(
    context: RemoteIssueContext,
    team_id: str,
    team_key: str,
    expected: str,
) -> None:
    if context.team.id != team_id or context.team.key.casefold() != team_key.casefold():
        raise _error(
            "work_item_wrong_team",
            "Linear returned an Issue outside the repository's bound Team",
        )
    actual = _key(context.identifier, team_key, "Linear Issue identifier")
    if actual != expected:
        raise _error(
            "work_item_identity_conflict",
            "Linear returned a different Issue than requested",
            category="conflict",
        )


def _absent(path: Path) -> dict[str, object]:
    diagnostic = Diagnostic(
        "linear_config_absent",
        "configuration file was not found",
        str(path),
        severity="info",
    )
    return {
        "code": 0,
        "category": "absent",
        "status": "absent",
        "message": "Linear configuration is absent; use the unconfigured work-item path",
        "resolution": None,
        "diagnostics": [diagnostic.as_dict()],
    }


def resolve_work_item(
    payload: Mapping[str, object],
    *,
    root: Path,
    config_path: str | None = None,
    client_factory: Callable[[Credentials, str], LinearClient] | None = None,
) -> dict[str, object]:
    """Resolve ``{"issue_key": "TEAM-123"}`` to native Issue context."""
    if not isinstance(payload, Mapping):
        raise _input("request must be a JSON object")
    if set(payload) != {"issue_key"}:
        raise _input("request must contain only issue_key")

    load_dotenv_files(root)
    config_file = resolve_config_path(root, config_path)
    if not config_file.exists():
        return _absent(config_file)

    config, _ = load_config(root, config_path)
    team_id, team_key = team_binding(config)
    raw_key = payload["issue_key"]
    if isinstance(raw_key, str) and FEATURE_RE.fullmatch(raw_key.strip()):
        diagnostic = Diagnostic(
            "work_item_feature_excluded",
            "feature/task references are outside work-item resolution",
            severity="info",
        )
        return {
            "code": 0,
            "category": "excluded",
            "status": "excluded",
            "message": "feature/task reference is outside work-item resolution",
            "resolution": None,
            "diagnostics": [diagnostic.as_dict()],
        }
    issue_key = _key(raw_key, team_key, "issue_key")

    endpoint = resolve_endpoint()
    credentials = load_credentials()
    client = (
        client_factory(credentials, endpoint)
        if client_factory
        else LinearClient(credentials, endpoint=endpoint)
    )
    context = client.resolve_issue_context(issue_key)
    _validate(context, team_id, team_key, issue_key)
    return {
        "code": 0,
        "category": "ok",
        "status": "resolved",
        "message": "Linear work item resolved",
        "resolution": asdict(context),
        "diagnostics": [],
    }
