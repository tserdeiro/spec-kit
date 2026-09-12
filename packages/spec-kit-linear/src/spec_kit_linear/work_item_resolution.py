"""Resolve ``issue_key`` or ordered ``branch_names``/``pull_requests`` arrays."""

from __future__ import annotations

import os
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
from .parser import _matchable_lines

KEY_RE = re.compile(r"^(?P<team>[A-Za-z][A-Za-z0-9]*)-(?P<number>[0-9]+)$")
FEATURE_RE = re.compile(r"^[0-9]{3}-[^/]+$")
TRACKER_SECTION_RE = re.compile(
    r"(?ms)^##[ \t]+Work item[ \t]*\r?\n(?P<section>.*?)(?=^#{1,6}[ \t]+|\Z)"
)
TRACKER_LINE_RE = re.compile(
    r"(?m)^[ ]{0,3}-[ \t]+Tracker:[ \t]+Fixes[ \t]+"
    r"(?P<key>[A-Za-z][A-Za-z0-9]*-[0-9]+)[ \t]*$"
)
OBSERVATION_CONFLICT = Diagnostic(
    "work_item_identity_conflict",
    "multiple observations for one branch carry different Issue keys",
)
OBSERVATION_UNRESOLVED = Diagnostic(
    "work_item_unresolved",
    "native branch lookup returned no Issue",
    severity="warning",
)


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


def _strict_key(branch: str, team_key: str) -> str | None:
    pattern = re.compile(rf"^(?:[^/]+/)?{re.escape(team_key)}-(\d+)(?:-.*)?$", re.IGNORECASE)
    match = pattern.fullmatch(branch)
    return f"{team_key.upper()}-{int(match.group(1))}" if match else None


def _tracker_keys(body: object, team_key: str, source: str) -> list[str]:
    if body is None:
        return []
    if not isinstance(body, str):
        raise _input(f"{source}.body must be a string or null")
    lines = body.splitlines()
    matchable = _matchable_lines(lines)
    visible = "\n".join(line if is_matchable else "" for line, is_matchable in zip(lines, matchable))
    values = [
        match.group("key")
        for section in TRACKER_SECTION_RE.finditer(visible)
        for match in TRACKER_LINE_RE.finditer(section.group("section"))
    ]
    return list(dict.fromkeys(_key(value, team_key, f"{source}.body Work item Tracker") for value in values))


def _entry(
    kind: str,
    branch: str,
    *,
    keys: list[str] | None = None,
    status: str = "active",
    diagnostics: list[Diagnostic] | None = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "branch": branch,
        "keys": keys or [],
        "status": status,
        "diagnostics": diagnostics or [],
    }


def _observations(payload: Mapping[str, object], team_key: str) -> tuple[str | None, list[dict[str, object]]]:
    issue_key = payload.get("issue_key")
    if issue_key is not None:
        if set(payload) != {"issue_key"}:
            raise _input("issue_key cannot be combined with branch_names or pull_requests")
        if isinstance(issue_key, str) and FEATURE_RE.fullmatch(issue_key.strip()):
            return None, [_entry("issue", issue_key.strip(), status="excluded")]
        return _key(issue_key, team_key, "issue_key"), []

    unknown = set(payload) - {"branch_names", "pull_requests"}
    if unknown:
        raise _input(f"request contains unsupported fields: {', '.join(sorted(unknown))}")
    if not any(name in payload for name in ("branch_names", "pull_requests")):
        raise _input("request must contain issue_key, branch_names, or pull_requests")
    observations: list[dict[str, object]] = []
    branch_names = payload.get("branch_names")
    if branch_names is not None:
        if not isinstance(branch_names, list):
            raise _input("branch_names must be an array")
        for value in branch_names:
            if not isinstance(value, str) or not value.strip():
                raise _input("branch_names must contain non-empty branch names")
            branch = value.strip()
            if FEATURE_RE.fullmatch(branch):
                observations.append(_entry("branch", branch, status="excluded"))
            else:
                strict = _strict_key(branch, team_key)
                observations.append(_entry("branch", branch, keys=[strict] if strict else []))

    pull_requests = payload.get("pull_requests")
    if pull_requests is not None:
        if not isinstance(pull_requests, list):
            raise _input("pull_requests must be an array")
        for value in pull_requests:
            if not isinstance(value, Mapping):
                raise _input("pull_requests entries must be objects")
            branch_value = value.get("head_branch")
            if not isinstance(branch_value, str) or not branch_value.strip():
                raise _input("pull_requests.head_branch must be a non-empty string")
            branch = branch_value.strip()
            if FEATURE_RE.fullmatch(branch):
                observations.append(_entry("pull_request", branch, status="excluded"))
                continue
            status = "active"
            diagnostics: list[Diagnostic] = []
            try:
                keys = _tracker_keys(value.get("body"), team_key, "pull_requests")
            except AppError as caught:
                if caught.category == "usage":
                    raise
                keys, status, diagnostics = [], "conflict", caught.diagnostics
            strict = _strict_key(branch, team_key)
            keys = list(dict.fromkeys(([strict] if strict else []) + keys))
            if len(keys) > 1:
                status = "conflict"
                diagnostics = [Diagnostic("work_item_identity_conflict", "branch and Tracker evidence disagree within one pull request")]
            observations.append(_entry("pull_request", branch, keys=keys, status=status, diagnostics=diagnostics))
    if not observations:
        raise _input("request must contain at least one observation")
    return None, observations


