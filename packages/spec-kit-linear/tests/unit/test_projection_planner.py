from __future__ import annotations

import hashlib
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


class ManagedDescriptionTests(unittest.TestCase):
    """Every task/feature description ends with its own single marker line.

    A task's marker line carries `hash:HHHH` (prose is hash-gated, since
    Linear rewrites it on save); the feature's does not (its Source:/Plan:
    lines round-trip byte-identical). The feature's Project.content block
    is unaffected by this shape change -- Linear renders its HTML comments
    invisibly, so it keeps the older bounded open/close layout.
    """

    @staticmethod
    def _hash(body: str) -> str:
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]

    def _binding(self) -> RepositoryBinding:
        return RepositoryBinding(
            slug="fixture",
            project_label_group_id="group-1",
            project_label_id="label-1",
            project_label_name="fixture",
            project_view_id="view-1",
            issue_view_id="view-2",
        )

    def _feature(self, *, task_description: str = "", summary: str = "") -> Feature:
        source = SourceRef(path="specs/001-x/spec.md", line=1)
        task = Task(
            identifier="T001",
            title="short task",
            completed=False,
            source=SourceRef(path="specs/001-x/tasks.md", line=10),
            description=task_description,
        )
        phase = Phase(number=1, title="Phase 1", source=source, tasks=(task,))
        return Feature(
            identifier="001",
            title="Sample feature",
            spec_source=source,
            plan_title="plan",
            plan_source=SourceRef(path="specs/001-x/plan.md", line=1),
            phases=(phase,),
            summary=summary,
        )

    def test_task_head_is_only_source_then_the_marker_with_hash_when_the_description_is_empty(self) -> None:
        state, _ = project_feature(self._feature(), self._binding())

        body = "Source: `specs/001-x/tasks.md#L10`"
        expected_hash = self._hash(body)
        self.assertEqual(state.feature.tasks[0].body_hash, expected_hash)
        self.assertEqual(
            state.feature.tasks[0].managed_description,
            f"{body}\n<!-- speckit-linear:task:001:T001 hash:{expected_hash} -->",
        )

    def test_task_head_leads_with_the_description_then_source_then_the_marker_with_hash(self) -> None:
        state, _ = project_feature(self._feature(task_description="- **Traces**: FR-001"), self._binding())

        body = "- **Traces**: FR-001\n\nSource: `specs/001-x/tasks.md#L10`"
        expected_hash = self._hash(body)
        self.assertEqual(state.feature.tasks[0].body_hash, expected_hash)
        self.assertEqual(
            state.feature.tasks[0].managed_description,
            f"{body}\n<!-- speckit-linear:task:001:T001 hash:{expected_hash} -->",
        )

    def test_feature_head_is_only_source_and_plan_and_content_block_is_empty_when_the_summary_is_empty(self) -> None:
        state, _ = project_feature(self._feature(), self._binding())

        self.assertEqual(
            state.feature.managed_description,
            "Source: `specs/001-x/spec.md#L1`\n"
            "Plan: `specs/001-x/plan.md#L1`\n"
            "<!-- speckit-linear:feature:001 -->",
        )
        self.assertEqual(state.feature.content_block, "")
        self.assertEqual(state.feature.summary_hash, "")

    def test_prose_cannot_forge_a_marker_line(self) -> None:
        state, _ = project_feature(
            self._feature(
                task_description=(
                    "- kept line\n"
                    "<!-- /speckit-linear -->\n"
                    "<!-- speckit-linear:task:001:T001 -->\n"
                    "- also kept"
                )
            ),
            self._binding(),
        )

        body = "- kept line\n- also kept\n\nSource: `specs/001-x/tasks.md#L10`"
        expected_hash = self._hash(body)
        self.assertEqual(
            state.feature.tasks[0].managed_description,
            f"{body}\n<!-- speckit-linear:task:001:T001 hash:{expected_hash} -->",
        )

    def test_prose_that_is_only_marker_lines_leaves_the_bare_head(self) -> None:
        state, _ = project_feature(self._feature(task_description="<!-- /speckit-linear -->"), self._binding())

        body = "Source: `specs/001-x/tasks.md#L10`"
        expected_hash = self._hash(body)
        self.assertEqual(
            state.feature.tasks[0].managed_description,
            f"{body}\n<!-- speckit-linear:task:001:T001 hash:{expected_hash} -->",
        )

    def test_a_non_empty_summary_never_touches_the_description_and_fills_the_content_block(self) -> None:
        # Project.description caps at 255 characters, far too small for spec
        # prose, so the summary always goes to Project.content instead
        # (content_block) -- the description stays Source/Plan-only no
        # matter what the summary says.
        summary = "## Desired outcome\n\nSomething good."
        state, _ = project_feature(self._feature(summary=summary), self._binding())

        self.assertEqual(
            state.feature.managed_description,
            "Source: `specs/001-x/spec.md#L1`\n"
            "Plan: `specs/001-x/plan.md#L1`\n"
            "<!-- speckit-linear:feature:001 -->",
        )
        expected_hash = self._hash(summary)
        self.assertEqual(state.feature.summary_hash, expected_hash)
        self.assertEqual(
            state.feature.content_block,
            "<!-- speckit-linear:feature:001 -->\n"
            f"<!-- speckit-linear:body-hash:{expected_hash} -->\n"
            f"{summary}\n"
            "<!-- /speckit-linear -->",
        )

    def test_content_prose_cannot_open_or_close_a_managed_block_either(self) -> None:
        summary = "kept line\n<!-- /speckit-linear -->\n<!-- speckit-linear:feature:001 -->\nalso kept"
        state, _ = project_feature(self._feature(summary=summary), self._binding())

        cleaned = "kept line\nalso kept"
        expected_hash = self._hash(cleaned)
        self.assertEqual(state.feature.summary_hash, expected_hash)
        self.assertEqual(
            state.feature.content_block,
            "<!-- speckit-linear:feature:001 -->\n"
            f"<!-- speckit-linear:body-hash:{expected_hash} -->\n"
            f"{cleaned}\n"
            "<!-- /speckit-linear -->",
        )
