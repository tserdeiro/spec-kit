"""``review`` with no candidate: the advisory review of the pending diff.

The properties worth defending are the ones that separate it from an anchored
review: it never contacts GitHub, it opens no session, it writes nothing inside
the repository, and the packet it produces says out loud that it is advisory.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from spec_kit_code_review.errors import EXIT_SUCCESS
from tests.unit.test_cli import CliCase


RULES = json.dumps({"rules": [{"path": "src/**", "rule": "Validate every input."}]}, indent=2)


class WorkingTreeCase(CliCase):
    def setUp(self) -> None:
        super().setUp()
        self.invocations = self.workspace / "ocr-invocations.txt"
        self.gh_invocations = self.workspace / "gh-invocations.txt"
        # The scaffolding writes the lock file after its own commit; this command
        # reviews whatever is uncommitted, so the tree starts clean on purpose.
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "scaffolding")

    def _dirty(self, *paths: str, lines: int = 3) -> None:
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join(f"x = {index}\n" for index in range(lines)), encoding="utf-8")

    def _packet(self, payload: dict) -> str:
        return Path(payload["packet"]["path"]).read_text(encoding="utf-8")


class AdvisoryReviewTests(WorkingTreeCase):
    def test_the_packet_is_produced_and_says_it_is_advisory(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")

        code, payload = self.invoke_json("review")

        self.assertEqual(code, EXIT_SUCCESS, payload["diagnostics"])
        packet = self._packet(payload)
        self.assertIn("## 1. Workspace (no candidate)", packet)
        self.assertIn("the output is advisory", packet)
        # No pull request exists, so none is described.
        self.assertIn("### 0.1 Advisory review", packet)
        self.assertNotIn("Pull-request metadata", packet)
        self.assertNotIn("### 4.7 Pull-request body", packet)
        self.assertIn("advisory", payload["message"])
        codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("advisory", codes)
        self.assertIn("working_tree_review", codes)

    def test_untracked_content_is_reviewed_and_counted(self) -> None:
        # `git diff` cannot see an untracked file, and the usual remedy writes to
        # the index -- which this command must never do. Its lines still count.
        self._dirty("src/brand_new.py", lines=12)
        self._engine_reports("src/brand_new.py")

        _code, payload = self.invoke_json("review")

        entry = next(item for item in payload["budget"]["files"] if item["path"] == "src/brand_new.py")
        self.assertEqual(entry["added"], 12)
        self.assertEqual(entry["counted"], 12)
        self.assertEqual(payload["budget"]["counted"], 12)

    def test_no_session_is_opened_and_nothing_is_written_in_the_repository(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")
        before = self.repository.git("status", "--porcelain")

        _code, payload = self.invoke_json("review")

        self.assertNotIn("session", payload)
        self.assertEqual(self.repository.git("status", "--porcelain"), before)
        self.assertFalse(list(self.root.rglob("review-packet.md")))
        self.assertFalse(list(self.root.rglob("session.json")))
        self.assertTrue(Path(payload["packet"]["path"]).is_file())

    def test_the_checkout_is_never_materialized(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")

        code, _payload = self.invoke_json("review")

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(list(self.evidence.glob("*/*/worktree")), [])
        self.assertEqual(self.repository.git("rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_github_is_never_contacted(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")
        from tests.support.fixtures import install_fake_gh

        install_fake_gh(
            self.bin,
            {
                "auth": {"authenticated": True, "scopes": ["repo"]},
                "user": "tester",
                "record_invocations": str(self.gh_invocations),
            },
        )

        code, _payload = self.invoke_json("review")

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertFalse(self.gh_invocations.exists(), "the advisory review invoked gh")

    def test_the_engines_raw_output_is_preserved_before_it_is_parsed(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")

        _code, payload = self.invoke_json("review")

        raw = Path(payload["packet"]["path"]).parent / "raw"
        self.assertTrue((raw / "ocr-delegate-preview.stdout").is_file())
        self.assertTrue((raw / "ocr-delegate-rule.stdout").is_file())

    def test_the_engine_is_invoked_without_a_range(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py", record_invocations=str(self.invocations))

        self.invoke_json("review")

        recorded = self.invocations.read_text(encoding="utf-8")
        preview = next(line for line in recorded.splitlines() if "delegate preview" in line)
        self.assertNotIn("--from", preview)
        self.assertNotIn("--to", preview)

    def test_the_scope_is_cross_checked_against_the_working_tree(self) -> None:
        # The same format-independent invariant as an anchored review, over the
        # set this mode actually reviews.
        self._dirty("src/uncommitted.py", "src/forgotten.py")
        self._engine_reports("src/uncommitted.py")

        code, payload = self.invoke_json("review")

        self.assertEqual(code, 9)
        self.assertIn("engine_scope_mismatch", {item["code"] for item in payload["diagnostics"]})


class ContextTests(WorkingTreeCase):
    def test_the_sdd_context_and_rules_come_from_the_working_tree(self) -> None:
        # Uncommitted edits to both are exactly what a pre-pull-request review
        # should be reading: they are the operator's own work in progress.
        (self.root / ".opencodereview").mkdir(parents=True, exist_ok=True)
        (self.root / ".opencodereview" / "rule.json").write_text(RULES, encoding="utf-8")
        specs = self.root / "specs" / "001-review-skeleton"
        specs.mkdir(parents=True, exist_ok=True)
        (specs / "plan.md").write_text("# Plan\n\nUncommitted plan text.\n", encoding="utf-8")
        self._dirty("src/uncommitted.py")
        self._engine_reports(
            "src/uncommitted.py",
            ".opencodereview/rule.json",
            "specs/001-review-skeleton/plan.md",
        )

        _code, payload = self.invoke_json("review")

        self.assertEqual(payload["rules"]["ref_kind"], "working-tree")
        packet = self._packet(payload)
        self.assertIn("Read from the working tree.", packet)
        self.assertIn("Uncommitted plan text.", packet)

    def test_the_packets_instructions_forbid_declaring_the_change_reviewed(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")

        _code, payload = self.invoke_json("review")

        packet = self._packet(payload)
        self.assertIn("declare the change reviewed, approved, or ready to merge", packet)
        self.assertNotIn("approve or merge the pull request", packet)

    def test_the_budget_warns_before_a_large_pull_request_is_opened(self) -> None:
        self._dirty("src/huge.py", lines=450)
        self._engine_reports("src/huge.py")

        _code, payload = self.invoke_json("review")

        self.assertTrue(payload["budget"]["over_budget"])
        self.assertIn("budget_exceeded", {item["code"] for item in payload["diagnostics"]})
        message = next(
            item["message"] for item in payload["diagnostics"] if item["code"] == "budget_exceeded"
        )
        self.assertIn("stacked pull requests", message)

    def test_an_absent_context_is_a_warning_not_a_refusal(self) -> None:
        for path in self.root.rglob("specs"):
            shutil.rmtree(path, ignore_errors=True)
        (self.root / ".specify" / "feature.json").unlink(missing_ok=True)
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "no spec kit context")
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")

        code, payload = self.invoke_json("review")

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertIn("sdd_context_absent", {item["code"] for item in payload["diagnostics"]})


class EvidenceTests(WorkingTreeCase):
    def test_each_run_gets_its_own_directory_and_latest_points_at_it(self) -> None:
        # Two concurrent previews must not overwrite each other's packet, and a
        # failed run must not leave a stale packet beside fresh raw output.
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")

        _code, first = self.invoke_json("review")
        _code, second = self.invoke_json("review")

        first_path = Path(first["packet"]["path"])
        second_path = Path(second["packet"]["path"])
        self.assertNotEqual(first_path.parent, second_path.parent)
        self.assertTrue(first_path.is_file())
        pointer = first_path.parent.parent / "latest"
        target = pointer if pointer.exists() else first_path.parent.parent / "latest.txt"
        self.assertTrue(target.exists())
        resolved = target.read_text(encoding="utf-8").strip() if target.suffix else target.resolve().name
        self.assertEqual(resolved, second_path.parent.name)

    def test_the_evidence_root_comes_from_the_environment(self) -> None:
        self._dirty("src/uncommitted.py")
        self._engine_reports("src/uncommitted.py")
        explicit = self.workspace / "explicit-evidence"
        self.environment["SPECKIT_CODE_REVIEW_EVIDENCE_DIR"] = str(explicit)

        _code, payload = self.invoke_json("review")

        self.assertTrue(str(Path(payload["packet"]["path"])).startswith(str(explicit)))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
