from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.git import open_git
from spec_kit_code_review.sdd_context import (
    CommitReader,
    SOURCE_BUG,
    SOURCE_DIFF,
    SOURCE_FEATURE_JSON,
    SOURCE_FLAG,
    SOURCE_NONE,
    SOURCE_PR_BODY,
    load_context,
    parse_tasks,
    resolve_feature,
)
from tests.support.repo import TemporaryRepository


SPEC = """\
# Feature Specification: Review skeleton

## Requirements

- **FR-001**: The candidate identity is the pair (merge base, head commit).
- **FR-002**: Nothing in the candidate tree governs execution.
- **NFR-001**: The packet is deterministic.
"""
TASKS = """\
# Tasks

- [x] T001 Resolve the immutable candidate (forecast: 120 lines, PR strategy: single)
- [ ] T002 Report prerequisites (forecast: 90 lines, PR strategy: feature-chain)
- [ ] T003 Something with no declared size
"""
CHECKLIST = """\
# Checklist: requirements

- [x] CHK001 Every requirement has an identifier.
- [ ] CHK002 The budget is reported.
"""


class SddCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.repository = TemporaryRepository(self.workspace / "consumer")
        self.addCleanup(self.repository.cleanup)

        self.repository.write(".specify/memory/constitution.md", "# Constitution\n\n- Tests ship with the change.\n")
        self.repository.write("specs/001-review-skeleton/spec.md", SPEC)
        self.repository.write("specs/001-review-skeleton/plan.md", "# Plan\n\n## Decisions\n\n- Read from Git objects.\n")
        self.repository.write("specs/001-review-skeleton/tasks.md", TASKS)
        self.repository.write("specs/001-review-skeleton/checklists/requirements.md", CHECKLIST)
        self.repository.write(".specify/feature.json", json.dumps({"feature": "001-review-skeleton"}))
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "feature artifacts")
        self.head = self.repository.head()
        self.git = open_git(self.repository.path)


class DiscoveryOrderTests(SddCase):
    def test_an_explicit_feature_wins(self) -> None:
        self.repository.write("specs/002-other/spec.md", "# Other\n")
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "second feature")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=[], explicit="002-other")

        self.assertEqual(resolution.feature, "002-other")
        self.assertEqual(resolution.source, SOURCE_FLAG)

    def test_a_three_digit_number_resolves_to_its_directory(self) -> None:
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[], explicit="001")

        self.assertEqual(resolution.feature, "001-review-skeleton")

    def test_an_explicit_feature_that_does_not_exist_degrades_with_a_warning(self) -> None:
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[], explicit="404-nope")

        self.assertIsNone(resolution.feature)
        self.assertEqual([item.code for item in resolution.diagnostics], ["sdd_feature_unknown"])

    def test_feature_json_is_the_second_path(self) -> None:
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[])

        self.assertEqual(resolution.feature, "001-review-skeleton")
        self.assertEqual(resolution.source, SOURCE_FEATURE_JSON)

    def test_a_single_touched_feature_directory_is_the_third_path(self) -> None:
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.git("commit", "-m", "drop the active feature")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=["specs/001-review-skeleton/spec.md", "src/module.py"]
        )

        self.assertEqual(resolution.feature, "001-review-skeleton")
        self.assertEqual(resolution.source, SOURCE_DIFF)

    def test_the_pull_request_body_is_the_fourth_path(self) -> None:
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.git("commit", "-m", "drop the active feature")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=["src/module.py"],
            pr_body="## Verification evidence\n\nSpec Kit evidence: specs/001-review-skeleton/tasks.md\n",
        )

        self.assertEqual(resolution.feature, "001-review-skeleton")
        self.assertEqual(resolution.source, SOURCE_PR_BODY)

    def test_a_bug_directory_is_the_fifth_path(self) -> None:
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.write(".specify/bugs/flaky-login/assessment.md", "# Assessment\n")
        self.repository.write(".specify/bugs/flaky-login/fix.md", "# Fix\n")
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "a bug fix candidate")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=[".specify/bugs/flaky-login/fix.md", "src/login.py"]
        )

        self.assertEqual(resolution.bug_slug, "flaky-login")
        self.assertEqual(resolution.source, SOURCE_BUG)

    def test_nothing_resolvable_is_a_warning_not_a_failure(self) -> None:
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.git("commit", "-m", "drop the active feature")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=["src/module.py"])

        self.assertIsNone(resolution.feature)
        self.assertEqual(resolution.source, SOURCE_NONE)
        self.assertEqual([item.code for item in resolution.diagnostics], ["sdd_context_absent"])


