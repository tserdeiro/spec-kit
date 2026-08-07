"""The complete, deliberately small remote-write contract.

Keeping this in one module makes it difficult for a GraphQL document to become
an accidental second write path.  A plan is invalid unless both its operation
kind *and* every input key are listed here.
"""

from __future__ import annotations

from collections.abc import Mapping
import uuid

from .errors import AppError, Diagnostic


# Exactly the operations `planner.build_push_plan` can emit, plus the three
# `onboard` emits (`team.automation.create`, `project.label.create`,
# `view.create`: the missing pieces of the one-shot binding — additive only,
# updates and deletes stay forbidden); nothing else is ever a valid mutation.
PUSH_MUTATIONS = frozenset(
    {
        "project.create",
        "project.update",
        "project.label.attach",
        "issue.create",
        "issue.update",
        "issue.lifecycle.update",
        "team.automation.create",
        "project.label.create",
        "view.create",
    }
)

# Each GraphQL input is intentionally enumerated.  In particular there is no
# assigneeId, leadId, memberIds, parentId, archive or delete field anywhere
# in this table: assignment is native Linear (the UI or the official Linear
# MCP acting as the human), never the harness.
ALLOWED_INPUTS = {
    "project.create": frozenset({"id", "name", "teamIds", "description", "labelIds"}),
    "project.update": frozenset({"name", "description"}),
    "project.label.attach": frozenset({"labelId"}),
    "issue.create": frozenset({"id", "title", "teamId", "projectId", "description", "stateId"}),
    "issue.update": frozenset({"title", "description"}),
    "issue.lifecycle.update": frozenset({"stateId"}),
    # No targetBranchId: onboard only manages the Team's global mappings and
    # never touches branch-scoped rules.
    "team.automation.create": frozenset({"id", "teamId", "stateId", "event"}),
    "project.label.create": frozenset({"id", "name", "parentId", "isGroup"}),
    "view.create": frozenset({"id", "name", "filterData", "projectFilterData", "shared"}),
}


def assert_allowed(kind: str, input_values: Mapping[str, object]) -> None:
    """Reject unknown and over-broad operations fail-closed."""

    if kind not in PUSH_MUTATIONS:
        raise _policy_error("mutation_not_allowed", f"'{kind}' is not an allowed mutation")
    permitted = ALLOWED_INPUTS[kind]
    unexpected = sorted(set(input_values) - permitted)
    if unexpected:
        raise _policy_error("mutation_input_not_allowed", f"'{kind}' contains forbidden input fields: {', '.join(unexpected)}")
    if kind.endswith(".create"):
        value = input_values.get("id")
        if not isinstance(value, str):
            raise _policy_error("mutation_create_id", f"'{kind}' requires an input.id UUID v4")
        try:
            parsed = uuid.UUID(value)
        except ValueError as error:
            raise _policy_error("mutation_create_id", f"'{kind}' requires an input.id UUID v4") from error
        if parsed.version != 4:
            raise _policy_error("mutation_create_id", f"'{kind}' requires an input.id UUID v4")
    elif "id" in input_values:
        raise _policy_error("mutation_update_id", f"'{kind}' must target its remote ID through GraphQL variables, not input.id")
    forbidden = {"assigneeId", "leadId", "memberIds", "archive", "delete"} & set(input_values)
    # The one parent relationship the harness itself creates is the repository
    # label under its group; every other kind treats parentId as hierarchy.
    if "parentId" in input_values and kind != "project.label.create":
        forbidden.add("parentId")
    if forbidden:
        raise _policy_error("mutation_preserved_field", f"'{kind}' would modify a preserved field")


def assert_known_mutation(kind: str) -> None:
    """Client-side belt-and-suspenders guard for all mutation callers."""

    if kind not in ALLOWED_INPUTS:
        raise _policy_error("mutation_unknown", f"unknown Linear mutation kind: {kind}")


def forbidden_operations() -> list[str]:
    """Public machine-readable operation classes excluded by this release."""

    return [
        "initiative.create",
        "issue.delete",
        "issue.archive",
        "project.delete",
        "project.archive",
        "subissue.create",
        "checklist.create",
        "issue.assignee.update",
        "project.lead.update",
        "project.members.update",
        "custom_view.update",
        "custom_view.delete",
    ]


def _policy_error(code: str, message: str) -> AppError:
    return AppError(message, code=6, category="mutation_policy", diagnostics=[Diagnostic(code, message)])
