"""Read-only adoption of configured Linear resources and bridge markers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .domain import DesiredState
from .errors import AppError, Diagnostic
from .linear_client import LinearClient, RemoteBinding, RemoteIssue, RemoteProject


@dataclass(frozen=True)
class AdoptedResource:
    kind: str
    desired_identity: str
    remote_id: str
    updated_at: str
    # Populated only for a task_issue adoption: the remote issue identifier,
    # workflow state name, assignee display name, and permalink `status`
    # renders in its per-feature table.
    identifier: str | None = None
    state_name: str | None = None
    assignee_name: str | None = None
    url: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "kind": self.kind,
            "desired_identity": self.desired_identity,
            "remote_id": self.remote_id,
            "updated_at": self.updated_at,
        }
        if self.identifier is not None:
            result["identifier"] = self.identifier
        if self.state_name is not None:
            result["state_name"] = self.state_name
        if self.assignee_name is not None:
            result["assignee_name"] = self.assignee_name
        if self.url is not None:
            result["url"] = self.url
        return result


@dataclass(frozen=True)
class UnmanagedIssue:
    """A remote Issue inside an adopted Feature Project with no bridge task marker.

    A PM or a bug report can create an Issue directly in Linear, inside the
    Feature Project, without ever going through `push`. These carry no
    ``<!-- speckit-linear:task:... -->`` marker at all, so they are never
    adopted as a ``Txxx`` Issue -- they are surfaced here as a read-only
    collection instead, kept structurally separate from
    ``FeatureAdoption.tasks`` so no planner ever iterates over them.
    """

    id: str
    identifier: str
    title: str
    state_name: str | None
    assignee_name: str | None
    url: str

    def as_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "state": self.state_name,
            "assignee": self.assignee_name,
            "url": self.url,
        }


@dataclass(frozen=True)
class FeatureAdoption:
    feature: str
    project: AdoptedResource | None
    tasks: Mapping[str, AdoptedResource]
    drift: tuple[Diagnostic, ...]
    unmanaged_issues: tuple[UnmanagedIssue, ...] = ()

    @property
    def missing(self) -> tuple[str, ...]:
        resources: list[str] = []
        if self.project is None:
            resources.append("feature_project")
        resources.extend(identity for identity in self._expected_tasks if identity not in self.tasks)
        return tuple(resources)

    _expected_tasks: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "feature": self.feature,
            "project": self.project.as_dict() if self.project is not None else None,
            "tasks": [self.tasks[key].as_dict() for key in sorted(self.tasks)],
            "missing": list(self.missing),
            "drift": [item.as_dict() for item in self.drift],
            "unmanaged_issues": [item.as_dict() for item in self.unmanaged_issues],
        }


@dataclass(frozen=True)
class RemoteDiscovery:
    binding: RemoteBinding
    projects: tuple[RemoteProject, ...]
    features: tuple[FeatureAdoption, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.as_dict(),
            "remote_project_count": len(self.projects),
            "features": [feature.as_dict() for feature in self.features],
        }


def discover_and_adopt(
    client: LinearClient,
    config: Mapping[str, object],
    desired_states: tuple[DesiredState, ...],
) -> RemoteDiscovery:
    """Inspect existing resources and adopt only unambiguous bridge markers."""

    binding = client.inspect_binding(config)
    linear = config["linear"]
    if not isinstance(linear, Mapping):
        raise AssertionError("configuration was validated before remote discovery")
    expected_team_id = linear["team_id"]
    if not isinstance(expected_team_id, str):
        raise AssertionError("configuration was validated before remote discovery")
    projects = client.discover_projects(binding.project_label_id)
    for project in projects:
        if binding.project_label_id not in project.label_ids:
            raise _identity_error("project_label_scope", "a discovered Feature Project does not carry the configured repository label")
    features = tuple(_adopt_feature(desired, projects, expected_team_id) for desired in desired_states)
    return RemoteDiscovery(binding=binding, projects=projects, features=features)


def _adopt_feature(desired: DesiredState, projects: tuple[RemoteProject, ...], expected_team_id: str) -> FeatureAdoption:
    feature = desired.feature
    project = _one_by_marker(projects, feature.project_marker, "feature_project")
    expected_tasks = tuple(task.identity for task in feature.tasks)
    if project is None:
        return FeatureAdoption(
            feature=feature.identifier,
            project=None,
            tasks={},
            drift=(),
            _expected_tasks=expected_tasks,
        )
    project_ref = AdoptedResource("feature_project", feature.project_identity, project.id, project.updated_at)
    drift: list[Diagnostic] = []
    if expected_team_id not in project.team_ids:
        drift.append(Diagnostic("feature_project_team", "Feature Project is not associated with the configured Team"))
    tasks: dict[str, AdoptedResource] = {}
    for desired_task in feature.tasks:
        remote = _one_by_marker(project.issues, desired_task.marker, "task_issue")
        if remote is None:
            continue
        _validate_task_identity(remote, project, drift)
        tasks[desired_task.identity] = AdoptedResource(
            "task_issue",
            desired_task.identity,
            remote.id,
            remote.updated_at,
            identifier=remote.identifier,
            state_name=remote.state_name,
            assignee_name=remote.assignee_name,
            url=remote.url or None,
        )
    return FeatureAdoption(
        feature=feature.identifier,
        project=project_ref,
        tasks=tasks,
        drift=tuple(drift),
        unmanaged_issues=_unmanaged_issues(project),
        _expected_tasks=expected_tasks,
    )


# Any bridge task marker, not one specific Txxx's -- used to tell "no Txxx
# task exists for this issue at all" apart from "this Txxx marker just doesn't
# match any *currently declared* desired task" (an orphaned marker for a Txxx
# since removed from tasks.md, which is still bridge-managed and must never be
# surfaced as a human-created remote-only issue).
_TASK_MARKER_PREFIX = "<!-- speckit-linear:task:"


def _unmanaged_issues(project: RemoteProject | None) -> tuple[UnmanagedIssue, ...]:
    """Issues in this Feature Project with no bridge task marker at all."""

    if project is None:
        return ()
    unmanaged = [
        UnmanagedIssue(
            id=issue.id,
            identifier=issue.identifier,
            title=issue.title,
            state_name=issue.state_name,
            assignee_name=issue.assignee_name,
            url=issue.url,
        )
        for issue in project.issues
        if _TASK_MARKER_PREFIX not in issue.description
    ]
    return tuple(sorted(unmanaged, key=lambda item: item.identifier))


def _one_by_marker(resources: tuple[RemoteProject, ...] | tuple[RemoteIssue, ...], marker: str, kind: str):
    matches = [resource for resource in resources if f"<!-- {marker} -->" in resource.description]
    if len(matches) > 1:
        raise _identity_error("remote_marker_duplicate", f"multiple {kind} resources carry the same bridge marker")
    return matches[0] if matches else None


def _validate_task_identity(task: RemoteIssue, project: RemoteProject, drift: list[Diagnostic]) -> None:
    if task.project_id != project.id:
        drift.append(Diagnostic("task_project", "Txxx Issue is attached to another Feature Project"))
    if task.parent_id is not None:
        drift.append(Diagnostic("task_parent", "Txxx Issue cannot be a sub-issue in the managed hierarchy"))


def _identity_error(code: str, message: str) -> AppError:
    return AppError(message, code=6, category="remote_identity", diagnostics=[Diagnostic(code, message)])
