from __future__ import annotations

import json
import unittest

from spec_kit_linear.config import load_config, repository_binding
from spec_kit_linear.credentials import Credentials
from spec_kit_linear.errors import AppError
from spec_kit_linear.linear_client import LinearClient
from spec_kit_linear.parser import parse_feature
from spec_kit_linear.planner import build_push_plan
from spec_kit_linear.projection import project_feature
from spec_kit_linear.remote_discovery import discover_and_adopt
from spec_kit_linear.reporting import status_report
from tests.support.fixtures import copy_consumer_fixture
from tests.support.linear_transport import MemoryResponse, ScriptedOpener


class RemoteDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()
        self.config, _ = load_config(self.fixture_root)
        feature = parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")
        self.desired, _ = project_feature(feature, repository_binding(self.config))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _client(self, outcomes: list[MemoryResponse]) -> tuple[LinearClient, ScriptedOpener]:
        opener = ScriptedOpener(outcomes)
        return (
            LinearClient(
                Credentials("api_key", "test-secret"),
                endpoint="http://127.0.0.1:8123/graphql",
                opener=opener,
                sleeper=lambda _delay: None,
                jitter=lambda _lower, _upper: 0.0,
            ),
            opener,
        )

    def _binding(self) -> dict[str, object]:
        return {
            "data": {
                "viewer": {"organization": {"id": "11111111-1111-4111-8111-111111111111"}},
                "team": {"id": "22222222-2222-4222-8222-222222222222", "key": "WOR", "name": "Work"},
                "projectLabelGroup": {"id": "33333333-3333-4333-8333-333333333333", "name": "Repository", "isGroup": True},
                "projectLabel": {
                    "id": "44444444-4444-4444-8444-444444444444",
                    "name": "sample-repository",
                    "isGroup": False,
                    "parent": {"id": "33333333-3333-4333-8333-333333333333"},
                },
                "projectView": {
                    "id": "55555555-5555-4555-8555-555555555555",
                    "name": "Features",
                    "type": "project",
                    "shared": True,
                    "projectFilterData": {"labels": {"some": {"id": {"eq": "44444444-4444-4444-8444-444444444444"}}}},
                },
                "issueView": {
                    "id": "66666666-6666-4666-8666-666666666666",
                    "name": "Work",
                    "type": "issue",
                    "shared": True,
                    "filterData": {"project": {"labels": {"some": {"id": {"eq": "44444444-4444-4444-8444-444444444444"}}}}},
                },
            }
        }

    def _connection(self, key: str, nodes: list[dict[str, object]]) -> dict[str, object]:
        return {"data": {key: {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}

    def test_discovers_and_adopts_one_complete_feature_without_non_query_requests(self) -> None:
        project = {
            "id": "project-001",
            "name": "001: Local projection",
            "description": "<!-- speckit-linear:feature:001 -->\n<!-- /speckit-linear -->",
            "updatedAt": "2026-07-25T00:00:00.000Z",
            "teams": {"nodes": [{"id": "22222222-2222-4222-8222-222222222222", "key": "WOR"}]},
            "labels": {"nodes": [{"id": "44444444-4444-4444-8444-444444444444", "name": "sample-repository"}]},
        }
        issues = [
            {
                "id": f"issue-{number}",
                "identifier": f"WOR-{number}",
                "title": f"T00{number} Task",
                "description": f"<!-- speckit-linear:task:001:T00{number} -->\n<!-- /speckit-linear -->",
                "updatedAt": "2026-07-25T00:00:00.000Z",
                "project": {"id": "project-001"},
                "parent": None,
                "assignee": None,
                "labels": {"nodes": []},
            }
            for number in range(1, 4)
        ]
        client, opener = self._client(
            [
                MemoryResponse(self._binding()),
                MemoryResponse(self._connection("projects", [project])),
                MemoryResponse(self._connection("issues", issues)),
            ]
        )

        discovery = discover_and_adopt(client, self.config, (self.desired,))

        feature = discovery.features[0]
        self.assertIsNotNone(feature.project)
        self.assertEqual(len(feature.tasks), 3)
        self.assertEqual(feature.drift, ())
        self.assertEqual(status_report(discovery)["remote_operations"]["writes"], 0)
        self.assertTrue(all(str(request["payload"]["query"]).lstrip().startswith("query ") for request in opener.requests))

    def test_status_task_rows_carry_remote_identifier_state_and_assignee(self) -> None:
        # The human-mode task table (and its --json structural twin,
        # task_rows) reads the Issue's
        # identifier/state name/assignee display name straight off the
        # PROJECT_ISSUES_QUERY response -- no second query.
        project = {
            "id": "project-001",
            "name": "001: Local projection",
            "description": "<!-- speckit-linear:feature:001 -->\n<!-- /speckit-linear -->",
            "updatedAt": "2026-07-25T00:00:00.000Z",
            "teams": {"nodes": [{"id": "22222222-2222-4222-8222-222222222222", "key": "WOR"}]},
            "labels": {"nodes": [{"id": "44444444-4444-4444-8444-444444444444", "name": "sample-repository"}]},
        }
        issues = [
            {
                "id": "issue-1",
                "identifier": "WOR-21",
                "title": "T001 Task",
                "description": "<!-- speckit-linear:task:001:T001 -->\n<!-- /speckit-linear -->",
                "updatedAt": "2026-07-25T00:00:00.000Z",
                "project": {"id": "project-001"},
                "parent": None,
                "assignee": {"id": "user-1", "displayName": "Jane Doe"},
                "state": {"id": "state-done", "name": "Done"},
                "labels": {"nodes": []},
            },
            {
                "id": "issue-2",
                "identifier": "WOR-22",
                "title": "T002 Task",
                "description": "<!-- speckit-linear:task:001:T002 -->\n<!-- /speckit-linear -->",
                "updatedAt": "2026-07-25T00:00:00.000Z",
                "project": {"id": "project-001"},
                "parent": None,
                "assignee": None,
                "state": {"id": "state-todo", "name": "Todo"},
                "labels": {"nodes": []},
            },
            {
                "id": "issue-3",
                "identifier": "WOR-23",
                "title": "T003 Task",
                "description": "<!-- speckit-linear:task:001:T003 -->\n<!-- /speckit-linear -->",
                "updatedAt": "2026-07-25T00:00:00.000Z",
                "project": {"id": "project-001"},
                "parent": None,
                "assignee": None,
                "labels": {"nodes": []},
            },
        ]
        client, _ = self._client(
            [
                MemoryResponse(self._binding()),
                MemoryResponse(self._connection("projects", [project])),
                MemoryResponse(self._connection("issues", issues)),
            ]
        )

        discovery = discover_and_adopt(client, self.config, (self.desired,))

        adopted_t001 = discovery.features[0].tasks["task:001:T001"]
        self.assertEqual(adopted_t001.identifier, "WOR-21")
        self.assertEqual(adopted_t001.state_name, "Done")
        self.assertEqual(adopted_t001.assignee_name, "Jane Doe")
        adopted_t002 = discovery.features[0].tasks["task:001:T002"]
        self.assertEqual(adopted_t002.state_name, "Todo")
        self.assertIsNone(adopted_t002.assignee_name)
        # T003's remote Issue has no `state` field at all in this fixture --
        # RemoteIssue's schema-nullability guard treats an absent key the
        # same as an explicit null, never a crash.
        adopted_t003 = discovery.features[0].tasks["task:001:T003"]
        self.assertIsNone(adopted_t003.state_name)

        report = status_report(discovery, (self.desired,))
        task_rows = report["task_rows"][0]["tasks"]
        by_task = {row["task"]: row for row in task_rows}
        self.assertEqual(
            by_task["T001"],
            {
                "task": "T001",
                "local_complete": False,
                "derived_state": None,
                "state_source": None,
                "next": None,
                "remote_identifier": "WOR-21",
                "remote_state": "Done",
                "assignee": "Jane Doe",
            },
        )
        self.assertEqual(by_task["T002"]["assignee"], None)

    def test_unmanaged_issues_are_surfaced_separately_and_never_enter_a_push_plan(self) -> None:
        # A PM/bug-report Issue created directly in Linear, inside the
        # Feature Project, with no bridge task marker at all.
        project = {
            "id": "project-001",
            "name": "001: Local projection",
            "description": "<!-- speckit-linear:feature:001 -->\n<!-- /speckit-linear -->",
            "updatedAt": "2026-07-25T00:00:00.000Z",
            "teams": {"nodes": [{"id": "22222222-2222-4222-8222-222222222222", "key": "WOR"}]},
            "labels": {"nodes": [{"id": "44444444-4444-4444-8444-444444444444", "name": "sample-repository"}]},
        }
        managed_issues = [
            {
                "id": f"issue-{number}",
                "identifier": f"WOR-{number}",
                "title": f"T00{number} Task",
                "description": f"<!-- speckit-linear:task:001:T00{number} -->\n<!-- /speckit-linear -->",
                "updatedAt": "2026-07-25T00:00:00.000Z",
                "project": {"id": "project-001"},
                "parent": None,
                "assignee": None,
                "labels": {"nodes": []},
            }
            for number in range(1, 4)
        ]
        remote_only_issue = {
            "id": "issue-bug-report",
            "identifier": "WOR-99",
            "title": "Users report a login redirect loop",
            "description": "Filed directly from a customer report; no bridge marker here at all.",
            "updatedAt": "2026-07-25T00:00:00.000Z",
            "project": {"id": "project-001"},
            "parent": None,
            "assignee": {"id": "user-1", "displayName": "Jane Doe"},
            "state": {"id": "state-todo", "name": "Todo", "type": "unstarted"},
            "labels": {"nodes": []},
            "url": "https://linear.app/example/issue/WOR-99",
        }
        client, _ = self._client(
            [
                MemoryResponse(self._binding()),
                MemoryResponse(self._connection("projects", [project])),
                MemoryResponse(self._connection("issues", managed_issues + [remote_only_issue])),
            ]
        )

        discovery = discover_and_adopt(client, self.config, (self.desired,))

        feature = discovery.features[0]
        self.assertEqual(len(feature.tasks), 3)
        self.assertEqual(len(feature.unmanaged_issues), 1)
        unmanaged = feature.unmanaged_issues[0]
        self.assertEqual(unmanaged.identifier, "WOR-99")
        self.assertEqual(unmanaged.title, "Users report a login redirect loop")
        self.assertEqual(unmanaged.state_name, "Todo")
        self.assertEqual(unmanaged.assignee_name, "Jane Doe")
        self.assertEqual(unmanaged.url, "https://linear.app/example/issue/WOR-99")

        plan = build_push_plan(self.desired, discovery)

        # Structural guarantee, not a fragile string search: build_push_plan
        # (planner.py) only ever reads `.project`/`.tasks` off a
        # FeatureAdoption -- it never touches `.unmanaged_issues` at all, so
        # this remote-only issue cannot possibly reach a plan operation. The
        # serialized-plan scan below is a behavioral belt-and-suspenders
        # check on top of that structural fact.
        serialized = json.dumps(plan["operations"])
        self.assertNotIn("WOR-99", serialized)
        self.assertNotIn("issue-bug-report", serialized)
        for operation in plan["operations"]:
            self.assertNotEqual(operation["target"], "WOR-99")

    def test_duplicate_marker_is_a_fail_closed_identity_error(self) -> None:
        project = {
            "id": "project-001",
            "name": "001: Local projection",
            "description": "<!-- speckit-linear:feature:001 -->",
            "updatedAt": "2026-07-25T00:00:00.000Z",
            "teams": {"nodes": [{"id": "22222222-2222-4222-8222-222222222222", "key": "WOR"}]},
            "labels": {"nodes": [{"id": "44444444-4444-4444-8444-444444444444", "name": "sample-repository"}]},
        }
        duplicate = {**project, "id": "project-duplicate"}
        client, _ = self._client(
            [
                MemoryResponse(self._binding()),
                MemoryResponse(self._connection("projects", [project, duplicate])),
                MemoryResponse(self._connection("issues", [])),
                MemoryResponse(self._connection("issues", [])),
            ]
        )

        with self.assertRaises(AppError) as raised:
            discover_and_adopt(client, self.config, (self.desired,))
        self.assertEqual(raised.exception.code, 6)
