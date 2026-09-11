"""Command-line boundary: onboard, push, status, doctor."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .config import (
    ROOT_CONFIG_FILENAME,
    SLUG_RE,
    UUID_RE,
    deep_merge,
    dump_yaml_subset,
    find_secret_keys,
    hooks_gate,
    lifecycle_state_ids,
    load_config,
    load_yaml_subset,
    repository_binding,
    team_binding,
    validate_config,
)
from .credentials import load_credentials
from .discovery import FEATURE_RE, has_feature_directories, select_features
from .domain import DesiredState
from .endpoint import (
    ALWAYS_ANNOUNCE_COMMANDS,
    DEFAULT_ENDPOINT,
    endpoint_banner,
    endpoint_report,
    is_default_endpoint,
    resolve_endpoint,
)
from .env_files import REPO_ENV_FILENAME, credential_source, load_dotenv_files, persist_process_credential, repo_env_path
from .errors import AppError, Diagnostic
from .git_refs import known_branches
from .github import PullRequestScan, cli_diagnostic as github_cli_diagnostic, scan_pull_requests
from .gitignore import ensure_entries as ensure_gitignore_entries, has_entry as has_gitignore_entry
from .lifecycle_registry import load_registry as load_lifecycle_registry, registry_diagnostics as lifecycle_registry_diagnostics
from .linear_client import LinearClient, RemoteTeamSummary, RemoteWorkflowState, RemoteWorkItem
from .mutation_executor import LinearMutationExecutor
from .parser import parse_feature
from .planner import build_push_plan, build_work_item_plan, snapshot_from_discovery
from .projection import project_feature
from .redaction import redact_structure, redact_text
from .reconciler import apply_plan
from .remote_discovery import RemoteDiscovery, discover_and_adopt
from .reporting import observation_report, render_status_table, render_work_item_table, status_report
from .view_discovery import conventional_view_name, resolve_shared_views_by_name
from .work_items import WorkItemState, derive_work_items, issue_key_pattern, issue_numbers
from .work_state import TaskWorkState, derive_task_states


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIGURATION = 3
EXIT_PREREQUISITE = 4


class _ArgumentParser(argparse.ArgumentParser):
    """Emit the public JSON error shape when --json accompanies bad input."""

    def error(self, message: str) -> None:
        if getattr(self, "json_requested", False):
            _write_json(
                {
                    "code": EXIT_USAGE,
                    "category": "usage",
                    "message": message,
                    "retryable": False,
                    "operations": [],
                    "diagnostics": [{"code": "arguments", "message": message, "severity": "error"}],
                }
            )
            raise SystemExit(EXIT_USAGE)
        super().error(message)


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--quiet", action="store_true", help="suppress human-readable detail")
    parser.add_argument("--config", help="path to the shared configuration")
    parser.add_argument("--root", help="explicit consumer repository root")


def _feature_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--feature", metavar="NNN", help="feature to select")
    parser.add_argument("--current", action="store_true", help="read the feature from .specify/feature.json, branch, or worktree")
    parser.add_argument("--all", action="store_true", dest="all_features", help="select every local feature")


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="spec-kit-linear", description="Project Spec Kit feature state into Linear")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="diagnose local and remote prerequisites; never mutates Linear")
    _common_arguments(doctor)
    doctor.add_argument("--offline", action="store_true", help="do not contact Linear")
    doctor.add_argument("--fix", action="store_true", help="apply the mechanical, local-only remediations doctor knows how to make")

    onboard = subparsers.add_parser("onboard", help="bind this repository to a Linear team; creates the missing bindings and PR-automation mappings, additively")
    _common_arguments(onboard)
    onboard.add_argument("--team-id", help="Linear Team UUID")
    onboard.add_argument("--team-key", help="Linear Team key; resolved to a UUID")
    onboard.add_argument("--repository", help="stable repository slug (required)")
    onboard.add_argument("--dry-run", action="store_true", help="preview the resolution and the config diff without writing")
    onboard.add_argument("--apply", action="store_true", help="write the configuration (the default when neither flag is given)")

    push = subparsers.add_parser("push", help="project the current feature state into Linear")
    _common_arguments(push)
    _feature_arguments(push)
    push.add_argument("--dry-run", action="store_true", help="preview the operations without writing (the default)")
    push.add_argument("--apply", action="store_true", help="apply the operations this invocation renders")
    push.add_argument("--hook", action="store_true", help="mark this invocation as lifecycle-hook originated; honors the hooks.* gates")

    status = subparsers.add_parser("status", help="report the local feature state and its Linear projection; never writes")
    _common_arguments(status)
    _feature_arguments(status)

    session_start = subparsers.add_parser("session-start", help="internal: the session_start runtime-event handler")
    session_start.add_argument("--root", help="explicit consumer repository root")

    post_tool_use = subparsers.add_parser("post-tool-use", help="internal: the post_tool_use runtime-event handler")
    post_tool_use.add_argument("--root", help="explicit consumer repository root")
    return parser


def _root_from_args(value: str | None) -> Path:
    root = Path(value).expanduser() if value else Path.cwd()
    try:
        resolved = root.resolve(strict=True)
    except FileNotFoundError as error:
        raise AppError(
            f"repository root does not exist: {root}",
            code=EXIT_USAGE,
            category="usage",
            diagnostics=[Diagnostic("root_missing", "--root must exist", str(root))],
        ) from error
    # `.speckit-linear.env`/operator-global env auto-loading must happen before
    # any credential or other environment variable is read. Every caller
    # resolves the consumer root through this function first, so this is the
    # one choke point that guarantees the ordering unconditionally; callers
    # that want the (rare) malformed-line diagnostics call load_dotenv_files
    # again themselves -- it is idempotent and cheap.
    load_dotenv_files(resolved)
    return resolved


def _runtime_checks(root: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if sys.version_info < (3, 11):
        raise AppError(
            "Python 3.11 or newer is required",
            code=EXIT_PREREQUISITE,
            category="prerequisite",
            diagnostics=[Diagnostic("python_version", "requires Python >= 3.11")],
        )
    diagnostics.append(Diagnostic("python", f"Python {sys.version.split()[0]}", severity="info"))
    if shutil.which("uv") is None:
        raise AppError(
            "uv is required by the extension runtime",
            code=EXIT_PREREQUISITE,
            category="prerequisite",
            diagnostics=[Diagnostic("uv_missing", "install uv before using this extension")],
        )
    diagnostics.append(Diagnostic("uv", "uv found on PATH", severity="info"))
    if not (root / ".specify").is_dir():
        raise AppError(
            "consumer repository is not initialized with Spec Kit",
            code=EXIT_PREREQUISITE,
            category="prerequisite",
            diagnostics=[Diagnostic("speckit_missing", "expected .specify/", str(root / ".specify"))],
        )
    diagnostics.append(Diagnostic("speckit", ".specify directory found", str(root / ".specify"), severity="info"))
    return diagnostics


def _git_check(root: Path) -> Diagnostic:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AppError(
            "consumer root is not inside a Git worktree",
            code=EXIT_PREREQUISITE,
            category="prerequisite",
            diagnostics=[Diagnostic("git_root", "initialize a Git repository", str(root))],
        )
    return Diagnostic("git", result.stdout.strip(), severity="info")


def _write_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    sys.stdout.write("\n")


def _success(message: str, *, diagnostics: list[Diagnostic], operations: list[dict[str, object]] | None = None) -> dict[str, Any]:
    return {
        "code": EXIT_SUCCESS,
        "category": "ok",
        "message": message,
        "retryable": False,
        "operations": operations or [],
        "diagnostics": [diagnostic.as_dict() for diagnostic in diagnostics],
    }


def _write_non_info_diagnostics(payload: Mapping[str, Any]) -> None:
    for diagnostic in payload["diagnostics"]:
        if diagnostic["severity"] == "info":
            continue
        location = ""
        if "path" in diagnostic:
            location = f" ({diagnostic['path']})"
        sys.stdout.write(f"{diagnostic['severity']}: {diagnostic['message']}{location}\n")


# One invocation, one endpoint, announced once. Module-level because the
# announcement has two triggers that cannot see each other: `main` (for the
# commands that always announce) and `_linear_client` (for every invocation
# that actually constructs a Linear client). `_begin_invocation` resets it, so
# a process that calls `main()` repeatedly -- the test suite -- never inherits
# a previous state.
_ENDPOINT_STATE: dict[str, Any] = {"endpoint": DEFAULT_ENDPOINT, "announced": False, "client_built": False}


def _begin_invocation(endpoint: str) -> None:
    _ENDPOINT_STATE.update({"endpoint": endpoint, "announced": False, "client_built": False})


def _announce_endpoint(endpoint: str) -> None:
    """Print the non-production endpoint notice; nothing can silence it.

    It goes to *stderr* precisely so that no output mode can drop it, and it
    is emitted before the command runs so that an invocation which then fails
    still carries it.
    """

    _ENDPOINT_STATE["endpoint"] = endpoint
    if _ENDPOINT_STATE["announced"] or is_default_endpoint(endpoint):
        return
    _ENDPOINT_STATE["announced"] = True
    sys.stderr.write(endpoint_banner(endpoint))
    sys.stderr.flush()


def _announces(command: str | None) -> bool:
    return command in ALWAYS_ANNOUNCE_COMMANDS or bool(_ENDPOINT_STATE["client_built"])


def _attach_endpoint_field(payload: dict[str, Any], command: str | None, endpoint: str) -> None:
    """Add the top-level `endpoint` object for a non-production destination.

    Its own field, not a diagnostic among others, so a machine consumer can
    tell without parsing prose that this result did not come from the
    production workspace.
    """

    if is_default_endpoint(endpoint) or not _announces(command):
        return
    payload["endpoint"] = endpoint_report(endpoint)


def _render(payload: dict[str, Any], as_json: bool, quiet: bool) -> None:
    if as_json:
        _write_json(payload)
        return
    if quiet:
        return
    sys.stdout.write(f"{payload['message']}\n")
    if payload["operations"]:
        sys.stdout.write(f"planned operations: {len(payload['operations'])}\n")
    _write_non_info_diagnostics(payload)


def _render_status(payload: dict[str, Any]) -> None:
    sys.stdout.write(f"{payload['message']}\n")
    status = payload.get("status")
    task_rows = status.get("task_rows") if isinstance(status, Mapping) else None
    remote_only_rows = status.get("remote_only_issues") if isinstance(status, Mapping) else None
    work_item_rows = status.get("work_items") if isinstance(status, Mapping) else None
    sys.stdout.write(render_status_table(task_rows or [], remote_only_rows or []))
    if work_item_rows:
        sys.stdout.write("\n" + render_work_item_table(list(work_item_rows)))
    _write_non_info_diagnostics(payload)


def _render_push(payload: dict[str, Any]) -> None:
    sys.stdout.write(f"{payload['message']}\n")
    for operation in payload["operations"]:
        if not isinstance(operation, Mapping):
            continue
        kind = str(operation.get("kind", ""))
        target = str(operation.get("target", ""))
        sys.stdout.write(f"  {kind:<22} {target:<34} {_operation_display_name(operation)}\n")
    _write_non_info_diagnostics(payload)


def _operation_display_name(operation: Mapping[str, object]) -> str:
    input_values = operation.get("input")
    if isinstance(input_values, Mapping):
        for key in ("title", "name"):
            value = input_values.get(key)
            if isinstance(value, str) and value:
                return value
    return str(operation.get("target", ""))


# `doctor --fix` is a narrow allowlist of fixable diagnostics, each with a
# mechanical, LOCAL-only remediation. Every other diagnostic doctor emits
# stays a plain warning with its existing manual hint, unchanged by `--fix`.
# None of these ever issues a GraphQL mutation or touches `specs/`. A "fixed:"
# message prefix marks the diagnostics `--fix` actually resolved.
_CREDENTIALS_TEMPLATE = """# spec-kit-linear credentials (gitignored; never commit).
# Personal API key: Linear -> Settings -> API -> Personal API keys.
LINEAR_API_KEY=
"""


def _doctor_local_file_diagnostics(root: Path, *, fix: bool) -> list[Diagnostic]:
    """The credential file and its `.gitignore` entry, scaffolded on `--fix`."""

    diagnostics: list[Diagnostic] = []
    gitignore_path = root / ".gitignore"
    existing_lines = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()} if gitignore_path.exists() else set()
    if not has_gitignore_entry(existing_lines, REPO_ENV_FILENAME):
        if fix:
            added = ensure_gitignore_entries(gitignore_path, (REPO_ENV_FILENAME,))
            diagnostics.append(Diagnostic("fixed_gitignore", f"fixed: added missing .gitignore entries: {', '.join(added)}", severity="info"))
        else:
            diagnostics.append(
                Diagnostic(
                    "gitignore_missing_entries",
                    f".gitignore is missing an entry for {REPO_ENV_FILENAME}, which can carry credentials; run `doctor --fix`, or `onboard`",
                    severity="warning",
                )
            )

    recorded = credential_source()
    env_path = repo_env_path(root)
    if recorded is not None:
        variable, source = recorded
        diagnostics.append(Diagnostic("linear_credentials_source", f"{variable} defined in {source}", severity="info"))
    elif not env_path.exists():
        if fix:
            env_path.write_text(_CREDENTIALS_TEMPLATE, encoding="utf-8")
            diagnostics.append(
                Diagnostic(
                    "fixed_credentials_template",
                    f"fixed: wrote the credentials template at {REPO_ENV_FILENAME}; paste your LINEAR_API_KEY (Linear -> Settings -> API -> Personal API keys)",
                    str(env_path),
                    severity="info",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    "linear_credentials_missing_file",
                    f"no Linear credential found; run `doctor --fix` to write the {REPO_ENV_FILENAME} template "
                    "(or set LINEAR_API_KEY in ~/.config/speckit-linear/env for every repo)",
                    severity="warning",
                )
            )
    else:
        diagnostics.append(
            Diagnostic(
                "linear_credentials_empty",
                f"{REPO_ENV_FILENAME} exists but defines no LINEAR_API_KEY; paste your key (Linear -> Settings -> API -> Personal API keys)",
                str(env_path),
                severity="warning",
            )
        )
    return diagnostics


def run_doctor(args: argparse.Namespace) -> dict[str, Any]:
    root = _root_from_args(args.root)
    fix = bool(args.fix)
    diagnostics: list[Diagnostic] = list(load_dotenv_files(root))
    diagnostics.extend(_runtime_checks(root))
    diagnostics.append(_git_check(root))
    diagnostics.extend(_doctor_local_file_diagnostics(root, fix=fix))

    config, shared_path = load_config(root, args.config)
    diagnostics.append(Diagnostic("config", "shared configuration is valid", str(shared_path), severity="info"))
    if lifecycle_state_ids(config) is None:
        diagnostics.append(
            Diagnostic(
                "lifecycle_disabled",
                "lifecycle sync is disabled; add a 'lifecycle' section with completed_state_id/open_state_id to sync Txxx Issue state from tasks.md",
                severity="warning",
            )
        )
    else:
        diagnostics.append(Diagnostic("lifecycle", "lifecycle sync is enabled", severity="info"))
    diagnostics.append(github_cli_diagnostic(root, offline=bool(args.offline)))
    registry = load_lifecycle_registry(root)
    diagnostics.extend(lifecycle_registry_diagnostics(registry, lifecycle_enabled=hooks_gate(config, "lifecycle_enabled")))
    if has_feature_directories(root):
        select_features(root, explicit_feature=None, current=False, all_features=True)
        diagnostics.append(Diagnostic("artifacts", "compatible feature artifacts found", severity="info"))
    else:
        # A repository that only tracks bugs and chores has no feature
        # artifact to validate, and that is a working state, not a defect.
        diagnostics.append(Diagnostic("artifacts", "no specs/NNN-* directory; push projects bugs and chores only", severity="info"))

    if args.offline:
        return _success("offline doctor checks passed", diagnostics=diagnostics)

    client = _linear_client()
    binding = client.inspect_binding(config)
    diagnostics.extend(
        [
            Diagnostic("linear_auth", f"authenticated with {client.credentials.scheme.replace('_', ' ')}", severity="info"),
            Diagnostic("linear_binding", "Workspace, Team, Project Label, and Shared Views were read successfully", severity="info"),
        ]
    )
    if binding.project_view_type.lower() != "project" or binding.issue_view_type.lower() != "issue":
        diagnostics.append(Diagnostic("shared_view_type", "configured Shared View types differ from the expected project/issue pair", severity="warning"))
    return _success("online doctor checks passed", diagnostics=diagnostics)


# `onboard` is the single entry path for a consumer repository: it resolves
# the workspace, the Team, the repository's `Repository` Project Label group
# and its `<slug>` child label, the two conventional Shared Views, and the
# Team's lifecycle workflow states -- all read-only, all by name -- and writes
# the committed root config. It never issues a single GraphQL mutation.
_REPOSITORY_LABEL_GROUP_NAME = "Repository"
_MISSING_FIELD_NAMES: dict[str, str] = {
    "project_label_group_id": "project_label_group",
    "project_label_id": "project_label",
    "project_view_id": "project_view",
    "issue_view_id": "issue_view",
}


def run_onboard(args: argparse.Namespace) -> dict[str, Any]:
    root = _root_from_args(args.root)
    if args.dry_run and args.apply:
        raise AppError(
            "choose only one of --dry-run or --apply",
            code=EXIT_USAGE,
            category="usage",
            diagnostics=[Diagnostic("onboard_mode", "onboard cannot both preview and write the configuration in the same invocation")],
        )
    apply_changes = args.apply or not args.dry_run

    if not args.repository:
        raise AppError(
            "onboard requires --repository",
            code=EXIT_USAGE,
            category="usage",
            diagnostics=[Diagnostic("onboard_repository_required", "pass --repository SLUG")],
        )
    if not SLUG_RE.fullmatch(args.repository):
        raise AppError(
            "--repository must use lowercase letters, numbers, and hyphens",
            code=EXIT_USAGE,
            category="usage",
            diagnostics=[Diagnostic("onboard_slug", "--repository is invalid")],
        )
    slug = args.repository

    client = _linear_client()
    diagnostics: list[Diagnostic] = list(load_dotenv_files(root))

    workspace_id = client.resolve_workspace_id()
    team = _resolve_team(client, args)
    diagnostics.append(Diagnostic("team", f"resolved Team '{team.key}' ({team.name})", severity="info"))

    repository_overlay: dict[str, Any] = {"slug": slug}
    diagnostics.extend(_resolve_repository_label(client, slug, repository_overlay))
    view_result = resolve_shared_views_by_name(client, slug)
    repository_overlay.update(view_result.resolved)
    diagnostics.extend(view_result.diagnostics)
    binding_operations = _plan_repository_bindings(slug, repository_overlay)
    if apply_changes and binding_operations:
        _create_repository_bindings(client, slug, repository_overlay, diagnostics)
    lifecycle_overlay, lifecycle_missing = _resolve_lifecycle(client, team.id, diagnostics)
    automation_operations = _plan_git_automations(client, team.id, lifecycle_overlay, diagnostics)

    root_path = (root / ROOT_CONFIG_FILENAME).resolve()
    existing: dict[str, Any] = load_yaml_subset(root_path) if root_path.exists() else {}
    secret_keys = find_secret_keys(existing)
    if secret_keys:
        raise AppError(
            "shared configuration must not contain secrets or operator identity",
            code=EXIT_CONFIGURATION,
            category="configuration",
            diagnostics=[Diagnostic("config_secret", f"remove '{key}' from shared configuration", str(root_path)) for key in secret_keys],
        )

    overlay: dict[str, Any] = {
        "schema_version": "1.0",
        "linear": {"workspace_id": workspace_id, "team_id": team.id, "team_key": team.key},
        "repository": repository_overlay,
    }
    if lifecycle_overlay is not None:
        overlay["lifecycle"] = lifecycle_overlay
    merged = deep_merge(existing, overlay)
    validate_config(merged, root_path, allow_unbound_repository=True)

    repository = merged.get("repository", {})
    missing = [name for field, name in _MISSING_FIELD_NAMES.items() if field not in repository]
    if not missing:
        client.inspect_binding(merged)
        diagnostics.append(Diagnostic("linear_binding", "Workspace, Team, Project Label, and Shared Views were read successfully", severity="info"))

    changes = {
        "config_path": str(root_path),
        "config_changes": _config_diff(existing, merged),
        # Repository bindings first, then whatever workflow state the Team
        # does not have; both are things a human creates in Linear by hand.
        "missing_remote_resources": missing + lifecycle_missing,
        "gitignore_entries_added": [],
        # The remote writes onboard performs: missing repository bindings and
        # missing Team PR-automation mappings, additive only.
        "binding_operations": binding_operations,
        "automation_operations": [
            f"team.automation.create {operation['input']['event']}" for operation in automation_operations
        ],
    }

    if apply_changes:
        root_path.parent.mkdir(parents=True, exist_ok=True)
        root_path.write_text(dump_yaml_subset(merged), encoding="utf-8")
        changes["gitignore_entries_added"] = ensure_gitignore_entries(root / ".gitignore", (REPO_ENV_FILENAME,))
        persisted = persist_process_credential(root)
        if persisted is not None:
            diagnostics.append(
                Diagnostic(
                    "onboard_credentials_persisted",
                    f"persisted LINEAR_API_KEY to {REPO_ENV_FILENAME} (gitignored) so later commands authenticate; "
                    "delete the file to keep the key per-invocation",
                    str(persisted),
                    severity="info",
                )
            )
        diagnostics.append(Diagnostic("onboard_apply", "configuration written", str(root_path), severity="info"))
        if automation_operations:
            executor = LinearMutationExecutor(client)
            for operation in automation_operations:
                executor.execute(operation)
            diagnostics.append(
                Diagnostic(
                    "automation_applied",
                    "created Team PR-automation mapping(s): " + ", ".join(operation["input"]["event"] for operation in automation_operations),
                    severity="info",
                )
            )
    else:
        diagnostics.append(Diagnostic("onboard_dry_run", "nothing was written; rerun without --dry-run to write the configuration", severity="info"))

    if missing:
        diagnostics.append(
            Diagnostic(
                "onboard_missing_remote",
                f"missing in Linear: {', '.join(missing)}; onboard creates them when it applies",
                severity="warning",
            )
        )
    else:
        diagnostics.append(Diagnostic("onboard_complete", "repository Project Label, child label, and both Shared Views are all bound", severity="info"))

    payload = _success(
        "onboard wrote the repository binding" if apply_changes else "onboard dry-run reviewed the repository binding",
        diagnostics=diagnostics,
    )
    payload["dry_run"] = not apply_changes
    payload["changes"] = changes
    return payload


def _resolve_team(client: LinearClient, args: argparse.Namespace) -> RemoteTeamSummary:
    if args.team_id:
        _validate_uuid_flag("--team-id", args.team_id)
        team = client.resolve_team_by_id(args.team_id)
        if args.team_key and team.key != args.team_key:
            raise AppError(
                "--team-key does not match the Team resolved from --team-id",
                code=6,
                category="remote_identity",
                diagnostics=[Diagnostic("team_key_mismatch", f"--team-id resolved to key '{team.key}', not '{args.team_key}'")],
            )
        return team
    if args.team_key:
        matches = client.find_team_by_key(args.team_key)
        if not matches:
            raise AppError(
                f"no Team was found with key '{args.team_key}'",
                code=6,
                category="remote_identity",
                diagnostics=[Diagnostic("team_key_not_found", f"no Team matches key '{args.team_key}'")],
            )
        if len(matches) > 1:
            raise AppError(
                f"multiple Teams match key '{args.team_key}'",
                code=6,
                category="remote_identity",
                diagnostics=[Diagnostic("team_key_ambiguous", f"'{args.team_key}' does not resolve to exactly one Team")],
            )
        return matches[0]
    raise AppError(
        "onboard requires --team-id or --team-key",
        code=EXIT_USAGE,
        category="usage",
        diagnostics=[Diagnostic("onboard_team_required", "pass --team-id or --team-key")],
    )


def _validate_uuid_flag(flag: str, value: str) -> None:
    if not UUID_RE.fullmatch(value):
        raise AppError(
            f"{flag} must be a UUID",
            code=EXIT_USAGE,
            category="usage",
            diagnostics=[Diagnostic("onboard_uuid", f"{flag} must be a UUID")],
        )


# The four bindings onboard creates when resolution left them missing, in
# dependency order: the child label needs the group, both views need the
# label. Ambiguity (2+ matches) still aborts during resolution — creation
# only ever fills a clean absence.
_BINDING_FIELDS = ("project_label_group_id", "project_label_id", "project_view_id", "issue_view_id")


def _plan_repository_bindings(slug: str, repository_overlay: dict[str, Any]) -> list[str]:
    """Name the missing bindings onboard will create, for the changes report."""

    labels = {
        "project_label_group_id": f"project.label.create '{_REPOSITORY_LABEL_GROUP_NAME}' (group)",
        "project_label_id": f"project.label.create '{slug}'",
        "project_view_id": f"view.create '{conventional_view_name(slug, 'Features')}'",
        "issue_view_id": f"view.create '{conventional_view_name(slug, 'Work')}'",
    }
    return [labels[field] for field in _BINDING_FIELDS if field not in repository_overlay]


def _create_repository_bindings(client: LinearClient, slug: str, repository_overlay: dict[str, Any], diagnostics: list[Diagnostic]) -> None:
    """Create the missing bindings, staged: each id feeds the next create."""

    executor = LinearMutationExecutor(client)

    def create(kind: str, input_values: dict[str, Any]) -> str:
        result = executor.execute({"kind": kind, "input": {"id": str(uuid.uuid4()), **input_values}})
        remote_id = result.get("id")
        if not isinstance(remote_id, str) or not remote_id:
            raise AppError(
                "Linear did not return the created resource's id",
                code=6,
                category="remote_identity",
                diagnostics=[Diagnostic("binding_create_id_missing", f"{kind} returned no id; re-run onboard to adopt whatever was created")],
            )
        return remote_id

    created: list[str] = []
    group_id = repository_overlay.get("project_label_group_id")
    if group_id is None:
        group_id = create("project.label.create", {"name": _REPOSITORY_LABEL_GROUP_NAME, "isGroup": True})
        repository_overlay["project_label_group_id"] = group_id
        created.append(f"Project Label Group '{_REPOSITORY_LABEL_GROUP_NAME}'")
    label_id = repository_overlay.get("project_label_id")
    if label_id is None:
        label_id = create("project.label.create", {"name": slug, "parentId": group_id})
        repository_overlay["project_label_id"] = label_id
        repository_overlay["project_label"] = slug
        created.append(f"Project Label '{slug}'")
    label_filter = {"labels": {"some": {"id": {"eq": label_id}}}}
    if "project_view_id" not in repository_overlay:
        name = conventional_view_name(slug, "Features")
        repository_overlay["project_view_id"] = create("view.create", {"name": name, "projectFilterData": label_filter, "shared": True})
        created.append(f"Shared View '{name}'")
    if "issue_view_id" not in repository_overlay:
        name = conventional_view_name(slug, "Work")
        repository_overlay["issue_view_id"] = create("view.create", {"name": name, "filterData": {"project": label_filter}, "shared": True})
        created.append(f"Shared View '{name}'")
    diagnostics.append(Diagnostic("binding_created", "created in Linear: " + ", ".join(created), severity="info"))


def _resolve_repository_label(client: LinearClient, slug: str, repository_overlay: dict[str, Any]) -> list[Diagnostic]:
    """Adopt the 'Repository' label group and its <slug> child label by name, read-only.

    Mirrors the 0/2+/1-match idiom used by
    :func:`view_discovery.resolve_shared_views_by_name`: 0 matches is a
    warning, 2+ matches always aborts (exit 6), and a single match must have
    the right identity shape (``isGroup`` for the group; parented under the
    resolved group for the child label) or aborts too.
    """

    diagnostics: list[Diagnostic] = []
    group_matches = tuple(item for item in client.find_project_labels_by_name(_REPOSITORY_LABEL_GROUP_NAME) if item.is_group)
    if not group_matches:
        diagnostics.append(
            Diagnostic(
                "project_label_group_missing",
                f"no Project Label Group named '{_REPOSITORY_LABEL_GROUP_NAME}' was found; onboard creates it when it applies",
                severity="warning",
            )
        )
        return diagnostics
    if len(group_matches) > 1:
        raise AppError(
            f"multiple Project Label Groups match name '{_REPOSITORY_LABEL_GROUP_NAME}'",
            code=6,
            category="remote_identity",
            diagnostics=[Diagnostic("project_label_group_ambiguous", f"'{_REPOSITORY_LABEL_GROUP_NAME}' does not resolve to exactly one Project Label Group")],
        )
    group_id = group_matches[0].id
    repository_overlay["project_label_group_id"] = group_id
    diagnostics.append(Diagnostic("project_label_group_adopted", f"adopted Project Label Group '{_REPOSITORY_LABEL_GROUP_NAME}' ({group_id})", severity="info"))

    candidates = tuple(item for item in client.find_project_labels_by_name(slug) if item.parent_id == group_id)
    if not candidates:
        diagnostics.append(
            Diagnostic(
                "project_label_missing",
                f"no Project Label named '{slug}' was found under '{_REPOSITORY_LABEL_GROUP_NAME}'; onboard creates it when it applies",
                severity="warning",
            )
        )
        return diagnostics
    if len(candidates) > 1:
        raise AppError(
            f"multiple Project Labels match name '{slug}' under '{_REPOSITORY_LABEL_GROUP_NAME}'",
            code=6,
            category="remote_identity",
            diagnostics=[Diagnostic("project_label_ambiguous", f"'{slug}' does not resolve to exactly one Project Label")],
        )
    label_id = candidates[0].id
    repository_overlay["project_label_id"] = label_id
    repository_overlay["project_label"] = slug
    diagnostics.append(Diagnostic("project_label_adopted", f"adopted Project Label '{slug}' ({label_id})", severity="info"))
    return diagnostics


# Installing the extension means you want Linear kept in sync, so `onboard`
# auto-configures the optional `lifecycle` section by resolving the Team's
# workflow states: the two endpoints (`completed`/`unstarted`) plus the two
# intermediate states vision steps 4-7 need, both of Linear type `started`
# and therefore told apart by name. Ambiguity is never fatal here: it is
# reported as a warning and onboarding continues, leaving whatever could not
# be resolved out of the configuration.
_LIFECYCLE_STATE_SPECS: dict[str, tuple[str, str | None]] = {
    "completed_state_id": ("completed", None),
    "open_state_id": ("unstarted", None),
    "started_state_id": ("started", "In Progress"),
    "review_state_id": ("started", "In Review"),
}
# Without these two the section means nothing, so failing to resolve either
# skips lifecycle entirely; the other two degrade instead (see
# planner._LIFECYCLE_FIELDS_BY_STATE) and are only reported as missing.
_LIFECYCLE_REQUIRED_FIELDS = ("completed_state_id", "open_state_id")
_LIFECYCLE_MISSING_NAMES: dict[str, str] = {"started_state_id": "started_state", "review_state_id": "review_state"}
# "In Review" is resolved by name only: two states share the `started` type,
# so a positional fallback would hand both fields the same id and silently
# stop distinguishing "in progress" from "ready for review".
_LIFECYCLE_NAME_ONLY_FIELDS = frozenset({"review_state_id"})
_LIFECYCLE_RESERVED_NAMES = frozenset({name.casefold() for _type, name in _LIFECYCLE_STATE_SPECS.values() if name is not None})


def _resolve_lifecycle(client: LinearClient, team_id: str, diagnostics: list[Diagnostic]) -> tuple[dict[str, str] | None, list[str]]:
    """Resolve the Team's four workflow states; report what stayed unresolved."""

    states = client.find_workflow_states_by_team(team_id)
    resolved = {field: _resolve_workflow_state_by_type(states, field, diagnostics) for field in _LIFECYCLE_STATE_SPECS}
    if any(resolved[field] is None for field in _LIFECYCLE_REQUIRED_FIELDS):
        diagnostics.append(
            Diagnostic(
                "lifecycle_skipped",
                "lifecycle auto-configuration was skipped because a workflow state could not be resolved unambiguously; "
                "add the 'lifecycle' section by hand to sync Txxx Issue state",
                severity="warning",
            )
        )
        return None, []
    overlay = {field: str(value) for field, value in resolved.items() if value is not None}
    missing = [name for field, name in _LIFECYCLE_MISSING_NAMES.items() if resolved[field] is None]
    for field, name in _LIFECYCLE_MISSING_NAMES.items():
        if resolved[field] is not None:
            continue
        preferred = _LIFECYCLE_STATE_SPECS[field][1]
        diagnostics.append(
            Diagnostic(
                f"lifecycle_{name}_missing",
                f"no Team workflow state named '{preferred}' was found; create it in Linear to project that step, "
                "or the tasks that reach it keep the state they already have",
                severity="warning",
            )
        )
    diagnostics.append(
        Diagnostic("lifecycle_configured", "lifecycle " + " ".join(f"{field}={value}" for field, value in overlay.items()), severity="info")
    )
    return overlay, missing


