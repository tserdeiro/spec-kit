"""Sanitized stdout-only reports for read-only Linear inspection commands."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Mapping

from .domain import DesiredState
from .linear_client import RemoteWorkItem
from .remote_discovery import RemoteDiscovery
from .work_items import WorkItemState
from .work_state import SOURCE_NONE, TaskWorkState


def _task_code(identity: str) -> str:
    # projection.py's DesiredTask.identity is always "task:<feature>:<Txxx>";
    # the human-mode table (contract "speckit.linear.status") only ever
    # shows the bare Txxx code, never the full identity string.
    return identity.rsplit(":", 1)[-1]


def build_task_rows(
    discovery: RemoteDiscovery,
    desired_states: tuple[DesiredState, ...],
    work_states: Mapping[str, TaskWorkState] | None = None,
) -> list[dict[str, object]]:
    """Combine the local `tasks.md` checkbox state with the adopted remote Issue, per feature.

    One entry per selected feature; each entry's ``tasks`` list has one row
    per local ``Txxx``, in `tasks.md` order, regardless of whether a remote
    Feature Project/Issue was adopted yet (contract "speckit.linear.status":
    "degrade gracefully when the feature has no remote project yet"). This
    is the single source both the human-mode table (``render_status_table``)
    and ``--json``'s structurally identical ``task_rows`` render from.

    ``work_states`` adds each task's derived state and the observation that
    produced it (checkbox, branch, or pull request), so `status` shows what
    the next `push` would reconcile and why.
    """

    adoption_by_feature = {feature.feature: feature for feature in discovery.features}
    rows: list[dict[str, object]] = []
    for desired in desired_states:
        adoption = adoption_by_feature.get(desired.feature.identifier)
        has_remote_project = adoption is not None and adoption.project is not None
        tasks: list[dict[str, object]] = []
        for task in desired.feature.tasks:
            adopted = adoption.tasks.get(task.identity) if adoption is not None else None
            derived = (work_states or {}).get(task.identity)
            tasks.append(
                {
                    "task": _task_code(task.identity),
                    "local_complete": task.completed,
                    "derived_state": derived.state if derived is not None else None,
                    "state_source": derived.source if derived is not None else None,
                    "remote_identifier": adopted.identifier if adopted is not None else None,
                    "remote_state": adopted.state_name if adopted is not None else None,
                    "assignee": adopted.assignee_name if adopted is not None else None,
                }
            )
        rows.append(
            {
                "feature": desired.feature.identifier,
                "has_remote_project": has_remote_project,
                "tasks": tasks,
            }
        )
    return rows


def build_remote_only_rows(discovery: RemoteDiscovery, desired_states: tuple[DesiredState, ...]) -> list[dict[str, object]]:
    """Doc "Cambios remotos realizados por humanos" (bidirectional-awareness
    chunk, item 1): per-feature "Remote-only issues" -- Issues that live in
    the adopted Feature Project but carry no bridge task marker at all.

    One entry per selected feature that has at least one such issue; a
    feature with none is left out of the list entirely (the contract's
    "empty section omitted"), mirroring the human-mode table's identical
    omission rule below. This is the single source both the human-mode
    table and `--json`'s structurally identical `remote_only_issues` render
    from, the same "one source, two renders" pattern `build_task_rows`
    already established.
    """

    adoption_by_feature = {feature.feature: feature for feature in discovery.features}
    rows: list[dict[str, object]] = []
    for desired in desired_states:
        adoption = adoption_by_feature.get(desired.feature.identifier)
        if adoption is None or not adoption.unmanaged_issues:
            continue
        rows.append(
            {
                "feature": desired.feature.identifier,
                "issues": [issue.as_dict() for issue in adoption.unmanaged_issues],
            }
        )
    return rows


def build_work_item_rows(
    work_items: Sequence[WorkItemState],
    remote_items: Mapping[str, RemoteWorkItem] | None = None,
) -> list[dict[str, object]]:
    """One row per observed bug/chore Issue key (Stage 5, "Workflow de bugs y chores").

    Feature-independent by construction: a work item is observed from a branch
    or a pull request named after a Linear Issue key, never from `tasks.md`, so
    these rows appear whatever feature is selected -- and the list is empty,
    and the whole section omitted, when no such branch exists.
    """

    rows: list[dict[str, object]] = []
    for item in work_items:
        remote = (remote_items or {}).get(item.identifier)
        rows.append(
            {
                "identifier": item.identifier,
                "derived_state": item.state,
                "state_source": item.source,
                "detail": item.detail,
                "known_remotely": remote is not None,
                "title": remote.title if remote is not None else None,
                "remote_state": remote.state_name if remote is not None else None,
            }
        )
    return rows


def render_work_item_table(work_item_rows: list[dict[str, object]]) -> str:
    """Render the human-mode "Work items" block; empty rows render nothing."""

    if not work_item_rows:
        return ""
    headers = ("ISSUE", "DERIVED", "FROM", "BRANCH", "TITLE", "STATE")
    rows = [
        (
            str(row["identifier"]),
            str(row["derived_state"]),
            str(row["state_source"]),
            str(row["detail"]),
            str(row["title"] or ("not found in Linear" if not row["known_remotely"] else "—")),
            str(row["remote_state"] or "—"),
        )
        for row in work_item_rows
    ]
    widths = [max(len(headers[index]), *(len(row[index]) for row in rows)) for index in range(len(headers))]

    def _format(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(width) for value, width in zip(values, widths))

    lines = ["Work items (bugs and chores observed from Issue-key branches)", _format(headers)]
    lines.extend(_format(row) for row in rows)
    return "\n".join(lines) + "\n"


def render_status_table(task_rows: list[dict[str, object]], remote_only_rows: list[dict[str, object]] | None = None) -> str:
    """Render the human-mode `status` per-feature task table: plain fixed-width text, no external deps.

    Columns: task id, local checkbox state, the state derived from
    observable reality and the observation that produced it, remote issue
    identifier, remote state name, assignee display name -- one row per
    `Txxx`, grouped by feature. A feature with no adopted remote Feature
    Project yet gets an explicit note instead of a wall of "-" placeholders
    with no explanation.

    When ``remote_only_rows`` carries an entry for a feature (item 1:
    Issues created directly in Linear, with no bridge task marker), a
    visually separated "Remote-only issues" block is appended after that
    feature's task rows; a feature absent from ``remote_only_rows`` gets no
    such block at all.
    """

    if not task_rows:
        return "No local features were selected.\n"

    remote_only_by_feature = {row["feature"]: row["issues"] for row in (remote_only_rows or [])}
    headers = ("TASK", "DONE", "DERIVED", "FROM", "ISSUE", "STATE", "ASSIGNEE")
    lines: list[str] = []
    for feature in task_rows:
        lines.append(f"Feature {feature['feature']}")
        if not feature["has_remote_project"]:
            lines.append("  (no remote Feature Project yet; local-only)")
        rows = [
            (
                str(task["task"]),
                "[x]" if task["local_complete"] else "[ ]",
                str(task.get("derived_state") or "—"),
                str(_source_label(task.get("state_source"))),
                str(task["remote_identifier"] or "—"),
                str(task["remote_state"] or "—"),
                str(task["assignee"] or "—"),
            )
            for task in feature["tasks"]
        ]
        widths = [
            max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
            for index in range(len(headers))
        ]

        def _format_row(values: tuple[str, ...], widths: list[int] = widths) -> str:
            return "  ".join(value.ljust(width) for value, width in zip(values, widths))

        lines.append(_format_row(headers))
        for row in rows:
            lines.append(_format_row(row))

        remote_only = remote_only_by_feature.get(feature["feature"])
        if remote_only:
            lines.append("")
            lines.append("  Remote-only issues (created directly in Linear; never touched by push/reconcile):")
            issue_headers = ("ISSUE", "TITLE", "STATE", "ASSIGNEE", "URL")
            issue_rows = [
                (
                    str(issue["identifier"]),
                    str(issue["title"]),
                    str(issue["state"] or "—"),
                    str(issue["assignee"] or "—"),
                    str(issue["url"] or "—"),
                )
                for issue in remote_only
            ]
            issue_widths = [
                max(len(issue_headers[index]), *(len(row[index]) for row in issue_rows))
                for index in range(len(issue_headers))
            ]

            def _format_issue_row(values: tuple[str, ...], widths: list[int] = issue_widths) -> str:
                return "  ".join(value.ljust(width) for value, width in zip(values, widths))

            lines.append("  " + _format_issue_row(issue_headers))
            for row in issue_rows:
                lines.append("  " + _format_issue_row(row))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _source_label(source: object) -> str:
    """`none` is an absence, not an observation, so it prints as a dash."""

    return str(source) if isinstance(source, str) and source != SOURCE_NONE else "—"


def status_report(
    discovery: RemoteDiscovery,
    desired_states: tuple[DesiredState, ...] = (),
    work_states: Mapping[str, TaskWorkState] | None = None,
    work_items: Sequence[WorkItemState] = (),
    remote_work_items: Mapping[str, RemoteWorkItem] | None = None,
) -> dict[str, object]:
    """Summarize configured bindings, adoption, and bridge-owned drift."""

    drift = [diagnostic.as_dict() for feature in discovery.features for diagnostic in feature.drift]
    return {
        "binding": discovery.binding.as_dict(),
        "remote_project_count": len(discovery.projects),
        "features": [feature.as_dict() for feature in discovery.features],
        "drift": drift,
        "task_rows": build_task_rows(discovery, desired_states, work_states),
        "remote_only_issues": build_remote_only_rows(discovery, desired_states),
        "work_items": build_work_item_rows(work_items, remote_work_items),
        "remote_operations": {"mode": "query-only", "writes": 0},
    }
