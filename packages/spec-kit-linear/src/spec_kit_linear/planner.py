"""Deterministic construction of the remote reconciliation plan."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence

from .allowlist import assert_allowed, forbidden_operations
from .bridge import merge_managed_block
from .domain import DesiredState, DesiredTask
from .errors import AppError, Diagnostic
from .linear_client import RemoteWorkItem
from .remote_discovery import FeatureAdoption, RemoteDiscovery
from .work_items import WorkItemState
from .work_state import STATE_COMPLETED, STATE_REVIEW, STATE_STARTED, STATE_UNSTARTED, TaskWorkState


PLAN_SCHEMA_VERSION = "2.0"
PRESERVED_FIELDS = ["taskAssigneeId", "projectLead", "projectMembers", "humanComments", "unmanagedLabels"]
FORBIDDEN_OPERATIONS = forbidden_operations()


def canonical_hash(value: object) -> str:
    """Hash JSON without whitespace or dictionary-order ambiguity."""

    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def snapshot_from_discovery(discovery: RemoteDiscovery, desired: DesiredState) -> dict[str, object]:
    """Render the exact versioned remote resources relevant to one feature."""

    feature = _feature_adoption(discovery, desired.feature.identifier)
    resources: list[dict[str, object]] = [
        {"identity": "binding:workspace", "id": discovery.binding.workspace_id, "updated_at": None},
        {"identity": "binding:team", "id": discovery.binding.team_id, "updated_at": None},
        {"identity": "binding:project-label-group", "id": discovery.binding.project_label_group_id, "updated_at": None},
        {"identity": "binding:project-label", "id": discovery.binding.project_label_id, "updated_at": None},
        {"identity": "binding:project-view", "id": discovery.binding.project_view_id, "updated_at": None},
        {"identity": "binding:issue-view", "id": discovery.binding.issue_view_id, "updated_at": None},
    ]
    if feature.project is not None:
        resources.append(_snapshot_resource(feature.project.desired_identity, feature.project.remote_id, feature.project.updated_at))
    resources.extend(_snapshot_resource(item.desired_identity, item.remote_id, item.updated_at) for item in feature.tasks.values())
    resources.sort(key=lambda item: str(item["identity"]))
    snapshot = {"kind": "linear-remote-v1", "resources": resources}
    return {**snapshot, "hash": canonical_hash(snapshot)}


def _snapshot_resource(identity: str, remote_id: str, updated_at: str) -> dict[str, object]:
    return {"identity": identity, "id": remote_id, "updated_at": updated_at}


def build_push_plan(
    desired: DesiredState,
    discovery: RemoteDiscovery,
    *,
    config: Mapping[str, object] | None = None,
    work_states: Mapping[str, TaskWorkState] | None = None,
) -> dict[str, object]:
    """Diff one feature against an adopted, versioned remote snapshot.

    Existing resources are identified by their marker, never by a fuzzy title.
    Any identity or hierarchy drift discovered while adopting is a hard error
    before an operation is emitted. Re-running against an unchanged Linear
    yields an empty operation list: the plan is the difference, so applying it
    twice is a no-op.


    ``work_states`` maps a task's ``identity`` to the state derived from
    observable reality moments ago (see ``work_state.py``). It is the
    difference the ``issue.lifecycle.update`` operations reconcile; with no
    mapping, a task falls back to what its `tasks.md` checkbox alone says.
    """

    adoption = _feature_adoption(discovery, desired.feature.identifier)
    if adoption.drift:
        raise AppError(
            "bridge-owned Linear drift prevents a safe plan",
            code=6,
            category="remote_identity",
            diagnostics=list(adoption.drift),
        )
    snapshot = snapshot_from_discovery(discovery, desired)
    resources = _resource_map(snapshot)
    project = _project_for(adoption, discovery)
    operations: list[dict[str, object]] = []
    if project is None:
        create_input: dict[str, object] = {
            "name": desired.feature.project_title,
            "teamIds": [discovery.binding.team_id],
            "description": desired.feature.managed_description,
            "labelIds": [desired.binding.project_label_id],
        }
        if desired.feature.content_block:
            create_input["content"] = desired.feature.content_block
        _append_operation(
            operations,
            kind="project.create",
            target=desired.feature.project_identity,
            reason="missing_feature_project",
            input_values=create_input,
            preconditions={"absent": True},
        )
    else:
        project_ref = resources[desired.feature.project_identity]
        name_changed = project.name != desired.feature.project_title
        description_changed = _needs_block_update(project.description, desired.feature.project_marker, desired.feature.managed_description)
        new_content = _needed_content(project.content, desired.feature.project_marker, desired.feature.content_block, desired.feature.summary_hash)
        if name_changed or description_changed or new_content is not None:
            update_input: dict[str, object] = {
                **({"name": desired.feature.project_title} if name_changed else {}),
                "description": merge_managed_block(project.description, desired.feature.project_marker, desired.feature.managed_description),
            }
            if new_content is not None:
                update_input["content"] = new_content
            _append_operation(
                operations, kind="project.update", target=desired.feature.project_identity,
                reason="bridge_owned_project_fields_changed",
                input_values=update_input,
                preconditions=project_ref,
            )
        if desired.binding.project_label_id not in project.label_ids:
            _append_operation(
                operations, kind="project.label.attach", target=desired.feature.project_identity,
                reason="repository_label_missing", input_values={"labelId": desired.binding.project_label_id},
                preconditions=project_ref,
            )

    for task in desired.feature.tasks:
        issue = _issue_for(adoption, project, task)
        if issue is None:
            issue_input: dict[str, object] = {
                "title": task.title,
                "teamId": discovery.binding.team_id,
                "projectId": _reference(desired.feature.project_identity),
                "description": task.managed_description,
            }
            state_id = _desired_state_id(config, _task_state(work_states, task))
            if state_id is not None:
                issue_input["stateId"] = state_id
            _append_operation(
                operations, kind="issue.create", target=task.identity,
                reason="missing_task_issue", input_values=issue_input,
                preconditions={"absent": True, "project": desired.feature.project_identity},
            )
            continue
        ref = resources[task.identity]
        if issue.title != task.title or _needs_block_update(issue.description, task.marker, task.managed_description):
            _append_operation(
                operations, kind="issue.update", target=task.identity,
                reason="bridge_owned_issue_fields_changed",
                input_values={
                    **({"title": task.title} if issue.title != task.title else {}),
                    "description": merge_managed_block(issue.description, task.marker, task.managed_description),
                }, preconditions=ref,
            )
        desired_state = _desired_state_id(config, _task_state(work_states, task))
        if desired_state is not None and getattr(issue, "state_id", None) != desired_state:
            _append_operation(
                operations, kind="issue.lifecycle.update", target=task.identity,
                reason="managed_task_lifecycle_changed", input_values={"stateId": desired_state},
                preconditions=ref,
            )

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "feature": desired.feature.identifier,
        "binding": discovery.binding.as_dict(),
        "desired": desired.as_dict(),
        "snapshot": snapshot,
        "assumptions": [
            "Remote identities are adopted only from one exact bridge marker.",
            "The repository Project Label and Shared Views are existing bindings, not Feature Projects.",
            "Task assignees and Feature Project lead/members are preserved and are absent from every mutation input.",
        ],
        "operations": operations,
        "preserved_fields": PRESERVED_FIELDS,
        "forbidden_operations": FORBIDDEN_OPERATIONS,
    }


WORK_ITEM_PLAN_SCHEMA_VERSION = "1.0"


def build_work_item_plan(
    work_items: Sequence[WorkItemState],
    remote_items: Mapping[str, RemoteWorkItem],
    *,
    config: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], tuple[Diagnostic, ...]]:
    """Diff every observed bug/chore Issue's workflow state against Linear.

    Deliberately far smaller than ``build_push_plan``: a bug or chore is a
    human-authored Issue, so the only operation this plan can ever contain is
    ``issue.lifecycle.update``. Nothing here creates, retitles, re-describes,
    labels, or assigns anything, and an Issue whose remote state already
    matches produces no operation at all -- which is what makes a second pass
    zero operations.

    An observed Issue key with no Issue behind it in Linear is reported as a
    warning diagnostic and produces no operation: the branch is simply named
    after something that does not exist, which is never a reason to fail a
    push.
    """

    resources: list[dict[str, object]] = []
    operations: list[dict[str, object]] = []
    diagnostics: list[Diagnostic] = []
    for item in work_items:
        remote = remote_items.get(item.identifier)
        if remote is None:
            diagnostics.append(
                Diagnostic(
                    "work_item_unknown",
                    f"{item.identifier} was observed on '{item.detail}' but no such Issue exists in the bound Linear Team; no state was projected",
                    severity="warning",
                )
            )
            continue
        resources.append(_snapshot_resource(item.identity, remote.id, remote.updated_at))
        state_id = _desired_state_id(config, item.state)
        if state_id is None or remote.state_id == state_id:
            continue
        _append_operation(
            operations, kind="issue.lifecycle.update", target=item.identity,
            reason="observed_work_item_lifecycle_changed", input_values={"stateId": state_id},
            preconditions={"id": remote.id, "updated_at": remote.updated_at},
        )
    resources.sort(key=lambda item: str(item["identity"]))
    snapshot = {"kind": "linear-work-items-v1", "resources": resources}
    plan = {
        "schema_version": WORK_ITEM_PLAN_SCHEMA_VERSION,
        "work_items": [item.as_dict() for item in work_items],
        "snapshot": {**snapshot, "hash": canonical_hash(snapshot)},
        "operations": operations,
    }
    return plan, tuple(diagnostics)


def _append_operation(
    operations: list[dict[str, object]], *, kind: str, target: str, reason: str,
    input_values: Mapping[str, object], preconditions: Mapping[str, object],
) -> None:
    operation_id = str(uuid.uuid4())
    full_input = dict(input_values)
    # Linear accepts caller-provided IDs for creation inputs.  This UUID is
    # carried in the plan and becomes the queryable recovery key if a response
    # is lost after a successful create.  Updates keep their remote target ID
    # exclusively in the GraphQL variable, never in input.
    if kind.endswith(".create"):
        full_input["id"] = operation_id
    assert_allowed(kind, full_input)
    operations.append({
        "id": operation_id,
        "kind": kind,
        "target": target,
        "reason": reason,
        "input": full_input,
        "allowed_input_fields": sorted(full_input),
        "preconditions": dict(preconditions),
    })


def snapshot_is_current(expected: Mapping[str, object], current: Mapping[str, object], *, ignored_identities: frozenset[str] = frozenset()) -> bool:
    """Compare versioned remote resources without accepting backward drift."""

    expected_resources = _resource_map(expected)
    current_resources = _resource_map(current)
    for identity, item in expected_resources.items():
        if identity in ignored_identities:
            continue
        if current_resources.get(identity) != item:
            return False
    return True


def operation_precondition_holds(operation: Mapping[str, object], current_snapshot: Mapping[str, object], *, created: frozenset[str] = frozenset()) -> bool:
    target = operation.get("target")
    preconditions = operation.get("preconditions")
    if not isinstance(target, str) or not isinstance(preconditions, Mapping):
        return False
    resources = _resource_map(current_snapshot)
    if preconditions.get("absent") is True:
        return target not in resources or target in created
    expected = {key: preconditions.get(key) for key in ("id", "updated_at")}
    return resources.get(target) == expected


def _resource_map(snapshot: Mapping[str, object]) -> dict[str, dict[str, object]]:
    raw = snapshot.get("resources")
    if not isinstance(raw, list):
        raise _plan_error("snapshot_resources", "snapshot resources must be a list")
    resources: dict[str, dict[str, object]] = {}
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("identity"), str) or not isinstance(item.get("id"), str):
            raise _plan_error("snapshot_resource", "snapshot resource identity and id are required")
        identity = str(item["identity"])
        if identity in resources:
            raise _plan_error("snapshot_duplicate", "snapshot contains duplicate resource identities")
        resources[identity] = {"id": item["id"], "updated_at": item.get("updated_at")}
    return resources


def _feature_adoption(discovery: RemoteDiscovery, identifier: str) -> FeatureAdoption:
    matches = [feature for feature in discovery.features if feature.feature == identifier]
    if len(matches) != 1:
        raise AppError("remote discovery did not return exactly one selected feature", code=6, category="remote_identity", diagnostics=[Diagnostic("feature_discovery", "selected feature has an ambiguous remote discovery result")])
    return matches[0]


def _project_for(adoption: FeatureAdoption, discovery: RemoteDiscovery):
    if adoption.project is None:
        return None
    matches = [project for project in discovery.projects if project.id == adoption.project.remote_id]
    if len(matches) != 1:
        raise AppError("adopted Feature Project could not be re-read", code=6, category="remote_identity", diagnostics=[Diagnostic("feature_project_missing", "adopted Feature Project is not in the remote snapshot")])
    return matches[0]


def _issue_for(adoption: FeatureAdoption, project: object, desired: DesiredTask):
    remote_ref = adoption.tasks.get(desired.identity)
    if remote_ref is None or project is None:
        return None
    matches = [issue for issue in project.issues if issue.id == remote_ref.remote_id]
    if len(matches) != 1:
        raise AppError("adopted Txxx Issue could not be re-read", code=6, category="remote_identity", diagnostics=[Diagnostic("task_missing", "adopted Txxx Issue is not in the remote snapshot")])
    return matches[0]


def _needs_block_update(existing: str, marker: str, desired_block: str) -> bool:
    return merge_managed_block(existing, marker, desired_block) != existing


_SUMMARY_HASH_RE = re.compile(r"<!-- speckit-linear:summary-hash:([0-9a-f]{12}) -->")


def _remote_summary_hash(content: str) -> str:
    match = _SUMMARY_HASH_RE.search(content)
    return match.group(1) if match else ""


def _needed_content(remote_content: str, marker: str, desired_content_block: str, desired_hash: str) -> str | None:
    """Return the new Project.content value, or ``None`` when no write is needed.

    Idempotency here is judged by the `summary-hash` comment, never by
    byte-comparing prose against `desired_content_block`: Linear normalizes
    markdown on write (inserts blank lines between block elements, rewrites
    `-` bullets to `*`), so our composed bytes are never the value Linear
    actually stores -- a byte compare would replan the same rewrite on every
    single push. Trade-off: a human edit made *inside* the content block is
    invisible to this hash (it cannot see prose drift once Linear has already
    rewritten our bytes) and persists until the spec summary itself changes.
    The description block has no such gap -- untouched by this function, it
    keeps self-healing byte-for-byte on every push, as before.
    """

    if desired_hash:
        if _remote_summary_hash(remote_content) == desired_hash:
            return None
        return merge_managed_block(remote_content, marker, desired_content_block)
    if f"<!-- {marker} -->" in remote_content:
        # Linear treats a content write of "" as a no-op (verified live), so
        # a removal that empties the document must send a lone space -- which
        # Linear normalizes to an actually-empty document -- or the stale
        # block would survive and this removal would replan on every push.
        return merge_managed_block(remote_content, marker, "") or " "
    return None


# Which `lifecycle` id each derived state writes to, in fallback order. The
# `review` fallback is the documented degradation: a Team with no "In Review"
# workflow state projects a ready-for-review task onto its "In Progress" one
# rather than leaving the Issue stale.
_LIFECYCLE_FIELDS_BY_STATE: dict[str, tuple[str, ...]] = {
    STATE_COMPLETED: ("completed_state_id",),
    STATE_REVIEW: ("review_state_id", "started_state_id"),
    STATE_STARTED: ("started_state_id",),
    STATE_UNSTARTED: ("open_state_id",),
}


def _task_state(work_states: Mapping[str, TaskWorkState] | None, task: DesiredTask) -> str:
    derived = (work_states or {}).get(task.identity)
    if derived is not None:
        return derived.state
    return STATE_COMPLETED if task.completed else STATE_UNSTARTED


def _desired_state_id(config: Mapping[str, object] | None, state: str) -> str | None:
    """Resolve a derived state to a configured Linear workflow state id.

    ``None`` -- an unconfigured `lifecycle` section, or a state the Team has
    no id for -- leaves the Issue's workflow state untouched, which is what
    keeps a partially resolvable Team usable instead of failing closed.
    """

    if not isinstance(config, Mapping):
        return None
    lifecycle = config.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        return None
    for field in _LIFECYCLE_FIELDS_BY_STATE.get(state, ()):
        value = lifecycle.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _reference(identity: str) -> dict[str, str]:
    """Plan-time symbolic reference resolved only by the applier."""

    return {"$ref": identity}


def _plan_error(code: str, message: str) -> AppError:
    return AppError(message, code=6, category="plan", diagnostics=[Diagnostic(code, message)])
