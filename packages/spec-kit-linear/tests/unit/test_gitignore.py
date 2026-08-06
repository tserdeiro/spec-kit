from __future__ import annotations

import unittest

from tests.support.fixtures import isolate_operator_global_env
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_linear.gitignore import ensure_entries


class GitignoreTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / ".gitignore"

    def test_creates_file_when_absent(self) -> None:
        added = ensure_entries(self.path, (".speckit-linear.env", "speckit-linear.local.yml"))

        self.assertEqual(added, [".speckit-linear.env", "speckit-linear.local.yml"])
        content = self.path.read_text(encoding="utf-8")
        self.assertIn(".speckit-linear.env", content)
        self.assertIn("speckit-linear.local.yml", content)

    def test_never_touches_the_committed_shared_config_entry(self) -> None:
        # onboard/install must never gitignore the shared speckit-linear.yml
        # itself in a consumer repository -- it is committed by default.
        added = ensure_entries(self.path, (".speckit-linear.env", "speckit-linear.local.yml"))

        content = self.path.read_text(encoding="utf-8")
        self.assertNotIn("speckit-linear.yml\n", content.replace("speckit-linear.local.yml", ""))
        self.assertEqual(added, [".speckit-linear.env", "speckit-linear.local.yml"])

    def test_preserves_existing_content_and_appends_only_missing_entries(self) -> None:
        self.path.write_text("node_modules/\n.speckit-linear.env\n", encoding="utf-8")

        added = ensure_entries(self.path, (".speckit-linear.env", "speckit-linear.local.yml"))

        self.assertEqual(added, ["speckit-linear.local.yml"])
        content = self.path.read_text(encoding="utf-8")
        self.assertIn("node_modules/", content)
        self.assertEqual(content.count(".speckit-linear.env"), 1)
        self.assertIn("speckit-linear.local.yml", content)

    def test_is_idempotent_across_repeated_calls(self) -> None:
        ensure_entries(self.path, (".speckit-linear.env", "speckit-linear.local.yml"))
        first_content = self.path.read_text(encoding="utf-8")

        added_second_time = ensure_entries(self.path, (".speckit-linear.env", "speckit-linear.local.yml"))

        self.assertEqual(added_second_time, [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), first_content)

    def test_handles_file_without_trailing_newline(self) -> None:
        self.path.write_text("node_modules/", encoding="utf-8")

        ensure_entries(self.path, (".speckit-linear.env",))

        content = self.path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("node_modules/\n"))
        self.assertIn(".speckit-linear.env", content.splitlines())

    def test_no_op_when_nothing_is_missing(self) -> None:
        self.path.write_text(".speckit-linear.env\nspeckit-linear.local.yml\n", encoding="utf-8")
        original_mtime = self.path.stat().st_mtime_ns

        added = ensure_entries(self.path, (".speckit-linear.env", "speckit-linear.local.yml"))

        self.assertEqual(added, [])
        self.assertEqual(self.path.stat().st_mtime_ns, original_mtime)


if __name__ == "__main__":
    unittest.main()


class AnchoredEntryTests(unittest.TestCase):
    """A root-anchored `/entry` already ignores the root-level file; neither
    ensure_entries nor doctor may append a duplicate (the onboard nit)."""

    def test_an_anchored_variant_counts_as_present(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from spec_kit_linear.gitignore import ensure_entries, has_entry

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / ".gitignore"
            path.write_text("/.speckit-linear.env\n", encoding="utf-8")

            added = ensure_entries(path, (".speckit-linear.env",))

            self.assertEqual(added, [])
            self.assertEqual(path.read_text(encoding="utf-8"), "/.speckit-linear.env\n")
        self.assertTrue(has_entry({"/.speckit-linear.env"}, ".speckit-linear.env"))
        self.assertFalse(has_entry({"other/.speckit-linear.env"}, ".speckit-linear.env"))