# The distribution's PR-automation semantics, mirrored from the derived state
# map: a draft PR is work in progress, a ready PR awaits review, a merge is
# done. `start` is Linear's event for a PR opened ready (or marked ready).
_AUTOMATION_EVENTS = (
    ("draft", "started_state_id"),
    ("start", "review_state_id"),
    ("merge", "completed_state_id"),
)


def _plan_git_automations(
    client: LinearClient, team_id: str, lifecycle_overlay: dict[str, str] | None, diagnostics: list[Diagnostic]
) -> list[dict[str, Any]]:
    """Plan the missing Team PR-automation mappings — additive and idempotent.

    A mapping the Team already has is never touched: same state produces no
    operation, a different state produces a warning and no operation.
    Branch-scoped rules are out of scope entirely.
    """

    if lifecycle_overlay is None:
        diagnostics.append(
            Diagnostic(
                "automation_skipped",
                "PR-automation sync was skipped because the lifecycle could not be resolved",
                severity="warning",
            )
        )
        return []
    existing = {state.event: state for state in client.find_git_automation_states(team_id) if state.target_branch_id is None}
    operations: list[dict[str, Any]] = []
    for event, field in _AUTOMATION_EVENTS:
        state_id = lifecycle_overlay.get(field)
        if state_id is None:
            continue  # the lifecycle resolution already warned about it
        current = existing.get(event)
        if current is None:
            operations.append(
                {
                    "kind": "team.automation.create",
                    "input": {"id": str(uuid.uuid4()), "teamId": team_id, "event": event, "stateId": state_id},
                }
            )
        elif current.state_id != state_id:
            diagnostics.append(
                Diagnostic(
                    "automation_conflict",
                    f"the Team maps PR '{event}' to '{current.state_name}', not this distribution's state; left untouched",
                    severity="warning",
                )
            )
    if not operations and "automation_conflict" not in {d.code for d in diagnostics}:
        diagnostics.append(Diagnostic("automation_complete", "the Team PR-automation mapping is already complete", severity="info"))
    if not client.has_github_integration():
        diagnostics.append(
            Diagnostic(
                "github_integration_missing",
                "no GitHub integration is connected to the workspace; the PR-automation mapping stays dormant until "
                "an admin connects it (Linear Settings -> Integrations -> GitHub, one time per workspace)",
                severity="warning",
            )
        )
    return operations


