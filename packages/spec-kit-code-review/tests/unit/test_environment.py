from __future__ import annotations

import os
import signal
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.environment import (
    FORBIDDEN_GIT_WRITES,
    PERMITTED_GIT_WRITES,
    SignalInterrupt,
    prepare,
    prepared_environment,
    restore,
)
from spec_kit_code_review.errors import EXIT_ENVIRONMENT, EXIT_USAGE, AppError
from spec_kit_code_review.git import open_git
from spec_kit_code_review.process import resolve_executable
from tests.support.repo import TemporaryRepository


class EnvironmentCase(unittest.TestCase):
    """A repository with a base branch, a feature head, and an evidence root."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.evidence = self.workspace / "evidence"
        self.evidence.mkdir()

        self.repository = TemporaryRepository(self.workspace / "consumer")
        self.addCleanup(self.repository.cleanup)
        self.base = self.repository.commit("README.md", "base\n", "base commit")
        self.repository.branch("feature")
        self.head = self.repository.commit("src/feature.py", "value = 1\n", "feature work")
        self.repository.checkout("main")
        self.root = self.repository.path
        self.git = open_git(self.root)

    def addCleanupWorktree(self, prepared) -> None:
        def _cleanup() -> None:
            if prepared.worktree_path and prepared.worktree_path.exists():
                self.git.run("worktree", "remove", "--force", str(prepared.worktree_path))

        self.addCleanup(_cleanup)


class PreparationTests(EnvironmentCase):
    def test_the_operators_work_in_progress_is_untouched(self) -> None:
        self.repository.write("README.md", "edited by the operator\n")
        self.repository.write("scratch.txt", "untracked notes\n")
        self.repository.git("add", "README.md")
        status_before = self.repository.git("status", "--porcelain")
        branch_before = self.repository.git("rev-parse", "--abbrev-ref", "HEAD")

        prepared = prepare(self.git, head_commit=self.head, worktree_parent=self.evidence)
        self.addCleanupWorktree(prepared)

        self.assertTrue(prepared.worktree_path.is_dir())
        self.assertEqual((prepared.worktree_path / "src" / "feature.py").read_text(encoding="utf-8"), "value = 1\n")
        self.assertEqual(self.repository.git("status", "--porcelain"), status_before)
        self.assertEqual(self.repository.git("rev-parse", "--abbrev-ref", "HEAD"), branch_before)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "edited by the operator\n")
        self.assertTrue((self.root / "scratch.txt").is_file())

    def test_the_working_root_is_the_worktree(self) -> None:
        prepared = prepare(self.git, head_commit=self.head, worktree_parent=self.evidence)
        self.addCleanupWorktree(prepared)

        self.assertEqual(prepared.working_root, prepared.worktree_path)
        self.assertEqual(prepared.repository_root, self.root)
        self.assertEqual(prepared.as_dict()["worktree_path"], str(prepared.worktree_path))

    def test_a_clean_worktree_is_withdrawn(self) -> None:
        prepared = prepare(self.git, head_commit=self.head, worktree_parent=self.evidence)
        path = prepared.worktree_path

        outcome = restore(prepared)

        self.assertTrue(outcome.restored)
        self.assertFalse(path.exists())
        self.assertNotIn(path, self.git.worktree_roots())

    def test_a_worktree_holding_uncommitted_content_is_kept_and_reported(self) -> None:
        prepared = prepare(self.git, head_commit=self.head, worktree_parent=self.evidence)
        self.addCleanupWorktree(prepared)
        (prepared.worktree_path / "verification-output.txt").write_text("left behind\n", encoding="utf-8")

        outcome = restore(prepared)

        self.assertFalse(outcome.restored)
        self.assertEqual(outcome.code, EXIT_ENVIRONMENT)
        self.assertEqual(outcome.retained_worktree, prepared.worktree_path)
        self.assertTrue(prepared.worktree_path.is_dir())
        message = outcome.diagnostics[0].message
        self.assertIn(f"git worktree remove {prepared.worktree_path}", message)
        self.assertIn("git worktree prune", message)

    def test_a_worktree_is_never_created_inside_the_repository(self) -> None:
        with self.assertRaises(AppError) as caught:
            prepare(self.git, head_commit=self.head, worktree_parent=self.root / ".specify" / "review")

        self.assertEqual(caught.exception.code, EXIT_USAGE)
        self.assertEqual(caught.exception.diagnostics[0].code, "worktree_inside_repository")

    def test_the_materialized_worktree_joins_the_forbidden_executable_roots(self) -> None:
        # The tree that was just materialized is candidate content too.
        prepared = prepare(
            self.git,
            head_commit=self.head,
            worktree_parent=self.evidence,
            forbidden_roots=(self.root,),
        )
        self.addCleanupWorktree(prepared)
        planted = prepared.worktree_path / "ocr"
        planted.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        planted.chmod(planted.stat().st_mode | stat.S_IXUSR)

        self.assertIn(prepared.worktree_path, prepared.forbidden_roots)
        with self.assertRaises(AppError) as caught:
            resolve_executable("ocr", override=str(planted), forbidden_roots=prepared.forbidden_roots)
        self.assertEqual(caught.exception.diagnostics[0].code, "executable_inside_candidate")

    def test_a_worktree_already_removed_by_hand_is_detected_not_forced(self) -> None:
        prepared = prepare(self.git, head_commit=self.head, worktree_parent=self.evidence)
        self.git.run("worktree", "remove", "--force", str(prepared.worktree_path))

        outcome = restore(prepared)

        self.assertTrue(outcome.restored)
        self.assertTrue(outcome.already_restored)
        self.assertIn("git worktree prune", outcome.diagnostics[0].message)


class GitWriteContractTests(EnvironmentCase):
    """The enumerated ``.git`` writes, asserted behaviourally rather than by comment."""

    def _config_digest(self) -> str:
        return (self.root / ".git" / "config").read_text(encoding="utf-8")

    def test_the_enumeration_is_explicit_in_the_module(self) -> None:
        self.assertTrue(any("worktree metadata" in entry for entry in PERMITTED_GIT_WRITES))
        self.assertTrue(any("bounded fetch" in entry for entry in PERMITTED_GIT_WRITES))
        self.assertTrue(any("local refs" in entry for entry in FORBIDDEN_GIT_WRITES))
        self.assertTrue(any("stash" in entry for entry in FORBIDDEN_GIT_WRITES))
        self.assertTrue(any("operator's own checkout" in entry for entry in FORBIDDEN_GIT_WRITES))

    def test_a_worktree_cycle_leaves_no_metadata_behind(self) -> None:
        refs_before = self.git.local_refs()
        config_before = self._config_digest()
        head_before = self.repository.head()

        prepared = prepare(self.git, head_commit=self.head, worktree_parent=self.evidence)
        self.addCleanupWorktree(prepared)
        self.assertTrue((self.root / ".git" / "worktrees").is_dir())

        restore(prepared)

        self.assertEqual(self.git.local_refs(), refs_before)
        self.assertEqual(self._config_digest(), config_before)
        self.assertEqual(self.git.worktree_roots(), [self.root])
        self.assertEqual(self.repository.git("stash", "list"), "")
        self.assertEqual(self.repository.head(), head_before)


class RestorationGuaranteeTests(EnvironmentCase):
    def test_an_exception_inside_the_block_withdraws_the_environment(self) -> None:
        class Boom(RuntimeError):
            pass

        with self.assertRaises(Boom):
            with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence) as prepared:
                self.assertTrue(prepared.worktree_path.is_dir())
                raise Boom("something failed after the environment was prepared")

        self.assertEqual(self.git.worktree_roots(), [self.root])

    def test_a_real_sigint_withdraws_the_environment(self) -> None:
        # A real signal, delivered to this process while the environment is
        # prepared -- not a simulated call to the handler.
        with self.assertRaises((KeyboardInterrupt, SignalInterrupt)):
            with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence):
                os.kill(os.getpid(), signal.SIGINT)

        self.assertEqual(self.git.worktree_roots(), [self.root])

    def test_a_real_sigterm_withdraws_the_environment(self) -> None:
        with self.assertRaises(SignalInterrupt):
            with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence):
                os.kill(os.getpid(), signal.SIGTERM)

        self.assertEqual(self.git.worktree_roots(), [self.root])

    def test_the_previous_signal_handlers_are_restored(self) -> None:
        original = signal.getsignal(signal.SIGINT)

        with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence) as prepared:
            self.assertNotEqual(signal.getsignal(signal.SIGINT), original)
        restore(prepared)

        self.assertEqual(signal.getsignal(signal.SIGINT), original)

    def test_a_failed_withdrawal_during_an_exception_becomes_exit_seven(self) -> None:
        with self.assertRaises(AppError) as caught:
            with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence) as prepared:
                self.addCleanupWorktree(prepared)
                (prepared.worktree_path / "left-behind.txt").write_text("work\n", encoding="utf-8")
                raise RuntimeError("the review failed")

        self.assertEqual(caught.exception.code, EXIT_ENVIRONMENT)
        self.assertEqual(caught.exception.diagnostics[0].code, "worktree_retained")

    def test_a_successful_first_phase_leaves_the_environment_prepared_on_purpose(self) -> None:
        with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence) as prepared:
            pass

        self.assertTrue(prepared.worktree_path.is_dir())
        restore(prepared)
        self.assertEqual(self.git.worktree_roots(), [self.root])

    def test_a_signal_during_the_materialization_itself_withdraws(self) -> None:
        # The worktree creation happens *inside* the guard, so an interruption in
        # the middle of it still finds a restorable record.
        original_add = type(self.git).worktree_add

        def signalling_add(instance, path, commit):
            result = original_add(instance, path, commit)
            os.kill(os.getpid(), signal.SIGINT)
            return result

        type(self.git).worktree_add = signalling_add
        self.addCleanup(setattr, type(self.git), "worktree_add", original_add)

        with self.assertRaises((KeyboardInterrupt, SignalInterrupt)):
            with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence):
                raise AssertionError("the body must never run: the signal arrives during preparation")

        self.assertEqual(self.git.worktree_roots(), [self.root])

    def test_a_second_signal_during_the_withdrawal_cannot_escape_it(self) -> None:
        # A second Ctrl-C while the cleanup block runs must not leave the
        # environment half withdrawn.
        original_remove = type(self.git).worktree_remove

        def signalling_remove(instance, path):
            os.kill(os.getpid(), signal.SIGINT)
            return original_remove(instance, path)

        type(self.git).worktree_remove = signalling_remove
        self.addCleanup(setattr, type(self.git), "worktree_remove", original_remove)

        with self.assertRaises((KeyboardInterrupt, SignalInterrupt)):
            with prepared_environment(self.git, head_commit=self.head, worktree_parent=self.evidence):
                os.kill(os.getpid(), signal.SIGINT)

        self.assertEqual(self.git.worktree_roots(), [self.root])


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
