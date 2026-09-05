"""Closing the review: correspondence, fail-closed, and the close it performs.

The whole point of this internal second phase is that it refuses to normalize
anything until it has proved it is closing the review that was opened. Every way
that proof can fail has a test here, and each one asserts that *nothing* was
written.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from spec_kit_code_review.errors import EXIT_SUCCESS, EXIT_USAGE
from tests.support.fixtures import install_fake_gh, pull_request_payload
from tests.unit.test_cli import RunCommandCase


def entry(**overrides):
    payload = {
        "path": "src/feature.py",
        "start_line": 1,
        "end_line": 1,
        "side": "RIGHT",
        "severity": "blocking",
        "category": "correctness",
        "title": "The value is never validated",
        "content": "`value = 1` is assigned without any validation.",
        "rule_source": "repo",
    }
    payload.update(overrides)
    return payload


class PhaseTwoCase(RunCommandCase):
    def setUp(self) -> None:
        super().setUp()
        code, payload = self._phase_one()
        self.assertEqual(code, EXIT_SUCCESS)
        self.session = payload["session"]["path"]
        self.findings_path = Path(self.session) / "findings.json"
        self.write_findings(entry())

    def write_findings(self, *entries, document=None) -> None:
        payload = document if document is not None else {"findings": list(entries)}
        self.findings_path.write_text(json.dumps(payload), encoding="utf-8")

    def close(self, *extra: str) -> tuple[int, dict]:
        return self.invoke_json("review", "--findings", str(self.findings_path), "--session", self.session, *extra)

    def session_payload(self) -> dict:
        return json.loads((Path(self.session) / "session.json").read_text(encoding="utf-8"))


class HappyPathTests(PhaseTwoCase):
    def test_the_session_closes_with_a_verdict_and_the_environment_withdrawn(self) -> None:
        code, payload = self.close()

        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"]["value"], "changes-requested")
        self.assertEqual(payload["verdict"]["blocking"], 1)
        self.assertFalse(payload["verdict"]["is_approval"])
        # The first phase left the candidate materialized on purpose; the
        # second withdraws it.
        self.assertEqual(list(self.evidence.glob("*/*/worktree")), [])
        self.assertEqual(self.session_payload()["phase"], "closed")

    def test_every_artifact_of_a_closed_session_is_written(self) -> None:
        self.close()

        directory = Path(self.session)
        for name in (
            "findings.json",
            "findings-normalized.json",
            "findings.md",
            "publication-plan.json",
            "review-packet.md",
            "session.json",
        ):
            with self.subTest(artifact=name):
                self.assertTrue((directory / name).is_file(), name)
        recorded = json.loads((directory / "findings-normalized.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["findings"][0]["id"], "F001")
        self.assertEqual(recorded["verdict"]["value"], "changes-requested")

    def test_the_findings_input_is_never_overwritten_by_its_own_normalization(self) -> None:
        # The bind forces the agent's input to `findings.json`; the normalized
        # document -- what F001, the verdict, and the digest below are about --
        # must land elsewhere, or this write destroys the very input its own
        # `findings_sha256` claims to describe.
        before = self.findings_path.read_bytes()

        self.close()

        self.assertEqual(self.findings_path.read_bytes(), before)
        self.assertEqual(self.session_payload()["findings_sha256"], hashlib.sha256(before).hexdigest())

    def test_the_json_document_carries_every_documented_key(self) -> None:
        _code, payload = self.close()

        for key in (
            "schema_version",
            "candidate",
            "engine",
            "packet_sha256",
            "rules_sha256",
            "scope",
            "budget",
            "findings",
            "verdict",
            "warnings",
            "diagnostics",
            "code",
            "category",
            "message",
            "retryable",
        ):
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_the_json_carries_no_home_path(self) -> None:
        _code, payload = self.close()

        self.assertNotIn(str(Path.home()), json.dumps(payload))

    def test_a_review_without_blocking_findings_exits_zero_and_is_not_an_approval(self) -> None:
        self.write_findings(entry(severity="minor"))

        code, payload = self.close()

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(payload["verdict"]["value"], "no-blocking-findings")
        self.assertIn("not an approval", json.dumps(payload["verdict"]))

    def test_an_empty_findings_document_is_a_legitimate_review(self) -> None:
        self.write_findings()

        code, payload = self.close()

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["verdict"]["value"], "no-blocking-findings")

    def test_a_publication_plan_is_written_but_never_executed(self) -> None:
        _code, payload = self.close()

        plan = json.loads((Path(self.session) / "publication-plan.json").read_text(encoding="utf-8"))
        self.assertFalse(plan["executed"])
        self.assertEqual(plan["event"], "COMMENT")
        self.assertEqual(plan["candidate_id"], payload["candidate"]["candidate_id"])

    def test_the_human_render_names_the_verdict_and_the_evidence(self) -> None:
        _code, payload = self.close()

        self.assertIn("VERDICT: changes-requested", payload["human"])
        self.assertIn(self.session, payload["human"])


class CorrespondenceTests(PhaseTwoCase):
    """Everything that means "this is not the review phase 1 opened"."""

    def _assert_session_untouched(self, findings_before: bytes) -> None:
        self.assertEqual(self.session_payload()["phase"], "open")
        self.assertFalse((Path(self.session) / "findings.md").exists())
        self.assertFalse((Path(self.session) / "publication-plan.json").exists())
        # A refused or aborted close must never touch the agent's input, even
        # when that input is itself the reason the close was refused.
        self.assertEqual(
            self.findings_path.read_bytes(), findings_before, "the findings input must survive an aborted close"
        )

    def test_findings_without_a_session_are_refused(self) -> None:
        code, payload = self.invoke_json("review", "--findings", str(self.findings_path))

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "session_path_missing")

    def test_findings_outside_the_session_are_a_usage_error_naming_the_expected_location(self) -> None:
        outside = self.workspace / "findings-from-another-review.json"
        outside.write_text(json.dumps({"findings": [entry()]}), encoding="utf-8")
        before = self.findings_path.read_bytes()

        code, payload = self.invoke_json(
            "review", "--findings", str(outside), "--session", self.session
        )

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "findings_session_mismatch")
        self.assertIn(str(Path(self.session) / "findings.json"), payload["message"])
        self.assertIn(str(Path(self.session) / "findings.json"), payload["diagnostics"][0]["message"])
        self._assert_session_untouched(before)

    def test_a_sibling_file_inside_the_session_is_refused(self) -> None:
        # Containment would accept this -- it resolves inside the session --
        # but the bind is equality: only the exact expected file may close the
        # review, or a stale sibling would survive a reopen and close the next
        # one on reused findings.
        sibling = Path(self.session) / "stale-findings.json"
        sibling.write_text(json.dumps({"findings": [entry()]}), encoding="utf-8")
        before = self.findings_path.read_bytes()

        code, payload = self.invoke_json(
            "review", "--findings", str(sibling), "--session", self.session
        )

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "findings_session_mismatch")
        self._assert_session_untouched(before)

    def test_a_findings_symlink_that_resolves_outside_the_session_is_refused(self) -> None:
        outside = self.workspace / "reused-findings.json"
        outside.write_text(json.dumps({"findings": [entry()]}), encoding="utf-8")
        linked = Path(self.session) / "linked-findings.json"
        linked.symlink_to(outside)
        before = self.findings_path.read_bytes()

        code, payload = self.invoke_json(
            "review", "--findings", str(linked), "--session", self.session
        )

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "findings_session_mismatch")
        self._assert_session_untouched(before)

    def test_an_unresolvable_home_directory_is_a_usage_error_not_a_crash(self) -> None:
        # `expanduser` raises `RuntimeError` for a user it cannot look up; that
        # must land as this usage error, not escape as an internal failure.
        before = self.findings_path.read_bytes()

        code, payload = self.invoke_json(
            "review", "--findings", "~nosuchuser/findings.json", "--session", self.session
        )

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "findings_session_mismatch")
        self._assert_session_untouched(before)

    def test_a_head_that_moved_is_drift(self) -> None:
        self.repository.git("switch", "feature")
        self.repository.commit("src/feature.py", "value = 2\n", "the head moved")
        self.repository.checkout("main")
        before = self.findings_path.read_bytes()

        code, payload = self.close()

        self.assertEqual(code, 8)
        self.assertEqual(payload["diagnostics"][0]["code"], "drift_head")
        self._assert_session_untouched(before)

    def test_a_merge_base_that_moved_is_drift_with_its_own_message(self) -> None:
        # The base branch is rewritten -- an amend, a rebase, a force-push --
        # so the fork point the candidate was computed against no longer exists.
        # The head never moved, and the review is still about a different range.
        rewritten = self.repository.git(
            "commit-tree", f"{self.base}^{{tree}}", "-p", f"{self.base}~1", "-m", "the base was rewritten"
        )
        # `main` is checked out, so the branch is moved by moving the checkout.
        self.repository.git("reset", "--hard", rewritten.strip())
        before = self.findings_path.read_bytes()

        code, payload = self.close()

        self.assertEqual(code, 8)
        self.assertEqual(payload["diagnostics"][0]["code"], "drift_merge_base")
        self.assertIn("merge_base", payload["message"])
        self._assert_session_untouched(before)

    def test_a_session_of_another_candidate_is_refused(self) -> None:
        payload = self.session_payload()
        payload["candidate"]["candidate_id"] = "f" * 64
        (Path(self.session) / "session.json").write_text(json.dumps(payload), encoding="utf-8")
        before = self.findings_path.read_bytes()

        code, response = self.close()

        self.assertEqual(code, 8)
        self.assertEqual(response["diagnostics"][0]["code"], "session_candidate_mismatch")
        self._assert_session_untouched(before)

    def test_a_packet_edited_after_phase_one_is_refused(self) -> None:
        packet = Path(self.session) / "review-packet.md"
        packet.write_text(packet.read_text(encoding="utf-8") + "\nAn extra line.\n", encoding="utf-8")
        before = self.findings_path.read_bytes()

        code, payload = self.close()

        self.assertEqual(code, 8)
        self.assertEqual(payload["diagnostics"][0]["code"], "packet_sha256_mismatch")
        self._assert_session_untouched(before)

    def test_a_missing_packet_is_refused(self) -> None:
        (Path(self.session) / "review-packet.md").unlink()

        code, payload = self.close()

        self.assertEqual(code, 8)
        self.assertEqual(payload["diagnostics"][0]["code"], "session_packet_missing")

    def test_a_session_that_is_already_closed_cannot_be_closed_again(self) -> None:
        self.close()

        code, payload = self.close()

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "session_not_open")

    def test_a_configuration_changed_between_the_phases_is_refused(self) -> None:
        configuration = self.root / "speckit-code-review.yml"
        configuration.write_text(
            configuration.read_text(encoding="utf-8").replace("limit: 400", "limit: 40"), encoding="utf-8"
        )
        before = self.findings_path.read_bytes()

        code, payload = self.close()

        self.assertEqual(code, 3)
        self.assertEqual(payload["diagnostics"][0]["code"], "config_sha256_mismatch")
        self._assert_session_untouched(before)

    def test_invalid_findings_leave_the_session_open(self) -> None:
        self.findings_path.write_text("{not json", encoding="utf-8")
        before = self.findings_path.read_bytes()

        code, payload = self.close()

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "findings_invalid_json")
        self._assert_session_untouched(before)

    def test_publishing_without_a_pull_request_is_refused_after_the_close(self) -> None:
        # This session was resolved with --base/--head, so there is no pull
        # request to publish to. The review still closes; only the publication
        # is refused -- as a usage error, before `gh` is required and before any
        # remote call is made for nothing.
        code, payload = self.close("--publish")

        self.assertEqual(code, EXIT_USAGE)
        self.assertIn(
            "publish_no_pull_request", {item["code"] for item in payload["diagnostics"]}
        )
        # The review itself completed and is on disk: a publication that cannot
        # happen must not cost the work that was already done.
        self.assertEqual(self.session_payload()["phase"], "closed")
        self.assertTrue((Path(self.session) / "findings.json").is_file())


class InconclusiveThroughTheCommandTests(PhaseTwoCase):
    """The engine cause, reached the way it will be reached in production."""

    def _set_engine_status(self, status) -> None:
        payload = self.session_payload()
        payload["engine"]["status"] = status
        (Path(self.session) / "session.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_phase_one_records_the_engine_status(self) -> None:
        self.assertEqual(self.session_payload()["engine"]["status"], "success")

    def test_a_known_complete_status_is_not_inconclusive(self) -> None:
        self._set_engine_status("completed_with_warnings")

        code, payload = self.close()

        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"]["value"], "changes-requested")

    def test_an_inconclusive_review_with_blocking_findings_exits_one(self) -> None:
        # A truncated packet must not turn a blocking finding into a green run.
        payload = self.session_payload()
        payload["engine"]["status"] = "success"
        payload["packet"]["truncations"] = [
            {"path": "specs/001/plan.md", "omitted_bytes": 4096, "omitted_lines": 80, "command": "git show ..."}
        ]
        (Path(self.session) / "session.json").write_text(json.dumps(payload), encoding="utf-8")

        code, response = self.close()

        self.assertEqual(code, 1)
        self.assertEqual(response["verdict"]["value"], "inconclusive")
        self.assertEqual(response["verdict"]["blocking"], 1)
        self.assertNotIn(
            "verdict_inconclusive_not_failed", {item["code"] for item in response["diagnostics"]}
        )

    def test_a_failed_engine_makes_the_review_inconclusive_with_exit_nine(self) -> None:
        self._set_engine_status("failed")

        code, payload = self.close()

        self.assertEqual(code, 9)
        self.assertEqual(payload["verdict"]["value"], "inconclusive")
        self.assertEqual(payload["verdict"]["causes"][0]["kind"], "engine")
        self.assertTrue(payload["retryable"])

    def test_an_unknown_status_fails_closed(self) -> None:
        # A status this version cannot vouch for is not "fine": calling it fine
        # is the silent half-coverage the verdict exists to prevent.
        self._set_engine_status("some_future_status")

        code, payload = self.close()

        self.assertEqual(code, 9)
        self.assertIn("some_future_status", payload["verdict"]["causes"][0]["detail"])

    def test_the_human_render_names_what_was_not_covered(self) -> None:
        self._set_engine_status("budget_exceeded")

        code, out, _err = self.invoke(
            "review", "--findings", str(self.findings_path), "--session", self.session
        )

        self.assertEqual(code, 9)
        self.assertIn("VERDICT: inconclusive", out)
        self.assertIn("The review did NOT cover its intended scope", out)
        self.assertIn("budget_exceeded", out)


class HumanRenderTests(PhaseTwoCase):
    def test_the_whole_report_reaches_stdout(self) -> None:
        code, out, _err = self.invoke(
            "review", "--findings", str(self.findings_path), "--session", self.session
        )

        self.assertEqual(code, 1)
        self.assertIn("Review summary", out)
        self.assertIn("VERDICT: changes-requested", out)
        self.assertIn("F001", out)
        self.assertIn("evidence:", out)

    def test_quiet_keeps_the_verdict_and_drops_the_detail(self) -> None:
        code, out, _err = self.invoke(
            "review", "--findings", str(self.findings_path), "--session", self.session, "--quiet"
        )

        self.assertEqual(code, 1)
        self.assertIn("changes-requested", out)
        self.assertNotIn("Review summary", out)


class RestoreFailureTests(PhaseTwoCase):
    """A close that cannot restore leaves the session open, and can be retried."""

    def test_a_failed_restore_keeps_the_session_open_and_records_the_attempt(self) -> None:
        from unittest import mock

        from spec_kit_code_review.environment import RestoreOutcome

        failed = RestoreOutcome(restored=False, code=7)
        with mock.patch("spec_kit_code_review.cli.restore", return_value=failed):
            code, payload = self.close()

        self.assertEqual(code, 7)
        recorded = self.session_payload()
        self.assertEqual(recorded["phase"], "open")
        self.assertIn("last_restore_attempt", recorded)
        self.assertFalse(recorded["last_restore_attempt"]["restored"])
        # Nothing was written as if the review had closed.
        self.assertFalse((Path(self.session) / "findings.md").exists())
        self.assertFalse((Path(self.session) / "publication-plan.json").exists())

    def test_the_same_command_works_once_the_obstacle_is_gone(self) -> None:
        from unittest import mock

        from spec_kit_code_review.environment import RestoreOutcome

        failed = RestoreOutcome(restored=False, code=7)
        with mock.patch("spec_kit_code_review.cli.restore", return_value=failed):
            self.close()

        code, payload = self.close()

        self.assertEqual(code, 1)
        self.assertEqual(self.session_payload()["phase"], "closed")
        self.assertEqual(payload["verdict"]["value"], "changes-requested")


class NormalizationThroughTheCommandTests(PhaseTwoCase):
    def test_a_hallucinated_path_is_discarded_and_recorded(self) -> None:
        self.write_findings(entry(), entry(path="src/never_existed.py", title="Invented"))

        code, payload = self.close()

        self.assertEqual(code, 1)
        self.assertEqual([item["path"] for item in payload["findings"]], ["src/feature.py"])
        self.assertEqual(payload["discarded_findings"][0]["title"], "Invented")
        self.assertIn("finding_discarded", {item["code"] for item in payload["diagnostics"]})

    def test_a_hostile_path_is_a_usage_error_and_nothing_is_closed(self) -> None:
        self.write_findings(entry(path="../../etc/passwd"))

        code, payload = self.close()

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(payload["diagnostics"][0]["code"], "findings_path_invalid")
        self.assertEqual(self.session_payload()["phase"], "open")

    def test_a_finding_outside_the_diff_is_kept_but_degraded(self) -> None:
        # `src/feature.py` has a single line, so line 1 is inside the file; a
        # finding there anchors. This one asks for a line the diff never touched
        # by pointing at a file the candidate did not change.
        self.write_findings(entry(path="src/module.py", start_line=1, end_line=1))

        code, payload = self.close()

        self.assertEqual(code, 1)
        self.assertEqual(len(payload["findings"]), 1)
        self.assertFalse(payload["findings"][0]["anchorable"])
        self.assertIn("not inside a hunk", payload["findings"][0]["degraded_reason"])

    def test_a_left_side_finding_reaches_the_summary_of_the_plan(self) -> None:
        # `src/feature.py` is created by the candidate, so a LEFT finding about
        # it belongs to a file the merge base does not have: this one is about a
        # file that exists in both.
        self.write_findings(entry(path="src/module.py", side="LEFT", severity="major", start_line=1, end_line=1))

        _code, payload = self.close()

        self.assertFalse(payload["findings"][0]["anchorable"])
        plan = payload["publication_plan"]
        self.assertEqual(plan["inline_count"], 0)
        self.assertEqual(plan["degraded"][0]["finding_id"], "F001")

    def test_the_findings_digest_is_recorded_in_the_session(self) -> None:
        self.close()

        self.assertEqual(len(self.session_payload()["findings_sha256"]), 64)
        self.assertEqual(self.session_payload()["findings_count"], 1)


class ProtectedPathThroughTheCommandTests(RunCommandCase):
    """FR-010 / plan D1, wired end to end -- `test_contract.py` covers the
    generated finding's shapes directly and much more cheaply; this is the
    proof that phase two actually reaches it and the verdict follows. Only a
    real pull request carries a ``base_branch``, hence the PR selector."""

    PR_NUMBER = 900

    def _review(self, *, base_branch: str, base_commit: str, head_commit: str) -> tuple[int, dict]:
        self._engine_reports("specs/004-x/spec.md")
        install_fake_gh(
            self.bin,
            {
                "auth": {"authenticated": True, "scopes": ["repo"]},
                "user": "tester",
                "pull_requests": {
                    str(self.PR_NUMBER): pull_request_payload(
                        number=self.PR_NUMBER,
                        repository="tserdeiro/consumer",
                        base_branch=base_branch,
                        base_commit=base_commit,
                        head_commit=head_commit,
                    )
                },
            },
        )
        code, opened = self.invoke_json("review", str(self.PR_NUMBER))
        self.assertEqual(code, EXIT_SUCCESS, opened)
        session = opened["session"]["path"]
        findings_path = Path(session) / "findings.json"
        findings_path.write_text(json.dumps({"findings": []}), encoding="utf-8")
        return self.invoke_json("review", "--findings", str(findings_path), "--session", session)

    def test_a_protected_path_on_a_task_base_reaches_changes_requested(self) -> None:
        feature_base = self.repository.commit("specs/004-x/spec.md", "Initial spec.\n", "seed the protected path")
        head = self.repository.commit("specs/004-x/spec.md", "Initial spec.\nMore.\n", "touch the spec")

        code, payload = self._review(base_branch="004-feature", base_commit=feature_base, head_commit=head)

        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"]["value"], "changes-requested")
        finding = payload["findings"][0]
        self.assertEqual((finding["severity"], finding["category"], finding["path"]), ("blocking", "contract", "specs/004-x/spec.md"))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()


class RedactedSessionPathTests(PhaseTwoCase):
    """Production sessions persist home-redacted paths; closing must still
    withdraw the real worktree (the tilde leak this class regresses)."""

    def test_a_tilde_redacted_worktree_path_is_still_withdrawn(self) -> None:
        session_file = Path(self.session) / "session.json"
        document = json.loads(session_file.read_text(encoding="utf-8"))
        environment = document["environment"]
        real_worktree = Path(environment["worktree_path"])
        self.assertTrue(real_worktree.exists(), "phase one materialized no worktree")

        # Redact the way production evidence does: the home prefix becomes `~`.
        fake_home = real_worktree.parents[3]
        for key in ("worktree_path", "working_root"):
            value = environment.get(key)
            if value and value.startswith(str(fake_home)):
                environment[key] = "~" + value[len(str(fake_home)):]
        session_file.write_text(json.dumps(document), encoding="utf-8")

        # invoke() replaces the whole environ with self.environment, so the
        # fake home must live in that snapshot, not in an outer patch.
        self.environment["HOME"] = str(fake_home)
        code, payload = self.close()

        self.assertEqual(code, 1)
        restore_outcome = (self.session_payload().get("environment") or {}).get("restore") or {}
        self.assertFalse(
            restore_outcome.get("already_restored"),
            f"restore treated the redacted path as already gone: {restore_outcome}",
        )
        self.assertTrue(restore_outcome.get("restored"), restore_outcome)
        self.assertFalse(real_worktree.exists(), "the redacted path leaked the worktree")

    def test_a_tilde_redacted_repository_root_still_closes(self) -> None:
        session_file = Path(self.session) / "session.json"
        document = json.loads(session_file.read_text(encoding="utf-8"))
        real_root = Path(document["repository_root"])
        fake_home = real_root.parent
        document["repository_root"] = "~" + str(real_root)[len(str(fake_home)):]
        session_file.write_text(json.dumps(document), encoding="utf-8")

        self.environment["HOME"] = str(fake_home)
        code, payload = self.close()

        self.assertEqual(code, 1, payload)
        self.assertEqual(payload["verdict"]["value"], "changes-requested")
