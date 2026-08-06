from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.candidate import (
    _require_local_commit as require_local_commit,
    compute_candidate_id,
    verify_checkout_matches_pull_request,
    parse_selector,
    resolve_from_pull_request,
    resolve_from_refs,
    resolve_repository,
)
from spec_kit_code_review.errors import EXIT_AUTHENTICATION, EXIT_CANDIDATE, EXIT_USAGE, AppError
from spec_kit_code_review.git import open_git
from spec_kit_code_review.github import GitHub, PullRequest
from spec_kit_code_review.github import _pull_request_from_payload as pull_request_from_payload
from tests.support.fixtures import install_fake_gh, pull_request_payload
from tests.support.repo import TemporaryRepository


class SelectorTests(unittest.TestCase):
    def test_number_selector(self) -> None:
        selector = parse_selector("128")

        self.assertEqual(selector.number, 128)
        self.assertIsNone(selector.repository)

    def test_url_selector_carries_the_repository(self) -> None:
        selector = parse_selector("https://github.com/tserdeiro/spec-kit/pull/128")

        self.assertEqual(selector.number, 128)
        self.assertEqual(selector.repository, "tserdeiro/spec-kit")

    def test_url_with_a_suffix_still_parses(self) -> None:
        selector = parse_selector("https://github.com/tserdeiro/spec-kit/pull/128/files")

        self.assertEqual(selector.number, 128)

    def test_garbage_selector_is_a_usage_error(self) -> None:
        for value in ("", "  ", "main", "https://gitlab.com/o/r/pull/1", "12a"):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as caught:
                    parse_selector(value)
                self.assertEqual(caught.exception.code, EXIT_USAGE)


class CandidateIdentityTests(unittest.TestCase):
    def test_candidate_id_is_the_documented_digest(self) -> None:
        merge_base = "a" * 40
        head = "b" * 40

        self.assertEqual(
            compute_candidate_id(merge_base, head),
            hashlib.sha256(f"{merge_base}\n{head}\n".encode("utf-8")).hexdigest(),
        )

    def test_identity_depends_on_the_merge_base_not_only_on_the_head(self) -> None:
        head = "b" * 40

        self.assertNotEqual(compute_candidate_id("a" * 40, head), compute_candidate_id("c" * 40, head))


