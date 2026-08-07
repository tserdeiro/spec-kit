"""The sole production adapter from allowlisted plan operations to GraphQL."""

from __future__ import annotations

from collections.abc import Mapping

from .allowlist import assert_allowed
from .errors import AppError, Diagnostic
from .linear_client import LinearClient


# Documents are named and fixed in source.  Dynamic user strings are variables,
# never interpolated into GraphQL.  The response selection is deliberately
# small: an ID is all the reconciler needs for safe create recovery.
_DOCUMENTS: dict[str, tuple[str, str, str | None, bool, str, str]] = {
    "project.create": ("projectCreate", "projectCreate", "ProjectCreateInput!", False, "project", "input"),
    "project.update": ("projectUpdate", "projectUpdate", "ProjectUpdateInput!", True, "project", "input"),
    "project.label.attach": ("projectAddLabel", "projectAddLabel", None, True, "project", "label"),
    "issue.create": ("issueCreate", "issueCreate", "IssueCreateInput!", False, "issue", "input"),
    "issue.update": ("issueUpdate", "issueUpdate", "IssueUpdateInput!", True, "issue", "input"),
    "issue.lifecycle.update": ("issueUpdate", "issueUpdate", "IssueUpdateInput!", True, "issue", "input"),
    "team.automation.create": ("gitAutomationStateCreate", "gitAutomationStateCreate", "GitAutomationStateCreateInput!", False, "gitAutomationState", "input"),
}


class LinearMutationExecutor:
    """Execute only a reviewed plan operation through :class:`LinearClient`."""

    def __init__(self, client: LinearClient) -> None:
        self.client = client

    def execute(self, operation: Mapping[str, object]) -> Mapping[str, object]:
        kind = operation.get("kind")
        input_values = operation.get("input")
        if not isinstance(kind, str) or not isinstance(input_values, Mapping):
            raise _mutation_error("mutation_operation", "plan operation is missing kind or input")
        assert_allowed(kind, input_values)
        operation_name, result_key, input_type, needs_id, resource_key, argument_style = _document_metadata(kind)
        variables: dict[str, object] = {"input": dict(input_values)} if argument_style == "input" else {}
        if needs_id:
            preconditions = operation.get("preconditions")
            remote_id = preconditions.get("id") if isinstance(preconditions, Mapping) else None
            if not isinstance(remote_id, str) or not remote_id:
                raise _mutation_error("mutation_target", "update operation is missing its remote ID")
            variables["id"] = remote_id
        if argument_style == "label":
            label_id = input_values.get("labelId")
            if not isinstance(label_id, str) or not label_id:
                raise _mutation_error("mutation_label", "project label mutation requires one labelId")
            variables["labelId"] = label_id
        document = _document(operation_name, result_key, input_type, needs_id, resource_key, argument_style)
        data = self.client.mutation(document, variables, operation_kind=kind)
        result = data.get(result_key)
        if not isinstance(result, Mapping):
            raise _mutation_error("mutation_response", "Linear mutation response is missing its result")
        if result.get("success") is not True:
            raise _mutation_error("mutation_rejected", "Linear mutation did not report success")
        resource = result.get(resource_key)
        if resource is not None and not isinstance(resource, Mapping):
            raise _mutation_error("mutation_response", "Linear mutation resource must be an object when present")
        return {"id": resource.get("id")} if resource is not None else {}


def _document_metadata(kind: str) -> tuple[str, str, str | None, bool, str, str]:
    try:
        return _DOCUMENTS[kind]
    except KeyError as error:
        raise _mutation_error("mutation_kind", f"unknown mutation kind: {kind}") from error


def _document(operation_name: str, result_key: str, input_type: str | None, needs_id: bool, resource_key: str, argument_style: str) -> str:
    if argument_style == "label":
        if not needs_id:
            raise AssertionError("label mutations require a reviewed remote target")
        arguments = "id: $id, labelId: $labelId"
        variables = "$id: String!, $labelId: String!"
    else:
        if input_type is None:
            raise AssertionError("input mutations require a GraphQL input type")
        arguments = "id: $id, input: $input" if needs_id else "input: $input"
        variables = f"$id: String!, $input: {input_type}" if needs_id else f"$input: {input_type}"
    return f"mutation {operation_name}({variables}) {{ {result_key}({arguments}) {{ success {resource_key} {{ id }} }} }}"


def _mutation_error(code: str, message: str) -> AppError:
    return AppError(message, code=9, category="graphql", diagnostics=[Diagnostic(code, message)])
