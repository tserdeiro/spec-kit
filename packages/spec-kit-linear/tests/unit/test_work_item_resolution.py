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

    def resolve_branch_issues(self, branches: list[str]) -> dict[str, RemoteIssueContext | None]:
        self.calls.append(("branches", tuple(branches)))
        return {branch: self.issue for branch in branches}

    def resolve_issue_contexts(self, team_id: str, identifiers: list[str]) -> dict[str, RemoteIssueContext | None]:
        self.calls.append(("issues", tuple(identifiers)))
        return {identifier: context(identifier) for identifier in identifiers}


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
        cases = (("WOR-invalid", "must match TEAM-number"), (None, "non-empty Issue key"))
        for issue_key, message in cases:
            with self.subTest(issue_key=issue_key):
                with self.assertRaisesRegex(AppError, message):
                    self.resolve({"issue_key": issue_key})
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

    def test_strict_branch_key_falls_back_after_native_null(self) -> None:
        result = self.resolve({"branch_names": ["user-2/WOR-12-fix"]})
        self.assertEqual(result["observations"][0]["status"], "resolved")
        self.assertEqual(self.client.calls, [("branches", ("user-2/WOR-12-fix",)), ("issues", ("WOR-12",))])

    def test_multiple_branch_keys_conflict_with_or_without_native(self) -> None:
        cases = [
            ("WOR-1-WOR-2-fix", None),
            ("WOR-1-WOR-2-fix", context("WOR-1", branch="WOR-1-WOR-2-fix")),
            ("WOR-1-WOR-2-fix", context("WOR-2", branch="WOR-1-WOR-2-fix")),
            ("WOR-1-OTHER-2-fix", None),
            ("WOR-1-OTHER-2-fix", context("WOR-2", branch="WOR-1-OTHER-2-fix")),
        ]
        for branch, native in cases:
            with self.subTest(branch=branch, native=native is not None):
                self.client.issue = native
                result = self.resolve({"branch_names": [branch]})
                expected = "resolved" if native is not None and native.identifier == "WOR-1" else "conflict"
                self.assertEqual(result["observations"][0]["status"], expected)

    def test_native_branch_without_explicit_key(self) -> None:
        cases = ((None, "unresolved"), (context(branch="fix-related-WOR-1"), "resolved"))
        for native, expected in cases:
            with self.subTest(expected=expected):
                self.client.issue = native
                result = self.resolve({"branch_names": ["fix-related-WOR-1"]})
                self.assertEqual(result["observations"][0]["status"], expected)
        self.assertEqual(self.client.calls, [("branches", ("fix-related-WOR-1",))] * 2)

    def test_native_wrong_team_is_a_conflict_observation(self) -> None:
        self.client.issue = context(team_id="99999999-9999-4999-8999-999999999999")
        result = self.resolve({"branch_names": ["users/alice/fix"]})
        self.assertEqual(result["observations"][0]["status"], "conflict")

    def test_tracker_section_cases(self) -> None:
        cases = [
            ("Mention WOR-12 here.\n\n## Work item\n\n- Tracker: Fixes WOR-12\n\n## Outcome\n\nWOR-99", "resolved"),
            ("## Work item\n\n- Tracker: Fixes WOR-12\n\n## Outcome\n\n## Work item\n\n- Tracker: Fixes WOR-13", "conflict"),
            ("## Work item\n\n```markdown\n- Tracker: Fixes WOR-12\n```\n", "unresolved"),
            ("## Work item\n\n    - Tracker: Fixes WOR-12\n\n\t- Tracker: Fixes WOR-13", "unresolved"),
            ("## Work item\n\n- Tracker: Fixes OTHER-foo", "conflict"),
            ("## Work item\n\n- Tracker:", "conflict"),
            ("## Work item\n\n- Tracker: WOR-12", "conflict"),
            ("## Work item\n\n- Tracker: Fixes N/A", "conflict"),
            ("## Work item\n\n- Tracker: Fixes placeholder", "conflict"),
            ("## Work item\n\n- Tracker: Fixes WOR-12\n\n# Outcome\n\n- Tracker: Fixes WOR-13", "resolved"),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                result = self.resolve({"pull_requests": [{"head_branch": "old-title", "body": body}]})
                self.assertEqual(result["observations"][0]["status"], expected)

    def test_tracker_and_strict_branch_conflict_stays_per_observation(self) -> None:
        result = self.resolve(
            {"pull_requests": [{"head_branch": "WOR-1-fix", "body": "## Work item\n\n- Tracker: Fixes WOR-2"}]}
        )
        self.assertEqual(result["observations"][0]["status"], "conflict")
        self.assertEqual(self.client.calls, [("branches", ("WOR-1-fix",))])
        matching = self.resolve({"pull_requests": [{"head_branch": "WOR-1-WOR-2-fix", "body": "## Work item\n\n- Tracker: Fixes WOR-1"}]})
        self.assertEqual(matching["observations"][0]["status"], "resolved")
        combined = self.resolve({"branch_names": ["WOR-1-WOR-2-fix"], "pull_requests": [{"head_branch": "WOR-1-WOR-2-fix", "body": "## Work item\n\n- Tracker: Fixes WOR-1"}]})
        self.assertEqual([item["status"] for item in combined["observations"]], ["resolved", "resolved"])

    def test_feature_head_is_excluded_before_tracker_and_nested_head_is_not(self) -> None:
        result = self.resolve(
            {
                "pull_requests": [
                    {"head_branch": "001-T002-change", "body": "## Work item\n\n- Tracker: Fixes WOR-1"},
                    {"head_branch": "users/alice/001-T002-change"},
                ]
            }
        )
        self.assertEqual([item["status"] for item in result["observations"]], ["excluded", "unresolved"])

    def test_excluded_observations_do_not_load_credentials(self) -> None:
        failure = AppError("credentials are missing", code=4, category="credentials")
        with patch("spec_kit_linear.work_item_resolution.load_credentials", side_effect=failure):
            issue = resolve_work_item({"issue_key": "009-T002-change"}, root=self.root, client_factory=lambda *_: self.client)
            batch = resolve_work_item({"branch_names": ["009-feature"]}, root=self.root, client_factory=lambda *_: self.client)
        self.assertEqual((issue["status"], batch["status"]), ("excluded", "excluded"))

    def test_all_feature_heads_return_excluded_batch_without_remote_reads(self) -> None:
        result = self.resolve({"branch_names": ["001-feature", "001-T002-change"]})
        self.assertEqual((result["category"], result["status"]), ("excluded", "excluded"))
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(self.client.calls, [])

    def test_same_head_conflicting_pull_requests_keep_two_conflicts(self) -> None:
        payload = {
            "pull_requests": [
                {"head_branch": "old-title", "body": "## Work item\n\n- Tracker: Fixes WOR-12"},
                {"head_branch": "old-title", "body": "## Work item\n\n- Tracker: Fixes WOR-13"},
            ]
        }
        for native in (None, context("WOR-1", branch="old-title")):
            with self.subTest(native=native is not None):
                self.client.issue = native
                result = self.resolve(payload)
                self.assertEqual([item["status"] for item in result["observations"]], ["conflict", "conflict"])
        self.assertEqual(self.client.calls, [("branches", ("old-title",))] * 2)

    def test_same_head_branch_and_conflicting_tracker_have_no_resolved_row(self) -> None:
        self.client.issue = context("WOR-1", branch="WOR-1-fix")
        result = self.resolve(
            {
                "branch_names": ["WOR-1-fix"],
                "pull_requests": [{"head_branch": "WOR-1-fix", "body": "## Work item\n\n- Tracker: Fixes WOR-2"}],
            }
        )
        self.assertEqual([item["status"] for item in result["observations"]], ["conflict", "conflict"])
        self.assertEqual(result["observations"][1]["diagnostics"][0]["message"], "branch and Tracker evidence disagree within one pull request")

    def test_same_head_wrong_team_tracker_conflicts_for_every_observation(self) -> None:
        self.client.issue = context("WOR-12", branch="old-title")
        result = self.resolve(
            {
                "branch_names": ["old-title"],
                "pull_requests": [{"head_branch": "old-title", "body": "## Work item\n\n- Tracker: Fixes OTHER-13"}],
            }
        )
        self.assertEqual([item["status"] for item in result["observations"]], ["conflict", "conflict"])
        self.assertEqual(result["observations"][1]["diagnostics"][0]["code"], "work_item_wrong_team")

    def test_batch_fields_are_arrays(self) -> None:
        for payload in ({"branch_names": "WOR-1"}, {"pull_requests": {"head_branch": "WOR-1"}}):
            with self.subTest(payload=payload), self.assertRaisesRegex(AppError, "must be an array"):
                self.resolve(payload)


if __name__ == "__main__":
    unittest.main()
