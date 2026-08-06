from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review import env_files
from spec_kit_code_review.env_files import (
    ENV_PREFIX,
    EXECUTABLE_OVERRIDE_KEYS,
    REPO_ENV_FILENAME,
    assert_repo_env_not_tracked,
    load_env_files,
)
from spec_kit_code_review.errors import EXIT_CONFIGURATION, AppError
from tests.support.fixtures import isolate_operator_global_env


class EnvFileTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _repo_env(self, text: str) -> Path:
        path = self.root / REPO_ENV_FILENAME
        path.write_text(text, encoding="utf-8")
        return path

    def _operator_env(self, text: str) -> Path:
        path = self.root / "operator-env"
        path.write_text(text, encoding="utf-8")
        env_files.set_operator_env_override(path)
        self.addCleanup(env_files.set_operator_env_override, None)
        return path

    def test_the_operator_file_is_read_from_the_configured_xdg_root(self) -> None:
        # The wiring itself, not only the parsing: with the override cleared,
        # `XDG_CONFIG_HOME` decides which file is read.
        env_files.set_operator_env_override(None)
        self.addCleanup(
            env_files.set_operator_env_override, Path(tempfile.gettempdir()) / "spec-kit-code-review-tests-no-global-env"
        )
        configured = self.root / "cfg"
        operator_file = configured / "tserdeiro" / "spec-kit" / "env"
        operator_file.parent.mkdir(parents=True, exist_ok=True)
        operator_file.write_text("SPECKIT_CODE_REVIEW_OCR_BIN=/opt/ocr\n", encoding="utf-8")

        snapshot = load_env_files(self.root, {"XDG_CONFIG_HOME": str(configured)})

        self.assertEqual(snapshot.executable_override("SPECKIT_CODE_REVIEW_OCR_BIN"), "/opt/ocr")
        self.assertEqual(env_files.operator_env_file({"XDG_CONFIG_HOME": str(configured)}), operator_file)

    def test_a_relative_config_root_is_ignored_rather_than_trusted(self) -> None:
        # A relative XDG_CONFIG_HOME resolves against the working directory,
        # which during a review is the repository under review -- so honouring
        # it would put the *trusted* source of executable paths inside the tree
        # the candidate controls.
        env_files.set_operator_env_override(None)
        self.addCleanup(
            env_files.set_operator_env_override, Path(tempfile.gettempdir()) / "spec-kit-code-review-tests-no-global-env"
        )
        planted = self.root / "relcfg" / "tserdeiro" / "spec-kit" / "env"
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("SPECKIT_CODE_REVIEW_OCR_BIN=/candidate/ocr\n", encoding="utf-8")
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

        resolved = env_files.operator_env_file({"XDG_CONFIG_HOME": "relcfg"})
        snapshot = load_env_files(self.root, {"XDG_CONFIG_HOME": "relcfg"})

        self.assertTrue(resolved.is_absolute())
        self.assertNotEqual(resolved, planted)
        self.assertIsNone(snapshot.executable_override("SPECKIT_CODE_REVIEW_OCR_BIN"))

    def test_the_prefix_is_the_documented_one(self) -> None:
        self.assertEqual(ENV_PREFIX, "SPECKIT_CODE_REVIEW_")
        self.assertEqual(REPO_ENV_FILENAME, ".speckit-code-review.env")

    def test_only_prefixed_keys_are_loaded(self) -> None:
        self._repo_env(
            "SPECKIT_CODE_REVIEW_LOG_LEVEL=debug\n"
            "GITHUB_TOKEN=ghp_should_never_be_read\n"
            "PATH=/never/touched\n"
        )

        snapshot = load_env_files(self.root, {})

        self.assertEqual(snapshot.values, {"SPECKIT_CODE_REVIEW_LOG_LEVEL": "debug"})

    def test_the_real_process_environment_always_wins(self) -> None:
        self._repo_env("SPECKIT_CODE_REVIEW_LOG_LEVEL=from-repo\n")
        self._operator_env("SPECKIT_CODE_REVIEW_LOG_LEVEL=from-operator\n")

        snapshot = load_env_files(self.root, {"SPECKIT_CODE_REVIEW_LOG_LEVEL": "from-process"})

        self.assertEqual(snapshot.get("SPECKIT_CODE_REVIEW_LOG_LEVEL"), "from-process")

    def test_the_operator_file_wins_over_the_repository_file(self) -> None:
        self._repo_env("SPECKIT_CODE_REVIEW_LOG_LEVEL=from-repo\n")
        self._operator_env("SPECKIT_CODE_REVIEW_LOG_LEVEL=from-operator\n")

        snapshot = load_env_files(self.root, {})

        self.assertEqual(snapshot.get("SPECKIT_CODE_REVIEW_LOG_LEVEL"), "from-operator")

    def test_the_repository_file_can_never_define_an_executable_path(self) -> None:
        self._repo_env(
            "SPECKIT_CODE_REVIEW_OCR_BIN=./tools/evil-ocr\n"
            "SPECKIT_CODE_REVIEW_GH_BIN=./tools/evil-gh\n"
            "SPECKIT_CODE_REVIEW_LOG_LEVEL=debug\n"
        )

        snapshot = load_env_files(self.root, {})

        for key in EXECUTABLE_OVERRIDE_KEYS:
            self.assertIsNone(snapshot.get(key))
            self.assertIsNone(snapshot.executable_override(key))
        self.assertEqual(snapshot.get("SPECKIT_CODE_REVIEW_LOG_LEVEL"), "debug")
        warnings = [item for item in snapshot.diagnostics if item.code == "env_file_executable_override_ignored"]
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(item.severity == "warning" for item in warnings))

    def test_the_operator_file_may_define_an_executable_path(self) -> None:
        self._operator_env("SPECKIT_CODE_REVIEW_OCR_BIN=/opt/ocr\n")

        snapshot = load_env_files(self.root, {})

        self.assertEqual(snapshot.executable_override("SPECKIT_CODE_REVIEW_OCR_BIN"), "/opt/ocr")

    def test_the_process_environment_may_define_an_executable_path(self) -> None:
        snapshot = load_env_files(self.root, {"SPECKIT_CODE_REVIEW_OCR_BIN": "/opt/ocr"})

        self.assertEqual(snapshot.executable_override("SPECKIT_CODE_REVIEW_OCR_BIN"), "/opt/ocr")

    def test_malformed_lines_are_diagnostics_not_crashes(self) -> None:
        self._repo_env("this is not an assignment\n1BAD=value\nSPECKIT_CODE_REVIEW_LOG_LEVEL=debug\n")

        snapshot = load_env_files(self.root, {})

        self.assertEqual(snapshot.get("SPECKIT_CODE_REVIEW_LOG_LEVEL"), "debug")
        self.assertEqual(len([item for item in snapshot.diagnostics if item.code == "env_file_malformed"]), 2)

    def test_quotes_are_stripped_and_nothing_is_interpolated(self) -> None:
        self._repo_env('SPECKIT_CODE_REVIEW_LOG_LEVEL="$HOME/debug"\n')

        snapshot = load_env_files(self.root, {})

        self.assertEqual(snapshot.get("SPECKIT_CODE_REVIEW_LOG_LEVEL"), "$HOME/debug")

    def test_no_value_is_ever_written_back_into_the_process_environment(self) -> None:
        import os

        self._repo_env("SPECKIT_CODE_REVIEW_LOG_LEVEL=debug\n")

        load_env_files(self.root, {})

        self.assertIsNone(os.environ.get("SPECKIT_CODE_REVIEW_LOG_LEVEL"))

    def test_a_repository_env_file_tracked_in_the_candidate_head_rejects_the_session(self) -> None:
        with self.assertRaises(AppError) as caught:
            assert_repo_env_not_tracked(True, ref="deadbeef", root=self.root)

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)
        self.assertIn(REPO_ENV_FILENAME, str(caught.exception))

    def test_an_untracked_repository_env_file_is_accepted(self) -> None:
        assert_repo_env_not_tracked(False, ref="deadbeef", root=self.root)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
