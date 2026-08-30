"""Filesystem authority and projection data structures, independent of Linear."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRef:
    path: str
    line: int

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line}


@dataclass(frozen=True)
class Task:
    identifier: str
    title: str
    completed: bool
    source: SourceRef
    description: str = ""


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    source: SourceRef
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Feature:
    identifier: str
    title: str
    spec_source: SourceRef
    plan_title: str
    plan_source: SourceRef
    phases: tuple[Phase, ...]
    summary: str = ""


@dataclass(frozen=True)
class RepositoryBinding:
    slug: str
    project_label_group_id: str
    project_label_id: str
    project_label_name: str
    project_view_id: str
    issue_view_id: str


@dataclass(frozen=True)
class DesiredTask:
    identity: str
    title: str
    completed: bool
    project_identity: str
    marker: str
    managed_description: str
    source: SourceRef

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "title": self.title,
            "completed": self.completed,
            "project_identity": self.project_identity,
            "marker": self.marker,
            "managed_description": self.managed_description,
            "source": self.source.as_dict(),
        }


@dataclass(frozen=True)
class DesiredFeature:
    identifier: str
    project_identity: str
    project_title: str
    project_marker: str
    project_label_id: str
    managed_description: str
    source: SourceRef
    plan_source: SourceRef
    tasks: tuple[DesiredTask, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "project": {
                "identity": self.project_identity,
                "title": self.project_title,
                "marker": self.project_marker,
                "project_label_id": self.project_label_id,
                "managed_description": self.managed_description,
                "source": self.source.as_dict(),
            },
            "tasks": [task.as_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class DesiredState:
    binding: RepositoryBinding
    feature: DesiredFeature

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": {
                "project_label": {
                    "id": self.binding.project_label_id,
                    "group_id": self.binding.project_label_group_id,
                    "name": self.binding.project_label_name,
                    "marker": f"speckit-linear:repository:{self.binding.slug}",
                },
                "shared_views": [
                    {
                        "id": self.binding.project_view_id,
                        "kind": "project",
                        "name": f"{self.binding.slug} / Features",
                        "filter": {"project_label_id": self.binding.project_label_id},
                    },
                    {
                        "id": self.binding.issue_view_id,
                        "kind": "issue",
                        "name": f"{self.binding.slug} / Work",
                        "filter": {"project_label_id": self.binding.project_label_id},
                    },
                ],
            },
            "feature": self.feature.as_dict(),
        }
