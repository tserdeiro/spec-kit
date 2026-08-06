from __future__ import annotations

import unittest

from spec_kit_linear.domain import DesiredFeature, DesiredState, DesiredTask, RepositoryBinding, SourceRef
from spec_kit_linear.remote_discovery import AdoptedResource, FeatureAdoption, UnmanagedIssue
from spec_kit_linear.reporting import build_remote_only_rows, build_task_rows, render_status_table
from spec_kit_linear.work_state import SOURCE_CHECKBOX, SOURCE_PULL_REQUEST, STATE_COMPLETED, STATE_REVIEW, TaskWorkState


def _binding() -> RepositoryBinding:
    return RepositoryBinding(
        slug="sample-repository",
        project_label_group_id="group-1",
        project_label_id="label-1",
        project_label_name="sample-repository",
        project_view_id="view-project-1",
        issue_view_id="view-issue-1",
    )


def _task(identifier: str, *, completed: bool) -> DesiredTask:
    return DesiredTask(
        identity=f"task:001:{identifier}",
        title=f"{identifier} Title",
        completed=completed,
        project_identity="feature:001",
        marker=f"speckit-linear:task:001:{identifier}",
        managed_description="",
        source=SourceRef("specs/001/tasks.md", 1),
    )


def _desired_state(*tasks: DesiredTask) -> DesiredState:
    feature = DesiredFeature(
        identifier="001",
        project_identity="feature:001",
        project_title="001: Local projection",
        project_marker="speckit-linear:feature:001",
        project_label_id="label-1",
        managed_description="",
        source=SourceRef("specs/001/spec.md", 1),
        plan_source=SourceRef("specs/001/plan.md", 1),
        tasks=tasks,
    )
    return DesiredState(binding=_binding(), feature=feature)


class BuildTaskRowsTests(unittest.TestCase):
    def test_no_remote_project_yields_local_only_rows_with_no_remote_data(self) -> None:
        desired = _desired_state(_task("T001", completed=False), _task("T002", completed=True))

        rows = build_task_rows(discovery=_FakeDiscovery(features=()), desired_states=(desired,))

        self.assertEqual(len(rows), 1)
        feature_row = rows[0]
        self.assertEqual(feature_row["feature"], "001")
        self.assertFalse(feature_row["has_remote_project"])
        self.assertEqual(
            feature_row["tasks"],
            [
                {
                    "task": "T001",
                    "local_complete": False,
                    "derived_state": None,
                    "state_source": None,
                    "remote_identifier": None,
                    "remote_state": None,
                    "assignee": None,
                },
                {
                    "task": "T002",
                    "local_complete": True,
                    "derived_state": None,
                    "state_source": None,
                    "remote_identifier": None,
                    "remote_state": None,
                    "assignee": None,
                },
            ],
        )

    def test_derived_state_and_its_source_travel_with_each_row(self) -> None:
        desired = _desired_state(_task("T001", completed=False), _task("T002", completed=True))
        work_states = {
            "task:001:T001": TaskWorkState(STATE_REVIEW, SOURCE_PULL_REQUEST, "001-T001-parser"),
            "task:001:T002": TaskWorkState(STATE_COMPLETED, SOURCE_CHECKBOX),
        }

        rows = build_task_rows(discovery=_FakeDiscovery(features=()), desired_states=(desired,), work_states=work_states)

        by_task = {row["task"]: row for row in rows[0]["tasks"]}
        self.assertEqual((by_task["T001"]["derived_state"], by_task["T001"]["state_source"]), (STATE_REVIEW, SOURCE_PULL_REQUEST))
        self.assertEqual((by_task["T002"]["derived_state"], by_task["T002"]["state_source"]), (STATE_COMPLETED, SOURCE_CHECKBOX))

    def test_adopted_task_carries_remote_identifier_state_and_assignee(self) -> None:
        desired = _desired_state(_task("T001", completed=True))
        adoption = FeatureAdoption(
            feature="001",
            project=AdoptedResource("feature_project", "feature:001", "remote-project-1", "2026-07-29T00:00:00Z"),
            tasks={
                "task:001:T001": AdoptedResource(
                    "task_issue",
                    "task:001:T001",
                    "remote-issue-1",
                    "2026-07-29T00:00:00Z",
                    identifier="WOR-21",
                    state_name="Done",
                    assignee_name="Jane Doe",
                )
            },
            drift=(),
        )

        rows = build_task_rows(discovery=_FakeDiscovery(features=(adoption,)), desired_states=(desired,))

        self.assertTrue(rows[0]["has_remote_project"])
        self.assertEqual(
            rows[0]["tasks"][0],
            {
                "task": "T001",
                "local_complete": True,
                "derived_state": None,
                "state_source": None,
                "remote_identifier": "WOR-21",
                "remote_state": "Done",
                "assignee": "Jane Doe",
            },
        )

    def test_adopted_task_with_no_assignee_or_state_reports_none(self) -> None:
        desired = _desired_state(_task("T003", completed=False))
        adoption = FeatureAdoption(
            feature="001",
            project=AdoptedResource("feature_project", "feature:001", "remote-project-1", "2026-07-29T00:00:00Z"),
            tasks={"task:001:T003": AdoptedResource("task_issue", "task:001:T003", "remote-issue-3", "2026-07-29T00:00:00Z", identifier="WOR-23")},
            drift=(),
        )

        rows = build_task_rows(discovery=_FakeDiscovery(features=(adoption,)), desired_states=(desired,))

        self.assertEqual(rows[0]["tasks"][0]["remote_state"], None)
        self.assertEqual(rows[0]["tasks"][0]["assignee"], None)