def _resolve_workflow_state_by_type(states: tuple[RemoteWorkflowState, ...], field: str, diagnostics: list[Diagnostic]) -> str | None:
    state_type, preferred_name = _LIFECYCLE_STATE_SPECS[field]
    candidates = tuple(state for state in states if state.type == state_type)
    if preferred_name is not None:
        named = tuple(state for state in candidates if state.name.strip().casefold() == preferred_name.casefold())
        if len(named) == 1:
            return named[0].id
        if len(named) > 1:
            diagnostics.append(
                Diagnostic("lifecycle_state_ambiguous", f"multiple Team workflow states are named '{preferred_name}'", severity="warning")
            )
            return None
        if field in _LIFECYCLE_NAME_ONLY_FIELDS:
            return None
        # A Team that names its in-progress state something else still
        # resolves positionally, but never onto a state reserved by name for
        # another field.
        candidates = tuple(state for state in candidates if state.name.strip().casefold() not in _LIFECYCLE_RESERVED_NAMES)
    if not candidates:
        diagnostics.append(Diagnostic("lifecycle_state_missing", f"no Team workflow state of type '{state_type}' was found", severity="warning"))
        return None
    if len(candidates) == 1:
        return candidates[0].id
    positions = [state.position for state in candidates]
    if len(set(positions)) != len(positions):
        listing = ", ".join(f"{state.id} (name={state.name!r}, position={state.position})" for state in candidates)
        diagnostics.append(
            Diagnostic("lifecycle_state_ambiguous", f"multiple Team workflow states of type '{state_type}' tie on position: {listing}", severity="warning")
        )
        return None
    chosen = min(candidates, key=lambda state: state.position)
    diagnostics.append(
        Diagnostic(
            "lifecycle_state_resolved",
            f"resolved {field} to '{chosen.id}' ({state_type}, lowest position among {len(candidates)} candidates)",
            severity="info",
        )
    )
    return chosen.id


