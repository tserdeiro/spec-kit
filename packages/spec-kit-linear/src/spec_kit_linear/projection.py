"""Pure filesystem-to-desired-state transformation rules."""

from __future__ import annotations

import hashlib

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


def _strip_forged_markers(prose: str) -> str:
    """Drop any line in ``prose`` carrying one of the bridge's own comment markers.

    Prose quoting the projection format must never open a second managed
    block or close this one early, which would corrupt `merge_managed_block`'s
    ownership boundary. Shared by everywhere free-form prose is embedded in a
    managed block: the task/feature description prefix and the feature
    content block.
    """

    safe = [
        line
        for line in prose.splitlines()
        if "<!-- speckit-linear:" not in line and "<!-- /speckit-linear -->" not in line
    ]
    return "\n".join(safe).strip("\n")


def _prefixed_body(prose: str, lines: list[str]) -> list[str]:
    """Prepend human-readable prose to the block's `Source:`/`Plan:` lines.

    Empty prose leaves the block exactly as it was before descriptions
    existed, so an absent task body is not a behavior change.
    """

    cleaned = _strip_forged_markers(prose)
    if not cleaned:
        return lines
    return [cleaned, "", *lines]


# Truncated sha256 identifying a block's own body (everything between the
# outer markers except the hash comment itself). See planner._needed_content
# and the task-description branch of planner.build_push_plan for why a hash,
# and not a block's raw bytes, decides whether a remote write is needed: once
# a body has any markdown construct, Linear rewrites it on save (blank lines
# inserted after HTML comments, `-` bullets rewritten to `*`), so composed
# bytes are never the value actually stored.
BODY_HASH_LENGTH = 12


def _hashed_block(marker: str, body_lines: list[str]) -> tuple[str, str]:
    """Build a managed block whose first body line is its own body-hash comment.

    One regime for every block that can carry markdown prose (the feature
    content block, every task description): the hash comment always leads,
    whether or not there is any human-authored prose in ``body_lines`` at
    all, so callers never special-case "no prose" as a different block shape.
    """

    body_text = "\n".join(body_lines)
    digest = hashlib.sha256(body_text.encode("utf-8")).hexdigest()[:BODY_HASH_LENGTH]
    block = _block(marker, [f"<!-- speckit-linear:body-hash:{digest} -->", *body_lines])
    return block, digest


def _content_block(marker: str, summary: str) -> tuple[str, str]:
    """Build the feature's Project.content block and its body hash.

    Project.description caps at 255 characters -- too small for spec prose --
    so the summary instead targets Project.content (the project overview
    document). Returns ("", "") when the summary is empty, meaning no content
    block is projected at all.
    """

    cleaned = _strip_forged_markers(summary)
    if not cleaned:
        return "", ""
    return _hashed_block(marker, [cleaned])


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
            body_lines = _prefixed_body(task.description, [f"Source: `{task.source.path}#L{task.source.line}`"])
            managed_description, body_hash = _hashed_block(task_marker, body_lines)
            tasks.append(
                DesiredTask(
                    identity=f"task:{feature.identifier}:{task.identifier}",
                    title=_title(f"{task.identifier} {task.title}", ISSUE_TITLE_LIMIT, "Issue title", task.source.path, task.source.line),
                    completed=task.completed,
                    project_identity=project_identity,
                    marker=task_marker,
                    managed_description=managed_description,
                    body_hash=body_hash,
                    source=task.source,
                )
            )
    feature_marker = f"speckit-linear:feature:{feature.identifier}"
    content_block, summary_hash = _content_block(feature_marker, feature.summary)
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
        # Source/Plan only, never the summary: Project.description caps at
        # 255 characters, which spec prose blows past immediately. The
        # summary is projected onto Project.content instead (content_block).
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
        content_block=content_block,
        summary_hash=summary_hash,
    )
    return DesiredState(binding=binding, feature=desired_feature), tuple(warnings)
