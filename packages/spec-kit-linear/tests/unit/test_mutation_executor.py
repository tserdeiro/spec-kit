from __future__ import annotations

import unittest

from spec_kit_linear.allowlist import assert_allowed
from spec_kit_linear.errors import AppError
from spec_kit_linear.mutation_executor import LinearMutationExecutor


class _CapturingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def mutation(self, document: str, variables: dict[str, object], *, operation_kind: str) -> dict[str, object]:
        self.calls.append((document, variables, operation_kind))
        if operation_kind == "project.label.attach":
            return {"projectAddLabel": {"success": True, "project": {"id": "project-1"}}}
        if operation_kind in {"project.update", "project.create"}:
            return {"projectUpdate" if operation_kind == "project.update" else "projectCreate": {"success": True, "project": {"id": "project-1"}}}
        return {"issueCreate" if operation_kind == "issue.create" else "issueUpdate": {"success": True, "issue": {"id": "issue-1"}}}


class MutationExecutorContractTests(unittest.TestCase):
    def test_project_label_attach_is_additive_and_selects_only_the_project_payload(self) -> None:
        client = _CapturingClient()
        result = LinearMutationExecutor(client).execute(
            {"kind": "project.label.attach", "input": {"labelId": "repository-label"}, "preconditions": {"id": "project-1"}}
        )
        document, variables, operation_kind = client.calls[0]
        self.assertEqual(result, {"id": "project-1"})
        self.assertEqual(operation_kind, "project.label.attach")
        self.assertIn("projectAddLabel", document)
        self.assertIn("$id: String!", document)
        self.assertIn("$labelId: String!", document)
        self.assertNotIn("$id: ID!", document)
        self.assertIn("project { id }", document)
        self.assertNotIn("input: $input", document)
        self.assertEqual(variables, {"id": "project-1", "labelId": "repository-label"})

    def test_updates_use_exact_string_remote_id_variable_type(self) -> None:
        client = _CapturingClient()
        LinearMutationExecutor(client).execute(
            {"kind": "project.update", "input": {"name": "New title"}, "preconditions": {"id": "project-1"}}
        )
        document, variables, _ = client.calls[0]
        self.assertIn("$id: String!", document)
        self.assertNotIn("$id: ID!", document)
        self.assertEqual(variables, {"id": "project-1", "input": {"name": "New title"}})

    def test_issue_lifecycle_update_maps_onto_issue_update(self) -> None:
        client = _CapturingClient()
        LinearMutationExecutor(client).execute(
            {"kind": "issue.lifecycle.update", "input": {"stateId": "state-1"}, "preconditions": {"id": "issue-1"}}
        )
        document, variables, _ = client.calls[0]
        self.assertIn("issueUpdate", document)
        self.assertEqual(variables, {"id": "issue-1", "input": {"stateId": "state-1"}})

    def test_issue_create_carries_its_own_uuid_in_the_input(self) -> None:
        client = _CapturingClient()
        create_id = "00000000-0000-4000-8000-000000000000"
        result = LinearMutationExecutor(client).execute(
            {"kind": "issue.create", "input": {"id": create_id, "title": "T001 Do it", "teamId": "team-1", "projectId": "project-1", "description": "body"}}
        )
        document, variables, _ = client.calls[0]
        self.assertIn("issueCreate", document)
        self.assertIn("IssueCreateInput!", document)
        self.assertNotIn("$id:", document)
        self.assertEqual(variables["input"]["id"], create_id)
        self.assertEqual(result, {"id": "issue-1"})

    def test_kinds_outside_the_allowlist_are_refused(self) -> None:
        for kind, input_values in (
            ("project_label.create", {"id": "00000000-0000-4000-8000-000000000000", "name": "Repository"}),
            ("custom_view.create", {"id": "00000000-0000-4000-8000-000000000000", "name": "Features"}),
            ("milestone.create", {"id": "00000000-0000-4000-8000-000000000000", "name": "Phase 01"}),
            ("issue.delete", {}),
        ):
            with self.subTest(kind=kind):
                with self.assertRaises(AppError):
                    assert_allowed(kind, input_values)
                with self.assertRaises(AppError):
                    LinearMutationExecutor(_CapturingClient()).execute({"kind": kind, "input": input_values})

    def test_create_requires_uuid4_input_id_and_update_rejects_input_id(self) -> None:
        with self.assertRaises(AppError):
            assert_allowed("project.create", {"name": "Feature", "teamIds": ["team"]})
        with self.assertRaises(AppError):
            assert_allowed("project.create", {"id": "00000000-0000-5000-8000-000000000000", "name": "Feature", "teamIds": ["team"]})
        with self.assertRaises(AppError):
            assert_allowed("project.update", {"id": "00000000-0000-4000-8000-000000000000", "name": "Feature"})