def _config_diff(before: Mapping[str, Any], after: Mapping[str, Any], *, prefix: str = "") -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    for key in sorted(set(before) | set(after)):
        path = f"{prefix}.{key}" if prefix else key
        old = before.get(key)
        new = after.get(key)
        if isinstance(old, Mapping) or isinstance(new, Mapping):
            changes.extend(_config_diff(old if isinstance(old, Mapping) else {}, new if isinstance(new, Mapping) else {}, prefix=path))
        elif old != new:
            changes.append({"path": path, "before": old, "after": new})
    return changes


def _observe(
    root: Path,
    config: Mapping[str, Any],
    desired_states: tuple[DesiredState, ...],
    diagnostics: list[Diagnostic],
) -> tuple[dict[str, TaskWorkState], tuple[WorkItemState, ...], PullRequestScan]:
    """Observe the repository once and derive everything that follows from it.

    One `git for-each-ref` and one `gh pr list` per invocation, never one per
    task and never one per bug, and never a fetch: states come from what can
    be seen right now, so nothing is remembered between runs and no event can
    be missed. The same two observations feed both derivations -- the selected
    features' `Txxx` tasks (`NNN-Txxx` branches) and the bugs and chores
    (`<TEAM>-<number>` branches) -- which is why `gh` is still consulted
    exactly once whatever the invocation projects.
    """

    scan = scan_pull_requests(root)
    diagnostics.extend(scan.diagnostics)
    branches = known_branches(root)
    _team_id, team_key = team_binding(config)
    work_states = derive_task_states(
        desired_states, branches=branches, scan=scan
    )
    work_items = derive_work_items(
        team_key, branches=branches, scan=scan
    )
    if scan.outcome != "complete":
        names = ", ".join(desired.feature.identifier for desired in desired_states) or "none"
        diagnostics.append(Diagnostic(
            "observation_unknown",
            f"GitHub pull-request observation is {scan.outcome}; selected features [{names}] and all repository work items remain unverified, including items absent from partial output",
            severity="warning",
        ))
    return work_states, work_items, scan