class AmbiguityTests(SddCase):
    def test_two_touched_features_never_pick_one(self) -> None:
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.write("specs/002-other/spec.md", "# Other\n")
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "second feature")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=["specs/001-review-skeleton/spec.md", "specs/002-other/spec.md"],
        )

        self.assertTrue(resolution.ambiguous)
        self.assertIsNone(resolution.feature)
        self.assertEqual(resolution.candidates, ("001-review-skeleton", "002-other"))
        warning = resolution.diagnostics[0]
        self.assertEqual(warning.code, "sdd_context_ambiguous")
        self.assertIn("001-review-skeleton", warning.message)
        self.assertIn("002-other", warning.message)
        self.assertIn("--feature", warning.message)

    def test_the_review_continues_without_context(self) -> None:
        # Losing a whole review because two directories were touched would be
        # worse than reviewing with less context.
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.write("specs/002-other/spec.md", "# Other\n")
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "second feature")
        head = self.repository.head()
        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=["specs/001-review-skeleton/spec.md", "specs/002-other/spec.md"],
        )

        context = load_context(CommitReader(self.git, head), resolution=resolution)

        self.assertFalse(context.present)
        self.assertTrue(context.constitution.present, "the constitution is still readable")

    def test_two_touched_bug_directories_are_ambiguous_too(self) -> None:
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.git("commit", "-m", "drop the active feature")
        head = self.repository.head()

        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=[".specify/bugs/one/fix.md", ".specify/bugs/two/fix.md"],
        )

        self.assertTrue(resolution.ambiguous)
        self.assertEqual(resolution.candidates, ("one", "two"))


class ArtifactLoadingTests(SddCase):
    def test_every_artifact_comes_from_the_commit(self) -> None:
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[])

        context = load_context(CommitReader(self.git, self.head), resolution=resolution)

        self.assertTrue(context.present)
        self.assertTrue(context.spec.present and context.plan.present and context.tasks.present)
        self.assertEqual(len(context.checklists), 1)
        self.assertEqual(context.requirement_ids, ("FR-001", "FR-002", "NFR-001"))
        self.assertEqual(context.checklist_summary, {"files": 1, "items": 2, "checked": 1})
        self.assertEqual(len(context.artifacts()), 6)

    def test_a_working_tree_that_disagrees_with_the_commit_is_ignored(self) -> None:
        (self.repository.path / "specs" / "001-review-skeleton" / "spec.md").write_text(
            "# HOSTILE WORKING TREE\n", encoding="utf-8"
        )
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[])

        context = load_context(CommitReader(self.git, self.head), resolution=resolution)

        self.assertNotIn("HOSTILE", context.spec.text or "")

    def test_the_declared_forecast_is_summed_from_the_tasks(self) -> None:
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[])

        context = load_context(CommitReader(self.git, self.head), resolution=resolution)

        self.assertEqual(context.forecast_total, 210)
        self.assertEqual([entry.identifier for entry in context.task_entries], ["T001", "T002", "T003"])
        self.assertEqual(context.task_entries[0].strategy, "single")
        self.assertEqual(context.task_entries[1].strategy, "feature-chain")
        self.assertIsNone(context.task_entries[2].forecast)

    def test_checklists_can_be_left_out(self) -> None:
        resolution = resolve_feature(
            CommitReader(self.git, self.head),
            changed_paths=[])

        context = load_context(CommitReader(self.git, self.head), resolution=resolution, include_checklists=False)

        self.assertEqual(context.checklists, ())

    def test_a_bug_candidate_loads_its_three_artifacts(self) -> None:
        # A bug-fix candidate has no active feature; that is what puts it on the
        # fifth discovery path.
        self.repository.git("rm", "-q", ".specify/feature.json")
        self.repository.write(".specify/bugs/flaky/assessment.md", "# Assessment\n")
        self.repository.write(".specify/bugs/flaky/fix.md", "# Fix\n")
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "bug artifacts")
        head = self.repository.head()
        resolution = resolve_feature(
            CommitReader(self.git, head),
            changed_paths=[".specify/bugs/flaky/fix.md"], explicit=None
        )

        context = load_context(CommitReader(self.git, head), resolution=resolution)

        self.assertEqual(len(context.bug_artifacts), 3)
        self.assertTrue(context.bug_artifacts[0].present)
        self.assertFalse(context.bug_artifacts[2].present, "test.md was never written")


