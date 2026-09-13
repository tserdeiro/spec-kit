from __future__ import annotations

import unittest

from spec_kit_linear.github import PullRequest, PullRequestScan
from spec_kit_linear.linear_client import RemoteWorkItem
from spec_kit_linear.planner import build_work_item_plan
from spec_kit_linear.work_items import derive_work_items as _derive_work_items, issue_key_pattern, issue_numbers
from spec_kit_linear.work_state import (
    SOURCE_BRANCH,
    SOURCE_PULL_REQUEST,
    STATE_COMPLETED,
    STATE_REVIEW,
    STATE_STARTED,
)


COMPLETED_STATE_ID = "77777777-7777-4777-8777-777777777777"
OPEN_STATE_ID = "88888888-8888-4888-8888-888888888888"
STARTED_STATE_ID = "99999999-9999-4999-8999-999999999999"
REVIEW_STATE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

LIFECYCLE_CONFIG = {
    "lifecycle": {
        "completed_state_id": COMPLETED_STATE_ID,
        "open_state_id": OPEN_STATE_ID,
        "started_state_id": STARTED_STATE_ID,
        "review_state_id": REVIEW_STATE_ID,
    }
}


def _pull_request(head_branch: str, *, draft: bool = False, state: str = "OPEN", number: int | None = None, body: str = "") -> PullRequest:
    return PullRequest(head_branch=head_branch, is_draft=draft, state=state, number=number, body=body)


def _resolved(*identifiers: str) -> dict[str, object]:
    return {
        "observations": [
            {
                "status": "resolved",
                "resolution": {"identifier": identifier},
                "affected_issue_keys": [identifier],
            }
            for identifier in identifiers
        ]
    }


def _excluded(count: int) -> dict[str, object]:
    return {
        "observations": [
            {"status": "excluded", "resolution": None, "affected_issue_keys": []}
            for _ in range(count)
        ]
    }


def _unresolved(count: int) -> dict[str, object]:
    return {
        "observations": [
            {"status": "unresolved", "resolution": None, "affected_issue_keys": []}
            for _ in range(count)
        ]
    }


def derive_work_items(*, branches=(), pull_requests=(), resolution, outcome="complete"):
    return _derive_work_items(
        branches=branches,
        scan=PullRequestScan(outcome, tuple(pull_requests)),
        resolution=resolution,
    )


def _remote(identifier: str, *, state_id: str | None = None) -> RemoteWorkItem:
    return RemoteWorkItem(
        id=f"issue-{identifier}",
        identifier=identifier,
        title=f"{identifier} title",
        updated_at="2099-01-01T00:00:00Z",
        state_id=state_id,
        state_name="Todo" if state_id is None else "Some state",
        url=f"https://linear.app/example/issue/{identifier}",
    )


class IssueKeyConventionTests(unittest.TestCase):
    def test_the_convention_matches_the_key_alone_and_a_suffixed_branch_case_insensitively(self) -> None:
        pattern = issue_key_pattern("WOR")

        for name in ("WOR-123", "wor-123", "wor-123-fix-crash", "WOR-45", "Wor-45-x", "wor-045"):
            with self.subTest(name=name):
                self.assertTrue(pattern.fullmatch(name))

    def test_linears_native_copy_branch_format_matches(self) -> None:
        # Linear's "Copy git branch name" produces `<username>/wor-123-slug`;
        # the native button must be a first-class way to start a work item.
        pattern = issue_key_pattern("WOR")

        for name in ("devs/wor-123-slug", "Facu/WOR-45", "a.b/wor-9-fix"):
            with self.subTest(name=name):
                self.assertTrue(pattern.fullmatch(name))

    def test_names_that_only_look_like_the_convention_never_match(self) -> None:
        pattern = issue_key_pattern("WOR")

        for name in ("WORX-1", "wor123", "wor-", "wor-12x", "xwor-1", "001-T004", "main", "WOR", "-wor-1", "a/b/wor-1", "/wor-1", "devs/xwor-1"):
            with self.subTest(name=name):
                self.assertIsNone(pattern.fullmatch(name))

    def test_the_team_key_comes_from_configuration_and_nothing_else_matches(self) -> None:
        pattern = issue_key_pattern("PLAT")

        self.assertTrue(pattern.fullmatch("plat-9-chore"))
        self.assertIsNone(pattern.fullmatch("wor-9"))