def _remote_work_items(client: LinearClient, config: Mapping[str, Any], work_items: tuple[WorkItemState, ...]) -> dict[str, RemoteWorkItem]:
    """Resolve every observed Issue key to its real Issue in one batched query.

    Never one query per key, and never a query at all when nothing was
    observed. An Issue key with nothing behind it is simply absent from the
    result; the planner turns that into a warning, never an operation.
    """

    if not work_items:
        return {}
    team_id, _team_key = team_binding(config)
    return {item.identifier: item for item in client.find_issues_by_numbers(team_id, issue_numbers(work_items))}


def _select_feature_directories(root: Path, args: argparse.Namespace) -> list[Path]:
    """Select the features to project, or none in a bugs-and-chores repository.

    An explicit `--feature`/`--current` always resolves or fails: asking for a
    feature that is not there is a mistake, not a short path. Every other
    selection degrades to no feature at all when the repository has no
    `specs/NNN-*` directory, so `push` and `status` still reconcile work items
    in a repository that only tracks bugs and chores. Ambiguity between
    several existing features remains an error, so a bare `push` can never
    silently project nothing.
    """

    if args.feature or args.current or has_feature_directories(root):
        return select_features(root, explicit_feature=args.feature, current=args.current, all_features=args.all_features)
    return []


def _tasks_pending(feature_dir: Path) -> Diagnostic:
    """Info diagnostic for a feature whose `tasks.md` does not exist yet (plan D15)."""

    return Diagnostic(
        "tasks_pending",
        "tasks.md is absent; the Project is projected without Issues until the ledger exists",
        str(feature_dir / "tasks.md"),
        severity="info",
    )


def run_push(args: argparse.Namespace) -> dict[str, Any]:
    root = _root_from_args(args.root)
    if args.dry_run and args.apply:
        raise AppError(
            "choose only one of --dry-run or --apply",
            code=EXIT_USAGE,
            category="usage",
            diagnostics=[Diagnostic("push_mode", "push cannot both preview and apply in the same invocation")],
        )
    if args.hook:
        # A lifecycle hook must degrade to a clean no-op rather than surface a
        # scary error mid-workflow when there is no valid configuration yet.
        try:
            config, shared_path = load_config(root, args.config)
        except AppError as error:
            return _hook_noop("no valid Linear configuration was found", detail=str(error))
        if not hooks_gate(config, "lifecycle_enabled"):
            return _hook_noop("hooks.lifecycle_enabled is false")
    else:
        config, shared_path = load_config(root, args.config)

    feature_dirs = _select_feature_directories(root, args)
    binding = repository_binding(config)
    diagnostics = [Diagnostic("config", "configuration loaded by spec-kit-linear", str(shared_path), severity="info")]
    projected = []
    for feature_dir in feature_dirs:
        feature = parse_feature(root, feature_dir)
        state, projection_warnings = project_feature(feature, binding)
        projected.append(state)
        diagnostics.extend(projection_warnings)
        if not feature.phases:
            diagnostics.append(_tasks_pending(feature_dir))
    desired_states = tuple(projected)
    diagnostics.extend(load_dotenv_files(root))
    work_states, work_items, scan = _observe(root, config, desired_states, diagnostics)
    client = _linear_client()
    discovery = discover_and_adopt(client, config, desired_states)
    plans = [build_push_plan(desired, discovery, config=config, work_states=work_states) for desired in desired_states]
    # Work items are feature-independent by construction: they are observed
    # from branches named after Linear Issue keys, never from `tasks.md`. So
    # every push reconciles all of them -- with `--feature`, with `--all`, and
    # in a repository that has no feature at all -- while the feature
    # selectors keep scoping the `Txxx` tasks alone.
    work_item_plan, work_item_diagnostics = build_work_item_plan(work_items, _remote_work_items(client, config, work_items), config=config)
    diagnostics.extend(work_item_diagnostics)
    operations = [operation for plan in plans for operation in plan["operations"]] + list(work_item_plan["operations"])
    observation = observation_report(scan, desired_states, work_items)
    if scan.outcome != "complete" and any(operation.get("kind") == "issue.create" for operation in operations):
        diagnostics.append(Diagnostic("linear_default_state", "uncertain tasks are created without a derived state; Linear will apply its configured default workflow state", severity="warning"))

    apply_changes = bool(args.apply)
    if args.hook and not args.dry_run:
        apply_changes = hooks_gate(config, "auto_apply")
        if not apply_changes:
            diagnostics.append(Diagnostic("hook_auto_apply_disabled", "hooks.auto_apply is false; a preview was rendered instead", severity="info"))
    if not apply_changes:
        payload = _success(f"push preview: {len(operations)} operation(s)", diagnostics=diagnostics, operations=operations)
        payload["plans"] = plans
        payload["work_item_plan"] = work_item_plan
        payload["dry_run"] = True
        payload["hook_invocation"] = bool(args.hook)
        payload["observation"] = observation
        return payload

    results = []
    failure: AppError | None = None
    failed_plan_index: int | None = None
    for plan_index, (desired, plan) in enumerate(zip(desired_states, plans)):
        if not plan["operations"]:
            continue
        try:
            results.append(_apply_push_plan(config, client, desired, plan, work_states))
        except AppError as error:
            results.extend(error.apply_results)
            error.apply_results = list(results)
            failure = error
            failed_plan_index = plan_index
            break
    if failure is None and work_item_plan["operations"]:
        try:
            results.append(_apply_work_item_plan(config, client, work_items, work_item_plan))
        except AppError as error:
            results.extend(error.apply_results)
            error.apply_results = list(results)
            failure = error
    if failure is not None:
        # Keep every later plan visible as unattempted in this invocation.
        remaining = []
        if failed_plan_index is not None:
            for plan in plans[failed_plan_index + 1:]:
                remaining.extend(str(item["id"]) for item in plan["operations"])
            remaining.extend(str(item["id"]) for item in work_item_plan["operations"])
        if failure.apply_results and remaining:
            last = failure.apply_results[-1]
            failure.apply_results[-1] = replace(last, unattempted_operation_ids=tuple(last.unattempted_operation_ids) + tuple(remaining))
        raise failure
    diagnostics.append(Diagnostic("push_apply", "post-apply read verification passed", severity="info"))
    payload = _success(f"push applied {sum(result.writes for result in results)} operation(s)", diagnostics=diagnostics, operations=operations)
    payload["apply"] = [result.as_dict() for result in results]
    payload["work_item_plan"] = work_item_plan
    payload["dry_run"] = False
    payload["hook_invocation"] = bool(args.hook)
    payload["observation"] = observation
    return payload