class _CandidateCase(unittest.TestCase):
    """A temporary repository with a base branch, a feature head, and a fake gh."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)

        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.base = self.repository.commit("README.md", "base\n", "base commit")
        self.repository.branch("feature")
        self.head = self.repository.commit("src/feature.py", "value = 1\n", "feature work")
        self.repository.checkout("main")
        self.base_tip = self.repository.commit("CHANGELOG.md", "base advances\n", "base advances")
        self.repository.add_remote("origin", "git@github.com:tserdeiro/consumer.git")
        self.git = open_git(self.repository.path)

    def github(self, state: dict) -> GitHub:
        executable, environment = install_fake_gh(self.workspace / "bin", state)
        import os

        for key, value in environment.items():
            os.environ[key] = value
            self.addCleanup(os.environ.pop, key, None)
        return GitHub(executable)

    def payload(self, **overrides) -> dict:
        defaults = dict(
            number=128,
            repository="tserdeiro/consumer",
            base_branch="main",
            base_commit=self.base_tip,
            head_commit=self.head,
        )
        defaults.update(overrides)
        return pull_request_payload(**defaults)


class RepositoryResolutionTests(_CandidateCase):
    def test_explicit_repository_wins(self) -> None:
        self.assertEqual(resolve_repository(self.git, explicit="other/name"), "other/name")

    def test_selector_url_repository_is_used(self) -> None:
        selector = parse_selector("https://github.com/tserdeiro/consumer/pull/128")

        self.assertEqual(resolve_repository(self.git, selector=selector), "tserdeiro/consumer")

    def test_configured_remote_is_used(self) -> None:
        self.assertEqual(resolve_repository(self.git), "tserdeiro/consumer")

    def test_several_github_remotes_without_a_flag_are_ambiguous(self) -> None:
        self.repository.git("remote", "remove", "origin")
        self.repository.add_remote("first", "git@github.com:one/consumer.git")
        self.repository.add_remote("second", "git@github.com:two/consumer.git")

        with self.assertRaises(AppError) as caught:
            resolve_repository(self.git)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("ambiguous", str(caught.exception))
        self.assertIn("one/consumer", caught.exception.diagnostics[0].message)

    def test_no_github_remote_is_a_candidate_failure(self) -> None:
        self.repository.git("remote", "remove", "origin")

        with self.assertRaises(AppError) as caught:
            resolve_repository(self.git)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)


class ExplicitRefsTests(_CandidateCase):
    def test_base_and_head_resolve_offline(self) -> None:
        candidate = resolve_from_refs(self.git, base="main", head="feature")

        self.assertEqual(candidate.head_commit, self.head)
        self.assertEqual(candidate.merge_base, self.base)
        self.assertEqual(candidate.base_commit, self.base_tip)
        self.assertEqual(candidate.candidate_id, compute_candidate_id(self.base, self.head))
        self.assertEqual(candidate.selector_kind, "refs")
        self.assertIsNone(candidate.repository)

    def test_one_of_the_pair_alone_is_a_usage_error(self) -> None:
        for base, head in ((None, "feature"), ("main", None), (None, None), ("", "")):
            with self.subTest(base=base, head=head):
                with self.assertRaises(AppError) as caught:
                    resolve_from_refs(self.git, base=base, head=head)
                self.assertEqual(caught.exception.code, EXIT_USAGE)

    def test_unrelated_histories_have_no_merge_base(self) -> None:
        self.repository.git("checkout", "--orphan", "unrelated")
        self.repository.commit("unrelated.txt", "no shared history\n", "unrelated root")

        with self.assertRaises(AppError) as caught:
            resolve_from_refs(self.git, base="unrelated", head="feature")

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("merge base", str(caught.exception))


class BoundedFetchTests(unittest.TestCase):
    """Resolution rule 4: exactly one bounded fetch, and only when writing is allowed.

    The consumer is a real single-branch clone over the real transport, so the
    candidate's objects are genuinely absent until something fetches them --
    there is no honest way to fake that. The identity plumbing (which remote is
    ``owner/name``) is exercised elsewhere; what is under test here is the fetch
    itself: whether it happens at all, with which refspec, and what it writes.
    """

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()

        self.upstream = TemporaryRepository(self.workspace / "upstream")
        self.addCleanup(self.upstream.cleanup)
        self.base = self.upstream.commit("README.md", "base\n", "base commit")
        self.upstream.branch("feature")
        self.head = self.upstream.commit("src/feature.py", "value = 1\n", "feature work")
        self.upstream.checkout("main")
        self.advanced_base = self.upstream.commit("CHANGELOG.md", "base advances\n", "base advances")
        # GitHub publishes the pull ref; a plain remote does not, so it is created
        # here exactly as the real one would be.
        self.upstream.git("update-ref", "refs/pull/128/head", self.head)
        self.upstream.git("config", "uploadpack.allowAnySHA1InWant", "true")

        self.consumer = TemporaryRepository.clone(self.upstream.path, self.workspace / "consumer")
        self.addCleanup(self.consumer.cleanup)
        self.git = open_git(self.consumer.path)
        self.pull_request = PullRequest(
            number=128,
            repository="tserdeiro/consumer",
            base_branch="main",
            base_commit=self.advanced_base,
            head_commit=self.head,
            head_repository="tserdeiro/consumer",
            cross_repository=False,
            state="OPEN",
            url="https://github.com/tserdeiro/consumer/pull/128",
            title="A candidate",
            body="",
        )

    def _require(self, sha: str, *, label: str, fetch_missing: bool) -> str:
        return require_local_commit(
            self.git,
            sha,
            label=label,
            pull_request=self.pull_request,
            remote="origin",
            fetch_missing=fetch_missing,
        )

    def test_the_head_is_genuinely_absent_before_any_fetch(self) -> None:
        self.assertFalse(self.git.has_commit(self.head))

    def test_without_permission_to_write_nothing_is_fetched(self) -> None:
        with self.assertRaises(AppError) as caught:
            self._require(self.head, label="head", fetch_missing=False)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("fetch it yourself", caught.exception.diagnostics[0].message)
        self.assertIn("git fetch origin refs/pull/128/head", caught.exception.diagnostics[0].message)
        self.assertFalse(self.git.has_commit(self.head))

    def test_one_bounded_fetch_brings_the_head_and_creates_no_local_ref(self) -> None:
        refs_before = self.git.local_refs()

        resolved = self._require(self.head, label="head", fetch_missing=True)

        self.assertEqual(resolved, self.head)
        self.assertTrue(self.git.has_commit(self.head))
        # Doc "Que significa exactamente solo lectura": objects and FETCH_HEAD,
        # never a local ref.
        self.assertEqual(self.git.local_refs(), refs_before)

    def test_the_fetched_head_makes_the_merge_base_computable(self) -> None:
        self._require(self.head, label="head", fetch_missing=True)

        self.assertEqual(self.git.merge_base(self.advanced_base, self.head), self.base)

    def test_an_absent_base_commit_is_fetched_by_its_sha_not_by_the_pull_refspec(self) -> None:
        self.upstream.checkout("main")
        orphan_base = self.upstream.commit("other.md", "unrelated base tip\n", "base moves again")
        self.assertFalse(self.git.has_commit(orphan_base))

        resolved = self._require(orphan_base, label="base", fetch_missing=True)

        self.assertEqual(resolved, orphan_base)
        self.assertTrue(self.git.has_commit(orphan_base))

    def test_an_object_the_remote_does_not_have_still_ends_in_exit_six(self) -> None:
        with self.assertRaises(AppError) as caught:
            self._require("0" * 40, label="base", fetch_missing=True)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("one bounded fetch was attempted", caught.exception.diagnostics[0].message)

    def test_a_refspec_carrying_a_destination_is_refused(self) -> None:
        # `<src>:<dst>` writes into the local ref namespace -- the first entry of
        # the forbidden list -- and reaches git straight from a `gh` payload if
        # nothing checks it.
        refs_before = self.git.local_refs()

        for refspec in ("refs/heads/main:refs/heads/pwned", "+refs/heads/main", "refs/heads/main:"):
            with self.subTest(refspec=refspec):
                with self.assertRaises(AppError) as caught:
                    self.git.fetch("origin", refspec)
                self.assertEqual(caught.exception.diagnostics[0].code, "fetch_refspec_destination")

        self.assertEqual(self.git.local_refs(), refs_before)
        self.assertNotIn("refs/heads/pwned", self.git.local_refs())

    def test_the_fetch_never_triggers_implicit_maintenance(self) -> None:
        recorded: list[tuple[str, ...]] = []
        original = type(self.git).run

        def recording_run(instance, *arguments, **keywords):
            recorded.append(arguments)
            return original(instance, *arguments, **keywords)

        type(self.git).run = recording_run
        self.addCleanup(setattr, type(self.git), "run", original)

        self.git.fetch("origin", "refs/pull/128/head")

        fetch_arguments = next(item for item in recorded if item and item[0] == "fetch")
        self.assertIn("--no-auto-maintenance", fetch_arguments)
        self.assertIn("--no-tags", fetch_arguments)

    def test_a_fetch_that_fails_on_authentication_is_still_a_candidate_failure(self) -> None:
        # Not an engine failure: the candidate could not be resolved, and the
        # relayed reason is redacted.
        self.consumer.git("remote", "set-url", "origin", "https://github.invalid/does-not-exist.git")

        with self.assertRaises(AppError) as caught:
            self._require(self.head, label="head", fetch_missing=True)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("one bounded fetch was attempted", caught.exception.diagnostics[0].message)

    def test_a_remote_name_that_looks_like_an_option_is_rejected(self) -> None:
        with self.assertRaises(AppError) as caught:
            self.git.fetch("--upload-pack=touch /tmp/pwned", "refs/pull/128/head")

        self.assertEqual(caught.exception.diagnostics[0].code, "remote_name_invalid")


class FetchRemoteTests(unittest.TestCase):
    """The objects come from the remote that satisfied rule 8, never from --remote.

    ``origin`` points at an unrelated project and ``upstream`` at the pull
    request's repository. Fetching from ``origin`` would take objects from a
    repository that is not the candidate's -- exactly what rule 8 exists to stop.
    """

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()

        self.upstream = TemporaryRepository(self.workspace / "upstream")
        self.addCleanup(self.upstream.cleanup)
        self.base = self.upstream.commit("README.md", "base\n", "base commit")
        self.upstream.branch("feature")
        self.head = self.upstream.commit("src/feature.py", "value = 1\n", "feature work")
        self.upstream.checkout("main")
        self.upstream.git("update-ref", "refs/pull/128/head", self.head)
        self.upstream.git("config", "uploadpack.allowAnySHA1InWant", "true")

        self.unrelated = TemporaryRepository(self.workspace / "unrelated")
        self.addCleanup(self.unrelated.cleanup)
        self.unrelated.commit("README.md", "someone else\n", "unrelated base")

        self.consumer = TemporaryRepository.clone(self.upstream.path, self.workspace / "consumer")
        self.addCleanup(self.consumer.cleanup)
        self.consumer.git("remote", "set-url", "origin", str(self.unrelated.path))
        self.consumer.git("remote", "add", "upstream", str(self.upstream.path))
        self.git = open_git(self.consumer.path)
        self.pull_request = PullRequest(
            number=128,
            repository="tserdeiro/consumer",
            base_branch="main",
            base_commit=self.base,
            head_commit=self.head,
            head_repository="tserdeiro/consumer",
            cross_repository=False,
            state="OPEN",
            url="https://github.com/tserdeiro/consumer/pull/128",
            title="A candidate",
            body="",
        )

    def _require(self, remote: str | None):
        return require_local_commit(
            self.git,
            self.head,
            label="head",
            pull_request=self.pull_request,
            remote=remote,
            fetch_missing=True,
        )

    def test_the_correspondence_check_names_the_remote_that_matched(self) -> None:
        self.consumer.git("remote", "set-url", "origin", "https://github.com/someone-else/other-project.git")
        self.consumer.git("remote", "set-url", "upstream", "https://github.com/tserdeiro/consumer.git")

        diagnostic, matched = verify_checkout_matches_pull_request(self.git, self.pull_request)

        self.assertEqual(matched, "upstream")
        self.assertIn("upstream", diagnostic.message)

    def test_the_matching_remote_is_the_one_the_objects_come_from(self) -> None:
        self.assertFalse(self.git.has_commit(self.head))

        resolved = self._require("upstream")

        self.assertEqual(resolved, self.head)
        self.assertTrue(self.git.has_commit(self.head))

    def test_fetching_from_the_unrelated_remote_never_produces_the_candidate(self) -> None:
        # `origin` is a different project: it does not have this object, so the
        # only way the resolution could "succeed" is by taking objects from a
        # repository that is not the pull request's.
        with self.assertRaises(AppError) as caught:
            self._require("origin")

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertFalse(self.git.has_commit(self.head))

    def test_without_a_matching_remote_nothing_is_fetched_from_anywhere(self) -> None:
        with self.assertRaises(AppError) as caught:
            self._require(None)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("no configured remote corresponds to this pull request", caught.exception.diagnostics[0].message)
        self.assertFalse(self.git.has_commit(self.head))


class PullRequestPayloadValidationTests(unittest.TestCase):
    def test_an_object_id_that_is_not_a_sha1_is_refused(self) -> None:
        for field, value in (
            ("headRefOid", "refs/heads/main:refs/heads/pwned"),
            ("baseRefOid", "--upload-pack=touch /tmp/pwned"),
            ("headRefOid", "HEAD"),
            ("baseRefOid", "a" * 39),
        ):
            with self.subTest(field=field, value=value):
                payload = pull_request_payload(
                    number=128,
                    repository="tserdeiro/consumer",
                    base_branch="main",
                    base_commit="b" * 40,
                    head_commit="c" * 40,
                )
                payload[field] = value
                with self.assertRaises(AppError) as caught:
                    pull_request_from_payload(payload, fallback_repository="tserdeiro/consumer")
                self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
                self.assertEqual(caught.exception.diagnostics[0].code, "pr_oid_invalid")

    def test_a_well_formed_payload_still_parses(self) -> None:
        payload = pull_request_payload(
            number=128,
            repository="tserdeiro/consumer",
            base_branch="main",
            base_commit="b" * 40,
            head_commit="c" * 40,
        )

        pull_request = pull_request_from_payload(payload, fallback_repository="tserdeiro/consumer")

        self.assertEqual(pull_request.head_commit, "c" * 40)


class PullRequestResolutionTests(_CandidateCase):
    def test_ordinary_pull_request(self) -> None:
        github = self.github({"pull_requests": {"128": self.payload()}})

        candidate, pull_request = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(candidate.head_commit, self.head)
        self.assertEqual(candidate.merge_base, self.base)
        self.assertEqual(candidate.base_branch, "main")
        self.assertEqual(candidate.base_commit, self.base_tip)
        self.assertEqual(candidate.base_observed_at, candidate.resolved_at)
        self.assertEqual(candidate.repository, "tserdeiro/consumer")
        self.assertEqual(candidate.candidate_id, compute_candidate_id(self.base, self.head))
        self.assertFalse(candidate.cross_repository)
        self.assertEqual(pull_request.state, "OPEN")

    def test_the_real_base_branch_wins_over_the_active_branch(self) -> None:
        # The operator sits on `feature`; the pull request's base is `main`.
        self.repository.checkout("feature")
        github = self.github({"pull_requests": {"128": self.payload()}})

        candidate, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(candidate.base_branch, "main")
        self.assertEqual(candidate.merge_base, self.base)

    def test_fork_candidate_is_marked_cross_repository(self) -> None:
        github = self.github(
            {"pull_requests": {"128": self.payload(cross_repository=True, head_repository="contributor/consumer")}}
        )

        candidate, pull_request = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertTrue(candidate.cross_repository)
        self.assertEqual(pull_request.head_repository, "contributor/consumer")

    def test_closed_pull_request_is_a_valid_historical_candidate(self) -> None:
        github = self.github({"pull_requests": {"128": self.payload(state="MERGED")}})

        candidate, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(candidate.state, "MERGED")

    def test_unknown_pull_request_is_a_candidate_failure(self) -> None:
        github = self.github({"pull_requests": {}})

        with self.assertRaises(AppError) as caught:
            resolve_from_pull_request(self.git, github, parse_selector("999"))

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)

    def test_authentication_failure_is_reported_as_such(self) -> None:
        github = self.github({"pull_requests": {"128": {"__error": "auth"}}})

        with self.assertRaises(AppError) as caught:
            resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(caught.exception.code, EXIT_AUTHENTICATION)

    def test_checkout_that_does_not_correspond_to_the_pull_request_is_rejected(self) -> None:
        self.repository.git("remote", "set-url", "origin", "git@github.com:someone-else/other-project.git")
        github = self.github({"pull_requests": {"128": self.payload()}})

        with self.assertRaises(AppError) as caught:
            resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("does not correspond", str(caught.exception))
        self.assertIn("someone-else/other-project", caught.exception.diagnostics[0].message)

    def test_repository_flag_never_exempts_the_correspondence_check(self) -> None:
        self.repository.git("remote", "set-url", "origin", "git@github.com:someone-else/other-project.git")
        github = self.github({"pull_requests": {"128": self.payload(repository="tserdeiro/consumer")}})

        with self.assertRaises(AppError) as caught:
            resolve_from_pull_request(self.git, github, parse_selector("128"), repository="tserdeiro/consumer")

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)

    def test_a_head_commit_absent_locally_names_the_fetch_command(self) -> None:
        github = self.github({"pull_requests": {"128": self.payload(head_commit="0" * 40)}})

        with self.assertRaises(AppError) as caught:
            resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertIn("git fetch origin refs/pull/128/head", caught.exception.diagnostics[0].message)

    def test_an_absent_base_commit_names_the_command_that_actually_fetches_it(self) -> None:
        # The pull refspec brings the head and says nothing about the base branch
        # tip, so printing it here would send the operator round the same loop.
        absent = "0" * 40
        github = self.github({"pull_requests": {"128": self.payload(base_commit=absent)}})

        with self.assertRaises(AppError) as caught:
            resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        message = caught.exception.diagnostics[0].message
        self.assertIn(f"git fetch origin {absent}", message)
        self.assertNotIn("refs/pull/128/head", message)

    def test_a_checkout_whose_pull_ref_contains_the_head_corresponds(self) -> None:
        # "Reachable from refs/pull/<n>/head", not "equal to": the local ref may
        # already carry a newer head than the pull request currently reports.
        self.repository.git("remote", "set-url", "origin", "git@github.com:someone-else/other-project.git")
        self.repository.checkout("feature")
        newer = self.repository.commit("src/feature.py", "value = 3\n", "newer head")
        self.repository.checkout("main")
        self.repository.git("update-ref", "refs/pull/128/head", newer)
        github = self.github({"pull_requests": {"128": self.payload()}})

        candidate, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(candidate.head_commit, self.head)
        self.assertEqual(candidate.diagnostics[0].code, "checkout_matches_pull_request")

    def test_a_new_head_is_a_new_candidate(self) -> None:
        github = self.github({"pull_requests": {"128": self.payload()}})
        first, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.repository.checkout("feature")
        second_head = self.repository.commit("src/feature.py", "value = 2\n", "more work")
        self.repository.checkout("main")
        github = self.github({"pull_requests": {"128": self.payload(head_commit=second_head)}})
        second, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertNotEqual(first.candidate_id, second.candidate_id)

    def test_a_new_merge_base_with_the_same_head_is_a_new_candidate(self) -> None:
        # The feature branch grows a second commit, then the base branch
        # fast-forwards onto the first one -- exactly what happens when part of
        # the work lands through another pull request. The head never moves, but
        # the comparison range does, so the candidate is a different one.
        self.repository.checkout("feature")
        second_head = self.repository.commit("src/feature.py", "value = 2\n", "more work")
        self.repository.checkout("main")
        self.repository.git("merge", "--no-edit", self.head)
        advanced_base = self.repository.head()

        github = self.github(
            {"pull_requests": {"128": self.payload(head_commit=second_head, base_commit=advanced_base)}}
        )
        moved, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertEqual(moved.head_commit, second_head)
        self.assertEqual(moved.merge_base, self.head)
        self.assertEqual(moved.base_commit, advanced_base)
        self.assertNotEqual(moved.candidate_id, compute_candidate_id(self.base, second_head))

    def test_base_commit_is_a_dated_observation_not_identity(self) -> None:
        github = self.github({"pull_requests": {"128": self.payload()}})
        first, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        # The base branch advances on a path that does not touch the candidate:
        # base_commit moves, the merge base does not, so the candidate is the same.
        advanced = self.repository.commit("unrelated.md", "base moves on\n", "base moves on")
        github = self.github({"pull_requests": {"128": self.payload(base_commit=advanced)}})
        second, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        self.assertNotEqual(first.base_commit, second.base_commit)
        self.assertEqual(first.merge_base, second.merge_base)
        self.assertEqual(first.candidate_id, second.candidate_id)

    def test_candidate_dict_carries_the_documented_fields(self) -> None:
        github = self.github({"pull_requests": {"128": self.payload()}})
        candidate, _ = resolve_from_pull_request(self.git, github, parse_selector("128"))

        payload = candidate.as_dict()

        self.assertEqual(
            set(payload),
            {
                "repository",
                "pr_number",
                "pr_url",
                "base_branch",
                "base_commit",
                "base_observed_at",
                "head_commit",
                "merge_base",
                "cross_repository",
                "candidate_id",
                "state",
                "selector_kind",
                "resolved_at",
            },
        )


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
