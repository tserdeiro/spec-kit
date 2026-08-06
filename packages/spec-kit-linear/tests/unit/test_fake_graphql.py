from __future__ import annotations

import json
import unittest
from urllib.request import Request, urlopen

from tests.support.fake_graphql import FakeGraphQLResponse, FakeGraphQLServer


class FakeGraphQLTests(unittest.TestCase):
    def test_fake_graphql_server_is_loopback_only_and_captures_requests(self) -> None:
        try:
            with FakeGraphQLServer({"data": {"ok": True}}) as server:
                request = Request(
                    server.endpoint,
                    method="POST",
                    data=json.dumps({"query": "query { viewer { id } }"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=2) as response:  # noqa: S310 - explicit loopback fixture
                    self.assertEqual(json.loads(response.read()), {"data": {"ok": True}})
        except PermissionError:
            self.skipTest("the execution sandbox forbids loopback socket binding")

        self.assertEqual(server.requests, [{"path": "/graphql", "payload": {"query": "query { viewer { id } }"}}])

    def test_fake_graphql_server_records_headers_and_query_only_audit(self) -> None:
        try:
            with FakeGraphQLServer(
                responses=[
                    FakeGraphQLResponse({"data": {"page": 1}}),
                    FakeGraphQLResponse({"data": {"page": 2}}, headers={"X-RateLimit-Reset": "0"}),
                ]
            ) as server:
                for cursor in (None, "one"):
                    request = Request(
                        server.endpoint,
                        method="POST",
                        data=json.dumps({"query": "query Things { things { id } }", "variables": {"after": cursor}}).encode("utf-8"),
                        headers={"Authorization": "secret"},
                    )
                    with urlopen(request, timeout=2):  # noqa: S310 - explicit loopback fixture
                        pass
        except PermissionError:
            self.skipTest("the execution sandbox forbids loopback socket binding")

        self.assertEqual(len(server.request_headers), 2)
        self.assertEqual(server.request_headers[0]["Authorization"], "secret")
        self.assertEqual(server.request_methods, ["POST", "POST"])
        self.assertFalse(server.has_non_query_request)