def _apply_push_plan(
    config: dict[str, Any],
    client: LinearClient,
    desired: DesiredState,
    plan: dict[str, object],
    work_states: Mapping[str, TaskWorkState],
):
    """Apply exactly ``plan``, re-reading Linear before every mutation.

    The plan is the difference between the filesystem and a snapshot taken
    moments ago in this same process, so applying it is idempotent: a second
    run renders no operations at all, and ``post_verify`` refuses to report
    success while any bridge-owned difference remains. Verification reuses
    the states derived at the top of this invocation rather than observing
    Git and GitHub again, so a branch pushed mid-apply cannot turn a correct
    apply into a spurious failure.
    """

    def discover() -> RemoteDiscovery:
        return discover_and_adopt(client, config, (desired,))

    def provider() -> dict[str, object]:
        return snapshot_from_discovery(discover(), desired)

    def post_verify(_snapshot: dict[str, object]) -> bool:
        return not build_push_plan(desired, discover(), config=config, work_states=work_states)["operations"]

    return apply_plan(plan, snapshot_provider=provider, transport=LinearMutationExecutor(client), post_verify=post_verify)


def _apply_work_item_plan(
    config: dict[str, Any],
    client: LinearClient,
    work_items: tuple[WorkItemState, ...],
    plan: dict[str, object],
):
    """Apply exactly the work-item plan, re-reading Linear before every write.

    Same fail-closed machinery the feature plan uses, over the same
    observations taken at the top of this invocation: the plan is a
    difference, so a second run renders nothing and `post_verify` refuses to
    report success while any observed work item still disagrees with Linear.
    """

    def provider() -> dict[str, object]:
        return build_work_item_plan(work_items, _remote_work_items(client, config, work_items), config=config)[0]["snapshot"]

    def post_verify(_snapshot: dict[str, object]) -> bool:
        return not build_work_item_plan(work_items, _remote_work_items(client, config, work_items), config=config)[0]["operations"]

    return apply_plan(plan, snapshot_provider=provider, transport=LinearMutationExecutor(client), post_verify=post_verify)


def _hook_noop(reason: str, *, detail: str | None = None) -> dict[str, Any]:
    """A disabled gate (or a hook running before `onboard` configured
    anything) must produce a clean no-op -- exit 0, an explicit diagnostic --
    never an error."""

    message = f"hook-originated push skipped: {reason}"
    diagnostic = Diagnostic("hook_noop", message if detail is None else f"{message} ({detail})", severity="info")
    payload = _success(message, diagnostics=[diagnostic])
    payload["dry_run"] = True
    payload["hook_invocation"] = True
    payload["hook_noop"] = True
    return payload


def _linear_client() -> LinearClient:
    """The single construction site for a Linear client.

    Endpoint resolution and validation live in `.endpoint` and nowhere else,
    and *building a client is itself an announcing event*. Announcing here
    rather than only from a list of command names is what guarantees the
    property: no invocation that can reach a Linear endpoint is ever silent
    about which one.
    """

    endpoint = resolve_endpoint()
    _ENDPOINT_STATE["client_built"] = True
    _announce_endpoint(endpoint)
    return LinearClient(load_credentials(), endpoint=endpoint)


def run_status(args: argparse.Namespace) -> dict[str, Any]:
    root = _root_from_args(args.root)
    config, shared_path = load_config(root, args.config)
    feature_dirs = _select_feature_directories(root, args)
    diagnostics = [
        Diagnostic("read_only", "Linear inspection used query-only GraphQL operations", severity="info"),
        Diagnostic("config", "configuration loaded by spec-kit-linear", str(shared_path), severity="info"),
    ]
    projected = []
    for feature_dir in feature_dirs:
        feature = parse_feature(root, feature_dir)
        state, projection_warnings = project_feature(feature, repository_binding(config))
        projected.append(state)
        diagnostics.extend(projection_warnings)
        if not feature.phases:
            diagnostics.append(_tasks_pending(feature_dir))
    desired = tuple(projected)
    diagnostics.extend(load_dotenv_files(root))
    work_states, work_items, scan = _observe(root, config, desired, diagnostics)
    client = _linear_client()
    discovery = discover_and_adopt(client, config, desired)
    for diagnostic in (item for feature in discovery.features for item in feature.drift):
        diagnostics.append(Diagnostic(diagnostic.code, diagnostic.message, diagnostic.path, severity="warning"))
    remote_work_items = _remote_work_items(client, config, work_items)
    diagnostics.extend(
        Diagnostic("work_item_unknown", f"{item.identifier} was observed on '{item.detail}' but no such Issue exists in the bound Linear Team", severity="warning")
        for item in work_items
        if item.identifier not in remote_work_items
    )
    payload = _success("read-only Linear status rendered", diagnostics=diagnostics)
    payload["read_only"] = True
    observation = observation_report(scan, desired, work_items)
    payload["observation"] = observation
    payload["status"] = status_report(discovery, desired, work_states, work_items, remote_work_items, observation)
    return payload


def _current_branch(root: Path) -> str | None:
    """The current branch name, or `None` outside Git, or on a detached HEAD."""

    result = subprocess.run(
        ["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"],
        check=False,
        text=True,
        capture_output=True,
        timeout=20,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _emit_hook_result_warning(payload: Mapping[str, object]) -> None:
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, list):
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, Mapping) or diagnostic.get("severity") == "info":
                continue
            safe = redact_structure(diagnostic)
            if isinstance(safe, Mapping):
                sys.stderr.write(
                    f"warning: reconciliation {safe.get('code', 'failure')}: "
                    f"{redact_text(safe.get('message', 'operation failed'))}\n"
                )
    observation = payload.get("observation")
    if isinstance(observation, Mapping) and observation.get("outcome") != "complete":
        outcome = redact_text(observation.get("outcome", "unknown"))
        sys.stderr.write(f"warning: reconciliation GitHub observation {outcome}; state derivation is unverified\n")
    sys.stderr.flush()


def _emit_hook_error_warning(error: AppError) -> None:
    sys.stderr.write(f"warning: reconciliation failure: {redact_text(str(error))}\n")
    for diagnostic in error.diagnostics:
        safe = redact_structure(diagnostic.as_dict())
        if isinstance(safe, Mapping):
            sys.stderr.write(
                f"warning: reconciliation {safe.get('code', 'failure')}: "
                f"{redact_text(safe.get('message', 'operation failed'))}\n"
            )
    for result in error.apply_results:
        line = _format_apply_evidence(result)
        if line:
            sys.stderr.write(f"warning: reconciliation partial failure: {line}\n")
    sys.stderr.flush()


def _format_apply_evidence(result: object) -> str | None:
    safe = redact_structure(result.as_dict() if hasattr(result, "as_dict") else result)
    if not isinstance(safe, Mapping):
        return None
    applied = ",".join(map(str, safe.get("applied_operation_ids", []))) or "none"
    recovered = ",".join(map(str, safe.get("recovered_operation_ids", []))) or "none"
    remaining = ",".join(map(str, safe.get("unattempted_operation_ids", []))) or "none"
    line = f"applied [{applied}], recovered [{recovered}], unattempted [{remaining}]"
    operation = " ".join(str(safe.get(key)) for key in ("failed_operation_id", "failed_operation_kind", "failed_operation_target") if safe.get(key))
    if operation:
        line += f", failed {operation}"
    if safe.get("failure_phase") is not None:
        line += f", failure {safe.get('failure_phase')} ({safe.get('failure_status')})"
    return line


