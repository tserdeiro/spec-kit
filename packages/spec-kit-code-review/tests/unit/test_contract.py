"""Protected paths: the generated finding, direct and below the CLI (FR-010, plan D1)."""

from __future__ import annotations

import unittest

from spec_kit_code_review.anchors import load_hunks
from spec_kit_code_review.contract import is_task_base, protected_path_findings
from spec_kit_code_review.findings import normalize
from spec_kit_code_review.git import open_git
from tests.support.repo import TemporaryRepository


DEFAULTS = ("specs/*/spec.md", ".specify/memory/constitution.md")


class IsTaskBaseTests(unittest.TestCase):
    def test_a_numeric_final_path_segment_is_a_task_base(self) -> None:
        for branch in ("004-delivery-discipline", "004-T008-protected-paths", "team/004-feature"):
            with self.subTest(branch=branch):
                self.assertTrue(is_task_base(branch))

    def test_the_trunk_and_no_base_are_exempt(self) -> None:
        for branch in (None, "", "main", "release/2.0"):
            with self.subTest(branch=branch):
                self.assertFalse(is_task_base(branch))


class ProtectedPathFindingsTests(unittest.TestCase):
    """Cheaper than a CLI round trip; each shape must also survive `normalize`."""

    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.base = self.repository.commit("specs/004-x/spec.md", "Initial spec.\nMore.\n", "seed")
        self.git = open_git(self.repository.path)

    def _findings(self, head: str, *, base_branch: str | None = "004-feature", protected_paths=DEFAULTS) -> list:
        hunks = load_hunks(self.git, merge_base=self.base, head_commit=head)
        return protected_path_findings(
            base_branch=base_branch,
            protected_paths=protected_paths,
            git=self.git,
            hunks=hunks,
            merge_base=self.base,
            head_commit=head,
        )

    def _kept_blocking_count(self, head: str, entries: list) -> int:
        hunks = load_hunks(self.git, merge_base=self.base, head_commit=head)
        found = normalize(entries, git=self.git, head_commit=head, merge_base=self.base, hunks=hunks)
        return sum(1 for item in found.findings if item.severity == "blocking")

    def _delete_spec(self) -> str:
        self.repository.git("rm", "specs/004-x/spec.md")
        self.repository.git("commit", "-m", "delete")
        return self.repository.head()

    def _trim_spec(self) -> str:
        # Removes a line but leaves the file in place -- unlike `_delete_spec`,
        # which removes the whole file; both must anchor at LEFT 1..1.
        return self.repository.commit("specs/004-x/spec.md", "Initial spec.\n", "trim")

    def test_each_shape_is_blocking_and_survives_normalization(self) -> None:
        cases = (
            ("modified", lambda: self.repository.commit("specs/004-x/spec.md", "Initial spec.\nMore.\nEven more.\n", "touch"), "RIGHT"),
            ("added", lambda: self.repository.commit("specs/004-y/spec.md", "New spec.\n", "add"), "RIGHT"),
            ("deleted", self._delete_spec, "LEFT"),
            ("in-file removal", self._trim_spec, "LEFT"),
        )
        for shape, build, side in cases:
            with self.subTest(shape=shape):
                self.repository.git("reset", "--hard", self.base)
                head = build()
                findings = self._findings(head)
                self.assertEqual(len(findings), 1)
                self.assertEqual((findings[0]["side"], findings[0]["severity"], findings[0]["category"]), (side, "blocking", "contract"))
                if side == "LEFT":
                    # A base file always has a line 1, whether it was removed
                    # whole or only some of its lines were.
                    self.assertEqual((findings[0]["start_line"], findings[0]["end_line"]), (1, 1))
                self.assertEqual(self._kept_blocking_count(head, findings), 1)

    def test_a_non_protected_change_yields_nothing(self) -> None:
        head = self.repository.commit("src/other.py", "value = 1\n", "unrelated")

        self.assertEqual(self._findings(head), [])

    def test_a_trunk_base_is_exempt(self) -> None:
        head = self.repository.commit("specs/004-x/spec.md", "Initial spec.\nMore.\nEven more.\n", "touch")

        self.assertEqual(self._findings(head, base_branch="main"), [])

    def test_a_custom_protected_paths_list_is_honored(self) -> None:
        head = self.repository.commit("src/other.py", "value = 1\n", "touch")

        findings = self._findings(head, protected_paths=["src/**"])

        self.assertEqual([item["path"] for item in findings], ["src/other.py"])


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
