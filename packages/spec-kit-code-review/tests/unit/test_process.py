from __future__ import annotations

import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.errors import EXIT_ENGINE, EXIT_PREREQUISITE, AppError
from spec_kit_code_review.process import resolve_executable, run_command, sha256_file, sha256_text


class RunCommandTests(unittest.TestCase):
    def test_captures_output_without_a_shell(self) -> None:
        result = run_command(["/bin/sh", "-c", "printf 'out'; printf 'err' >&2; exit 3"])

        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "out")
        self.assertEqual(result.stderr, "err")
        self.assertFalse(result.ok)

    def test_arguments_are_never_expanded_by_a_shell(self) -> None:
        result = run_command(["/bin/echo", "$HOME; rm -rf /"])

        self.assertEqual(result.stdout.strip(), "$HOME; rm -rf /")

    def test_missing_executable_is_a_prerequisite_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            run_command(["/nonexistent/spec-kit-code-review-binary"])

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)

    def test_timeout_is_an_engine_failure_naming_the_invocation(self) -> None:
        with self.assertRaises(AppError) as caught:
            run_command(["/bin/sh", "-c", "sleep 5"], timeout=1)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("timed out", str(caught.exception))
        self.assertTrue(caught.exception.retryable)


class ResolveExecutableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def _executable(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_absent_executable_is_none_not_an_error(self) -> None:
        self.assertIsNone(resolve_executable("spec-kit-code-review-absent-binary"))

    def test_override_is_resolved_to_an_absolute_path(self) -> None:
        target = self._executable(self.root / "bin" / "ocr")

        resolved = resolve_executable("ocr", override=str(target))

        self.assertEqual(resolved, target.resolve())

    def test_executable_inside_the_candidate_tree_is_rejected(self) -> None:
        repository = self.root / "repository"
        target = self._executable(repository / "tools" / "ocr")

        with self.assertRaises(AppError) as caught:
            resolve_executable("ocr", override=str(target), forbidden_roots=(repository,))

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)
        self.assertIn("inside the repository under review", str(caught.exception))

    def test_symlink_into_the_candidate_tree_is_rejected(self) -> None:
        repository = self.root / "repository"
        target = self._executable(repository / "tools" / "ocr")
        link = self.root / "outside-ocr"
        link.symlink_to(target)

        with self.assertRaises(AppError) as caught:
            resolve_executable("ocr", override=str(link), forbidden_roots=(repository,))

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)

    def test_missing_override_is_a_prerequisite_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            resolve_executable("ocr", override=str(self.root / "absent"))

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)

    def test_non_executable_override_is_rejected(self) -> None:
        target = self.root / "not-executable"
        target.write_text("", encoding="utf-8")
        target.chmod(0o600)

        with self.assertRaises(AppError) as caught:
            resolve_executable("ocr", override=str(target))

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)


class DigestTests(unittest.TestCase):
    def test_text_digest_is_stable(self) -> None:
        self.assertEqual(
            sha256_text("candidate\n"),
            "1e81270f1a47dce22a2e4985250c74b2e3374443734f1492b03ea2cd2af4ec48",
        )

    def test_file_digest_matches_text_digest(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "file.txt"
            path.write_text("candidate\n", encoding="utf-8")

            self.assertEqual(sha256_file(path), sha256_text("candidate\n"))

    def test_digest_of_a_directory_is_none(self) -> None:
        with TemporaryDirectory() as directory:
            self.assertIsNone(sha256_file(Path(directory)))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