class _FakeDiscovery:
    """Stands in for RemoteDiscovery: build_task_rows only reads `.features`."""

    def __init__(self, features: tuple[FeatureAdoption, ...]) -> None:
        self.features = features


class BuildRemoteOnlyRowsTests(unittest.TestCase):
    def test_a_feature_with_no_unmanaged_issues_is_omitted_entirely(self) -> None:
        desired = _desired_state(_task("T001", completed=False))
        adoption = FeatureAdoption(
            feature="001",
            project=AdoptedResource("feature_project", "feature:001", "remote-project-1", "2026-07-29T00:00:00Z"),
            tasks={},
            drift=(),
        )

        rows = build_remote_only_rows(discovery=_FakeDiscovery(features=(adoption,)), desired_states=(desired,))

        self.assertEqual(rows, [])

    def test_a_feature_with_no_adopted_project_at_all_is_also_omitted(self) -> None:
        desired = _desired_state(_task("T001", completed=False))

        rows = build_remote_only_rows(discovery=_FakeDiscovery(features=()), desired_states=(desired,))

        self.assertEqual(rows, [])

    def test_a_feature_with_unmanaged_issues_lists_them(self) -> None:
        desired = _desired_state(_task("T001", completed=False))
        unmanaged = UnmanagedIssue(
            id="issue-99",
            identifier="WOR-99",
            title="Users report a login redirect loop",
            state_name="Todo",
            assignee_name="Jane Doe",
            url="https://linear.app/example/issue/WOR-99",
        )
        adoption = FeatureAdoption(
            feature="001",
            project=AdoptedResource("feature_project", "feature:001", "remote-project-1", "2026-07-29T00:00:00Z"),
            tasks={},
            drift=(),
            unmanaged_issues=(unmanaged,),
        )

        rows = build_remote_only_rows(discovery=_FakeDiscovery(features=(adoption,)), desired_states=(desired,))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature"], "001")
        self.assertEqual(
            rows[0]["issues"],
            [{"identifier": "WOR-99", "title": "Users report a login redirect loop", "state": "Todo", "assignee": "Jane Doe", "url": "https://linear.app/example/issue/WOR-99"}],
        )


