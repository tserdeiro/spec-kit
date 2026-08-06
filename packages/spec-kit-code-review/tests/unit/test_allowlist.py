"""The allowlist is the perimeter, and it is tested operation by operation."""

from __future__ import annotations

import unittest

from spec_kit_code_review.allowlist import (
    ALLOWED,
    EVENT_COMMENT,
    EVENT_REQUEST_CHANGES,
    EventConditions,
    FORBIDDEN_EVENT,
    FORBIDDEN_EXAMPLES,
    PERMITTED_EVENTS,
    READ,
    WRITE,
    Ledger,
    assert_never_approves,
    authorize,
    describe,
    find,
)
from spec_kit_code_review.errors import EXIT_PUBLICATION, AppError


PERMITTED = (
    ("GET", "repos/tserdeiro/consumer/pulls/128"),
    ("GET", "repos/tserdeiro/consumer/pulls/128/files"),
    ("GET", "repos/tserdeiro/consumer/issues/128/comments"),
    ("GET", "repos/tserdeiro/consumer/pulls/128/reviews"),
    ("GET", "user"),
)


class PermittedTests(unittest.TestCase):
    def test_every_documented_read_is_authorized(self) -> None:
        for method, path in PERMITTED:
            with self.subTest(operation=f"{method} {path}"):
                self.assertEqual(authorize(method, path).kind, READ)

    def test_a_comment_review_needs_nothing_but_its_event(self) -> None:
        self.assertEqual(
            authorize("POST", "repos/o/r/pulls/128/reviews", event=EVENT_COMMENT).kind, WRITE
        )
        self.assertEqual(authorize("POST", "repos/o/r/issues/128/comments").kind, WRITE)

    def test_request_changes_needs_all_four_conditions_met(self) -> None:
        met = EventConditions(
            ceiling="request-changes",
            requested=True,
            verdict="changes-requested",
            author_is_authenticated_user=False,
        )

        self.assertEqual(
            authorize(
                "POST", "repos/o/r/pulls/128/reviews", event=EVENT_REQUEST_CHANGES, conditions=met
            ).kind,
            WRITE,
        )

    def test_request_changes_is_refused_when_any_condition_fails(self) -> None:
        from dataclasses import replace

        met = EventConditions(
            ceiling="request-changes",
            requested=True,
            verdict="changes-requested",
            author_is_authenticated_user=False,
        )
        for field, value in (
            ("ceiling", "comment"),
            ("requested", False),
            ("verdict", "no-blocking-findings"),
            ("author_is_authenticated_user", True),
        ):
            with self.subTest(condition=field):
                with self.assertRaises(AppError):
                    authorize(
                        "POST",
                        "repos/o/r/pulls/128/reviews",
                        event=EVENT_REQUEST_CHANGES,
                        conditions=replace(met, **{field: value}),
                    )

    def test_request_changes_without_conditions_is_refused(self) -> None:
        # The four conditions live inside the perimeter: a caller that builds
        # the event elsewhere cannot skip them by not presenting them.
        with self.assertRaises(AppError):
            authorize("POST", "repos/o/r/pulls/128/reviews", event=EVENT_REQUEST_CHANGES)

    def test_a_leading_slash_and_a_query_string_do_not_change_the_operation(self) -> None:
        self.assertIsNotNone(authorize("GET", "/repos/o/r/issues/128/comments?per_page=100"))

    def test_the_method_is_case_insensitive_but_the_path_is_not_guessed(self) -> None:
        self.assertIsNotNone(authorize("get", "user"))
        with self.assertRaises(AppError):
            authorize("GET", "USER")

    def test_the_list_matches_the_contract_in_size_and_shape(self) -> None:
        self.assertEqual(len(ALLOWED), 7)
        self.assertEqual(len([item for item in ALLOWED if item.kind == WRITE]), 2)
        self.assertEqual(len(describe()), len(ALLOWED))


