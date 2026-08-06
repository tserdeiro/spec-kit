from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.budget import compute, compute_working_tree, is_executable_path
from spec_kit_code_review.errors import EXIT_CANDIDATE, AppError
from spec_kit_code_review.git import open_git
from tests.support.repo import TemporaryRepository


class ClassificationTests(unittest.TestCase):
    def test_source_tests_and_migrations_count(self) -> None:
        for path in ("src/module.py", "tests/test_module.py", "migrations/0001_initial.sql", "scripts/deploy.sh"):
            with self.subTest(path=path):
                self.assertTrue(is_executable_path(path))

    def test_documentation_lockfiles_and_images_do_not(self) -> None:
        for path in ("docs/guide.md", "uv.lock", "packages/a/uv.lock", "logo.svg", "notes.txt", "a/b.png"):
            with self.subTest(path=path):
                self.assertFalse(is_executable_path(path))


class BudgetCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = TemporaryRepository(Path(self.temporary.name) / "consumer")
        self.addCleanup(self.repository.cleanup)
        self.base = self.repository.commit("README.md", "base\n", "base commit")
        self.git = open_git(self.repository.path)


class ComputeTests(BudgetCase):
    def test_only_executable_lines_are_counted(self) -> None:
        self.repository.branch("feature")
        self.repository.write("src/module.py", "\n".join(f"line_{index} = {index}" for index in range(10)) + "\n")
        self.repository.write("docs/guide.md", "\n".join(f"paragraph {index}" for index in range(50)) + "\n")
        self.repository.git("add", "-A")
        self.repository.git("commit", "-m", "work")
        head = self.repository.head()

        report = compute(self.git, merge_base=self.base, head_commit=head)

        self.assertEqual(report.counted, 10)
        self.assertFalse(report.over_budget)
        self.assertEqual(report.diagnostics, [])
        paths = {entry.path: entry for entry in report.entries}
        self.assertEqual(paths["docs/guide.md"].counted, 0)
        self.assertEqual(paths["src/module.py"].counted, 10)

    def test_over_budget_warns_and_suggests_stacked_pull_requests(self) -> None:
        self.repository.branch("feature")
        self.repository.commit("src/big.py", "\n".join(f"x{index} = {index}" for index in range(20)) + "\n", "big")
        head = self.repository.head()

        report = compute(self.git, merge_base=self.base, head_commit=head, limit=5)

        self.assertTrue(report.over_budget)
        self.assertEqual(report.counted, 20)
        self.assertEqual([item.code for item in report.diagnostics], ["budget_exceeded"])
        self.assertEqual(report.diagnostics[0].severity, "warning")
        self.assertIn("stacked pull requests", report.diagnostics[0].message)
        # Never a failure: accepting a large pull request is a human decision.
        self.assertEqual(report.as_dict()["over_budget"], True)

    def test_a_binary_contributes_nothing_and_is_still_reported(self) -> None:
        self.repository.branch("feature")
        (self.repository.path / "assets").mkdir()
        (self.repository.path / "assets" / "logo.bin").write_bytes(bytes(range(256)) * 4)
        self.repository.git("add", "-A")
        self.repository.git("commit", "-m", "binary")
        head = self.repository.head()

        report = compute(self.git, merge_base=self.base, head_commit=head)

        entry = next(item for item in report.entries if item.path == "assets/logo.bin")
        self.assertTrue(entry.binary)
        self.assertEqual(entry.counted, 0)
        self.assertIsNone(entry.added)

    def test_a_pure_rename_authors_no_lines(self) -> None:
        self.repository.commit("src/module.py", "\n".join(f"value_{index} = {index}" for index in range(30)) + "\n", "seed")
        base = self.repository.head()
        self.repository.branch("feature")
        self.repository.git("mv", "src/module.py", "src/renamed.py")
        self.repository.git("commit", "-m", "rename")
        head = self.repository.head()

        report = compute(self.git, merge_base=base, head_commit=head)

        self.assertEqual(report.counted, 0)

    def test_an_unreadable_range_is_exit_six(self) -> None:
        with self.assertRaises(AppError) as caught:
            compute(self.git, merge_base=self.base, head_commit="0" * 40)

        self.assertEqual(caught.exception.code, EXIT_CANDIDATE)
        self.assertEqual(caught.exception.diagnostics[0].code, "numstat_unreadable")


class WorkingTreeTests(BudgetCase):
    def test_uncommitted_and_untracked_content_both_count(self) -> None:
        self.repository.write("README.md", "base\nmore documentation\n")
        self.repository.write("src/new.py", "a = 1\nb = 2\nc = 3\n")

        report = compute_working_tree(self.git, self.repository.path)

        paths = {entry.path: entry for entry in report.entries}
        self.assertEqual(paths["src/new.py"].counted, 3)
        self.assertEqual(paths["README.md"].counted, 0)
        self.assertEqual(report.counted, 3)

    def test_reading_the_working_tree_never_writes_to_the_index(self) -> None:
        index = self.repository.path / ".git" / "index"
        self.repository.write("src/new.py", "a = 1\n")
        before = index.stat().st_mtime_ns

        compute_working_tree(self.git, self.repository.path)

        self.assertEqual(index.stat().st_mtime_ns, before)

    def test_an_untracked_binary_is_reported_without_counting(self) -> None:
        (self.repository.path / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)

        report = compute_working_tree(self.git, self.repository.path)

        entry = next(item for item in report.entries if item.path == "blob.bin")
        self.assertTrue(entry.binary)
        self.assertEqual(entry.counted, 0)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
