from __future__ import annotations

import unittest

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
