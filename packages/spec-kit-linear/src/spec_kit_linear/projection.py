"""Pure filesystem-to-desired-state transformation rules."""

from __future__ import annotations

from .domain import DesiredFeature, DesiredState, DesiredTask, Feature, RepositoryBinding


def _block(marker: str, body: list[str]) -> str:
    return "\n".join([f"<!-- {marker} -->", *body, "<!-- /speckit-linear -->"])


def project_feature(feature: Feature, binding: RepositoryBinding) -> DesiredState:
    """Project one feature onto the Feature Project -> Txxx Issue hierarchy.

    `tasks.md` phases are a document structure, not a projected resource:
    every Txxx becomes an Issue directly under the feature's Project, in
    `tasks.md` order.
    """

    project_identity = f"feature:{feature.identifier}"
    tasks: list[DesiredTask] = []
    for phase in feature.phases:
        for task in phase.tasks:
            task_marker = f"speckit-linear:task:{feature.identifier}:{task.identifier}"
            tasks.append(
                DesiredTask(
                    identity=f"task:{feature.identifier}:{task.identifier}",
                    title=f"{task.identifier} {task.title}",
                    completed=task.completed,
                    project_identity=project_identity,
                    marker=task_marker,
                    managed_description=_block(
                        task_marker,
                        [
                            f"Source: `{task.source.path}#L{task.source.line}`",
                            f"Status: {'complete' if task.completed else 'incomplete'}",
                        ],
                    ),
                    source=task.source,
                    assignee_alias=task.assignee_alias,
                )
            )
    feature_marker = f"speckit-linear:feature:{feature.identifier}"
    desired_feature = DesiredFeature(
        identifier=feature.identifier,
        project_identity=project_identity,
        project_title=f"{feature.identifier}: {feature.title}",
        project_marker=feature_marker,
        project_label_id=binding.project_label_id,
        managed_description=_block(
            feature_marker,
            [
                f"Source: `{feature.spec_source.path}#L{feature.spec_source.line}`",
                f"Plan: `{feature.plan_source.path}#L{feature.plan_source.line}`",
            ],
        ),
        source=feature.spec_source,
        plan_source=feature.plan_source,
        tasks=tuple(tasks),
    )
    return DesiredState(binding=binding, feature=desired_feature)
