from __future__ import annotations

import socket
import unittest

from spec_kit_linear.credentials import Credentials
from spec_kit_linear.errors import AppError
from spec_kit_linear.linear_client import LinearClient
from tests.support.linear_transport import MemoryResponse, ScriptedOpener


READ_QUERY = "query Viewer { viewer { id } }"
PAGED_QUERY = "query Things($first: Int!, $after: String) { things(first: $first, after: $after) { nodes { id } pageInfo { hasNextPage endCursor } } }"


class LinearClientTests(unittest.TestCase):
    def _client(self, outcomes: list[MemoryResponse | Exception], *, max_attempts: int = 3) -> tuple[LinearClient, ScriptedOpener, list[float]]:
        opener = ScriptedOpener(outcomes)
        delays: list[float] = []
        client = LinearClient(
            Credentials("api_key", "super-secret-key"),
            endpoint="http://127.0.0.1:8123/graphql",
            opener=opener,
            sleeper=delays.append,
            jitter=lambda _lower, _upper: 0.0,
            max_attempts=max_attempts,
        )
        return client, opener, delays

    def test_query_uses_authorization_request_id_and_only_named_queries(self) -> None:
        client, opener, _ = self._client([MemoryResponse({"data": {"viewer": {"id": "viewer"}}})])

        self.assertEqual(client.query(READ_QUERY), {"viewer": {"id": "viewer"}})
        request = opener.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertTrue(str(request["payload"]["query"]).lstrip().startswith("query "))
        headers = {str(key).lower(): value for key, value in request["headers"].items()}
        self.assertEqual(headers["authorization"], "super-secret-key")
        self.assertIn("x-speckit-linear-request-id", headers)
        with self.assertRaises(ValueError):
            client.query("subscription Bad { viewer { id } }")

    def test_connection_paginates_with_cursors(self) -> None:
        client, opener, _ = self._client(
            [
                MemoryResponse({"data": {"things": {"nodes": [{"id": "one"}], "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}}}}),
                MemoryResponse({"data": {"things": {"nodes": [{"id": "two"}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}),
            ]
        )

        self.assertEqual(client.connection(PAGED_QUERY, root_key="things", variables={}), [{"id": "one"}, {"id": "two"}])
        self.assertIsNone(opener.requests[0]["payload"]["variables"]["after"])
        self.assertEqual(opener.requests[1]["payload"]["variables"]["after"], "cursor-1")

    def test_graphql_errors_with_http_success_are_sanitized_and_fail(self) -> None:
        client, _, _ = self._client(
            [MemoryResponse({"data": {"viewer": None}, "errors": [{"message": "Bearer top-secret", "extensions": {"code": "BAD_USER_INPUT"}}]})]
        )

        with self.assertRaises(AppError) as raised:
            client.query(READ_QUERY)
        self.assertEqual(raised.exception.code, 9)
        self.assertNotIn("top-secret", str(raised.exception))
        self.assertNotIn("top-secret", " ".join(item.message for item in raised.exception.diagnostics))

    def test_rate_limit_http_400_retries_safe_read_query(self) -> None:
        client, opener, delays = self._client(
            [
                MemoryResponse(
                    {"errors": [{"message": "slow", "extensions": {"code": "RATELIMITED"}}]},
                    status=400,
                    headers={"Retry-After": "0"},
                ),
                MemoryResponse({"data": {"viewer": {"id": "viewer"}}}),
            ]
        )

        self.assertEqual(client.query(READ_QUERY), {"viewer": {"id": "viewer"}})
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(len(delays), 1)
        self.assertTrue(all(str(item["payload"]["query"]).lstrip().startswith("query ") for item in opener.requests))

    def test_mutation_is_allowlisted_named_and_never_blindly_retries(self) -> None:
        opener = ScriptedOpener([TimeoutError("response lost")])
        client = LinearClient(
            Credentials("api_key", "test-secret"),
            endpoint="http://127.0.0.1:8123/graphql",
            opener=opener,
            sleeper=lambda _delay: None,
            jitter=lambda _lower, _upper: 0.0,
        )
        with self.assertRaises(AppError) as raised:
            client.mutation("mutation ProjectCreate($input: ProjectCreateInput!) { projectCreate(input: $input) { success } }", {"input": {"name": "x"}}, operation_kind="project.create")
        self.assertEqual(raised.exception.category, "transport")
        self.assertEqual(len(opener.requests), 1)
        with self.assertRaises(AppError):
            client.mutation("mutation Unsafe { issueDelete(id: \"x\") { success } }", operation_kind="issue.delete")

    def test_find_workflow_states_by_team_lists_every_state(self) -> None:
        client, opener, _ = self._client(
            [
                MemoryResponse(
                    {
                        "data": {
                            "workflowStates": {
                                "nodes": [
                                    {"id": "state-done", "name": "Done", "type": "completed", "position": 3.0, "updatedAt": "2099-01-01T00:00:00Z"},
                                    {"id": "state-todo", "name": "Todo", "type": "unstarted", "position": 1.0, "updatedAt": "2099-01-01T00:00:00Z"},
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                ),
            ]
        )

        found = client.find_workflow_states_by_team("team-1")

        self.assertEqual({(item.id, item.type, item.position) for item in found}, {("state-done", "completed", 3.0), ("state-todo", "unstarted", 1.0)})
        self.assertEqual(opener.requests[0]["payload"]["variables"]["teamId"], "team-1")
        self.assertNotIn("name", opener.requests[0]["payload"]["variables"])

    def test_find_users_by_email_maps_fields(self) -> None:
        client, opener, _ = self._client(
            [MemoryResponse({"data": {"users": {"nodes": [{"id": "user-1", "email": "facu@example.com"}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}})]
        )

        found = client.find_users_by_email("facu@example.com")

        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].id, found[0].email), ("user-1", "facu@example.com"))
        self.assertEqual(opener.requests[0]["payload"]["variables"]["email"], "facu@example.com")

    def test_resolve_workspace_id_reads_viewer_organization(self) -> None:
        client, opener, _ = self._client([MemoryResponse({"data": {"viewer": {"organization": {"id": "workspace-1"}}}})])

        self.assertEqual(client.resolve_workspace_id(), "workspace-1")
        self.assertTrue(str(opener.requests[0]["payload"]["query"]).lstrip().startswith("query "))

    def test_resolve_team_by_id_reads_key_and_name(self) -> None:
        client, opener, _ = self._client([MemoryResponse({"data": {"team": {"id": "team-1", "key": "WOR", "name": "Work"}}})])

        team = client.resolve_team_by_id("team-1")

        self.assertEqual((team.id, team.key, team.name), ("team-1", "WOR", "Work"))
        self.assertEqual(opener.requests[0]["payload"]["variables"]["id"], "team-1")

    def test_find_team_by_key_paginates_and_maps_fields(self) -> None:
        client, opener, _ = self._client(
            [MemoryResponse({"data": {"teams": {"nodes": [{"id": "team-1", "key": "WOR", "name": "Work"}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}})]
        )

        found = client.find_team_by_key("WOR")

        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].id, found[0].key, found[0].name), ("team-1", "WOR", "Work"))
        self.assertEqual(opener.requests[0]["payload"]["variables"]["key"], "WOR")

    def test_find_project_labels_by_name_maps_group_and_parent_fields(self) -> None:
        client, opener, _ = self._client(
            [
                MemoryResponse(
                    {
                        "data": {
                            "projectLabels": {
                                "nodes": [
                                    {"id": "group-1", "name": "Repository", "isGroup": True, "updatedAt": "2099-01-01T00:00:00Z", "parent": None},
                                    {"id": "child-1", "name": "Repository", "isGroup": False, "updatedAt": "2099-01-01T00:00:00Z", "parent": {"id": "group-1"}},
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                ),
            ]
        )

        found = client.find_project_labels_by_name("Repository")

        self.assertEqual([(item.id, item.is_group, item.parent_id) for item in found], [("group-1", True, None), ("child-1", False, "group-1")])
        self.assertNotIn("teamId", opener.requests[0]["payload"]["variables"])

    def test_auth_service_timeout_invalid_json_and_nullability_have_typed_errors(self) -> None:
        cases = [
            (MemoryResponse({"errors": []}, status=401), 5),
            (MemoryResponse({"errors": []}, status=403), 5),
            (MemoryResponse({"error": "unavailable"}, status=503), 8),
            (socket.timeout("slow"), 8),
            (MemoryResponse("not-json"), 9),
            (MemoryResponse({"data": None}), 9),
        ]
        for outcome, expected_code in cases:
            with self.subTest(expected_code=expected_code, outcome=type(outcome).__name__):
                client, _, _ = self._client([outcome], max_attempts=1)
                with self.assertRaises(AppError) as raised:
                    client.query(READ_QUERY)
                self.assertEqual(raised.exception.code, expected_code)
