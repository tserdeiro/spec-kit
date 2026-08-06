from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.lockfile import (
    EXTENSION_ID,
    extension_pin,
    load_lock,
    lock_path,
    platform_key,
    self_external_tool_pin,
)
from tests.support.fixtures import DEFAULT_OCR_VERSION, write_lock


class LockfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_missing_lock_is_none_not_an_error(self) -> None:
        self.assertIsNone(load_lock(lock_path(self.root)))
        self.assertIsNone(extension_pin(None))

    def test_malformed_lock_is_none_not_a_crash(self) -> None:
        lock_path(self.root).write_text("extensions:\n\tcode-review: broken\n", encoding="utf-8")

        self.assertIsNone(load_lock(lock_path(self.root)))

    def test_the_nested_external_tool_pin_is_read(self) -> None:
        write_lock(lock_path(self.root), platform_key="darwin-arm64", binary_digest="a" * 64)

        pin = extension_pin(load_lock(lock_path(self.root)))

        self.assertIsNotNone(pin)
        assert pin is not None
        self.assertEqual(pin.identifier, EXTENSION_ID)
        self.assertEqual(pin.version, "0.1.0")
        tool = pin.external_tool()
        self.assertIsNotNone(tool)
        assert tool is not None
        self.assertEqual(tool.release_tag, "v1.8.3")
        self.assertEqual(tool.version_string, DEFAULT_OCR_VERSION)
        self.assertEqual(tool.npm_package, "@alibaba-group/open-code-review")
        self.assertEqual(tool.binary_digest("darwin-arm64"), "a" * 64)
        self.assertIsNone(tool.binary_digest("linux-amd64"))

    def test_an_entry_without_external_tools_answers_none(self) -> None:
        lock_path(self.root).write_text(
            'schema_version: "1.0"\nextensions:\n  code-review:\n    id: code-review\n    version: 0.1.0\n',
            encoding="utf-8",
        )

        pin = extension_pin(load_lock(lock_path(self.root)))

        assert pin is not None
        self.assertIsNone(pin.external_tool())

    def test_an_unrelated_extension_entry_is_not_ours(self) -> None:
        lock_path(self.root).write_text(
            'schema_version: "1.0"\nextensions:\n  linear:\n    id: linear\n    version: 0.2.0\n',
            encoding="utf-8",
        )

        self.assertIsNone(extension_pin(load_lock(lock_path(self.root))))

    def test_platform_key_shape(self) -> None:
        key = platform_key()

        self.assertRegex(key, r"^[a-z0-9]+-[a-z0-9_]+$")


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()


class SelfPinTests(unittest.TestCase):
    """The pin the extension ships in its own engine.lock.yml."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_the_shipped_pin_parses_and_is_complete(self) -> None:
        pin = self_external_tool_pin()

        self.assertIsNotNone(pin)
        assert pin is not None
        self.assertEqual(pin.release_tag, "v1.8.3")
        self.assertIsNotNone(pin.npm_package)
        self.assertIsNotNone(pin.version_string)
        for key in ("darwin-arm64", "darwin-amd64", "linux-amd64", "linux-arm64"):
            self.assertRegex(pin.binaries[key], r"^[0-9a-f]{64}$")

    def test_the_shipped_pin_matches_the_distribution_lock(self) -> None:
        # Drift guard: the file the extension ships and the source
        # repository's own lock must pin the same engine.
        distribution_lock = Path(__file__).resolve().parents[4] / "versions.lock.yml"
        if not distribution_lock.is_file():
            self.skipTest("not running inside the source repository")
        entry = extension_pin(load_lock(distribution_lock))
        assert entry is not None
        lock_pin = entry.external_tool()
        assert lock_pin is not None

        shipped = self_external_tool_pin()
        assert shipped is not None
        self.assertEqual(shipped.values, lock_pin.values)

    def test_a_consumer_root_lock_wins_over_the_shipped_pin(self) -> None:
        from spec_kit_code_review.doctor import external_tool_pin

        write_lock(lock_path(self.root), platform_key="darwin-arm64", binary_digest="b" * 64)
        pin = external_tool_pin(self.root)
        assert pin is not None
        self.assertEqual(pin.binary_digest("darwin-arm64"), "b" * 64)

    def test_a_consumer_without_a_lock_falls_back_to_the_shipped_pin(self) -> None:
        from spec_kit_code_review.doctor import external_tool_pin

        pin = external_tool_pin(self.root)
        assert pin is not None
        self.assertEqual(pin.release_tag, "v1.8.3")