def _validate(
    context: RemoteIssueContext,
    team_id: str,
    team_key: str,
    expected: str | None = None,
) -> None:
    if context.team.id != team_id or context.team.key.casefold() != team_key.casefold():
        raise _error(
            "work_item_wrong_team",
            "Linear returned an Issue outside the repository's bound Team",
        )
    actual = _key(context.identifier, team_key, "Linear Issue identifier")
    if expected is not None and actual != expected:
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


def _result(
    item: Mapping[str, object],
    status: str,
    resolution: dict[str, object] | None = None,
    diagnostics: tuple[Diagnostic, ...] | list[Diagnostic] = (),
) -> dict[str, object]:
    return {
        "observation": {"kind": item["kind"], "value": item["branch"]},
        "status": status,
        "resolution": resolution,
        "diagnostics": [diagnostic.as_dict() for diagnostic in diagnostics],
    }


def resolve_work_item(
    payload: Mapping[str, object],
    *,
    root: Path,
    config_path: str | None = None,
    client_factory: Callable[[Credentials, str], LinearClient] | None = None,
) -> dict[str, object]:
    """Resolve one Issue or ordered ``branch_names``/``pull_requests`` arrays."""
    if not isinstance(payload, Mapping):
        raise _input("request must be a JSON object")

    load_dotenv_files(root)
    config_file = resolve_config_path(root, config_path)
    if not config_path and not os.environ.get("SPECKIT_LINEAR_CONFIG"):
        try:
            config_file.lstat()
        except FileNotFoundError:
            return _absent(config_file)

    config, _ = load_config(root, config_path)
    team_id, team_key = team_binding(config)
    issue_key, observations = _observations(payload, team_key)

    if issue_key is not None:
        endpoint = resolve_endpoint()
        credentials = load_credentials()
        client = client_factory(credentials, endpoint) if client_factory else LinearClient(credentials, endpoint=endpoint)
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
    if observations and observations[0]["status"] == "excluded" and observations[0]["kind"] == "issue":
        return {
            "code": 0,
            "category": "excluded",
            "status": "excluded",
            "message": "feature/task reference is outside work-item resolution",
            "resolution": None,
            "diagnostics": [
                Diagnostic(
                    "work_item_feature_excluded",
                    "feature/task reference is outside work-item resolution",
                    severity="info",
                ).as_dict()
            ],
        }

    active = [item for item in observations if item["status"] != "excluded"]
    if not active:
        return {
            "code": 0,
            "category": "excluded",
            "status": "excluded",
            "message": "feature/task observations are outside work-item resolution",
            "observations": [_result(item, "excluded") for item in observations],
        }
    endpoint = resolve_endpoint()
    credentials = load_credentials()
    client = client_factory(credentials, endpoint) if client_factory else LinearClient(credentials, endpoint=endpoint)
    native = client.resolve_branch_issues(list(dict.fromkeys(str(item["branch"]) for item in active)))
    branch_keys: dict[str, set[str]] = {}
    for item in active:
        keys = item["keys"]
        if keys:
            branch_keys.setdefault(str(item["branch"]), set()).update(
                value for value in keys if isinstance(value, str)
            )
    conflicting_branches = {str(item["branch"]) for item in active if item["status"] == "conflict"}
    conflicting_branches.update(branch for branch, keys in branch_keys.items() if len(keys) > 1)
    for branch, keys in branch_keys.items():
        context = native.get(branch)
        if context is None:
            continue
        try:
            native_key = _key(context.identifier, team_key, "Linear Issue identifier")
        except AppError:
            continue
        if native_key not in keys:
            conflicting_branches.add(branch)
    missing = list(
        dict.fromkeys(
            item["keys"][0]
            for item in active
            if len(item["keys"]) == 1
            and str(item["branch"]) not in conflicting_branches
            and native.get(str(item["branch"])) is None
        )
    )
    contexts = client.resolve_issue_contexts(missing) if missing else {}
    results: list[dict[str, object]] = []
    resolved_count = 0
    for item in observations:
        if item["status"] != "active":
            results.append(_result(item, item["status"], diagnostics=item["diagnostics"]))
            continue
        if str(item["branch"]) in conflicting_branches:
            results.append(_result(item, "conflict", diagnostics=item["diagnostics"] or [OBSERVATION_CONFLICT]))
            continue
        context = native.get(str(item["branch"]))
        if context is None and len(item["keys"]) == 1:
            context = contexts.get(item["keys"][0])
        if context is None:
            results.append(
                _result(
                    item,
                    "unresolved",
                    diagnostics=[OBSERVATION_UNRESOLVED],
                )
            )
            continue
        try:
            expected = item["keys"][0] if item["keys"] else None
            _validate(context, team_id, team_key, expected)
        except AppError as caught:
            results.append(_result(item, "conflict", diagnostics=caught.diagnostics))
            continue
        results.append(_result(item, "resolved", asdict(context)))
        resolved_count += 1

    failures = [item for item in results if item["status"] in {"unresolved", "conflict", "error"}]
    status = "resolved" if not failures else "partial" if resolved_count else str(failures[0]["status"])
    return {
        "code": 0,
        "category": "ok",
        "status": status,
        "message": "Linear work-item observations resolved",
        "observations": results,
    }
