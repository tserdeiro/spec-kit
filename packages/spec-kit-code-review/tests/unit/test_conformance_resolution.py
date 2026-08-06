"""How the conformance capture finds the engine, and when it declines to run.

This is the logic that decides whether the *prerequisite* is satisfied on a
given machine. It gets its own test because reverting it is cheap and the
consequence is expensive in both directions: a suite that goes red on a machine
carrying a newer engine says the package is broken when it is not, and a capture
that silently runs against the wrong version says the pin is verified when it is
not.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.conformance.test_real_ocr import PINNED_TAG, resolve_pinned_engine


PINNED_OUTPUT = "open-code-review v1.8.3 (80a579466) darwin/arm64"
NEWER_OUTPUT = "open-code-review v1.8.5 (582953937) darwin/arm64"


class ResolutionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.versions: dict[str, str] = {}

    def _binary(self, relative: str, version: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
        self.versions[str(path)] = version
        return path

    def _canonical(self, version: str = PINNED_OUTPUT) -> Path:
        # The layout `paths.tool_executable` prescribes, under a data root this
        # test owns.
        from spec_kit_code_review.paths import tool_executable

        target = tool_executable("ocr", PINNED_TAG, {"XDG_DATA_HOME": str(self.root / "data")})
        relative = target.relative_to(self.root)
        return self._binary(str(relative), version)

    def _resolve(self, *, environment=None, on_path=None):
        return resolve_pinned_engine(
            environment={"XDG_DATA_HOME": str(self.root / "data"), **(environment or {})},
            which=lambda _name: str(on_path) if on_path else None,
            version_of=lambda executable: self.versions.get(executable, ""),
        )


class OrderTests(ResolutionCase):
    def test_the_override_wins_over_everything(self) -> None:
        override = self._binary("override/ocr", PINNED_OUTPUT)
        self._canonical()
        on_path = self._binary("path/ocr", PINNED_OUTPUT)

        resolution = self._resolve(
            environment={"SPECKIT_CODE_REVIEW_OCR_BIN": str(override)}, on_path=on_path
        )

        self.assertTrue(resolution.usable)
        self.assertEqual(resolution.path, str(override))
        self.assertEqual(resolution.source, "SPECKIT_CODE_REVIEW_OCR_BIN")

    def test_the_canonical_location_wins_over_path(self) -> None:
        # The case this machine actually presents: a newer engine on PATH and
        # the pinned one installed where this distribution puts it.
        canonical = self._canonical()
        on_path = self._binary("path/ocr", NEWER_OUTPUT)

        resolution = self._resolve(on_path=on_path)

        self.assertTrue(resolution.usable)
        self.assertEqual(resolution.path, str(canonical))
        self.assertEqual(resolution.source, "the canonical pinned location")

    def test_path_is_used_when_it_is_the_pinned_version(self) -> None:
        on_path = self._binary("path/ocr", PINNED_OUTPUT)

        resolution = self._resolve(on_path=on_path)

        self.assertTrue(resolution.usable)
        self.assertEqual(resolution.source, "PATH")


class RefusalTests(ResolutionCase):
    def test_a_different_version_is_skipped_with_the_reason_not_failed(self) -> None:
        on_path = self._binary("path/ocr", NEWER_OUTPUT)

        resolution = self._resolve(on_path=on_path)

        self.assertFalse(resolution.usable)
        self.assertIsNone(resolution.path)
        # What was found, where, and what was expected -- all three.
        self.assertIn("v1.8.5", resolution.problem)
        self.assertIn(str(on_path), resolution.problem)
        self.assertIn(PINNED_TAG, resolution.problem)

    def test_a_different_version_in_the_override_is_also_refused(self) -> None:
        override = self._binary("override/ocr", NEWER_OUTPUT)

        resolution = self._resolve(environment={"SPECKIT_CODE_REVIEW_OCR_BIN": str(override)})

        self.assertFalse(resolution.usable)
        self.assertIn("SPECKIT_CODE_REVIEW_OCR_BIN", resolution.problem)
        self.assertIn("v1.8.5", resolution.problem)

    def test_an_override_pointing_nowhere_says_so(self) -> None:
        resolution = self._resolve(
            environment={"SPECKIT_CODE_REVIEW_OCR_BIN": str(self.root / "absent" / "ocr")}
        )

        self.assertFalse(resolution.usable)
        self.assertIn("is not a file", resolution.problem)

    def test_nothing_installed_at_all_says_that_instead(self) -> None:
        resolution = self._resolve()

        self.assertFalse(resolution.usable)
        self.assertIn("is not installed", resolution.problem)
        self.assertIn(PINNED_TAG, resolution.problem)

    def test_a_newer_engine_on_path_falls_back_to_the_canonical_one(self) -> None:
        # Order matters more than any single check: the canonical location is
        # consulted before PATH, so a machine with both is not penalised for the
        # one it did not choose.
        canonical = self._canonical()
        on_path = self._binary("path/ocr", NEWER_OUTPUT)

        resolution = self._resolve(on_path=on_path)

        self.assertEqual(resolution.path, str(canonical))
        self.assertIsNone(resolution.problem)

    def test_an_unreadable_engine_reports_rather_than_raising(self) -> None:
        # `--version` failing is not a crash of the suite: it is one more way
        # the prerequisite can be unmet.
        on_path = self._binary("path/ocr", "")

        resolution = self._resolve(on_path=on_path)

        self.assertFalse(resolution.usable)
        self.assertIn(str(on_path), resolution.problem)


class SkipMessageTests(unittest.TestCase):
    def test_the_module_level_skip_reason_names_the_prerequisite(self) -> None:
        from tests.conformance.test_real_ocr import SKIP_REASON

        self.assertIn("PREREQUISITE", SKIP_REASON)
        self.assertIn("doctor --fix", SKIP_REASON)
        # And it never suggests the shim, which would fail the digest check.
        self.assertIn("not at the JS shim", SKIP_REASON)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
