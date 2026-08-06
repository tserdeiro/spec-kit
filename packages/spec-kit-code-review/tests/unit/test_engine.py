"""Where the engine is found, and the only command allowed to install it.

Two contracts live here. The **resolution order** -- the operator's override,
then the canonical pinned path, and never ``PATH`` -- and the **installation**,
which is fail-closed: whatever cannot be verified against the lock does not stay
on disk.
"""

from __future__ import annotations

import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from spec_kit_code_review.engine import canonical_executable, install_engine, resolve_engine
from spec_kit_code_review.errors import EXIT_PREREQUISITE, AppError
from spec_kit_code_review.paths import OCR_TOOL_NAME, tool_root
from spec_kit_code_review.process import sha256_file
from tests.support.fixtures import FAKE_OCR_SOURCE, install_fake_npm, sealed_path


TAG = "v1.8.3"


class EngineCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.data_home = self.workspace / "data"
        self.bin = self.workspace / "bin"
        self.environment = {"XDG_DATA_HOME": str(self.data_home)}

    def _executable(self, path: Path, text: str = "#!/usr/bin/env sh\nexit 0\n") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def _canonical(self, **overrides) -> Path:
        return canonical_executable(TAG, {**self.environment, **overrides})

    def _path(self) -> str:
        return sealed_path(self.bin)


class ResolutionTests(EngineCase):
    def test_the_override_wins_and_is_still_guarded(self) -> None:
        override = self._executable(self.workspace / "elsewhere" / "ocr")
        self._executable(self._canonical())

        resolved = resolve_engine(tag=TAG, override=str(override), environment=self.environment)

        self.assertEqual(resolved, override.resolve())

    def test_without_an_override_the_canonical_pinned_path_is_used(self) -> None:
        canonical = self._executable(self._canonical())

        resolved = resolve_engine(tag=TAG, environment=self.environment)

        self.assertEqual(resolved, canonical.resolve())

    def test_the_canonical_path_is_the_one_for_this_tag(self) -> None:
        self._executable(canonical_executable("v1.9.0", self.environment))

        self.assertIsNone(resolve_engine(tag=TAG, environment=self.environment))

    def test_path_is_never_consulted(self) -> None:
        # The npm wrapper puts a JS shim named `ocr` on PATH whose digest is
        # never the pinned one; resolving it could only ever produce a mismatch
        # the operator has to diagnose after the fact.
        self._executable(self.bin / "ocr")

        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}, clear=False):
            self.assertIsNone(resolve_engine(tag=TAG, environment=self.environment))

    def test_an_engine_inside_the_tree_under_review_is_still_refused(self) -> None:
        repository = self.workspace / "consumer"
        planted = self._executable(repository / "tools" / "ocr")

        with self.assertRaises(AppError) as caught:
            resolve_engine(tag=TAG, override=str(planted), forbidden_roots=(repository,), environment=self.environment)

        self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)

    def test_nothing_installed_is_a_diagnosis_for_the_caller_not_an_error(self) -> None:
        self.assertIsNone(resolve_engine(tag=TAG, environment=self.environment))


class InstallTests(EngineCase):
    def setUp(self) -> None:
        super().setUp()
        self.log = self.workspace / "npm.log"
        self.digest = sha256_file(FAKE_OCR_SOURCE)

    def _npm(self, state: dict | None) -> None:
        install_fake_npm(self.bin, state)

    def _install(self, **overrides):
        with mock.patch.dict(os.environ, {"PATH": self._path()}, clear=False):
            return install_engine(
                **{
                    "tag": TAG,
                    "expected_digest": self.digest,
                    "platform": "darwin-arm64",
                    "environment": self.environment,
                    **overrides,
                }
            )

    def test_a_verified_install_stays_and_is_reported(self) -> None:
        self._npm({"binary_source": str(FAKE_OCR_SOURCE), "record_invocations": str(self.log)})

        outcome = self._install()

        self.assertEqual(outcome.path, self._canonical())
        self.assertIsNone(outcome.diagnostic)
        self.assertIn("digest verified against the lock", outcome.applied)
        self.assertTrue(self._canonical().is_file())

    def test_the_invocation_is_the_pinned_argv(self) -> None:
        self._npm({"binary_source": str(FAKE_OCR_SOURCE), "record_invocations": str(self.log)})

        self._install()

        destination = tool_root(OCR_TOOL_NAME, TAG, self.environment)
        self.assertEqual(
            self.log.read_text(encoding="utf-8").splitlines(),
            [f"install --prefix {destination} --save-exact @alibaba-group/open-code-review@1.8.3"],
        )

    def test_a_digest_mismatch_removes_the_tree_and_fails(self) -> None:
        self._npm({"binary_text": "#!/usr/bin/env sh\nexit 0\n"})

        outcome = self._install()

        self.assertIsNone(outcome.path)
        self.assertEqual(outcome.diagnostic.code, "ocr_install_digest_mismatch")
        self.assertFalse(tool_root(OCR_TOOL_NAME, TAG, self.environment).exists())

    def test_an_unpinned_platform_keeps_the_install_and_warns(self) -> None:
        # The same reading the review path gives an engine it cannot verify:
        # a lock with no digest for this platform is a warning, not a refusal.
        self._npm({"binary_source": str(FAKE_OCR_SOURCE)})

        outcome = self._install(expected_digest=None)

        self.assertTrue(self._canonical().is_file())
        self.assertEqual(outcome.diagnostic.severity, "warning")
        self.assertEqual(outcome.diagnostic.code, "ocr_install_unverified")

    def test_npm_absent_is_an_error_carrying_the_manual_command(self) -> None:
        empty = self.workspace / "empty"
        empty.mkdir()

        with mock.patch.dict(os.environ, {"PATH": str(empty)}, clear=False):
            outcome = install_engine(tag=TAG, expected_digest=self.digest, environment=self.environment)

        self.assertEqual(outcome.diagnostic.code, "npm_missing")
        self.assertIn("npm install --prefix", outcome.diagnostic.message)
        self.assertFalse(tool_root(OCR_TOOL_NAME, TAG, self.environment).exists())

    def test_a_tag_that_is_not_a_release_has_no_specifier_and_installs_nothing(self) -> None:
        self._npm({"binary_source": str(FAKE_OCR_SOURCE), "record_invocations": str(self.log)})

        outcome = self._install(tag="main")

        self.assertEqual(outcome.diagnostic.code, "ocr_install_unpinnable")
        self.assertFalse(self.log.exists())

    def test_nothing_outside_the_tools_directory_is_ever_removed(self) -> None:
        # The failure paths call `rm -rf` in Python. It is bounded to the
        # directory this module creates, and that bound is worth a test.
        from spec_kit_code_review.engine import _discard

        outside = self.workspace / "precious"
        outside.mkdir()

        _discard(outside, self.environment)

        self.assertTrue(outside.exists())


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
