from __future__ import annotations

import unittest

from spec_kit_linear.bridge import marker_present, merge_managed_block
from spec_kit_linear.errors import AppError


MARKER = "speckit-linear:task:001:T001"
REPLACEMENT = "<!-- speckit-linear:task:001:T001 hash:abcdef123456 -->\nSource: `specs/001-x/tasks.md#L10`\n<!-- /speckit-linear -->"


class MergeManagedBlockTests(unittest.TestCase):
    """The bridge owns one bounded block per marker; human text on both
    sides of it is preserved. The open tag is matched with or without a
    ` hash:HHHH` suffix, so the same merge composes a hash-gated block
    (a task's Issue description, Project.content) or a plain one (the
    feature's Project.description)."""

    def test_fresh_compose_against_empty_text_is_the_replacement_verbatim(self) -> None:
        merged = merge_managed_block("", MARKER, REPLACEMENT)

        self.assertEqual(merged, REPLACEMENT)

    def test_no_marker_at_all_appends_the_block_below_the_existing_text(self) -> None:
        existing = "A developer wrote this note directly in Linear."

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, f"{existing}\n{REPLACEMENT}")

    def test_a_bounded_block_with_a_plain_open_tag_is_replaced_preserving_both_sides(self) -> None:
        block = f"<!-- {MARKER} -->\nold Source line\n<!-- /speckit-linear -->"
        existing = f"Manual introduction\n{block}\nManual closing"

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, f"Manual introduction\n{REPLACEMENT}\nManual closing")

    def test_a_bounded_block_with_a_hashed_open_tag_is_also_replaced_preserving_both_sides(self) -> None:
        # Format-tolerant: the open tag itself may already carry a hash
        # suffix (a task's Issue description, or Project.content).
        block = f"<!-- {MARKER} hash:000000000000 -->\nstale body\n<!-- /speckit-linear -->"
        existing = f"Manual introduction\n{block}\nManual closing"

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, f"Manual introduction\n{REPLACEMENT}\nManual closing")

    def test_a_0_9_0_trailing_marker_with_nothing_below_migrates_to_the_replacement_verbatim(self) -> None:
        # The 0.9.0 head format: a task's description ends with the marker
        # line and carries no close tag anywhere.
        existing = f"stale body\n<!-- {MARKER} hash:000000000000 -->"

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, REPLACEMENT)

    def test_a_0_9_0_trailing_marker_with_human_text_below_preserves_it_on_migration(self) -> None:
        existing = f"stale body\n<!-- {MARKER} hash:000000000000 -->\nA human added this note after the push."

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, f"{REPLACEMENT}\nA human added this note after the push.")

    def test_a_bare_marker_with_no_hash_and_no_close_tag_also_migrates(self) -> None:
        # The feature Project's own description marker never carries a hash
        # (its Source:/Plan: lines round-trip byte-identical), so the bare
        # marker-only line must trigger the same no-close-tag migration.
        existing = f"Source: `spec.md#L1`\n<!-- {MARKER} -->\nHuman note below."

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, f"{REPLACEMENT}\nHuman note below.")

    def test_a_human_deleted_close_tag_degrades_to_the_same_migration_rule(self) -> None:
        # A human editing the Issue in Linear deletes the close tag but
        # leaves the rest of the old body in place below the marker. This is
        # indistinguishable from (and handled exactly like) the 0.9.0 shape:
        # everything from the start through the marker line is replaced,
        # and what used to be "inside" the block now survives as ordinary
        # visible text below the new block.
        existing = f"<!-- {MARKER} hash:000000000000 -->\nold prose\nold Source line"

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, f"{REPLACEMENT}\nold prose\nold Source line")

    def test_text_above_a_no_close_tag_marker_is_inside_the_owned_region(self) -> None:
        # Documents the trade-off: only text BELOW a no-close-tag marker
        # line is guaranteed to survive migration -- text above it (there is
        # no bounded block to preserve it against) is replaced.
        existing = f"A human edit above the marker.\n<!-- {MARKER} hash:000000000000 -->"

        merged = merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(merged, REPLACEMENT)
        self.assertNotIn("A human edit above the marker.", merged)

    def test_two_bounded_blocks_for_the_same_identity_is_a_remote_identity_error(self) -> None:
        block = f"<!-- {MARKER} -->\nold\n<!-- /speckit-linear -->"
        existing = f"{block}\n{block}"

        with self.assertRaises(AppError) as raised:
            merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.category, "remote_identity")
        self.assertEqual(raised.exception.diagnostics[0].code, "description_marker_duplicate")

    def test_two_no_close_tag_marker_lines_for_the_same_identity_is_also_a_duplicate_error(self) -> None:
        existing = (
            f"stale body one\n<!-- {MARKER} hash:000000000000 -->\n"
            f"stale body two\n<!-- {MARKER} hash:111111111111 -->"
        )

        with self.assertRaises(AppError) as raised:
            merge_managed_block(existing, MARKER, REPLACEMENT)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "description_marker_duplicate")


class MarkerPresentTests(unittest.TestCase):
    """Adoption (`remote_discovery._one_by_marker`) and content removal
    (`planner._needed_content`) must recognize a marker whichever format
    the resource's description currently uses."""

    def test_absent_when_the_marker_never_appears(self) -> None:
        self.assertFalse(marker_present("Nothing bridge-owned here.", MARKER))

    def test_present_for_a_bounded_block_with_a_plain_open_tag(self) -> None:
        self.assertTrue(marker_present(f"<!-- {MARKER} -->\nbody\n<!-- /speckit-linear -->", MARKER))

    def test_present_for_a_bounded_block_with_a_hashed_open_tag(self) -> None:
        self.assertTrue(marker_present(f"<!-- {MARKER} hash:abcdef123456 -->\nbody\n<!-- /speckit-linear -->", MARKER))

    def test_present_for_a_no_close_tag_marker_line_with_a_hash_suffix(self) -> None:
        self.assertTrue(marker_present(f"Source: x\n<!-- {MARKER} hash:abcdef123456 -->", MARKER))

    def test_present_for_a_no_close_tag_marker_line_with_no_hash_suffix(self) -> None:
        self.assertTrue(marker_present(f"Source: x\n<!-- {MARKER} -->", MARKER))

    def test_a_different_identity_does_not_match(self) -> None:
        self.assertFalse(marker_present(f"<!-- {MARKER} hash:abcdef123456 -->", "speckit-linear:task:001:T002"))


if __name__ == "__main__":
    unittest.main()
