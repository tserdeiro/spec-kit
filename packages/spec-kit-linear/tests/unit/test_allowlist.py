"""The write contract: what may be mutated, and with which input fields.

The assignee may be set only when a Txxx Issue is created; every update kind
must keep forbidding it unconditionally, exactly like
`leadId`/`memberIds`/`archive`/`delete`.
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from spec_kit_linear.allowlist import ALLOWED_INPUTS, PUSH_MUTATIONS, assert_allowed
from spec_kit_linear.errors import AppError


class AssigneeAllowlistTests(unittest.TestCase):
    def test_no_mutation_kind_accepts_assignee_id(self) -> None:
        # Assignment is native Linear (the UI or the official Linear MCP);
        # no harness mutation may ever carry assigneeId, fail-closed with a
        # mutation_policy error (code 6) rather than a silent pass-through.
        for kind in sorted(PUSH_MUTATIONS):
            with self.assertRaises(AppError, msg=kind) as raised:
                assert_allowed(kind, {"assigneeId": "user-1"})
            self.assertEqual(raised.exception.code, 6, kind)
            self.assertEqual(raised.exception.category, "mutation_policy", kind)
            self.assertIn(raised.exception.diagnostics[0].code, {"mutation_input_not_allowed", "mutation_preserved_field"}, kind)

    def test_issue_create_still_rejects_lead_and_member_fields(self) -> None:
        create_id = str(uuid.uuid4())
        with self.assertRaises(AppError) as raised:
            assert_allowed("issue.create", {"id": create_id, "title": "T001", "teamId": "team-1", "leadId": "user-1"})
        self.assertEqual(raised.exception.diagnostics[0].code, "mutation_input_not_allowed")

    def test_assignee_id_is_preserved_even_when_an_inputs_table_allows_it(self) -> None:
        # Proves the unconditional preserved-field check is real and not
        # merely an accident of assigneeId being absent from every kind's
        # ALLOWED_INPUTS.
        patched = dict(ALLOWED_INPUTS)
        patched["issue.lifecycle.update"] = frozenset(ALLOWED_INPUTS["issue.lifecycle.update"] | {"assigneeId"})
        with patch("spec_kit_linear.allowlist.ALLOWED_INPUTS", patched):
            with self.assertRaises(AppError) as raised:
                assert_allowed("issue.lifecycle.update", {"stateId": "state-1", "assigneeId": "user-1"})
        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "mutation_preserved_field")


class WriteSurfaceTests(unittest.TestCase):
    def test_the_write_surface_is_exactly_the_seven_allowed_operations(self) -> None:
        # Six projection operations (push) plus onboard's single additive
        # Team PR-automation create.
        self.assertEqual(
            PUSH_MUTATIONS,
            frozenset(
                {
                    "project.create",
                    "project.update",
                    "project.label.attach",
                    "issue.create",
                    "issue.update",
                    "issue.lifecycle.update",
                    "team.automation.create",
                }
            ),
        )
        self.assertEqual(set(ALLOWED_INPUTS), set(PUSH_MUTATIONS))

    def test_destructive_and_out_of_scope_kinds_are_never_allowed(self) -> None:
        for kind in (
            "issue.delete",
            "issue.archive",
            "project.delete",
            "project.archive",
            "project.label.detach",
            "milestone.create",
            "milestone.update",
            "issue.milestone.update",
            "workflow_state.create",
            "project_label.create",
            "issue_label.create",
            "custom_view.create",
            "custom_view.update",
            "custom_view.delete",
            "bridge_comment.create",
            "initiative.create",
        ):
            with self.subTest(kind=kind):
                with self.assertRaises(AppError) as raised:
                    assert_allowed(kind, {"id": str(uuid.uuid4()), "name": "anything"})
                self.assertEqual(raised.exception.code, 6)
                self.assertEqual(raised.exception.diagnostics[0].code, "mutation_not_allowed")

    def test_no_input_table_carries_a_hierarchy_or_ownership_field(self) -> None:
        for kind, fields in ALLOWED_INPUTS.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    fields & {"leadId", "memberIds", "parentId", "projectMilestoneId", "archive", "delete"},
                    frozenset(),
                )


if __name__ == "__main__":
    unittest.main()