def _reconcile_hook(root: Path) -> tuple[str | None, str | None]:
    """Resolve the branch shape and run `push --hook`; shared by both event handlers (D4, FR-006)."""
    branch = work_item_identifier = None
    branch_error = False
    try:
        branch = _current_branch(root)
        if branch and not FEATURE_RE.fullmatch(branch):
            config, _shared_path = load_config(root, None)
            _team_id, team_key = team_binding(config)
            match = issue_key_pattern(team_key).fullmatch(branch)
            work_item_identifier = f"{team_key.upper()}-{int(match.group(1))}" if match else None
    except Exception:
        branch_error = True

    # A work item resolves `--current` only through `.specify/feature.json`, often
    # absent; a feature/task branch resolves it by name, so only the former skips it.
    try:
        config, _shared_path = load_config(root, None)
    except AppError as error:
        if (root / ROOT_CONFIG_FILENAME).exists():
            _emit_hook_error_warning(error)
        return branch, work_item_identifier
    if not hooks_gate(config, "lifecycle_enabled"):
        return branch, work_item_identifier
    if branch_error:
        sys.stderr.write("warning: reconciliation failure: unexpected configured branch error\n")
        sys.stderr.flush()

    hook_args = argparse.Namespace(
        root=str(root), config=None, feature=None, current=work_item_identifier is None, all_features=False,
        dry_run=False, apply=False, hook=True,
    )
    try:
        result = run_push(hook_args)
        _emit_hook_result_warning(result)
    except AppError as error:
        _emit_hook_error_warning(error)
    except Exception:
        sys.stderr.write("warning: reconciliation failure: unexpected configured hook error\n")
        sys.stderr.flush()
    return branch, work_item_identifier


def _format_feature_context(branch: str, feature: str, tasks: list[dict[str, object]]) -> str:
    """FR-003's context line for a feature or task branch, from `status`'s own task rows.

    The open-PR clause names each pull request's own `#<n>` when the row
    carries it (D6/T013). The next command is the first unchecked task's
    `next`, else the first open task PR's: a stack fully checked but still
    in review or draft names the wait sentence or the review command, never
    nothing (FR-004).
    """

    first_unchecked = next((task for task in tasks if not task["local_complete"] and task.get("state_source") != "unknown"), None)
    unknown = next((task for task in tasks if task.get("state_source") == "unknown"), None)
    open_prs = [task for task in tasks if task.get("state_source") == "pr" and task.get("derived_state") != "completed"]
    segments = [f"Linear: {feature} on {branch}"]
    if unknown is not None:
        remote = unknown.get("remote_state") or "unavailable"
        segments.append(f"{unknown['task']} state unknown (remote: {remote})")
    if first_unchecked is not None:
        segments[0] += f" — next {first_unchecked['task']} (unchecked)"
    if open_prs:
        pr_text = ", ".join(
            f"{task['task']} ({task['derived_state']}, #{task['pr_number']})"
            if task.get("pr_number") is not None
            else f"{task['task']} ({task['derived_state']})"
            for task in open_prs
        )
        segments.append(f"open task PRs: {pr_text}")
    next_command = first_unchecked.get("next") if first_unchecked is not None else None
    if not next_command and open_prs:
        next_command = open_prs[0].get("next")
    if next_command:
        segments.append(f"next: {next_command}")
    return "; ".join(segments)


def _format_work_item_context(row: Mapping[str, object]) -> str:
    """FR-003's context line for a work-item branch, from `status`'s own work-item row."""

    state = "unknown (unverified)" if row.get("state_source") == "unknown" else str(row["derived_state"])
    line = f"Linear: {row['identifier']} ({state})"
    if row.get("state_source") == "unknown":
        line += f"; remote: {row.get('remote_state') or 'unavailable'}"
    if row.get("next"):
        line += f" — next: {row['next']}"
    return line


def _session_start_context_line(root: Path, branch: str, work_item_identifier: str | None) -> str | None:
    """FR-003's context line for the current branch's shape, or `None`.

    A feature/task branch (`NNN-...`) and a work-item branch (`<team
    key>-<number>...`) are the only two recognized shapes; anything else, or a
    configuration `status` cannot load, yields no line -- every exception here
    is treated identically by the caller (FR-006).
    """

    feature_match = FEATURE_RE.fullmatch(branch)
    if feature_match is None and work_item_identifier is None:
        return None

    # A feature/task branch resolves `--current` through its own name; a work
    # item has no feature to resolve, so `current` is False for it and this
    # lookup never raises for that reason (caller already resolved the id).
    status_args = argparse.Namespace(root=str(root), config=None, feature=None, current=work_item_identifier is None, all_features=False)
    status_payload = run_status(status_args)
    _emit_hook_result_warning(status_payload)
    status = status_payload["status"]

    if work_item_identifier is not None:
        row = next((item for item in status["work_items"] if item["identifier"] == work_item_identifier), None)
        return _format_work_item_context(row) if row is not None else None

    task_row = next((item for item in status["task_rows"] if item["feature"] == feature_match.group(1)), None)
    return _format_feature_context(branch, feature_match.group(1), task_row["tasks"]) if task_row is not None else None


def run_session_start(args: argparse.Namespace) -> int:
    """The `session_start` event handler (plan D4): reconcile, then one context line.

    Never raises and never exits nonzero: a session must not be blocked,
    slowed down, or spammed by tracking. Missing or disabled configuration is
    silent; configured failures become sanitized stderr warnings (FR-006).
    """

    try:
        root = _root_from_args(getattr(args, "root", None))
    except AppError:
        return EXIT_SUCCESS

    try:
        config, _shared_path = load_config(root, None)
    except AppError as error:
        if (root / ROOT_CONFIG_FILENAME).exists():
            _emit_hook_error_warning(error)
        return EXIT_SUCCESS
    if not hooks_gate(config, "lifecycle_enabled"):
        return EXIT_SUCCESS

    branch, work_item_identifier = _reconcile_hook(root)

    try:
        line = _session_start_context_line(root, branch, work_item_identifier)
    except AppError as error:
        _emit_hook_error_warning(error)
        line = None
    except Exception:
        # Configuration was already established by `_reconcile_hook`; a
        # failure here is therefore actionable but must remain non-blocking.
        try:
            config, _shared_path = load_config(root, None)
            if hooks_gate(config, "lifecycle_enabled"):
                sys.stderr.write("warning: reconciliation failure: unexpected configured context error\n")
                sys.stderr.flush()
        except Exception:
            pass
        line = None
    if line:
        sys.stdout.write(line + "\n")
    return EXIT_SUCCESS


# `run_post_tool_use` decides whether a finished Bash command ran `git push`
# or `gh pr create|ready|merge` (FR-005) by tokenizing it the way a shell
# would: a regex cannot see quoting, so `git -C "a b" push` (a real push) and
# `echo "a;git push"` (no push at all) look alike to one. POSIX `shlex` with
# `punctuation_chars` makes `();<>|&` and newline their own tokens (a run such
# as `&&` stays one token); `commenters=""` keeps `#` from swallowing the
# newline after `git status # note`. A punctuation-only token separates
# steps, except one carrying `<` or `>`: a redirection (`2>&1`) is dropped
# and the step continues. Each step is read the way a shell starts a process
# -- leading `NAME=value` assignments and one bare wrapper word skipped -- so
# the executable must be exactly `git` or `gh`; global options are skipped
# up to the subcommand. `#` comments and heredocs (the `<<DELIM` operator,
# body and terminator line) are removed from the text first (`_shell_text`),
# so prose is never tokenized: an apostrophe in a commit message would
# otherwise unbalance shlex's quotes and turn a real push into "no match".
# Unbalanced quoting (`ValueError`) is "no match". Punctuation inside quoted
# arguments is encoded before shlex so a quoted `;` is not mistaken for a
# command separator.
_STEP_PUNCTUATION = "();<>|&\n"
# The redirection operators a punctuation run may carry; whatever is left after
# removing them (`;`, `&&`, `|`, `()`, a newline) separates steps, so `2>&1`
# and `&>x` never split and `<;` still does.
_REDIRECTION_RE = re.compile(r"<<<|<<|>>|>&|&>|<&|<>|>|<")
_ASSIGNMENT_RE = re.compile(r"[A-Za-z_]\w*=")
_WRAPPER_WORDS = frozenset({"env", "command", "exec", "nohup", "time"})
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
_GH_VALUE_OPTIONS = frozenset({"-R", "--repo", "--hostname"})
_GH_RECONCILE_SUBCOMMANDS = frozenset({"create", "ready", "merge"})
_QUOTED_PUNCTUATION = {character: chr(0xE000 + index) for index, character in enumerate(_STEP_PUNCTUATION)}
_QUOTED_PUNCTUATION_RESTORE = {value: key for key, value in _QUOTED_PUNCTUATION.items()}


_HEREDOC_WORD_END = frozenset(" \t\r\n;&|()<>")


def _heredoc_operator(command: str, index: int) -> tuple[str, bool, int]:
    """Parse the ``<<`` operator whose ``<<`` ends at ``index``: the delimiter
    (quotes stripped), whether it was ``<<-``, and the index past it."""

    dashed = command.startswith("-", index)
    index += dashed
    while index < len(command) and command[index] in " \t":
        index += 1
    if index < len(command) and command[index] in "'\"":
        close = command.find(command[index], index + 1)
        if close < 0:
            return "", dashed, index
        return command[index + 1 : close], dashed, close + 1
    if command.startswith("\\", index):
        index += 1
    start = index
    while index < len(command) and command[index] not in _HEREDOC_WORD_END:
        index += 1
    return command[start:index], dashed, index


def _skip_heredoc_bodies(command: str, index: int, pending: list[tuple[str, bool]]) -> int:
    """Index past the bodies (and terminator lines) of ``pending`` heredocs starting at ``index``."""

    for delimiter, dashed in pending:
        while index < len(command):
            end = command.find("\n", index)
            line = command[index:] if end < 0 else command[index:end]
            index = len(command) if end < 0 else end + 1
            if (line.lstrip("\t") if dashed else line) == delimiter:
                break
    return index


