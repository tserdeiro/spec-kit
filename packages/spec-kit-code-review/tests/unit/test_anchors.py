"""Hunks come from `git diff --unified=0`, locally, and from nowhere else."""

from __future__ import annotations

import unittest

from spec_kit_code_review.anchors import HunkMap, file_line_counts, load_hunks, parse_unified_zero, summarize
from spec_kit_code_review.git import open_git
from tests.support.repo import TemporaryRepository


DIFF = """\
diff --git a/src/module.py b/src/module.py
index 1111111..2222222 100644
--- a/src/module.py
+++ b/src/module.py
@@ -3,0 +4,2 @@ def thing():
+    added = 1
+    also_added = 2
@@ -10 +12 @@ def other():
-    old = 1
+    new = 1
diff --git a/deleted.py b/deleted.py
deleted file mode 100644
--- a/deleted.py
+++ /dev/null
@@ -1,3 +0,0 @@
-gone = 1
-gone = 2
-gone = 3
"""


class ParseTests(unittest.TestCase):
    def test_ranges_come_from_the_new_side_only(self) -> None:
        hunks = parse_unified_zero(DIFF)

        self.assertEqual(
            [(hunk.path, hunk.start, hunk.end) for hunk in hunks],
            [("src/module.py", 4, 5), ("src/module.py", 12, 12)],
        )
        self.assertTrue(all(hunk.side == "RIGHT" for hunk in hunks))

    def test_a_pure_deletion_contributes_no_anchorable_range(self) -> None:
        # `+0,0` has no line on the head side to anchor to; every finding about
        # it degrades to the summary, which is the documented behaviour.
        hunks = parse_unified_zero(DIFF)

        self.assertNotIn("deleted.py", [hunk.path for hunk in hunks])

    def test_a_single_line_hunk_defaults_its_count_to_one(self) -> None:
        hunks = parse_unified_zero("--- a/x.py\n+++ b/x.py\n@@ -5 +7 @@\n-a\n+b\n")

        self.assertEqual([(hunk.start, hunk.end) for hunk in hunks], [(7, 7)])

    def test_a_path_with_spaces_survives_the_header(self) -> None:
        hunks = parse_unified_zero("--- a/two words.py\n+++ b/two words.py\n@@ -0,0 +1,2 @@\n+a\n+b\n")

        self.assertEqual([hunk.path for hunk in hunks], ["two words.py"])

    def test_output_that_is_not_a_diff_yields_nothing_rather_than_guessing(self) -> None:
        self.assertEqual(parse_unified_zero("not a diff at all\n@@ malformed @@\n"), ())

    def test_summarize_counts_hunks_per_path(self) -> None:
        self.assertEqual(summarize(parse_unified_zero(DIFF)), {"src/module.py": 2})


class AnchorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.map = HunkMap(hunks=parse_unified_zero(DIFF))

    def test_a_range_inside_a_hunk_anchors(self) -> None:
        self.assertIsNotNone(self.map.anchor("src/module.py", 4, 5))

    def test_a_range_that_only_partly_overlaps_does_not_anchor(self) -> None:
        # A partially-true anchor points the reader at lines the candidate did
        # not touch, and GitHub rejects the end line anyway.
        self.assertIsNone(self.map.anchor("src/module.py", 5, 6))

    def test_a_range_in_another_file_never_anchors(self) -> None:
        self.assertIsNone(self.map.anchor("other.py", 4, 5))


class GitBackedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.repository.write("src/module.py", "".join(f"line_{index}\n" for index in range(10)))
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "base")
        self.base = self.repository.head()
        self.repository.write("src/module.py", "".join(f"line_{index}\n" for index in range(10)) + "added = 1\n")
        self.repository.write("src/new.py", "fresh = 1\n")
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "candidate")
        self.head = self.repository.head()
        self.git = open_git(self.repository.path)

    def test_the_hunks_of_a_real_candidate(self) -> None:
        hunks = load_hunks(self.git, merge_base=self.base, head_commit=self.head)

        self.assertEqual(hunks.anchor("src/module.py", 11, 11).start, 11)
        self.assertIsNotNone(hunks.anchor("src/new.py", 1, 1))
        self.assertIsNone(hunks.anchor("src/module.py", 3, 3))

    def test_an_empty_candidate_reports_that_nothing_can_be_anchored(self) -> None:
        hunks = load_hunks(self.git, merge_base=self.head, head_commit=self.head)

        self.assertEqual(hunks.hunks, ())
        self.assertEqual([item.code for item in hunks.diagnostics], ["hunks_empty"])

    def test_line_counts_come_from_git_objects_not_the_working_tree(self) -> None:
        # The working tree may sit on another branch entirely; the count that
        # decides whether a finding is inside its file must be the head's.
        self.repository.write("src/module.py", "truncated\n")

        counts = file_line_counts(self.git, self.head, ["src/module.py", "absent.py"])

        self.assertEqual(counts["src/module.py"], 11)
        self.assertIsNone(counts["absent.py"])


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