class RenderStatusTableTests(unittest.TestCase):
    def test_empty_task_rows_reports_no_local_features(self) -> None:
        rendered = render_status_table([])

        self.assertEqual(rendered, "No local features were selected.\n")

    def test_table_has_fixed_width_columns_and_a_dash_placeholder(self) -> None:
        rows = [
            {
                "feature": "001",
                "has_remote_project": True,
                "tasks": [
                    {"task": "T001", "local_complete": True, "remote_identifier": "WOR-21", "remote_state": "Done", "assignee": "Jane Doe"},
                    {"task": "T002", "local_complete": False, "remote_identifier": "WOR-22", "remote_state": "Todo", "assignee": None},
                ],
            }
        ]

        rendered = render_status_table(rows)
        lines = rendered.splitlines()

        self.assertEqual(lines[0], "Feature 001")
        header_line = lines[1]
        self.assertIn("TASK", header_line)
        self.assertIn("ASSIGNEE", header_line)
        data_lines = [line for line in lines[2:] if line.strip()]
        self.assertEqual(len(data_lines), 2)
        self.assertIn("[x]", data_lines[0])
        self.assertIn("WOR-21", data_lines[0])
        self.assertIn("Jane Doe", data_lines[0])
        self.assertIn("—", data_lines[1])
        # Fixed-width: the ASSIGNEE column starts at the same offset on every row.
        assignee_offset = header_line.index("ASSIGNEE")
        for line in data_lines:
            self.assertGreaterEqual(len(line), assignee_offset)

    def test_feature_without_a_remote_project_gets_an_explicit_note(self) -> None:
        rows = [
            {
                "feature": "002",
                "has_remote_project": False,
                "tasks": [{"task": "T001", "local_complete": False, "remote_identifier": None, "remote_state": None, "assignee": None}],
            }
        ]

        rendered = render_status_table(rows)

        self.assertIn("no remote Feature Project yet", rendered)

    def test_no_remote_only_rows_omits_the_section_entirely(self) -> None:
        rows = [{"feature": "001", "has_remote_project": True, "tasks": [{"task": "T001", "local_complete": True, "remote_identifier": "WOR-1", "remote_state": "Done", "assignee": None}]}]

        rendered = render_status_table(rows)

        self.assertNotIn("Remote-only issues", rendered)

    def test_remote_only_rows_are_appended_after_that_feature_s_task_rows(self) -> None:
        rows = [{"feature": "001", "has_remote_project": True, "tasks": [{"task": "T001", "local_complete": True, "remote_identifier": "WOR-1", "remote_state": "Done", "assignee": None}]}]
        remote_only_rows = [
            {
                "feature": "001",
                "issues": [{"identifier": "WOR-99", "title": "Users report a login redirect loop", "state": "Todo", "assignee": "Jane Doe", "url": "https://linear.app/example/issue/WOR-99"}],
            }
        ]

        rendered = render_status_table(rows, remote_only_rows)

        self.assertIn("Remote-only issues", rendered)
        self.assertIn("WOR-99", rendered)
        self.assertIn("Users report a login redirect loop", rendered)
        self.assertIn("Jane Doe", rendered)
        self.assertIn("https://linear.app/example/issue/WOR-99", rendered)
        # The remote-only block comes after the task table for that feature.
        self.assertLess(rendered.index("T001"), rendered.index("Remote-only issues"))

    def test_a_feature_absent_from_remote_only_rows_gets_no_block(self) -> None:
        rows = [
            {"feature": "001", "has_remote_project": True, "tasks": [{"task": "T001", "local_complete": True, "remote_identifier": "WOR-1", "remote_state": "Done", "assignee": None}]},
            {"feature": "002", "has_remote_project": True, "tasks": [{"task": "T001", "local_complete": True, "remote_identifier": "WOR-2", "remote_state": "Done", "assignee": None}]},
        ]
        remote_only_rows = [{"feature": "001", "issues": [{"identifier": "WOR-99", "title": "Bug", "state": None, "assignee": None, "url": ""}]}]

        rendered = render_status_table(rows, remote_only_rows)

        lines = rendered.splitlines()
        feature_002_index = next(index for index, line in enumerate(lines) if line == "Feature 002")
        self.assertNotIn("Remote-only issues", "\n".join(lines[feature_002_index:]))

    def test_renders_multiple_features_each_with_their_own_header(self) -> None:
        rows = [
            {"feature": "001", "has_remote_project": True, "tasks": [{"task": "T001", "local_complete": True, "remote_identifier": "WOR-1", "remote_state": "Done", "assignee": None}]},
            {"feature": "002", "has_remote_project": False, "tasks": [{"task": "T001", "local_complete": False, "remote_identifier": None, "remote_state": None, "assignee": None}]},
        ]

        rendered = render_status_table(rows)

        self.assertIn("Feature 001", rendered)
        self.assertIn("Feature 002", rendered)


if __name__ == "__main__":
    unittest.main()