class WorkItemDerivationTests(unittest.TestCase):
    def test_native_resolution_uses_the_canonical_identity_for_a_nonconventional_branch(self) -> None:
        derived = derive_work_items(
            branches=("users/alice/fix-the-cache",),
            resolution={
                "observations": [
                    {
                        "status": "resolved",
                        "resolution": {"identifier": "WOR-12"},
                        "affected_issue_keys": ["WOR-12"],
                    }
                ]
            },
        )

        self.assertEqual([(item.identifier, item.state, item.detail) for item in derived], [("WOR-12", STATE_STARTED, "users/alice/fix-the-cache")])

    def test_conflict_preserves_every_affected_issue_and_blocks_projection(self) -> None:
        derived = derive_work_items(
            branches=("native-issue-one", "old-title"),
            resolution={
                "observations": [
                    {
                        "status": "resolved",
                        "resolution": {"identifier": "WOR-1"},
                        "affected_issue_keys": ["WOR-1"],
                    },
                    {
                        "status": "conflict",
                        "resolution": None,
                        "affected_issue_keys": ["WOR-1", "WOR-2"],
                    },
                ]
            },
        )

        self.assertEqual(
            [(item.identifier, item.state, item.source) for item in derived],
            [("WOR-1", None, "unknown"), ("WOR-2", None, "unknown")],
        )

    def test_unknown_native_head_does_not_freeze_an_unrelated_issue(self) -> None:
        derived = derive_work_items(
            branches=("old-title",),
            resolution={"observations": [{"status": "unresolved", "resolution": None, "affected_issue_keys": []}]},
        )

        self.assertEqual(derived, ())

    def test_feature_task_observation_is_excluded_even_with_a_tracker_link(self) -> None:
        derived = derive_work_items(
            pull_requests=(_pull_request("001-T002-change"),),
            resolution=_excluded(1),
        )

        self.assertEqual(derived, ())

    def test_incomplete_github_scan_keeps_resolved_identity_unknown(self) -> None:
        derived = derive_work_items(
            branches=("users/alice/fix-the-cache",),
            outcome="incomplete",
            resolution={
                "observations": [
                    {
                        "status": "resolved",
                        "resolution": {"identifier": "WOR-12"},
                        "affected_issue_keys": ["WOR-12"],
                    }
                ]
            },
        )

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-12", None, "unknown")])

    def test_a_merged_pull_request_completes_the_work_item(self) -> None:
        derived = derive_work_items(pull_requests=(_pull_request("wor-12-fix", state="MERGED"),), resolution=_resolved("WOR-12"))

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-12", STATE_COMPLETED, SOURCE_PULL_REQUEST)])

    def test_a_ready_pull_request_is_review_and_a_draft_is_started(self) -> None:
        derived = derive_work_items(pull_requests=(_pull_request("wor-12"), _pull_request("wor-13", draft=True)), resolution=_resolved("WOR-12", "WOR-13"))

        self.assertEqual([(item.identifier, item.state) for item in derived], [("WOR-12", STATE_REVIEW), ("WOR-13", STATE_STARTED)])

    def test_a_branch_alone_is_started_and_carries_the_branch_as_its_detail(self) -> None:
        derived = derive_work_items(branches=("main", "wor-7-chore-bump-deps"), resolution={"observations": _unresolved(1)["observations"] + _resolved("WOR-7")["observations"]})

        self.assertEqual([(item.identifier, item.state, item.source, item.detail) for item in derived], [("WOR-7", STATE_STARTED, SOURCE_BRANCH, "wor-7-chore-bump-deps")])

    def test_an_issue_with_no_branch_and_no_pull_request_is_not_observed_at_all(self) -> None:
        self.assertEqual(derive_work_items(branches=("main", "001-T004"), resolution=_excluded(2)), ())

    def test_a_closed_unmerged_pull_request_is_ignored_and_the_branch_decides(self) -> None:
        derived = derive_work_items(branches=("wor-12-fix",), pull_requests=(_pull_request("wor-12-fix", state="CLOSED"),), resolution=_resolved("WOR-12", "WOR-12"))

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-12", STATE_STARTED, SOURCE_BRANCH)])

    def test_stacked_pull_requests_keep_the_work_item_in_progress_when_one_is_draft(self) -> None:
        derived = derive_work_items(pull_requests=(_pull_request("wor-12-part-2", draft=True), _pull_request("wor-12-part-1")), resolution=_resolved("WOR-12", "WOR-12"))

        self.assertEqual([(item.state, item.source) for item in derived], [(STATE_STARTED, SOURCE_PULL_REQUEST)])

    def test_open_work_precedes_a_merge_and_same_rank_uses_lowest_pr_number(self) -> None:
        pull_requests = (
            _pull_request("wor-12-merged", state="MERGED", number=1),
            _pull_request("wor-12-ready", number=20),
            _pull_request("wor-12-draft-high", draft=True, number=30),
            _pull_request("wor-12-draft-low", draft=True, number=4),
        )

        first = derive_work_items(pull_requests=pull_requests, resolution=_resolved("WOR-12", "WOR-12", "WOR-12", "WOR-12"))[0]
        second = derive_work_items(pull_requests=tuple(reversed(pull_requests)), resolution=_resolved("WOR-12", "WOR-12", "WOR-12", "WOR-12"))[0]

        self.assertEqual((first.state, first.detail, first.pr_number), (STATE_STARTED, "wor-12-draft-low", 4))
        self.assertEqual(first, second)

    def test_precedence_table_is_shared_by_bug_and_chore_observations(self) -> None:
        cases = (("draft", ()), ("ready", ()), ("merged", ()), ("branch", ("wor-12-fix",)))
        expected = {"draft": STATE_STARTED, "ready": STATE_REVIEW, "merged": STATE_COMPLETED, "branch": STATE_STARTED}
        for name, branches in cases:
            with self.subTest(name=name):
                prs = {
                    "draft": (_pull_request("wor-12", draft=True, number=3),),
                    "ready": (_pull_request("wor-12", number=3),),
                    "merged": (_pull_request("wor-12", state="MERGED", number=3),),
                    "branch": (),
                }[name]
                item = derive_work_items(branches=branches, pull_requests=prs, resolution=_resolved("WOR-12"))[0]
                self.assertEqual(item.state, expected[name])

    def test_a_branch_and_a_pull_request_on_the_same_key_are_one_work_item(self) -> None:
        derived = derive_work_items(branches=("WOR-45", "wor-045-again"), pull_requests=(_pull_request("wor-45-fix", draft=True),), resolution=_resolved("WOR-45", "WOR-45", "WOR-45"))

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-45", STATE_STARTED, SOURCE_PULL_REQUEST)])

    def test_work_items_are_ordered_by_issue_number(self) -> None:
        derived = derive_work_items(branches=("wor-30", "wor-4", "wor-120"), resolution=_resolved("WOR-30", "WOR-4", "WOR-120"))

        self.assertEqual([item.identifier for item in derived], ["WOR-4", "WOR-30", "WOR-120"])
        self.assertEqual(issue_numbers(derived), (4, 30, 120))

    def test_a_pull_request_observation_carries_its_own_number(self) -> None:
        derived = derive_work_items(pull_requests=(_pull_request("wor-12-fix", draft=True, number=42),), resolution=_resolved("WOR-12"))

        self.assertEqual(derived[0].pr_number, 42)

    def test_a_branch_alone_carries_no_pull_request_number(self) -> None:
        derived = derive_work_items(branches=("wor-7-chore",), resolution=_resolved("WOR-7"))

        self.assertIsNone(derived[0].pr_number)


