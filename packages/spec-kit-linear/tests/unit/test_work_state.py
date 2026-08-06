from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from spec_kit_linear.git_refs import known_branches
from spec_kit_linear.github import PullRequest, scan_pull_requests
from spec_kit_linear.work_state import (
    SOURCE_BRANCH,
    SOURCE_CHECKBOX,
    SOURCE_NONE,
    SOURCE_PULL_REQUEST,
    STATE_COMPLETED,
    STATE_REVIEW,
    STATE_STARTED,
    STATE_UNSTARTED,
    branch_pattern,
    derive_task_state,
)


def _pull_request(head_branch: str, *, draft: bool = False, state: str = "OPEN") -> PullRequest:
    return PullRequest(head_branch=head_branch, is_draft=draft, state=state)


def _derive(**overrides: object):
    arguments: dict[str, object] = {"completed": False, "branches": (), "pull_requests": ()}
    arguments.update(overrides)
    return derive_task_state("001", "T004", **arguments)  # type: ignore[arg-type]


class BranchConventionTests(unittest.TestCase):
    def test_the_convention_matches_a_bare_task_branch_and_a_suffixed_one(self) -> None:
        pattern = branch_pattern("001", "T004")

        for name in ("001-T004", "001-T004-add-the-parser", "001-T004-"):
            with self.subTest(name=name):
                self.assertTrue(pattern.fullmatch(name))

    def test_names_that_only_look_like_the_convention_never_match(self) -> None:
        pattern = branch_pattern("001", "T004")

        for name in ("T004", "001-T004x", "001-T0041", "1-T004", "001-t004", "feature/001-T004", "002-T004", "001-T005"):
            with self.subTest(name=name):
                self.assertIsNone(pattern.fullmatch(name))


class DerivationTests(unittest.TestCase):
    def test_a_checked_checkbox_wins_over_every_other_observation(self) -> None:
        derived = _derive(completed=True, branches=("001-T004",), pull_requests=(_pull_request("001-T004", draft=True),))

        self.assertEqual((derived.state, derived.source), (STATE_COMPLETED, SOURCE_CHECKBOX))

    def test_a_merged_pull_request_completes_an_unchecked_task(self) -> None:
        derived = _derive(pull_requests=(_pull_request("001-T004", state="MERGED"),))

        self.assertEqual((derived.state, derived.source, derived.detail), (STATE_COMPLETED, SOURCE_PULL_REQUEST, "001-T004"))

    def test_a_ready_pull_request_is_review(self) -> None:
        derived = _derive(branches=("001-T004",), pull_requests=(_pull_request("001-T004-work"),))

        self.assertEqual((derived.state, derived.source), (STATE_REVIEW, SOURCE_PULL_REQUEST))

    def test_a_draft_pull_request_is_started_and_outranks_the_branch(self) -> None:
        derived = _derive(branches=("001-T004",), pull_requests=(_pull_request("001-T004", draft=True),))

        self.assertEqual((derived.state, derived.source), (STATE_STARTED, SOURCE_PULL_REQUEST))

    def test_a_branch_alone_is_started(self) -> None:
        derived = _derive(branches=("main", "001-T004-add-the-parser"))

        self.assertEqual((derived.state, derived.source, derived.detail), (STATE_STARTED, SOURCE_BRANCH, "001-T004-add-the-parser"))

    def test_nothing_observable_is_unstarted(self) -> None:
        derived = _derive(branches=("main", "001-T005"), pull_requests=(_pull_request("001-T005"),))

        self.assertEqual((derived.state, derived.source, derived.detail), (STATE_UNSTARTED, SOURCE_NONE, None))

    def test_a_closed_unmerged_pull_request_is_ignored_and_the_branch_decides(self) -> None:
        derived = _derive(branches=("001-T004",), pull_requests=(_pull_request("001-T004", state="CLOSED"),))

        self.assertEqual((derived.state, derived.source), (STATE_STARTED, SOURCE_BRANCH))

    def test_a_closed_pull_request_with_no_branch_left_is_unstarted(self) -> None:
        derived = _derive(pull_requests=(_pull_request("001-T004", state="CLOSED"),))

        self.assertEqual(derived.state, STATE_UNSTARTED)

    def test_stacked_pull_requests_report_the_furthest_the_task_reached(self) -> None:
        derived = _derive(
            pull_requests=(
                _pull_request("001-T004-part-2", draft=True),
                _pull_request("001-T004-part-1"),
            )
        )

        self.assertEqual(derived.state, STATE_REVIEW)


class KnownBranchesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(["git", "-C", str(self.root), *arguments], check=True, text=True, capture_output=True)
        return result.stdout.strip()

    def test_local_and_already_known_origin_branches_are_both_reported(self) -> None:
        for arguments in (("init", "-q", "-b", "main"), ("config", "user.email", "test@example.com"), ("config", "user.name", "Test")):
            self._git(*arguments)
        self._git("commit", "--allow-empty", "-q", "-m", "root")
        head = self._git("rev-parse", "HEAD")
        self._git("branch", "001-T001-local-work")
        # A remote-tracking ref, written without a remote and without a fetch:
        # this is exactly what the derivation reads, and it never goes out to
        # the network to read it.
        self._git("update-ref", "refs/remotes/origin/001-T002-pushed-work", head)
        self._git("update-ref", "refs/remotes/origin/HEAD", head)

        branches = known_branches(self.root)

        self.assertIn("001-T001-local-work", branches)
        self.assertIn("001-T002-pushed-work", branches)
        self.assertIn("main", branches)
        self.assertNotIn("HEAD", branches)
        self.assertNotIn("origin/001-T002-pushed-work", branches)

    def test_a_directory_that_is_not_a_repository_degrades_to_no_branches(self) -> None:
        self.assertEqual(known_branches(self.root), ())


class PullRequestScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _scan(self, *, gh: str | None = "/usr/bin/gh", returncode: int = 0, stdout: str = "[]"):
        # `shutil`/`subprocess` are shared module objects, so these patches are
        # global while they are active: nothing but the scan runs inside them.
        completed = SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
        with patch("spec_kit_linear.github.shutil.which", return_value=gh):
            with patch("spec_kit_linear.github.subprocess.run", return_value=completed) as run:
                scan = scan_pull_requests(self.root)
        return scan, run

    def test_a_successful_scan_reads_every_pull_request_in_one_call(self) -> None:
        payload = '[{"headRefName": "001-T001-work", "isDraft": true, "state": "OPEN"}, {"headRefName": "001-T002", "isDraft": false, "state": "MERGED"}]'

        scan, run = self._scan(stdout=payload)

        self.assertTrue(scan.available)
        self.assertEqual(scan.diagnostics, ())
        self.assertEqual([item.head_branch for item in scan.pull_requests], ["001-T001-work", "001-T002"])
        self.assertTrue(scan.pull_requests[0].is_draft)
        self.assertTrue(scan.pull_requests[1].is_merged)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:3], ["gh", "pr", "list"])

    def test_a_missing_gh_binary_warns_once_and_never_runs_anything(self) -> None:
        scan, run = self._scan(gh=None)

        self.assertFalse(scan.available)
        self.assertEqual(scan.pull_requests, ())
        self.assertEqual([item.code for item in scan.diagnostics], ["github_cli_missing"])
        self.assertEqual([item.severity for item in scan.diagnostics], ["warning"])
        self.assertEqual(run.call_count, 0)

    def test_an_unauthenticated_gh_degrades_with_one_warning(self) -> None:
        scan, _run = self._scan(returncode=1, stdout="")

        self.assertFalse(scan.available)
        self.assertEqual([item.code for item in scan.diagnostics], ["github_cli_unavailable"])

    def test_malformed_gh_output_degrades_instead_of_being_half_read(self) -> None:
        for payload in ("not json at all", '{"headRefName": "001-T001"}', '[{"headRefName": 7, "isDraft": false, "state": "OPEN"}]', '[{"isDraft": false}]'):
            with self.subTest(payload=payload):
                scan, _run = self._scan(stdout=payload)

                self.assertFalse(scan.available)
                self.assertEqual(scan.pull_requests, ())
                self.assertEqual([item.code for item in scan.diagnostics], ["github_cli_malformed"])


if __name__ == "__main__":
    unittest.main()
