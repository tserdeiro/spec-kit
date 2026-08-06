from __future__ import annotations

import unittest

from spec_kit_linear.github import PullRequest
from spec_kit_linear.linear_client import RemoteWorkItem
from spec_kit_linear.planner import build_work_item_plan
from spec_kit_linear.work_items import derive_work_items, issue_key_pattern, issue_numbers
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


def _pull_request(head_branch: str, *, draft: bool = False, state: str = "OPEN") -> PullRequest:
    return PullRequest(head_branch=head_branch, is_draft=draft, state=state)


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

    def test_names_that_only_look_like_the_convention_never_match(self) -> None:
        pattern = issue_key_pattern("WOR")

        for name in ("WORX-1", "wor123", "wor-", "wor-12x", "xwor-1", "001-T004", "main", "WOR", "-wor-1"):
            with self.subTest(name=name):
                self.assertIsNone(pattern.fullmatch(name))

    def test_the_team_key_comes_from_configuration_and_nothing_else_matches(self) -> None:
        pattern = issue_key_pattern("PLAT")

        self.assertTrue(pattern.fullmatch("plat-9-chore"))
        self.assertIsNone(pattern.fullmatch("wor-9"))


class WorkItemDerivationTests(unittest.TestCase):
    def test_a_merged_pull_request_completes_the_work_item(self) -> None:
        derived = derive_work_items("WOR", pull_requests=(_pull_request("wor-12-fix", state="MERGED"),))

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-12", STATE_COMPLETED, SOURCE_PULL_REQUEST)])

    def test_a_ready_pull_request_is_review_and_a_draft_is_started(self) -> None:
        derived = derive_work_items("WOR", pull_requests=(_pull_request("wor-12"), _pull_request("wor-13", draft=True)))

        self.assertEqual([(item.identifier, item.state) for item in derived], [("WOR-12", STATE_REVIEW), ("WOR-13", STATE_STARTED)])

    def test_a_branch_alone_is_started_and_carries_the_branch_as_its_detail(self) -> None:
        derived = derive_work_items("WOR", branches=("main", "wor-7-chore-bump-deps"))

        self.assertEqual([(item.identifier, item.state, item.source, item.detail) for item in derived], [("WOR-7", STATE_STARTED, SOURCE_BRANCH, "wor-7-chore-bump-deps")])

    def test_an_issue_with_no_branch_and_no_pull_request_is_not_observed_at_all(self) -> None:
        self.assertEqual(derive_work_items("WOR", branches=("main", "001-T004")), ())

    def test_a_closed_unmerged_pull_request_is_ignored_and_the_branch_decides(self) -> None:
        derived = derive_work_items("WOR", branches=("wor-12-fix",), pull_requests=(_pull_request("wor-12-fix", state="CLOSED"),))

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-12", STATE_STARTED, SOURCE_BRANCH)])

    def test_stacked_pull_requests_report_the_furthest_the_work_item_reached(self) -> None:
        derived = derive_work_items("WOR", pull_requests=(_pull_request("wor-12-part-2", draft=True), _pull_request("wor-12-part-1")))

        self.assertEqual([item.state for item in derived], [STATE_REVIEW])

    def test_a_branch_and_a_pull_request_on_the_same_key_are_one_work_item(self) -> None:
        derived = derive_work_items("WOR", branches=("WOR-45", "wor-045-again"), pull_requests=(_pull_request("wor-45-fix", draft=True),))

        self.assertEqual([(item.identifier, item.state, item.source) for item in derived], [("WOR-45", STATE_STARTED, SOURCE_PULL_REQUEST)])

    def test_work_items_are_ordered_by_issue_number(self) -> None:
        derived = derive_work_items("WOR", branches=("wor-30", "wor-4", "wor-120"))

        self.assertEqual([item.identifier for item in derived], ["WOR-4", "WOR-30", "WOR-120"])
        self.assertEqual(issue_numbers(derived), (4, 30, 120))


class WorkItemPlanTests(unittest.TestCase):
    def _plan(self, work_items, remote_items, config=LIFECYCLE_CONFIG):
        return build_work_item_plan(work_items, {item.identifier: item for item in remote_items}, config=config)

    def test_a_derived_state_that_differs_becomes_one_lifecycle_update(self) -> None:
        work_items = derive_work_items("WOR", branches=("wor-12-fix",))

        plan, diagnostics = self._plan(work_items, (_remote("WOR-12", state_id=OPEN_STATE_ID),))

        self.assertEqual(diagnostics, ())
        self.assertEqual([(item["kind"], item["target"], item["input"]["stateId"]) for item in plan["operations"]], [("issue.lifecycle.update", "workitem:WOR-12", STARTED_STATE_ID)])
        self.assertEqual(plan["operations"][0]["preconditions"], {"id": "issue-WOR-12", "updated_at": "2099-01-01T00:00:00Z"})

    def test_a_state_that_already_matches_produces_no_operation(self) -> None:
        work_items = derive_work_items("WOR", branches=("wor-12-fix",))

        plan, diagnostics = self._plan(work_items, (_remote("WOR-12", state_id=STARTED_STATE_ID),))

        self.assertEqual((plan["operations"], diagnostics), ([], ()))

    def test_a_review_state_degrades_onto_the_started_state_when_the_team_has_none(self) -> None:
        work_items = derive_work_items("WOR", pull_requests=(_pull_request("wor-12"),))
        config = {"lifecycle": {key: value for key, value in LIFECYCLE_CONFIG["lifecycle"].items() if key != "review_state_id"}}

        plan, _diagnostics = self._plan(work_items, (_remote("WOR-12", state_id=OPEN_STATE_ID),), config)

        self.assertEqual(plan["operations"][0]["input"]["stateId"], STARTED_STATE_ID)

    def test_an_unconfigured_lifecycle_leaves_every_work_item_untouched(self) -> None:
        work_items = derive_work_items("WOR", branches=("wor-12",))

        plan, diagnostics = self._plan(work_items, (_remote("WOR-12"),), {})

        self.assertEqual((plan["operations"], diagnostics), ([], ()))

    def test_an_issue_key_with_no_issue_behind_it_warns_and_emits_nothing(self) -> None:
        work_items = derive_work_items("WOR", branches=("wor-999-typo",))

        plan, diagnostics = self._plan(work_items, ())

        self.assertEqual(plan["operations"], [])
        self.assertEqual([(item.code, item.severity) for item in diagnostics], [("work_item_unknown", "warning")])
        self.assertIn("WOR-999", diagnostics[0].message)
        self.assertEqual(plan["snapshot"]["resources"], [])

    def test_the_plan_only_ever_contains_lifecycle_updates(self) -> None:
        work_items = derive_work_items("WOR", branches=("wor-1", "wor-2"), pull_requests=(_pull_request("wor-3", state="MERGED"),))

        plan, _diagnostics = self._plan(work_items, (_remote("WOR-1"), _remote("WOR-2"), _remote("WOR-3")))

        self.assertEqual({item["kind"] for item in plan["operations"]}, {"issue.lifecycle.update"})
        self.assertEqual({tuple(item["input"]) for item in plan["operations"]}, {("stateId",)})


if __name__ == "__main__":
    unittest.main()
