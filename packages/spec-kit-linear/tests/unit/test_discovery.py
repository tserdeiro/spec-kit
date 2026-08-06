from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from spec_kit_linear.discovery import select_features
from spec_kit_linear.errors import AppError


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def _make_repo(root: Path, *, feature_ids: list[str], branch: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for identifier in feature_ids:
        feature_dir = root / "specs" / f"{identifier}-sample-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Sample\n", encoding="utf-8")
    if branch is not None:
        _git(root, "checkout", "-q", "-b", branch)


class GitFeatureDiscoveryTests(unittest.TestCase):
    """Doc "Descubrimiento de feature": step 3 (branch/worktree) sits between
    .specify/feature.json (step 2) and the single-directory fallback (step 4).
    No network access; every repo here is a fresh local temp checkout.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_current_resolves_from_the_current_branch_name_when_feature_json_is_absent(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="002-sample-feature")

        selected = select_features(self.root, explicit_feature=None, current=True, all_features=False)

        self.assertEqual([path.name for path in selected], ["002-sample-feature"])

    def test_current_resolves_a_prefixed_branch_name_by_its_final_segment(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="feature/002-sample-feature")

        selected = select_features(self.root, explicit_feature=None, current=True, all_features=False)

        self.assertEqual([path.name for path in selected], ["002-sample-feature"])

    def test_feature_json_takes_precedence_over_the_branch_name(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="002-sample-feature")
        (self.root / ".specify").mkdir()
        (self.root / ".specify" / "feature.json").write_text(json.dumps({"feature": "001"}), encoding="utf-8")

        selected = select_features(self.root, explicit_feature=None, current=True, all_features=False)

        self.assertEqual([path.name for path in selected], ["001-sample-feature"])

    def test_feature_json_resolves_the_native_feature_directory_key(self) -> None:
        # Spec Kit's own create-new-feature.sh writes this exact shape.
        _make_repo(self.root, feature_ids=["001", "002"], branch="main")
        (self.root / ".specify").mkdir()
        (self.root / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": "specs/001-sample-feature"}), encoding="utf-8"
        )

        selected = select_features(self.root, explicit_feature=None, current=True, all_features=False)

        self.assertEqual([path.name for path in selected], ["001-sample-feature"])

    def test_feature_directory_key_yields_to_the_branch_when_its_last_segment_does_not_match(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="002-sample-feature")
        (self.root / ".specify").mkdir()
        (self.root / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": "specs/not-a-feature"}), encoding="utf-8"
        )

        selected = select_features(self.root, explicit_feature=None, current=True, all_features=False)

        self.assertEqual([path.name for path in selected], ["002-sample-feature"])

    def test_current_falls_back_to_the_worktree_directory_name_when_the_branch_does_not_match(self) -> None:
        worktree_root = self.root / "003-worktree-feature"
        _make_repo(worktree_root, feature_ids=["001", "003"], branch="main")

        selected = select_features(worktree_root, explicit_feature=None, current=True, all_features=False)

        # The worktree directory's own name ("003-worktree-feature") only
        # supplies the identifier "003"; the returned path is still the real
        # specs/003-*/ directory on disk.
        self.assertEqual([path.name for path in selected], ["003-sample-feature"])

    def test_implicit_resolution_without_the_current_flag_also_uses_the_branch(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="002-sample-feature")

        selected = select_features(self.root, explicit_feature=None, current=False, all_features=False)

        self.assertEqual([path.name for path in selected], ["002-sample-feature"])

    def test_current_raises_when_no_source_resolves_and_selection_is_ambiguous(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="main")

        with self.assertRaises(AppError) as raised:
            select_features(self.root, explicit_feature=None, current=True, all_features=False)

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(raised.exception.diagnostics[0].code, "feature_current")

    def test_branch_name_is_ignored_when_it_does_not_match_and_a_single_feature_directory_exists(self) -> None:
        _make_repo(self.root, feature_ids=["001"], branch="main")

        selected = select_features(self.root, explicit_feature=None, current=False, all_features=False)

        self.assertEqual([path.name for path in selected], ["001-sample-feature"])

    def test_explicit_feature_still_wins_over_any_branch_name(self) -> None:
        _make_repo(self.root, feature_ids=["001", "002"], branch="002-sample-feature")

        selected = select_features(self.root, explicit_feature="001", current=False, all_features=False)

        self.assertEqual([path.name for path in selected], ["001-sample-feature"])