class WorkItemPlanTests(unittest.TestCase):
    def _plan(self, work_items, remote_items, config=LIFECYCLE_CONFIG):
        return build_work_item_plan(work_items, {item.identifier: item for item in remote_items}, config=config)

    def test_a_derived_state_that_differs_becomes_one_lifecycle_update(self) -> None:
        work_items = derive_work_items(branches=("wor-12-fix",), resolution=_resolved("WOR-12"))

        plan, diagnostics = self._plan(work_items, (_remote("WOR-12", state_id=OPEN_STATE_ID),))

        self.assertEqual(diagnostics, ())
        self.assertEqual([(item["kind"], item["target"], item["input"]["stateId"]) for item in plan["operations"]], [("issue.lifecycle.update", "workitem:WOR-12", STARTED_STATE_ID)])
        self.assertEqual(plan["operations"][0]["preconditions"], {"id": "issue-WOR-12", "updated_at": "2099-01-01T00:00:00Z"})

    def test_a_state_that_already_matches_produces_no_operation(self) -> None:
        work_items = derive_work_items(branches=("wor-12-fix",), resolution=_resolved("WOR-12"))

        plan, diagnostics = self._plan(work_items, (_remote("WOR-12", state_id=STARTED_STATE_ID),))

        self.assertEqual((plan["operations"], diagnostics), ([], ()))

    def test_a_review_state_degrades_onto_the_started_state_when_the_team_has_none(self) -> None:
        work_items = derive_work_items(pull_requests=(_pull_request("wor-12"),), resolution=_resolved("WOR-12"))
        config = {"lifecycle": {key: value for key, value in LIFECYCLE_CONFIG["lifecycle"].items() if key != "review_state_id"}}

        plan, _diagnostics = self._plan(work_items, (_remote("WOR-12", state_id=OPEN_STATE_ID),), config)

        self.assertEqual(plan["operations"][0]["input"]["stateId"], STARTED_STATE_ID)

    def test_an_unconfigured_lifecycle_leaves_every_work_item_untouched(self) -> None:
        work_items = derive_work_items(branches=("wor-12",), resolution=_resolved("WOR-12"))

        plan, diagnostics = self._plan(work_items, (_remote("WOR-12"),), {})

        self.assertEqual((plan["operations"], diagnostics), ([], ()))

    def test_an_issue_key_with_no_issue_behind_it_warns_and_emits_nothing(self) -> None:
        work_items = derive_work_items(branches=("wor-999-typo",), resolution=_resolved("WOR-999"))

        plan, diagnostics = self._plan(work_items, ())

        self.assertEqual(plan["operations"], [])
        self.assertEqual([(item.code, item.severity) for item in diagnostics], [("work_item_unknown", "warning")])
        self.assertIn("WOR-999", diagnostics[0].message)
        self.assertEqual(plan["snapshot"]["resources"], [])

    def test_the_plan_only_ever_contains_lifecycle_updates(self) -> None:
        work_items = derive_work_items(branches=("wor-1", "wor-2"), pull_requests=(_pull_request("wor-3", state="MERGED"),), resolution=_resolved("WOR-1", "WOR-2", "WOR-3"))

        plan, _diagnostics = self._plan(work_items, (_remote("WOR-1"), _remote("WOR-2"), _remote("WOR-3")))

        self.assertEqual({item["kind"] for item in plan["operations"]}, {"issue.lifecycle.update"})
        self.assertEqual({tuple(item["input"]) for item in plan["operations"]}, {("stateId",)})


if __name__ == "__main__":
    unittest.main()
