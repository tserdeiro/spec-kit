from __future__ import annotations

from copy import deepcopy
import json
import unittest

from spec_kit_linear.config import load_config
from spec_kit_linear.credentials import Credentials
from spec_kit_linear.errors import AppError
from spec_kit_linear.linear_client import LinearClient
from tests.support.fixtures import copy_consumer_fixture
from tests.support.linear_transport import MemoryResponse, ScriptedOpener


class BindingValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()
        self.config, _ = load_config(self.fixture_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _binding(self) -> dict[str, object]:
        label_id = "44444444-4444-4444-8444-444444444444"
        return {
            "data": {
                "viewer": {"organization": {"id": "11111111-1111-4111-8111-111111111111"}},
                "team": {"id": "22222222-2222-4222-8222-222222222222", "key": "WOR", "name": "Work"},
                "projectLabelGroup": {"id": "33333333-3333-4333-8333-333333333333", "name": "Repository", "isGroup": True},
                "projectLabel": {
                    "id": label_id,
                    "name": "sample-repository",
                    "isGroup": False,
                    "parent": {"id": "33333333-3333-4333-8333-333333333333"},
                },
                "projectView": {
                    "id": "55555555-5555-4555-8555-555555555555",
                    "name": "Features",
                    "type": "project",
                    "shared": True,
                    "projectFilterData": json.dumps({"labels": {"some": {"id": {"eq": label_id}}}}),
                },
                "issueView": {
                    "id": "66666666-6666-4666-8666-666666666666",
                    "name": "Work",
                    "type": "issue",
                    "shared": True,
                    "filterData": {"project": {"labels": {"some": {"id": {"eq": label_id}}}}},
                },
            }
        }

    def _inspect(self, response: dict[str, object]) -> None:
        opener = ScriptedOpener([MemoryResponse(response)])
        client = LinearClient(
            Credentials("api_key", "test-secret"),
            endpoint="http://127.0.0.1:8123/graphql",
            opener=opener,
            sleeper=lambda _delay: None,
            jitter=lambda _lower, _upper: 0.0,
        )
        client.inspect_binding(self.config)
        self.assertTrue(str(opener.requests[0]["payload"]["query"]).lstrip().startswith("query "))

    def test_correct_binding_with_json_serialized_view_filter_passes(self) -> None:
        self._inspect(self._binding())

    def test_ui_serialized_view_filters_pass(self) -> None:
        """Linear's saved-view UI wraps filters in and/or lists and matches labels by name.

        These shapes were captured verbatim from a real workspace during the
        Etapa 3 remote acceptance run; the binding must accept them because
        views created manually through the UI never serialize the canonical
        ``labels.some.id.eq`` API form.
        """

        response = deepcopy(self._binding())
        response["data"]["projectView"]["projectFilterData"] = {
            "and": [
                {
                    "labels": {
                        "and": [
                            {
                                "or": [
                                    {"name": {"eq": "sample-repository"}},
                                    {"parent": {"name": {"eq": "sample-repository"}}},
                                ]
                            }
                        ]
                    }
                }
            ]
        }
        response["data"]["issueView"]["filterData"] = {
            "and": [{"project": {"labels": {"and": [{"name": {"eq": "sample-repository"}}]}}}]
        }
        self._inspect(response)

    def test_issue_view_pinned_to_one_project_fails_closed(self) -> None:
        """A filter pinning specific Project IDs does not follow the label."""

        response = deepcopy(self._binding())
        response["data"]["issueView"]["filterData"] = {
            "and": [{"project": {"id": {"in": ["8a202391-7fba-4b19-aa2a-4a14b8c34145"]}}}]
        }
        with self.assertRaises(AppError) as raised:
            self._inspect(response)
        self.assertEqual(raised.exception.code, 6)

    def test_each_binding_mismatch_fails_closed(self) -> None:
        cases = {
            "team_key": lambda data: data["data"]["team"].update({"key": "OTHER"}),
            "label_name": lambda data: data["data"]["projectLabel"].update({"name": "other-repository"}),
            "project_view_type": lambda data: data["data"]["projectView"].update({"type": "issue"}),
            "project_view_shared": lambda data: data["data"]["projectView"].update({"shared": False}),
            "project_view_filter": lambda data: data["data"]["projectView"].update({"projectFilterData": {}}),
            "issue_view_type": lambda data: data["data"]["issueView"].update({"type": "project"}),
            "issue_view_shared": lambda data: data["data"]["issueView"].update({"shared": False}),
            "issue_view_filter": lambda data: data["data"]["issueView"].update({"filterData": {}}),
        }
        for name, alter in cases.items():
            with self.subTest(name=name):
                response = deepcopy(self._binding())
                alter(response)
                with self.assertRaises(AppError) as raised:
                    self._inspect(response)
                self.assertEqual(raised.exception.code, 6)
