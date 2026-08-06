from __future__ import annotations

import unittest

from spec_kit_code_review.errors import EXIT_CANDIDATE, AppError
from spec_kit_code_review.git import (
    MINIMUM_GIT_VERSION,
    normalize_remote_url,
    open_git,
    validate_ref_syntax,
    validate_repository_relative_path,
)
from tests.support.repo import TemporaryRepository


class RemoteUrlNormalizationTests(unittest.TestCase):
    def test_every_supported_github_form_normalizes_to_owner_name(self) -> None:
        for url in (
            "https://github.com/tserdeiro/spec-kit.git",
            "https://github.com/tserdeiro/spec-kit",
            "https://user:token@github.com/tserdeiro/spec-kit.git",
            "ssh://git@github.com/tserdeiro/spec-kit.git",
            "ssh://git@github.com:22/tserdeiro/spec-kit.git",
            "git@github.com:tserdeiro/spec-kit.git",
            "git://github.com/tserdeiro/spec-kit.git",
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_remote_url(url), "tserdeiro/spec-kit")

    def test_non_github_remotes_do_not_participate(self) -> None:
        for url in ("https://gitlab.com/tserdeiro/spec-kit.git", "git@bitbucket.org:tserdeiro/spec-kit.git", "", "   "):
            with self.subTest(url=url):
                self.assertIsNone(normalize_remote_url(url))


class ValidationTests(unittest.TestCase):
    def test_control_characters_are_rejected_in_refs(self) -> None:
        for ref in ("main\nrm -rf /", "main\x00", "\r"):
            with self.subTest(ref=ref):
                with self.assertRaises(AppError) as caught:
                    validate_ref_syntax(ref)
                self.assertEqual(caught.exception.code, EXIT_CANDIDATE)

    def test_paths_may_not_escape_the_repository(self) -> None:
        for path in ("../outside", "/etc/passwd", "a/../../b", "with\x00nul", ""):
            with self.subTest(path=path):
                with self.assertRaises(AppError) as caught:
                    validate_repository_relative_path(path)
                self.assertEqual(caught.exception.code, EXIT_CANDIDATE)

    def test_ordinary_paths_are_accepted(self) -> None:
        validate_repository_relative_path(".opencodereview/rule.json")


class GitRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.base = self.repository.commit("README.md", "base\n", "base commit")
        self.git = open_git(self.repository.path)

    def test_version_is_parsed_and_compared_against_the_engine_requirement(self) -> None:
        version = self.git.version()

        self.assertGreaterEqual(len(version.parts), 2)
        self.assertEqual(version.supported, version.parts >= MINIMUM_GIT_VERSION)

    def test_toplevel_is_resolved_from_a_subdirectory(self) -> None:
        nested = self.repository.path / "nested" / "deeper"
        nested.mkdir(parents=True)

        self.assertEqual(self.git.toplevel(nested), self.repository.path)

    def test_rev_parse_returns_the_full_sha_for_a_branch(self) -> None:
        self.assertEqual(self.git.rev_parse_commit("main"), self.base)

    def test_rev_parse_of_an_unknown_ref_is_a_candidate_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            self.git.rev_parse_commit("does-not-exist")

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)

    def test_option_shaped_refs_are_not_treated_as_options(self) -> None:
        # `--end-of-options` is what makes this a plain "unknown ref" instead of
        # git parsing the value as a flag.
        with self.assertRaises(AppError) as caught:
            self.git.rev_parse_commit("--output=/tmp/pwned")

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertFalse((self.repository.path / "tmp").exists())

    def test_merge_base_is_computed_between_two_branches(self) -> None:
        self.repository.branch("feature")
        head = self.repository.commit("feature.py", "value = 1\n", "feature work")
        self.repository.checkout("main")
        base_tip = self.repository.commit("main.py", "value = 0\n", "base advances")

        merge_base = self.git.merge_base(base_tip, head)

        self.assertEqual(merge_base, self.base)

    def test_merge_base_of_unrelated_histories_is_none(self) -> None:
        self.repository.git("checkout", "--orphan", "unrelated")
        orphan = self.repository.commit("unrelated.txt", "no shared history\n", "unrelated root commit")

        self.assertNotEqual(orphan, self.base)
        self.assertIsNone(self.git.merge_base(self.base, orphan))

    def test_status_reports_a_dirty_working_tree(self) -> None:
        self.assertTrue(self.git.is_clean())
        self.repository.dirty()

        self.assertFalse(self.git.is_clean())

    def test_tracked_paths_are_read_from_git_objects(self) -> None:
        self.repository.commit(".speckit-code-review.env", "SPECKIT_CODE_REVIEW_STRICT=true\n", "add env file")

        self.assertTrue(self.git.path_tracked_at("HEAD", ".speckit-code-review.env"))
        self.assertFalse(self.git.path_tracked_at("HEAD", "absent.txt"))
        self.assertEqual(self.git.show("HEAD", ".speckit-code-review.env"), "SPECKIT_CODE_REVIEW_STRICT=true\n")

    def test_show_reads_the_object_not_the_working_tree(self) -> None:
        self.repository.commit("file.txt", "committed\n", "add file")
        (self.repository.path / "file.txt").write_text("working tree only\n", encoding="utf-8")

        self.assertEqual(self.git.show("HEAD", "file.txt"), "committed\n")

    def test_remotes_are_normalized(self) -> None:
        self.repository.add_remote("origin", "git@github.com:tserdeiro/spec-kit.git")
        self.repository.add_remote("mirror", "https://gitlab.com/tserdeiro/spec-kit.git")

        remotes = {remote.name: remote.repository for remote in self.git.remotes()}

        self.assertEqual(remotes, {"origin": "tserdeiro/spec-kit", "mirror": None})

    def test_a_push_url_that_differs_from_the_fetch_url_is_normalized_too(self) -> None:
        self.repository.add_remote("origin", "https://example.invalid/mirror.git")
        self.repository.git("remote", "set-url", "--push", "origin", "git@github.com:tserdeiro/spec-kit.git")

        repositories = {remote.repository for remote in self.git.remotes()}

        self.assertIn("tserdeiro/spec-kit", repositories)

    def test_worktree_roots_include_the_main_worktree(self) -> None:
        self.assertIn(self.repository.path, self.git.worktree_roots())

    def test_forbidden_roots_cover_the_toplevel_and_every_worktree(self) -> None:
        extra = self.repository.path.parent / "extra-worktree"
        self.repository.git("worktree", "add", "--detach", str(extra), self.base)

        roots = self.git.forbidden_roots()

        self.assertIn(self.repository.path, roots)
        self.assertIn(extra.resolve(), roots)

    def test_is_ancestor_answers_reachability_not_equality(self) -> None:
        self.repository.branch("feature")
        head = self.repository.commit("feature.py", "value = 1\n", "feature work")

        self.assertTrue(self.git.is_ancestor(self.base, head))
        self.assertTrue(self.git.is_ancestor(head, head))
        self.assertFalse(self.git.is_ancestor(head, self.base))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
