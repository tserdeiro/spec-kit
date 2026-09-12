from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spec_kit_linear.errors import AppError, Diagnostic
from spec_kit_linear.linear_client import RemoteIssueContext, RemoteTeamSummary
from spec_kit_linear.work_item_resolution import resolve_work_item

TEAM_ID = "11111111-1111-4111-8111-111111111111"
CONFIG = {"linear": {"team_id": TEAM_ID, "team_key": "WOR"}}


def context(
    identifier: str = "WOR-12",
    *,
    team_id: str = TEAM_ID,
    branch: str = "users/alice/WOR-12",
) -> RemoteIssueContext:
    return RemoteIssueContext(
        id="issue-12",
        identifier=identifier,
        title="Fix the thing",
        description="Details",
        url="https://linear.app/i/12",
        branch_name=branch,
        team=RemoteTeamSummary(team_id, "WOR", "Work"),
    )


class FakeClient:
    def __init__(self, issue: RemoteIssueContext | None = None) -> None:
        self.issue = issue
        self.failure: AppError | None = None
        self.calls: list[str] = []

    def resolve_issue_context(self, identifier: str) -> RemoteIssueContext:
        self.calls.append(identifier)
        if self.failure is not None:
            raise self.failure
        if self.issue is None:
            return context(identifier)
        return self.issue


class WorkItemResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "speckit-linear.yml").touch()
        self.client = FakeClient()
        self.patches = [
            patch("spec_kit_linear.work_item_resolution.load_dotenv_files"),
            patch(
                "spec_kit_linear.work_item_resolution.load_config",
                return_value=(CONFIG, self.root / "speckit-linear.yml"),
            ),
            patch(
                "spec_kit_linear.work_item_resolution.resolve_endpoint",
                return_value="http://127.0.0.1/graphql",
            ),
            patch(
                "spec_kit_linear.work_item_resolution.load_credentials",
                return_value=object(),
            ),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def resolve(self, payload: dict[str, object]) -> dict[str, object]:
        return resolve_work_item(
            payload,
            root=self.root,
            client_factory=lambda *_: self.client,
        )

    def test_key_returns_exact_native_context_without_secrets(self) -> None:
        result = self.resolve({"issue_key": "WOR-12"})
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["resolution"]["branch_name"], "users/alice/WOR-12")
        self.assertNotIn("authorization", json.dumps(result))
        self.assertEqual(self.client.calls, ["WOR-12"])

    def test_feature_task_reference_is_excluded_before_remote_read(self) -> None:
        result = self.resolve({"issue_key": "009-T002-change"})
        self.assertEqual((result["category"], result["status"]), ("excluded", "excluded"))
        self.assertEqual(self.client.calls, [])

    def test_absent_config_is_an_explicit_success_outcome(self) -> None:
        other = self.root / "missing"
        other.mkdir()
        result = resolve_work_item(
            {"issue_key": "WOR-12"},
            root=other,
            client_factory=lambda *_: self.client,
        )
        self.assertEqual((result["category"], result["status"]), ("absent", "absent"))

    def test_wrong_team_is_rejected_at_resolver_boundary(self) -> None:
        self.client.issue = context(team_id="99999999-9999-4999-8999-999999999999")
        with self.assertRaisesRegex(AppError, "outside the repository") as raised:
            self.resolve({"issue_key": "WOR-12"})
        self.assertEqual(raised.exception.diagnostics[0].code, "work_item_wrong_team")

    def test_native_identity_mismatch_is_a_conflict(self) -> None:
        self.client.issue = context(identifier="WOR-13")
        with self.assertRaises(AppError) as raised:
            self.resolve({"issue_key": "WOR-12"})
        self.assertEqual(raised.exception.category, "conflict")

    def test_invalid_key_and_loader_failures_remain_actionable(self) -> None:
        with self.assertRaisesRegex(AppError, "must match TEAM-number"):
            self.resolve({"issue_key": "WOR-invalid"})
        failure = AppError(
            "Linear credentials are missing",
            code=4,
            category="credentials",
            diagnostics=[Diagnostic("credentials_missing", "Linear credentials are missing")],
        )
        with patch(
            "spec_kit_linear.work_item_resolution.load_credentials",
            side_effect=failure,
        ):
            with self.assertRaisesRegex(AppError, "credentials are missing"):
                self.resolve({"issue_key": "WOR-12"})

    def test_invalid_config_and_remote_failure_propagate(self) -> None:
        failure = AppError("invalid Linear configuration", code=2, category="config")
        with patch(
            "spec_kit_linear.work_item_resolution.load_config",
            side_effect=failure,
        ):
            with self.assertRaisesRegex(AppError, "invalid Linear configuration"):
                self.resolve({"issue_key": "WOR-12"})
        self.client.failure = AppError("Linear request was denied", code=7, category="graphql")
        with self.assertRaisesRegex(AppError, "request was denied"):
            self.resolve({"issue_key": "WOR-12"})

    def test_missing_explicit_or_env_config_is_a_configuration_failure(self) -> None:
        failure = AppError("configuration is missing", code=3, category="configuration")
        cases = [
            (str(self.root / "explicit.yml"), {}),
            (None, {"SPECKIT_LINEAR_CONFIG": str(self.root / "env.yml")}),
        ]
        for config_path, environment in cases:
            with self.subTest(config_path=config_path):
                with patch.dict(os.environ, environment, clear=True):
                    with patch(
                        "spec_kit_linear.work_item_resolution.load_config",
                        side_effect=failure,
                    ):
                        with self.assertRaisesRegex(AppError, "configuration is missing"):
                            resolve_work_item(
                                {"issue_key": "WOR-12"},
                                root=self.root,
                                config_path=config_path,
                                client_factory=lambda *_: self.client,
                            )


if __name__ == "__main__":
    unittest.main()
