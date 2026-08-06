from __future__ import annotations

import json
import unittest
from pathlib import Path

from spec_kit_linear.config import load_config, repository_binding
from spec_kit_linear.parser import parse_feature
from spec_kit_linear.projection import project_feature
from tests.support.fixtures import copy_consumer_fixture


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _desired(self):
        config, _ = load_config(self.fixture_root)
        feature = parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")
        return project_feature(feature, repository_binding(config))

    def test_projection_is_project_then_issues_with_no_intermediate_level(self) -> None:
        rendered = self._desired().as_dict()

        self.assertEqual(rendered["repository"]["project_label"]["name"], "sample-repository")
        self.assertEqual([view["kind"] for view in rendered["repository"]["shared_views"]], ["project", "issue"])
        self.assertEqual(rendered["feature"]["project"]["identity"], "feature:001")
        self.assertNotIn("milestones", rendered["feature"])
        self.assertEqual(
            [task["identity"] for task in rendered["feature"]["tasks"]],
            ["task:001:T001", "task:001:T002", "task:001:T003"],
        )
        # Every task hangs directly off the feature's Project.
        self.assertEqual({task["project_identity"] for task in rendered["feature"]["tasks"]}, {"feature:001"})

    def test_projection_flattens_tasks_md_phases_in_document_order(self) -> None:
        # `tasks.md` phases are a document structure, not a projected
        # resource: T003 lives under "Phase 2" in the fixture and still
        # follows T002 directly.
        rendered = self._desired().as_dict()
        self.assertEqual([task["title"].split(" ", 1)[0] for task in rendered["feature"]["tasks"]], ["T001", "T002", "T003"])

    def test_projection_is_deterministic_and_matches_the_golden_render(self) -> None:
        rendered = self._desired().as_dict()
        self.assertEqual(rendered, self._desired().as_dict())
        golden_path = Path(__file__).parents[1] / "golden" / "local-projection.json"
        self.assertEqual(rendered, json.loads(golden_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