class TaskParsingTests(unittest.TestCase):
    def test_entries_without_declarations_still_parse(self) -> None:
        entries = parse_tasks("- [ ] T007 Just a task\n")

        self.assertEqual(entries[0].identifier, "T007")
        self.assertIsNone(entries[0].forecast)
        self.assertIsNone(entries[0].strategy)
        self.assertFalse(entries[0].done)
        self.assertIn("missing field: traces", entries[0].gaps)
        self.assertIn("missing field: completion evidence", entries[0].gaps)

    def test_prose_is_not_a_task(self) -> None:
        self.assertEqual(parse_tasks("Some prose about T001 and its forecast: 900 lines.\n"), ())

    def test_complete_blocks_keep_ranges_and_indented_fields(self) -> None:
        text = """# Phase\n\n- [ ] T001 Add `src/app.py`\n  - **Traces**: FR-002, SC-001\n  - **Depends on**: T000\n  - **Boundaries**: Change `src/app.py`. Preserve `src/rules.py`.\n  - **Delivery**: single PR (~280 authored lines)\n  - **Completion evidence**: focused tests pass\n\n- [x] T002 Finish it\n  - **Evidence**: `pytest tests/unit`\n\n## Next phase\n- [ ] T003 A later task\n"""
        first, second, third = parse_tasks(text)

        self.assertEqual((first.source_start, first.source_end), (3, 9))
        self.assertEqual(first.block_text, "".join(text.splitlines(keepends=True)[2:9]))
        self.assertEqual(first.traces, ("FR-002", "SC-001"))
        self.assertEqual(first.dependencies, ("T000",))
        self.assertEqual(first.changed_path_hints, ("src/app.py",))
        self.assertEqual(first.completion_evidence, "focused tests pass")
        self.assertEqual(first.delivery, "single PR (~280 authored lines)")
        self.assertEqual(first.forecast, 280)
        self.assertEqual((second.source_start, second.source_end), (10, 12))
        self.assertEqual((third.source_start, third.source_end), (14, 14))

    def test_fenced_task_examples_are_ignored_but_fenced_evidence_is_retained(self) -> None:
        text = """```markdown\n- [ ] T900 Example only\n```\n- [ ] T001 Real task\n  - **Evidence**:\n    ```markdown\n    - [ ] T901 evidence text\n    ```\n- [ ] T002 Final task\n"""
        entries = parse_tasks(text)

        self.assertEqual([entry.identifier for entry in entries], ["T001", "T002"])
        self.assertIn("T901", entries[0].block_text)

    def test_nested_task_like_evidence_is_not_a_task(self) -> None:
        entries = parse_tasks(
            "- [ ] T001 Real task\n"
            "  - **Evidence**:\n"
            "    - [ ] T901 evidence item\n"
            "  - **Completion evidence**: fields remain attached\n"
        )

        self.assertEqual([entry.identifier for entry in entries], ["T001"])
        self.assertEqual(entries[0].completion_evidence, "fields remain attached")
        self.assertIn("T901 evidence item", entries[0].block_text)

    def test_duplicate_ids_are_retained_with_a_gap(self) -> None:
        entries = parse_tasks("- [ ] T001 First\n- [ ] T001 Duplicate\n")

        self.assertIn("duplicate task identifier", entries[0].gaps)
        self.assertIn("duplicate task identifier", entries[1].gaps)

    def test_missing_dependency_is_a_gap(self) -> None:
        entries = parse_tasks("- [ ] T001 First\n  - **Depends on**: T999\n")

        self.assertIn("unresolved dependency: T999", entries[0].gaps)

    def test_empty_required_field_is_a_gap(self) -> None:
        entries = parse_tasks("- [ ] T001 First\n  - **Evidence**:\n")

        self.assertIn("empty field: evidence", entries[0].gaps)

    def test_unrecognized_canonical_field_is_a_gap(self) -> None:
        entries = parse_tasks("- [ ] T001 First\n  - **Unknown field**: value\n")

        self.assertIn("unrecognized field: Unknown field", entries[0].gaps)

    def test_boundary_hints_keep_extension_periods_and_exclude_protected_paths(self) -> None:
        entries = parse_tasks(
            "- [ ] T001 No path in title\n"
            "  - **Boundaries**: Change src/extra.py. Preserve src/rules.py.\n"
        )

        self.assertEqual(entries[0].changed_path_hints, ("src/extra.py",))


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
