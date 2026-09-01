from __future__ import annotations

import unittest
from pathlib import Path

from spec_kit_linear.errors import AppError
from spec_kit_linear.parser import parse_feature
from tests.support.fixtures import copy_consumer_fixture


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_parses_spec_plan_phases_and_tasks(self) -> None:
        feature = parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")

        self.assertEqual(feature.identifier, "001")
        self.assertEqual(feature.title, "Local projection")
        self.assertEqual(feature.plan_title, "Local projection plan")
        self.assertEqual([phase.number for phase in feature.phases], [1, 2])
        self.assertEqual([task.identifier for phase in feature.phases for task in phase.tasks], ["T001", "T002", "T003"])
        self.assertTrue(feature.phases[0].tasks[1].completed)

    def test_rejects_duplicate_task_ids(self) -> None:
        tasks = self.fixture_root / "specs/001-local-projection/tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8") + "\n- [ ] T001 Duplicate\n", encoding="utf-8")

        with self.assertRaises(AppError) as raised:
            parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(raised.exception.diagnostics[0].code, "task_duplicate")


class FenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()
        self.feature_dir = self.fixture_root / "specs/001-local-projection"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_fences_are_ignored_for_titles_phases_and_tasks(self) -> None:
        spec = self.feature_dir / "spec.md"
        spec.write_text(
            "```markdown\n# Fenced spec title\n```\n\n" + spec.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        plan = self.feature_dir / "plan.md"
        plan.write_text(
            "~~~markdown\n# Fenced plan title\n~~~\n\n" + plan.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (self.feature_dir / "tasks.md").write_text(
            "# Tasks\n\n"
            "```markdown\n"
            "## Phase 98: Backtick example\n"
            "- [x] T001 Checked example\n"
            "```\n\n"
            "~~~markdown\n"
            "## Phase 99: Tilde example\n"
            "- [ ] T002 Unchecked example\n"
            "~~~\n\n"
            "## Phase 1: Real work\n\n"
            "- [ ] T001 Real task\n",
            encoding="utf-8",
        )

        feature = parse_feature(self.fixture_root, self.feature_dir)

        self.assertEqual(feature.title, "Local projection")
        self.assertEqual(feature.plan_title, "Local projection plan")
        self.assertEqual([phase.number for phase in feature.phases], [1])
        self.assertEqual([task.identifier for task in feature.phases[0].tasks], ["T001"])

    def test_template_task_format_section_parses_without_deletion(self) -> None:
        template = (
            Path(__file__).parents[4] / "presets/default/templates/tasks-template.md"
        ).read_text(encoding="utf-8")
        format_start = template.index("## Task block format")
        fence_start = template.index("```markdown", format_start)
        fence_end = template.index("\n```", fence_start) + len("\n```")
        (self.feature_dir / "tasks.md").write_text(
            template[:fence_end]
            + "\n\n## Phase 1: Real work\n\n"
            + "- [ ] T101 Parse the generated artifact\n",
            encoding="utf-8",
        )

        feature = parse_feature(self.fixture_root, self.feature_dir)

        self.assertEqual([phase.number for phase in feature.phases], [1])
        self.assertEqual([task.identifier for task in feature.phases[0].tasks], ["T101"])


class TaskBodyTests(unittest.TestCase):
    """The task body is the indented run of lines right under its checkbox."""

    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _tasks_path(self) -> Path:
        return self.fixture_root / "specs/001-local-projection/tasks.md"

    def _feature(self):
        return parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")

    def test_body_is_captured_and_dedented(self) -> None:
        feature = self._feature()

        self.assertEqual(
            feature.phases[0].tasks[0].description,
            "- **Traces**: FR-001; outcome: spec, plan, and tasks parse without mutation\n- **Depends on**: none",
        )

    def test_task_without_a_body_has_an_empty_description(self) -> None:
        feature = self._feature()

        self.assertEqual(feature.phases[0].tasks[1].description, "")
        self.assertEqual(feature.phases[1].tasks[0].description, "")

    def test_body_stops_at_the_first_blank_line(self) -> None:
        self._tasks_path().write_text(
            "# Tasks\n\n## Phase 1: Foundation\n\n"
            "- [ ] T001 Title\n"
            "  - kept line\n"
            "\n"
            "  - not part of the body\n",
            encoding="utf-8",
        )

        feature = self._feature()

        self.assertEqual(feature.phases[0].tasks[0].description, "- kept line")

    def test_body_stops_at_a_line_not_indented_deeper_than_the_bullet(self) -> None:
        self._tasks_path().write_text(
            "# Tasks\n\n## Phase 1: Foundation\n\n"
            "- [ ] T001 Title\n"
            "  - kept line\n"
            "- [ ] T002 Sibling task\n",
            encoding="utf-8",
        )

        feature = self._feature()

        self.assertEqual(feature.phases[0].tasks[0].description, "- kept line")
        self.assertEqual(feature.phases[0].tasks[1].description, "")

    def test_body_dedents_by_the_common_indent_while_preserving_nesting(self) -> None:
        self._tasks_path().write_text(
            "# Tasks\n\n## Phase 1: Foundation\n\n"
            "- [ ] T001 Title\n"
            "    - outer\n"
            "      - nested deeper\n",
            encoding="utf-8",
        )

        feature = self._feature()

        self.assertEqual(feature.phases[0].tasks[0].description, "- outer\n  - nested deeper")

    def test_body_stops_at_a_nested_checkbox_task(self) -> None:
        self._tasks_path().write_text(
            "# Tasks\n\n## Phase 1: Foundation\n\n"
            "- [ ] T001 Title\n"
            "  - kept line\n"
            "  - [ ] T002 Nested task\n",
            encoding="utf-8",
        )

        feature = self._feature()

        tasks = feature.phases[0].tasks
        self.assertEqual([task.identifier for task in tasks], ["T001", "T002"])
        self.assertEqual(tasks[0].description, "- kept line")


class SpecSummaryTests(unittest.TestCase):
    """The spec summary joins the Problem/Desired-outcome sections when present."""

    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _spec_path(self) -> Path:
        return self.fixture_root / "specs/001-local-projection/spec.md"

    def _feature(self):
        return parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")

    def test_summary_joins_both_sections_with_a_blank_line(self) -> None:
        feature = self._feature()

        self.assertEqual(
            feature.summary,
            "## Problem and affected users\n\n"
            "PMs reading Linear cannot tell what a feature does without opening the\n"
            "repository: the Project card carries only a file link.\n\n"
            "## Desired outcome\n\n"
            "Every projected Project and Issue carries enough prose that a PM\n"
            "understands the feature and each task without leaving Linear.",
        )

    def test_summary_with_only_one_section_present(self) -> None:
        self._spec_path().write_text(
            "# Local projection\n\n## Desired outcome\n\nJust the outcome.\n\n## Other\n\nUnrelated.\n",
            encoding="utf-8",
        )

        feature = self._feature()

        self.assertEqual(feature.summary, "## Desired outcome\n\nJust the outcome.")

    def test_summary_is_empty_when_neither_section_is_present(self) -> None:
        self._spec_path().write_text(
            "# Local projection\n\n## Overview\n\nSomething else entirely.\n",
            encoding="utf-8",
        )

        feature = self._feature()

        self.assertEqual(feature.summary, "")
