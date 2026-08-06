"""Tests for plan-time [@alias] -> Linear user id resolution.

An alias not present in `team.members` is a configuration error (exit 3); an
email that resolves to zero or 2+ Linear users is a remote identity error
(exit 6).
"""

from __future__ import annotations

import unittest

from spec_kit_linear.assignee_resolution import resolve_task_assignees
from spec_kit_linear.domain import DesiredFeature, DesiredState, DesiredTask, RepositoryBinding, SourceRef
from spec_kit_linear.errors import AppError
from spec_kit_linear.linear_client import RemoteUser


BINDING = RepositoryBinding(
    slug="sample-repository",
    project_label_group_id="group-1",
    project_label_id="label-1",
    project_label_name="sample-repository",
    project_view_id="view-1",
    issue_view_id="view-2",
)


def _desired_state(*, assignee_alias: str | None, identity: str = "task:001:T001") -> DesiredState:
    source = SourceRef("specs/001-feature/tasks.md", 5)
    task = DesiredTask(
        identity=identity,
        title="T001 Sample task",
        completed=False,
        project_identity="feature:001",
        marker=f"speckit-linear:task:001:{identity.rsplit(':', 1)[-1]}",
        managed_description="<!-- marker -->\nbody\n<!-- /speckit-linear -->",
        source=source,
        assignee_alias=assignee_alias,
    )
    feature = DesiredFeature(
        identifier="001",
        project_identity="feature:001",
        project_title="001: Sample feature",
        project_marker="speckit-linear:feature:001",
        project_label_id=BINDING.project_label_id,
        managed_description="<!-- marker -->\nbody\n<!-- /speckit-linear -->",
        source=source,
        plan_source=source,
        tasks=(task,),
    )
    return DesiredState(binding=BINDING, feature=feature)


class _FakeUsersClient:
    def __init__(self, users_by_email: dict[str, tuple[RemoteUser, ...]]) -> None:
        self._users_by_email = users_by_email
        self.email_lookups: list[str] = []

    def find_users_by_email(self, email: str) -> tuple[RemoteUser, ...]:
        self.email_lookups.append(email)
        return self._users_by_email.get(email, ())


class AssigneeResolutionTests(unittest.TestCase):
    def test_no_alias_resolves_to_an_empty_mapping_without_any_remote_query(self) -> None:
        client = _FakeUsersClient({})
        config = {"team": {"members": {"facu": "facu@example.com"}}}

        resolved = resolve_task_assignees(client, config, (_desired_state(assignee_alias=None),))

        self.assertEqual(resolved, {})
        self.assertEqual(client.email_lookups, [])

    def test_known_alias_resolves_to_the_single_matching_user_id(self) -> None:
        client = _FakeUsersClient({"facu@example.com": (RemoteUser(id="user-1", email="facu@example.com"),)})
        config = {"team": {"members": {"facu": "facu@example.com"}}}

        resolved = resolve_task_assignees(client, config, (_desired_state(assignee_alias="facu"),))

        self.assertEqual(resolved, {"task:001:T001": "user-1"})

    def test_unknown_alias_fails_closed_with_configuration_exit_code(self) -> None:
        client = _FakeUsersClient({})
        config = {"team": {"members": {}}}

        with self.assertRaises(AppError) as raised:
            resolve_task_assignees(client, config, (_desired_state(assignee_alias="ghost"),))

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "task_assignee_alias_unknown")
        self.assertEqual(raised.exception.diagnostics[0].path, "specs/001-feature/tasks.md")
        self.assertEqual(raised.exception.diagnostics[0].line, 5)
        self.assertEqual(client.email_lookups, [])

    def test_email_with_zero_users_fails_closed_with_remote_identity_exit_code(self) -> None:
        client = _FakeUsersClient({})
        config = {"team": {"members": {"facu": "facu@example.com"}}}

        with self.assertRaises(AppError) as raised:
            resolve_task_assignees(client, config, (_desired_state(assignee_alias="facu"),))

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "task_assignee_email_ambiguous")

    def test_email_with_two_users_fails_closed_with_remote_identity_exit_code(self) -> None:
        client = _FakeUsersClient(
            {"facu@example.com": (RemoteUser(id="user-1", email="facu@example.com"), RemoteUser(id="user-2", email="facu@example.com"))}
        )
        config = {"team": {"members": {"facu": "facu@example.com"}}}

        with self.assertRaises(AppError) as raised:
            resolve_task_assignees(client, config, (_desired_state(assignee_alias="facu"),))

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "task_assignee_email_ambiguous")

    def test_repeated_alias_across_tasks_resolves_the_email_only_once(self) -> None:
        client = _FakeUsersClient({"facu@example.com": (RemoteUser(id="user-1", email="facu@example.com"),)})
        config = {"team": {"members": {"facu": "facu@example.com"}}}
        first = _desired_state(assignee_alias="facu", identity="task:001:T001")
        second = _desired_state(assignee_alias="facu", identity="task:001:T002")

        resolved = resolve_task_assignees(client, config, (first, second))

        self.assertEqual(resolved, {"task:001:T001": "user-1", "task:001:T002": "user-1"})
        self.assertEqual(client.email_lookups, ["facu@example.com"])


if __name__ == "__main__":
    unittest.main()
