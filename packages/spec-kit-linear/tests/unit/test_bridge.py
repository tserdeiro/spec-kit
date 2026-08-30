from __future__ import annotations

import unittest

from spec_kit_linear.bridge import marker_present, merge_managed_head
from spec_kit_linear.errors import AppError


MARKER = "speckit-linear:task:001:T001"
REPLACEMENT_HEAD = "Source: `specs/001-x/tasks.md#L10`\n<!-- speckit-linear:task:001:T001 hash:abcdef123456 -->"


class MergeManagedHeadTests(unittest.TestCase):
    """The bridge owns everything from the start of the text through the
    marker's own single line; everything below that line is human space."""

    def test_fresh_compose_against_empty_text_is_the_head_verbatim(self) -> None:
        merged = merge_managed_head("", MARKER, REPLACEMENT_HEAD)

        self.assertEqual(merged, REPLACEMENT_HEAD)

    def test_no_marker_at_all_prepends_the_head_above_the_existing_text(self) -> None:
        existing = "A developer wrote this note directly in Linear."

        merged = merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(merged, f"{REPLACEMENT_HEAD}\n{existing}")

    def test_a_legacy_bounded_block_migrates_preserving_text_on_both_sides(self) -> None:
        legacy_block = f"<!-- {MARKER} -->\nold Source line\n<!-- /speckit-linear -->"
        existing = f"Manual introduction\n{legacy_block}\nManual closing"

        merged = merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(merged, f"Manual introduction\n{REPLACEMENT_HEAD}\nManual closing")

    def test_human_text_below_a_new_format_marker_survives_a_rewrite(self) -> None:
        stale_head = f"stale body\n<!-- {MARKER} hash:000000000000 -->"
        existing = f"{stale_head}\nA human added this note after the push."

        merged = merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(merged, f"{REPLACEMENT_HEAD}\nA human added this note after the push.")

    def test_a_marker_with_no_hash_suffix_is_also_recognized_as_the_new_format(self) -> None:
        # The feature Project's own description head never carries a hash
        # (its Source:/Plan: lines round-trip byte-identical), so the bare
        # marker-only line must be recognized too, not just the hashed form.
        existing = f"Source: `spec.md#L1`\n<!-- {MARKER} -->\nHuman note below."

        merged = merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(merged, f"{REPLACEMENT_HEAD}\nHuman note below.")

    def test_text_a_human_inserts_above_the_marker_is_inside_the_owned_region(self) -> None:
        # Documents the trade-off: only text BELOW the marker line is
        # guaranteed to survive -- a human edit above it is replaced.
        existing = f"A human edit above the marker.\n<!-- {MARKER} hash:000000000000 -->"

        merged = merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(merged, REPLACEMENT_HEAD)
        self.assertNotIn("A human edit above the marker.", merged)

    def test_two_new_format_marker_lines_for_the_same_identity_is_a_remote_identity_error(self) -> None:
        existing = (
            f"stale body one\n<!-- {MARKER} hash:000000000000 -->\n"
            f"stale body two\n<!-- {MARKER} hash:111111111111 -->"
        )

        with self.assertRaises(AppError) as raised:
            merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.category, "remote_identity")
        self.assertEqual(raised.exception.diagnostics[0].code, "description_marker_duplicate")

    def test_two_legacy_bounded_blocks_for_the_same_identity_is_also_a_duplicate_error(self) -> None:
        legacy_block = f"<!-- {MARKER} -->\nold\n<!-- /speckit-linear -->"
        existing = f"{legacy_block}\n{legacy_block}"

        with self.assertRaises(AppError) as raised:
            merge_managed_head(existing, MARKER, REPLACEMENT_HEAD)

        self.assertEqual(raised.exception.code, 6)


class MarkerPresentTests(unittest.TestCase):
    """Adoption (`remote_discovery._one_by_marker`) must recognize a marker
    whichever format the resource's description currently uses."""

    def test_absent_when_the_marker_never_appears(self) -> None:
        self.assertFalse(marker_present("Nothing bridge-owned here.", MARKER))

    def test_present_for_a_legacy_bounded_open_tag(self) -> None:
        self.assertTrue(marker_present(f"<!-- {MARKER} -->\nbody\n<!-- /speckit-linear -->", MARKER))

    def test_present_for_a_new_format_marker_with_a_hash_suffix(self) -> None:
        self.assertTrue(marker_present(f"Source: x\n<!-- {MARKER} hash:abcdef123456 -->", MARKER))

    def test_present_for_a_new_format_marker_with_no_hash_suffix(self) -> None:
        self.assertTrue(marker_present(f"Source: x\n<!-- {MARKER} -->", MARKER))

    def test_a_different_identity_does_not_match(self) -> None:
        self.assertFalse(marker_present(f"<!-- {MARKER} hash:abcdef123456 -->", "speckit-linear:task:001:T002"))


if __name__ == "__main__":
    unittest.main()
