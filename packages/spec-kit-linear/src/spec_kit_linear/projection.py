"""Pure filesystem-to-desired-state transformation rules."""

from __future__ import annotations

from .domain import DesiredFeature, DesiredState, DesiredTask, Feature, RepositoryBinding
from .errors import Diagnostic

# Linear caps Project names at 80 characters and Issue titles at 255. The
# projection clips deterministically at the limit — the desired state is
# always writable and reconciliation stays idempotent — and reports every
# clip, so the artifact's own title can be shortened instead. Without this,
# an over-long spec H1 surfaced as a bare INVALID_INPUT from the API.
PROJECT_NAME_LIMIT = 80
ISSUE_TITLE_LIMIT = 255


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _block(marker: str, body: list[str]) -> str:
    return "\n".join([f"<!-- {marker} -->", *body, "<!-- /speckit-linear -->"])


def _prefixed_body(prose: str, lines: list[str]) -> list[str]:
    """Prepend human-readable prose to the block's `Source:`/`Plan:` lines.

    Empty prose leaves the block exactly as it was before descriptions
    existed, so an absent task body or spec summary is not a behavior
    change. Lines carrying the bridge's own comment markers are dropped:
    prose quoting the projection format must never open a second block or
    close this one early, which would corrupt `merge_managed_block`'s
    ownership boundary.
    """

    safe = [
        line
        for line in prose.splitlines()
        if "<!-- speckit-linear:" not in line and "<!-- /speckit-linear -->" not in line
    ]
    cleaned = "\n".join(safe).strip("\n")
    if not cleaned:
        return lines
    return [cleaned, "", *lines]


def project_feature(feature: Feature, binding: RepositoryBinding) -> tuple[DesiredState, tuple[Diagnostic, ...]]:
    """Project one feature onto the Feature Project -> Txxx Issue hierarchy.

    `tasks.md` phases are a document structure, not a projected resource:
    every Txxx becomes an Issue directly under the feature's Project, in
    `tasks.md` order. Returns the desired state plus one warning per title
    the Linear limits forced this projection to clip.
    """

    project_identity = f"feature:{feature.identifier}"
    warnings: list[Diagnostic] = []

    def _title(composed: str, limit: int, kind: str, path: str, line: int) -> str:
        clipped = _clip(composed, limit)
        if clipped != composed:
            warnings.append(
                Diagnostic(
                    "linear_title_clipped",
                    f"{kind} clipped to Linear's {limit}-character limit ({len(composed)} composed); "
                    f"shorten the title at {path}#L{line} to control the projected name",
                    severity="warning",
                )
            )
        return clipped

    tasks: list[DesiredTask] = []
    for phase in feature.phases:
        for task in phase.tasks:
            task_marker = f"speckit-linear:task:{feature.identifier}:{task.identifier}"
            tasks.append(
                DesiredTask(
                    identity=f"task:{feature.identifier}:{task.identifier}",
                    title=_title(f"{task.identifier} {task.title}", ISSUE_TITLE_LIMIT, "Issue title", task.source.path, task.source.line),
                    completed=task.completed,
                    project_identity=project_identity,
                    marker=task_marker,
                    managed_description=_block(
                        task_marker,
                        _prefixed_body(task.description, [f"Source: `{task.source.path}#L{task.source.line}`"]),
                    ),
                    source=task.source,
                )
            )
    feature_marker = f"speckit-linear:feature:{feature.identifier}"
    desired_feature = DesiredFeature(
        identifier=feature.identifier,
        project_identity=project_identity,
        project_title=_title(
            f"{feature.identifier}: {feature.title}",
            PROJECT_NAME_LIMIT,
            "Project name",
            feature.spec_source.path,
            feature.spec_source.line,
        ),
        project_marker=feature_marker,
        project_label_id=binding.project_label_id,
        managed_description=_block(
            feature_marker,
            _prefixed_body(
                feature.summary,
                [
                    f"Source: `{feature.spec_source.path}#L{feature.spec_source.line}`",
                    f"Plan: `{feature.plan_source.path}#L{feature.plan_source.line}`",
                ],
            ),
        ),
        source=feature.spec_source,
        plan_source=feature.plan_source,
        tasks=tuple(tasks),
    )
    return DesiredState(binding=binding, feature=desired_feature), tuple(warnings)
