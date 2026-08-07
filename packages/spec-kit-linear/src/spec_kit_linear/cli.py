"""Command-line boundary: onboard, push, status, doctor, completions."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .completions import generate_completion_script
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
from .discovery import has_feature_directories, select_features
from .domain import DesiredState
from .endpoint import (
    ALWAYS_ANNOUNCE_COMMANDS,
    DEFAULT_ENDPOINT,
    endpoint_banner,
    endpoint_report,
    is_default_endpoint,
    resolve_endpoint,
)
from .env_files import REPO_ENV_FILENAME, load_dotenv_files
from .errors import AppError, Diagnostic
from .git_refs import known_branches
from .github import cli_diagnostic as github_cli_diagnostic, scan_pull_requests
from .gitignore import ensure_entries as ensure_gitignore_entries, has_entry as has_gitignore_entry
from .lifecycle_registry import load_registry as load_lifecycle_registry, registry_diagnostics as lifecycle_registry_diagnostics
from .linear_client import LinearClient, RemoteTeamSummary, RemoteWorkflowState, RemoteWorkItem
from .mutation_executor import LinearMutationExecutor
from .parser import parse_feature
from .planner import build_push_plan, build_work_item_plan, snapshot_from_discovery
from .projection import project_feature
from .reconciler import apply_plan
from .remote_discovery import RemoteDiscovery, discover_and_adopt
from .reporting import render_status_table, render_work_item_table, status_report
from .view_discovery import conventional_view_name, resolve_shared_views_by_name
from .work_items import WorkItemState, derive_work_items, issue_numbers
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

    completions = subparsers.add_parser("completions", help="print a bash or zsh completion script to stdout")
    completions.add_argument("shell", choices=("bash", "zsh"), help="shell to generate the completion script for")
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
def _doctor_local_file_diagnostics(root: Path, *, fix: bool) -> list[Diagnostic]:
    """Missing `.gitignore` entries for this extension's credential file."""

    gitignore_path = root / ".gitignore"
    existing_lines = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()} if gitignore_path.exists() else set()
    if has_gitignore_entry(existing_lines, REPO_ENV_FILENAME):
        return []
    if fix:
        added = ensure_gitignore_entries(gitignore_path, (REPO_ENV_FILENAME,))
        return [Diagnostic("fixed_gitignore", f"fixed: added missing .gitignore entries: {', '.join(added)}", severity="info")]
    return [
        Diagnostic(
            "gitignore_missing_entries",
            f".gitignore is missing an entry for {REPO_ENV_FILENAME}, which can carry credentials; run `doctor --fix`, or `onboard`",
            severity="warning",
        )
    ]


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
                f"no Project Label Group named '{_REPOSITORY_LABEL_GROUP_NAME}' was found; create it in Linear",
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
                f"no Project Label named '{slug}' was found under '{_REPOSITORY_LABEL_GROUP_NAME}'; create it in Linear",
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
) -> tuple[dict[str, TaskWorkState], tuple[WorkItemState, ...]]:
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
    work_states = derive_task_states(desired_states, branches=branches, pull_requests=scan.pull_requests)
    work_items = derive_work_items(team_key, branches=branches, pull_requests=scan.pull_requests)
    return work_states, work_items


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
    desired_states = tuple(project_feature(parse_feature(root, feature_dir), binding) for feature_dir in feature_dirs)
    diagnostics = [Diagnostic("config", "configuration loaded by spec-kit-linear", str(shared_path), severity="info")]
    diagnostics.extend(load_dotenv_files(root))
    work_states, work_items = _observe(root, config, desired_states, diagnostics)
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
        return payload

    results = [
        _apply_push_plan(config, client, desired, plan, work_states)
        for desired, plan in zip(desired_states, plans)
        if plan["operations"]
    ]
    if work_item_plan["operations"]:
        results.append(_apply_work_item_plan(config, client, work_items, work_item_plan))
    diagnostics.append(Diagnostic("push_apply", "post-apply read verification passed", severity="info"))
    payload = _success(f"push applied {sum(result.writes for result in results)} operation(s)", diagnostics=diagnostics, operations=operations)
    payload["apply"] = [result.as_dict() for result in results]
    payload["work_item_plan"] = work_item_plan
    payload["dry_run"] = False
    payload["hook_invocation"] = bool(args.hook)
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
    desired = tuple(project_feature(parse_feature(root, feature_dir), repository_binding(config)) for feature_dir in feature_dirs)
    diagnostics = [
        Diagnostic("read_only", "Linear inspection used query-only GraphQL operations", severity="info"),
        Diagnostic("config", "configuration loaded by spec-kit-linear", str(shared_path), severity="info"),
    ]
    diagnostics.extend(load_dotenv_files(root))
    work_states, work_items = _observe(root, config, desired, diagnostics)
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
    payload["status"] = status_report(discovery, desired, work_states, work_items, remote_work_items)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.json_requested = "--json" in (argv if argv is not None else sys.argv[1:])
    args = parser.parse_args(argv)
    if args.command == "completions":
        # Raw shell text on stdout, not the JSON result shape every other
        # command uses: this is local developer sugar, not an agent-facing
        # command, so it deliberately bypasses --json/--quiet.
        sys.stdout.write(generate_completion_script(args.shell, parser))
        return EXIT_SUCCESS
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
                diagnostics=[Diagnostic("command", "supported commands are onboard, push, status, doctor, and completions")],
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
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
