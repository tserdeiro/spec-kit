"""The complete, deliberately small remote-write contract.

Keeping this in one module makes it difficult for a GraphQL document to become
an accidental second write path.  A plan is invalid unless both its operation
kind *and* every input key are listed here.
"""

from __future__ import annotations

from collections.abc import Mapping
import uuid

from .errors import AppError, Diagnostic


# Exactly the operations `planner.build_push_plan` can emit; nothing else is
# ever a valid mutation.
PUSH_MUTATIONS = frozenset(
    {
        "project.create",
        "project.update",
        "project.label.attach",
        "issue.create",
        "issue.update",
        "issue.lifecycle.update",
    }
)

# Each GraphQL input is intentionally enumerated.  In particular there is no
# leadId, memberIds, parentId, archive or delete field anywhere in this
# table. The sole exception is `assigneeId`, permitted only on
# `issue.create`: the assignee may be set when a Txxx Issue is created if
# `team.members` maps its `[@alias]`, and Linear is the sole authority for
# reassignment afterward. Every update kind still forbids it unconditionally;
# see `assert_allowed` below, which enforces this per-kind exception rather
# than a blanket allow/deny.
ALLOWED_INPUTS = {
    "project.create": frozenset({"id", "name", "teamIds", "description", "labelIds"}),
    "project.update": frozenset({"name", "description"}),
    "project.label.attach": frozenset({"labelId"}),
    "issue.create": frozenset({"id", "title", "teamId", "projectId", "description", "stateId", "assigneeId"}),
    "issue.update": frozenset({"title", "description"}),
    "issue.lifecycle.update": frozenset({"stateId"}),
}

_ASSIGNEE_AT_CREATION_KINDS = frozenset({"issue.create"})


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
    forbidden = {"leadId", "memberIds", "parentId", "archive", "delete"} & set(input_values)
    if "assigneeId" in input_values and kind not in _ASSIGNEE_AT_CREATION_KINDS:
        forbidden.add("assigneeId")
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
        "custom_view.create",
        "custom_view.update",
        "custom_view.delete",
    ]


def _policy_error(code: str, message: str) -> AppError:
    return AppError(message, code=6, category="mutation_policy", diagnostics=[Diagnostic(code, message)])
