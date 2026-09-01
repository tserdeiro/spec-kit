"""Publication end to end, against a fake `gh` that records every call.

The assertions are about the *sequence of remote operations*, not only about the
outcome: this is the one stage that writes, and "it did not do anything
forbidden" has to be checked against what it actually attempted.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from spec_kit_code_review.errors import EXIT_SUCCESS, EXIT_USAGE
from tests.support.fixtures import install_fake_gh, pull_request_payload
from tests.unit.test_cli import RunCommandCase


FEATURE_BODY = "".join(f"value_{index} = {index}\n" for index in range(5))


def entry(**overrides):
    payload = {
        "path": "src/feature.py",
        "start_line": 1,
        "end_line": 1,
        "side": "RIGHT",
        "severity": "blocking",
        "category": "correctness",
        "title": "The value is never validated",
        "content": "`value_0 = 0` is assigned without validation.",
        "rule_source": "repo",
    }
    payload.update(overrides)
    return payload


class PublicationCase(RunCommandCase):
    """A candidate on GitHub, and a fake that records every call it receives."""

    def setUp(self) -> None:
        super().setUp()
        # Several reviewable lines, so a plan can carry several inline comments.
        self.repository.checkout("feature")
        self.head = self.repository.commit("src/feature.py", FEATURE_BODY, "feature work")
        self.repository.checkout("main")
        self.api_log = self.workspace / "gh-api.jsonl"
        self.gh_state = {
            "auth": {"authenticated": True, "scopes": ["repo"]},
            "user": "reviewer",
            "record_api": str(self.api_log),
            "issue_comments": [],
            "pull_requests": {
                "128": pull_request_payload(
                    number=128,
                    repository="tserdeiro/consumer",
                    base_branch="main",
                    base_commit=self.base,
                    head_commit=self.head,
                    author="contributor",
                )
            },
        }
        self._install_gh()
        self.session: str | None = None
        self.findings_path = self.workspace / "findings.json"
        self.findings_entries: tuple[dict, ...] = ()
        self.write_findings(entry())

    def _install_gh(self) -> None:
        path, environment = install_fake_gh(self.bin, self.gh_state)
        self.environment.update(environment)
        self.environment["SPECKIT_CODE_REVIEW_GH_BIN"] = path
        self.gh_state_path = Path(environment["SPECKIT_CODE_REVIEW_FAKE_GH_STATE"])

    def write_findings(self, *entries) -> None:
        self.findings_entries = entries
        if self.session is not None:
            self.findings_path.write_text(json.dumps({"findings": list(entries)}), encoding="utf-8")

    def calls(self) -> list[dict]:
        if not self.api_log.exists():
            return []
        return [json.loads(line) for line in self.api_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def writes(self) -> list[dict]:
        return [call for call in self.calls() if call["method"] != "GET"]

    def open_review(self, *extra: str) -> dict:
        code, payload = self.invoke_json("review", "128", *extra)
        self.assertEqual(code, EXIT_SUCCESS, payload)
        self.session = payload["session"]["path"]
        self.findings_path = Path(self.session) / "findings.json"
        self.write_findings(*self.findings_entries)
        return payload

    def close(self, *extra: str) -> tuple[int, dict]:
        """Review the candidate and close it; the log covers the close alone."""

        self.open_review()
        self.api_log.unlink(missing_ok=True)
        return self.invoke_json("review", "--findings", str(self.findings_path), "--session", self.session, *extra)

    def publish(self, *extra: str) -> tuple[int, dict]:
        return self.close("--publish", *extra)

    def reconfigure(self, replacement: tuple[str, str]) -> None:
        """Change the committed configuration on both branches, and re-resolve.

        The configuration governs the whole review and is frozen when it opens,
        so a value that exists only on the operator's branch would trip the
        frozen-configuration check instead of exercising the setting.
        """

        configuration = self.root / "speckit-code-review.yml"
        for branch in ("main", "feature"):
            self.repository.git("switch", branch)
            configuration.write_text(
                configuration.read_text(encoding="utf-8").replace(*replacement), encoding="utf-8"
            )
            self.repository.git("add", "--all")
            self.repository.git("commit", "-m", "reconfigure")
        self.repository.git("switch", "main")
        # The candidate now also changes the configuration file, so the engine
        # has to report it: the scope cross-check compares against the real diff.
        self._engine_reports("src/feature.py", "speckit-code-review.yml")
        self.head = self.repository.git("rev-parse", "feature").strip()
        self.gh_state["pull_requests"]["128"]["headRefOid"] = self.head
        self._install_gh()


class HappyPathTests(PublicationCase):
    def test_every_read_precedes_the_first_write_and_the_writes_are_the_two(self) -> None:
        code, payload = self.publish()

        self.assertEqual(code, 1, payload)  # changes-requested
        self.assertTrue(payload["publication"]["executed"])
        endpoints = [f"{call['method']} {call['endpoint']}" for call in self.calls()]
        writes = [item for item in endpoints if not item.startswith("GET ")]
        self.assertEqual(
            writes,
            [
                "POST repos/tserdeiro/consumer/pulls/128/reviews",
                "POST repos/tserdeiro/consumer/issues/128/comments",
            ],
        )
        first_write = endpoints.index(writes[0])
        self.assertTrue(all(item.startswith("GET ") for item in endpoints[:first_write]))

    def test_a_comment_on_a_file_github_does_not_list_is_reported(self) -> None:
        # The one thing the local diff cannot know: GitHub's own view of which
        # files belong to the pull request.
        self.gh_state["files"] = [{"filename": "docs/unrelated.md"}]
        self._install_gh()

        _code, payload = self.publish()

        self.assertIn("publish_path_not_listed", {item["code"] for item in payload["diagnostics"]})

    def test_the_reverification_precedes_the_first_write(self) -> None:
        self.publish()

        endpoints = [f"{call['method']} {call['endpoint']}" for call in self.calls()]
        first_write = next(index for index, item in enumerate(endpoints) if item.startswith("POST"))
        last_reverification = max(
            index for index, item in enumerate(endpoints) if item == "GET pr-view/128"
        )
        self.assertLess(last_reverification, first_write)

    def test_the_review_carries_a_body_and_the_head_it_reviewed(self) -> None:
        # An empty body is a 422 from the real API on the very first POST, and
        # a review without `commit_id` anchors to whatever the head is when the
        # request arrives rather than to the head this review read.
        _code, payload = self.publish()

        review = next(call for call in self.writes() if call["endpoint"].endswith("/reviews"))
        self.assertTrue(review["body"]["body"].strip())
        self.assertIn("not an approval", review["body"]["body"])
        self.assertEqual(review["body"]["commit_id"], payload["candidate"]["head_commit"])

    def test_the_summary_is_published_once(self) -> None:
        self.publish()

        summaries = [call for call in self.writes() if call["endpoint"].endswith("/issues/128/comments")]
        self.assertEqual(len(summaries), 1)
        review = next(call for call in self.writes() if call["endpoint"].endswith("/reviews"))
        self.assertNotIn("### Findings reported here", review["body"]["body"])

    def test_the_result_records_what_was_created(self) -> None:
        _code, payload = self.publish()

        result = payload["publication"]
        self.assertEqual(result["posted_inline"], 1)
        self.assertTrue(result["review_ids"])
        self.assertIsNotNone(result["summary_comment_id"])
        self.assertFalse(result["partial"])
        recorded = json.loads(
            (Path(self.session) / "publication-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded["review_ids"], result["review_ids"])

    def test_the_session_records_that_it_was_published(self) -> None:
        self.publish()

        session = json.loads((Path(self.session) / "session.json").read_text(encoding="utf-8"))
        self.assertTrue(session["published"])
        self.assertTrue(session["publication"]["executed"])

    def test_the_summary_carries_the_marker_and_the_candidate(self) -> None:
        _code, payload = self.publish()

        summary = next(call for call in self.writes() if call["endpoint"].endswith("/issues/128/comments"))
        candidate_id = payload["candidate"]["candidate_id"]
        self.assertIn(f"speckit-code-review:summary:{candidate_id}", summary["body"]["body"])
        self.assertIn("not an approval", summary["body"]["body"])

    def test_the_inline_comment_carries_its_anchor_and_contained_body(self) -> None:
        self.publish()

        review = next(call for call in self.writes() if call["endpoint"].endswith("/reviews"))
        comment = review["body"]["comments"][0]
        self.assertEqual(comment["path"], "src/feature.py")
        self.assertEqual(comment["side"], "RIGHT")
        self.assertIn("value_0 = 0", comment["body"])


class EventTests(PublicationCase):
    def test_a_blocking_verdict_requests_changes_out_of_the_box(self) -> None:
        _code, payload = self.publish()

        self.assertEqual(payload["publication"]["event"], "REQUEST_CHANGES")

    def test_a_review_without_blocking_findings_only_comments(self) -> None:
        self.write_findings(entry(severity="minor"))

        code, payload = self.publish()

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(payload["publication"]["event"], "COMMENT")

    def test_a_lowered_ceiling_degrades_to_a_comment(self) -> None:
        self.reconfigure(('event: "request-changes"', 'event: "comment"'))

        code, payload = self.publish()

        self.assertEqual(code, 1)
        self.assertEqual(payload["publication"]["event"], "COMMENT")

    def test_an_unknown_identity_degrades_rather_than_requesting_changes(self) -> None:
        # "the authenticated user is not the author" is not satisfied by an
        # identity that did not resolve at all.
        self.gh_state["api_failures"] = {"GET user": "HTTP 401: Bad credentials"}
        self._install_gh()

        _code, payload = self.publish()

        self.assertEqual(payload["publication"]["event"], "COMMENT")
        self.assertIn("publish_identity_unknown", {item["code"] for item in payload["diagnostics"]})

    def test_the_author_of_the_pull_request_degrades_to_comment(self) -> None:
        # GitHub refuses REQUEST_CHANGES from the author; degrading beats
        # failing the publication with an API error.
        self.gh_state["user"] = "contributor"
        self._install_gh()

        _code, payload = self.publish()

        self.assertEqual(payload["publication"]["event"], "COMMENT")
        self.assertIn("publish_event_self_review", {item["code"] for item in payload["diagnostics"]})

    def test_no_configuration_or_verdict_can_emit_an_approval(self) -> None:
        for label, prepare in (
            ("blocking", lambda: None),
            ("advisory", lambda: self.write_findings(entry(severity="minor"))),
            ("comment ceiling", lambda: self.reconfigure(('event: "request-changes"', 'event: "comment"'))),
        ):
            with self.subTest(case=label):
                self.setUp()
                prepare()
                self.publish()
                writes = self.writes()
                self.assertTrue(writes, "this iteration published nothing, so it asserted nothing")
                for call in writes:
                    self.assertNotEqual(str(call["body"].get("event", "")).upper(), "APPROVE")


class ExplicitnessTests(PublicationCase):
    def test_a_review_without_the_flag_publishes_nothing(self) -> None:
        code, payload = self.close()

        self.assertEqual(code, 1)
        self.assertEqual(self.writes(), [])
        self.assertNotIn("publication", payload)

    def test_the_flag_without_a_review_to_publish_is_a_usage_error(self) -> None:
        # This used to open a session, exit 0 and publish nothing.
        code, payload = self.invoke_json("review", "128", "--publish")

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "publish_without_review")
        self.assertEqual(self.writes(), [])

    def test_a_second_publication_of_the_same_candidate_is_refused(self) -> None:
        self.publish()
        self.api_log.unlink(missing_ok=True)

        code, payload = self.publish()

        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("publish_already_published", {item["code"] for item in payload["diagnostics"]})
        # It read to find out, and wrote nothing.
        self.assertEqual(self.writes(), [])
        # The existing comment was neither edited nor deleted.
        self.assertEqual(len(json.loads(self.gh_state_path.read_text(encoding="utf-8"))["issue_comments"]), 1)


class DriftTests(PublicationCase):
    def test_a_head_that_moved_publishes_nothing(self) -> None:
        self.open_review()
        self.api_log.unlink(missing_ok=True)
        self.repository.git("switch", "feature")
        moved = self.repository.commit("src/feature.py", FEATURE_BODY + "value_5 = 5\n", "the head moved")
        self.repository.checkout("main")
        self.gh_state["pull_requests"]["128"]["headRefOid"] = moved
        self._install_gh()

        code, payload = self.invoke_json(
            "review", "--findings", str(self.findings_path), "--session", self.session, "--publish"
        )

        self.assertEqual(code, 8)
        self.assertEqual(payload["diagnostics"][0]["code"], "drift_head")
        self.assertEqual(self.writes(), [])

    def test_a_closed_pull_request_is_never_published_to(self) -> None:
        self.open_review()
        self.api_log.unlink(missing_ok=True)
        self.gh_state["pull_requests"]["128"]["state"] = "MERGED"
        self._install_gh()

        code, payload = self.invoke_json(
            "review", "--findings", str(self.findings_path), "--session", self.session, "--publish"
        )

        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("publish_pull_request_not_open", {item["code"] for item in payload["diagnostics"]})
        self.assertEqual(self.writes(), [])


class PartialFailureTests(PublicationCase):
    def test_a_summary_that_fails_after_the_review_reports_exactly_what_landed(self) -> None:
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/issues/128/comments": "HTTP 422: Unprocessable Entity"
        }
        self._install_gh()

        code, payload = self.publish()

        self.assertEqual(code, 10)
        recorded = json.loads(
            (Path(self.session) / "publication-result.json").read_text(encoding="utf-8")
        )
        self.assertTrue(recorded["partial"])
        self.assertTrue(recorded["review_ids"])
        self.assertIsNone(recorded["summary_comment_id"])
        self.assertEqual(recorded["batches_completed"], recorded["batches_planned"])
        self.assertIn("publish_partial", {item["code"] for item in payload["diagnostics"]})

    def test_a_review_that_fails_first_leaves_nothing_behind(self) -> None:
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/pulls/128/reviews": "HTTP 422: Unprocessable Entity"
        }
        self._install_gh()

        code, _payload = self.publish()

        self.assertEqual(code, 10)
        recorded = json.loads(
            (Path(self.session) / "publication-result.json").read_text(encoding="utf-8")
        )
        self.assertFalse(recorded["partial"])
        self.assertEqual(recorded["review_ids"], [])
        self.assertEqual(recorded["batches_completed"], 0)
        self.assertIsNone(recorded["summary_comment_id"])

    def test_the_ledger_of_what_was_attempted_is_in_the_result(self) -> None:
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/issues/128/comments": "HTTP 500"
        }
        self._install_gh()

        self.publish()

        recorded = json.loads(
            (Path(self.session) / "publication-result.json").read_text(encoding="utf-8")
        )
        operations = [f"{item['method']} {item['path']}" for item in recorded["operations"]]
        self.assertIn("POST repos/tserdeiro/consumer/pulls/128/reviews", operations)
        self.assertIn("POST repos/tserdeiro/consumer/issues/128/comments", operations)

    def test_an_authentication_failure_is_exit_five_not_ten(self) -> None:
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/pulls/128/reviews": "HTTP 401: Bad credentials"
        }
        self._install_gh()

        code, payload = self.publish()

        self.assertEqual(code, 5)
        self.assertIn(
            "github_authentication_failed", {item["code"] for item in payload["diagnostics"]}
        )


class BatchingTests(PublicationCase):
    """More comments than a batch: several requests, in order, and honest about
    where a failure stopped."""

    def setUp(self) -> None:
        super().setUp()
        self.reconfigure(("batch_size: 25", "batch_size: 2"))
        self.write_findings(
            *(
                entry(start_line=line, end_line=line, title=f"finding {line}", content=f"line {line}")
                for line in range(1, 6)
            )
        )

    def test_comments_are_sent_in_batches_and_only_the_first_carries_the_event(self) -> None:
        code, payload = self.publish()

        self.assertEqual(code, 1)
        reviews = [call for call in self.writes() if call["endpoint"].endswith("/reviews")]
        self.assertEqual([len(call["body"]["comments"]) for call in reviews], [2, 2, 1])
        # The event is the verdict of the review as a whole; repeating it would
        # emit several verdicts for one candidate.
        self.assertEqual([call["body"]["event"] for call in reviews], ["REQUEST_CHANGES", "COMMENT", "COMMENT"])
        self.assertEqual(payload["publication"]["posted_inline"], 5)
        self.assertEqual(payload["publication"]["batches_completed"], 3)

    def test_a_failure_in_the_middle_reports_the_batches_that_landed(self) -> None:
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/pulls/128/reviews": {"after": 2, "message": "HTTP 502"}
        }
        self._install_gh()

        code, payload = self.publish()

        self.assertEqual(code, 10)
        recorded = json.loads(
            (Path(self.session) / "publication-result.json").read_text(encoding="utf-8")
        )
        self.assertTrue(recorded["partial"])
        self.assertEqual(recorded["batches_completed"], 2)
        self.assertEqual(recorded["batches_planned"], 3)
        self.assertEqual(recorded["posted_inline"], 4)
        self.assertEqual(recorded["planned_inline"], 5)
        self.assertEqual(len(recorded["review_ids"]), 2)
        self.assertIsNone(recorded["summary_comment_id"])
        message = " ".join(item["message"] for item in payload["diagnostics"])
        self.assertIn("2 of 3 review batch(es)", message)
        # The batch that carries the event landed, so the pull request already
        # shows the verdict: the retry must resume, not repeat.
        self.assertIn("already carries the verdict", message)
        self.assertIn("not sent twice", message)

    def test_a_retry_resumes_and_never_posts_the_same_comments_twice(self) -> None:
        # The evidence of a candidate is keyed by its head commit, so reviewing
        # it again lands in the same directory and finds what the failed
        # publication left behind.
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/pulls/128/reviews": {"after": 2, "message": "HTTP 502"}
        }
        self._install_gh()
        code, _payload = self.publish()
        self.assertEqual(code, 10)

        # The obstacle clears; the same command runs again.
        state = json.loads(self.gh_state_path.read_text(encoding="utf-8"))
        state.pop("api_failures", None)
        state.pop("counts", None)
        self.gh_state_path.write_text(json.dumps(state), encoding="utf-8")

        code, payload = self.publish()

        self.assertEqual(code, 1)
        # Only the batch that had not landed, plus the summary.
        reviews = [call for call in self.writes() if call["endpoint"].endswith("/reviews")]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(len(reviews[0]["body"]["comments"]), 1)
        self.assertEqual(payload["publication"]["resumed_from"], 2)
        self.assertIn("publish_resuming", {item["code"] for item in payload["diagnostics"]})
        # It confirmed against the pull request rather than trusting its own file.
        self.assertIn(
            "GET repos/tserdeiro/consumer/pulls/128/reviews",
            [f"{call['method']} {call['endpoint']}" for call in self.calls()],
        )

    def test_a_resume_whose_reviews_are_absent_starts_over_and_says_so(self) -> None:
        self.open_review()
        (Path(self.session) / "publication-result.json").write_text(
            json.dumps({"candidate_id": "unrelated", "batches_completed": 2, "failure": "HTTP 502"}),
            encoding="utf-8",
        )
        self.api_log.unlink(missing_ok=True)

        code, payload = self.invoke_json(
            "review", "--findings", str(self.findings_path), "--session", self.session, "--publish"
        )

        self.assertEqual(code, 1)
        self.assertEqual(payload["publication"]["resumed_from"], 0)

    def test_nothing_after_the_failure_is_attempted(self) -> None:
        self.gh_state["api_failures"] = {
            "POST repos/tserdeiro/consumer/pulls/128/reviews": {"after": 1, "message": "HTTP 502"}
        }
        self._install_gh()

        self.publish()

        reviews = [call for call in self.writes() if call["endpoint"].endswith("/reviews")]
        self.assertEqual(len(reviews), 2)  # the one that worked and the one that failed
        self.assertEqual([call for call in self.writes() if call["endpoint"].endswith("/issues/128/comments")], [])


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
