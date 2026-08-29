from __future__ import annotations

import json
import unittest
from pathlib import Path

from spec_kit_linear.config import load_config, repository_binding
from spec_kit_linear.parser import parse_feature
from spec_kit_linear.domain import Feature, Phase, RepositoryBinding, SourceRef, Task
from spec_kit_linear.projection import ISSUE_TITLE_LIMIT, PROJECT_NAME_LIMIT, project_feature
from tests.support.fixtures import copy_consumer_fixture


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _desired(self):
        config, _ = load_config(self.fixture_root)
        feature = parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")
        return project_feature(feature, repository_binding(config))[0]

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


class TitleClipTests(unittest.TestCase):
    """Linear caps Project names at 80 and Issue titles at 255 characters."""

    def _binding(self) -> RepositoryBinding:
        return RepositoryBinding(
            slug="fixture",
            project_label_group_id="group-1",
            project_label_id="label-1",
            project_label_name="fixture",
            project_view_id="view-1",
            issue_view_id="view-2",
        )

    def _feature(self, title: str, task_title: str = "short task") -> Feature:
        source = SourceRef(path="specs/001-x/spec.md", line=1)
        task = Task(identifier="T001", title=task_title, completed=False, source=SourceRef(path="specs/001-x/tasks.md", line=10))
        phase = Phase(number=1, title="Phase 1", source=source, tasks=(task,))
        return Feature(
            identifier="001",
            title=title,
            spec_source=source,
            plan_title="plan",
            plan_source=SourceRef(path="specs/001-x/plan.md", line=1),
            phases=(phase,),
        )

    def test_a_fitting_project_name_is_projected_verbatim_with_no_warning(self) -> None:
        state, warnings = project_feature(self._feature("a" * 75), self._binding())

        self.assertEqual(state.feature.project_title, "001: " + "a" * 75)
        self.assertEqual(warnings, ())

    def test_an_over_long_project_name_is_clipped_to_80_with_a_warning(self) -> None:
        state, warnings = project_feature(self._feature("a" * 85), self._binding())

        self.assertEqual(len(state.feature.project_title), PROJECT_NAME_LIMIT)
        self.assertTrue(state.feature.project_title.endswith("…"))
        self.assertEqual([item.code for item in warnings], ["linear_title_clipped"])
        self.assertIn("80-character limit", warnings[0].message)
        self.assertIn("specs/001-x/spec.md#L1", warnings[0].message)

    def test_an_over_long_issue_title_is_clipped_to_255_with_a_warning(self) -> None:
        state, warnings = project_feature(self._feature("short", task_title="b" * 300), self._binding())

        self.assertEqual(len(state.feature.tasks[0].title), ISSUE_TITLE_LIMIT)
        self.assertEqual([item.code for item in warnings], ["linear_title_clipped"])
        self.assertIn("255-character limit", warnings[0].message)
        self.assertIn("specs/001-x/tasks.md#L10", warnings[0].message)

    def test_clipping_is_idempotent_for_reconciliation(self) -> None:
        first, _ = project_feature(self._feature("a" * 200), self._binding())
        second, _ = project_feature(self._feature("a" * 200), self._binding())

        self.assertEqual(first.feature.project_title, second.feature.project_title)
        self.assertEqual(len(first.feature.project_title), PROJECT_NAME_LIMIT)