class ForbiddenTests(unittest.TestCase):
    """Every prohibition of the contract, one test each."""

    def _refused(self, method: str, path: str, **kwargs) -> AppError:
        with self.assertRaises(AppError) as caught:
            authorize(method, path, **kwargs)
        self.assertEqual(caught.exception.code, EXIT_PUBLICATION)
        self.assertEqual(caught.exception.diagnostics[0].code, "allowlist_refused")
        return caught.exception

    def test_every_enumerated_prohibition_fails_closed(self) -> None:
        for method, path in FORBIDDEN_EXAMPLES:
            with self.subTest(operation=f"{method} {path}"):
                self._refused(method, path)

    def test_merging_is_refused(self) -> None:
        self._refused("PUT", "repos/o/r/pulls/128/merge")

    def test_editing_the_pull_request_is_refused(self) -> None:
        for method in ("PATCH", "PUT", "DELETE"):
            with self.subTest(method=method):
                self._refused(method, "repos/o/r/pulls/128")

    def test_editing_or_deleting_a_comment_is_refused(self) -> None:
        for method in ("PATCH", "DELETE"):
            with self.subTest(method=method):
                self._refused(method, "repos/o/r/issues/comments/1")

    def test_resolving_a_thread_is_refused(self) -> None:
        self._refused("PUT", "repos/o/r/pulls/128/reviews/1/events")

    def test_any_git_write_is_refused(self) -> None:
        for path in ("repos/o/r/git/refs", "repos/o/r/git/refs/heads/main", "repos/o/r/releases"):
            with self.subTest(path=path):
                self._refused("POST", path)

    def test_an_unlisted_read_is_refused_too(self) -> None:
        # The list is closed in both directions: a read nobody enumerated is
        # still an operation this extension does not perform.
        for path in ("repos/o/r/collaborators", "repos/o/r/contents/x", "orgs/o/members"):
            with self.subTest(path=path):
                self._refused("GET", path)

    def test_a_traversing_path_is_refused_before_it_is_matched(self) -> None:
        self._refused("GET", "repos/o/r/pulls/128/../../../user")

    def test_an_absolute_url_is_refused(self) -> None:
        self._refused("GET", "https://evil.example/repos/o/r/pulls/128")

    def test_a_query_string_that_is_not_plain_api_syntax_is_refused(self) -> None:
        # What is checked must be what is sent: a query the check discards but
        # the request carries is a second, unchecked string.
        for query in ("?per_page=100#fragment", "?a=b c", "?x=<script>", "?path=../../user"):
            with self.subTest(query=query):
                self._refused("GET", f"repos/o/r/issues/128/comments{query}")

    def test_a_review_without_an_event_is_refused(self) -> None:
        self._refused("POST", "repos/o/r/pulls/128/reviews")


class ApproveTests(unittest.TestCase):
    """`APPROVE` is not rejected; it is unreachable."""

    def test_approve_is_refused_as_an_event(self) -> None:
        with self.assertRaises(AppError) as caught:
            authorize("POST", "repos/o/r/pulls/128/reviews", event=FORBIDDEN_EVENT)

        self.assertIn("human decision", caught.exception.diagnostics[0].message)

    def test_approve_is_refused_in_every_casing(self) -> None:
        for value in ("APPROVE", "approve", "Approve", "aPpRoVe"):
            with self.subTest(event=value):
                with self.assertRaises(AppError):
                    assert_never_approves({"event": value})

    def test_no_combination_of_inputs_produces_an_approving_operation(self) -> None:
        # The whole product: every allowed path, every method, every event value
        # this package knows about. None of them yields an authorized APPROVE.
        events = (*PERMITTED_EVENTS, FORBIDDEN_EVENT, "", None, "MERGE", "DISMISS")
        for operation in ALLOWED:
            for event in events:
                with self.subTest(path=operation.pattern, event=event):
                    try:
                        authorized = authorize(operation.method, _sample(operation.pattern), event=event)
                    except AppError:
                        continue
                    self.assertNotEqual(event, FORBIDDEN_EVENT)
                    self.assertIn(authorized.kind, (READ, WRITE))

    def test_the_body_check_is_independent_of_the_path_check(self) -> None:
        # Two locks, not one: the event is validated where the call is
        # authorized *and* on the body that is actually about to be sent.
        assert_never_approves({"event": "COMMENT"})
        with self.assertRaises(AppError):
            assert_never_approves({"event": "APPROVE", "body": "looks harmless"})


class LedgerTests(unittest.TestCase):
    def test_the_ledger_records_the_sequence_and_separates_the_writes(self) -> None:
        ledger = Ledger()
        authorize("GET", "user", ledger=ledger)
        authorize("POST", "repos/o/r/pulls/1/reviews", event="COMMENT", ledger=ledger)
        authorize("POST", "repos/o/r/issues/1/comments", ledger=ledger)

        self.assertEqual([entry["method"] for entry in ledger.entries], ["GET", "POST", "POST"])
        self.assertEqual(len(ledger.writes), 2)
        self.assertEqual(ledger.entries[1]["event"], "COMMENT")

    def test_a_refused_operation_never_reaches_the_ledger(self) -> None:
        ledger = Ledger()
        with self.assertRaises(AppError):
            authorize("PUT", "repos/o/r/pulls/1/merge", ledger=ledger)

        self.assertEqual(ledger.entries, [])


def _sample(pattern: str) -> str:
    """A concrete path matching one of the allowlist's patterns."""

    return (
        pattern.replace(r"[A-Za-z0-9._-]+", "consumer", 1)
        .replace(r"[A-Za-z0-9._-]+", "repo", 1)
        .replace(r"[0-9]+", "128")
    )


class FindTests(unittest.TestCase):
    def test_find_returns_none_rather_than_raising(self) -> None:
        self.assertIsNone(find("DELETE", "repos/o/r/pulls/1"))
        self.assertIsNotNone(find("GET", "user"))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