def _shell_text(command: str) -> str:
    """``command`` as shlex should see it: ``#`` comments (a ``#`` starting a word
    outside quotes, up to its newline) and every heredoc -- operator, body,
    terminator line -- removed, so prose is never tokenized."""

    out: list[str] = []
    quote: str | None = None
    pending: list[tuple[str, bool]] = []  # heredocs opened on the current line, in order
    index = 0
    while index < len(command):
        character = command[index]
        if quote is None:
            if character == "\\" and index + 1 < len(command):
                escaped = command[index + 1]
                if escaped == "\n":
                    index += 2; continue
                out.append(_QUOTED_PUNCTUATION.get(escaped, command[index : index + 2]))
                index += 2; continue
            if character in "'\"":
                quote = character
            elif character == "#" and (index == 0 or command[index - 1] in " \t\n;&|()"):
                end = command.find("\n", index)
                index = len(command) if end < 0 else end
                continue
            elif command.startswith("<<<", index):
                out.append("<<<"); index += 3; continue  # a here-string: a word follows, never a body
            elif command.startswith("<<", index):
                delimiter, dashed, index = _heredoc_operator(command, index + 2)
                if delimiter:
                    pending.append((delimiter, dashed))
                continue
            elif character == "\n" and pending:
                out.append(character)
                index = _skip_heredoc_bodies(command, index + 1, pending)
                pending = []
                continue
        elif character == "\\" and quote == '"' and index + 1 < len(command):
            escaped = command[index + 1]
            if escaped == "\n":
                index += 2; continue
            out.append("\\" + _QUOTED_PUNCTUATION.get(escaped, escaped)); index += 2; continue
        elif character == quote:
            quote = None
        out.append(_QUOTED_PUNCTUATION.get(character, character) if quote is not None else character); index += 1
    return "".join(out)


def _command_steps(command: str) -> list[list[str]]:
    """Tokenize ``command`` (comments and heredocs removed) into argv-shaped steps.

    Raises ``ValueError`` on unbalanced quoting; the caller treats that as
    "no match" rather than letting it propagate.
    """

    lexer = shlex.shlex(_shell_text(command), posix=True, punctuation_chars=_STEP_PUNCTUATION)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    steps: list[list[str]] = [[]]
    for token in lexer:
        if token and all(character in _STEP_PUNCTUATION for character in token):
            if _REDIRECTION_RE.sub("", token):
                steps.append([])
            continue  # a bare redirection (`2>&1`, `>out.log`) never starts a step
        steps[-1].append("".join(_QUOTED_PUNCTUATION_RESTORE.get(character, character) for character in token))
    return steps


def _skip_leading_wrapper(tokens: list[str]) -> list[str]:
    """Drop leading `NAME=value` assignments and bare wrapper words, in any order."""

    index = 0
    while index < len(tokens) and (_ASSIGNMENT_RE.match(tokens[index]) or tokens[index] in _WRAPPER_WORDS):
        index += 1
    return tokens[index:]


def _skip_global_options(tokens: list[str], value_options: frozenset[str]) -> list[str]:
    """Drop leading global options up to the subcommand.

    A token in `value_options` consumes the next token as its separate value
    (`-C .`, `--git-dir /x`); any other `-`-led token -- a bare flag or an
    attached `--opt=value` -- consumes only itself.
    """

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in value_options:
            index += 2
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        break
    return tokens[index:]


def _step_reconciles(tokens: list[str]) -> bool:
    """Does this one step run `git push` or `gh pr create|ready|merge`?"""

    tokens = _skip_leading_wrapper(tokens)
    if not tokens:
        return False
    executable, *arguments = tokens
    if executable == "git":
        remainder = _skip_global_options(arguments, _GIT_VALUE_OPTIONS)
        return bool(remainder) and remainder[0] == "push"
    if executable == "gh":
        remainder = _skip_global_options(arguments, _GH_VALUE_OPTIONS)
        return len(remainder) >= 2 and remainder[0] == "pr" and remainder[1] in _GH_RECONCILE_SUBCOMMANDS
    return False


def _is_reconcile_command(command: str) -> bool:
    """Does any step of `command` run `git push` or `gh pr create|ready|merge`?"""

    try:
        steps = _command_steps(command)
    except ValueError:
        return False
    return any(_step_reconciles(step) for step in steps)


def run_post_tool_use(args: argparse.Namespace) -> int:
    """The `post_tool_use` event handler (D4): reconcile after `git push`/`gh pr`, else no-op.

    Never raises, never prints, always exits 0 (FR-005, FR-006).
    """
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except Exception:
        payload = None
    command = None
    if isinstance(payload, Mapping) and payload.get("tool_name") == "Bash":
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, Mapping):
            value = tool_input.get("command")
            command = value if isinstance(value, str) else None
    if not command or not _is_reconcile_command(command):
        return EXIT_SUCCESS

    try:
        root = _root_from_args(getattr(args, "root", None))
    except AppError:
        return EXIT_SUCCESS
    _reconcile_hook(root)
    return EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.json_requested = "--json" in (argv if argv is not None else sys.argv[1:])
    args = parser.parse_args(argv)
    if args.command == "session-start":
        # Its own contract (one plain line or nothing, always exit 0) does not
        # fit the JSON/error result shape every other command renders below.
        return run_session_start(args)
    if args.command == "post-tool-use":
        # Same always-exit-0, no-JSON contract as `session-start`.
        return run_post_tool_use(args)
    endpoint = DEFAULT_ENDPOINT
    _begin_invocation(endpoint)
    try:
        # Resolved twice on purpose, before any command runs:
        #
        # (1) from the real process environment first, so that a command
        #     failing early -- a nonexistent `--root`, say -- still reports
        #     the endpoint it would have used, and so that an invalid
        #     override is exit code 3 for every command at the earliest
        #     possible moment, never a silent fallback to production;
        # (2) again after `_root_from_args`, which is the choke point that
        #     auto-loads `.speckit-linear.env` and the operator-global env
        #     file. An override arriving from there would otherwise be used
        #     by the client but missing from the notice. The real environment
        #     always wins over those files, so the value can only change when
        #     (1) found nothing at all: there is never a double banner.
        endpoint = resolve_endpoint()
        _begin_invocation(endpoint)
        if args.command in ALWAYS_ANNOUNCE_COMMANDS:
            _announce_endpoint(endpoint)
        _root_from_args(getattr(args, "root", None))
        refreshed = resolve_endpoint()
        if refreshed != endpoint:
            endpoint = refreshed
            if args.command in ALWAYS_ANNOUNCE_COMMANDS:
                _announce_endpoint(endpoint)
            else:
                _ENDPOINT_STATE["endpoint"] = endpoint
        if args.command == "doctor":
            payload = run_doctor(args)
        elif args.command == "onboard":
            payload = run_onboard(args)
        elif args.command == "push":
            payload = run_push(args)
        elif args.command == "status":
            payload = run_status(args)
        else:  # argparse makes this unreachable, but keeps the boundary explicit.
            raise AppError(
                f"unsupported command: {args.command}",
                code=EXIT_USAGE,
                category="usage",
                diagnostics=[Diagnostic("command", "supported commands are onboard, push, status, and doctor")],
            )
        _attach_endpoint_field(payload, args.command, endpoint)
        if args.json or args.quiet:
            _render(payload, args.json, args.quiet)
        elif args.command == "status":
            _render_status(payload)
        elif args.command == "push":
            _render_push(payload)
        else:
            _render(payload, args.json, args.quiet)
        return EXIT_SUCCESS
    except AppError as error:
        payload = {
            "code": error.code,
            "category": error.category,
            "message": str(error),
            "retryable": error.retryable,
            "operations": [],
            "diagnostics": [diagnostic.as_dict() for diagnostic in error.diagnostics],
        }
        if error.apply_results:
            payload["apply"] = [result.as_dict() for result in error.apply_results]
            payload["partial"] = True
            if payload["apply"]:
                evidence = payload["apply"][-1]
                for key in ("failed_operation_id", "failed_operation_kind", "failed_operation_target", "failure_phase", "failure_status"):
                    if key in evidence:
                        payload[key] = evidence[key]
        _attach_endpoint_field(payload, args.command, endpoint)
        if getattr(args, "json", False):
            _write_json(payload)
        # An invalid configuration is reported on stderr even under `--quiet`:
        # a fail-closed refusal nobody can see is indistinguishable from
        # success.
        elif not getattr(args, "quiet", False) or error.category == "configuration":
            sys.stderr.write(f"error: {payload['message']}\n")
            for diagnostic in error.diagnostics:
                location = f" ({diagnostic.path})" if diagnostic.path else ""
                line = f":{diagnostic.line}" if diagnostic.line else ""
                sys.stderr.write(f"  {diagnostic.code}{location}{line}: {diagnostic.message}\n")
            for evidence in error.apply_results:
                line = _format_apply_evidence(evidence)
                if line:
                    sys.stderr.write(f"  partial apply: {line}\n")
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
