from __future__ import annotations

import copy
import unittest
import uuid
from dataclasses import replace

from spec_kit_linear.allowlist import ALLOWED_INPUTS, PUSH_MUTATIONS
from spec_kit_linear.bridge import merge_managed_block
from spec_kit_linear.config import load_config, repository_binding
from spec_kit_linear.errors import AppError, Diagnostic
from spec_kit_linear.linear_client import RemoteBinding, RemoteIssue, RemoteProject
from spec_kit_linear.parser import parse_feature
from spec_kit_linear.planner import build_push_plan, snapshot_from_discovery
from spec_kit_linear.projection import project_feature
from spec_kit_linear.reconciler import apply_plan
from spec_kit_linear.remote_discovery import AdoptedResource, FeatureAdoption, RemoteDiscovery
from spec_kit_linear.work_state import STATE_COMPLETED, STATE_REVIEW, STATE_STARTED, STATE_UNSTARTED, TaskWorkState
from tests.support.fixtures import copy_consumer_fixture


COMPLETED_STATE_ID = "77777777-7777-4777-8777-777777777777"
OPEN_STATE_ID = "88888888-8888-4888-8888-888888888888"
STARTED_STATE_ID = "99999999-9999-4999-8999-999999999999"
REVIEW_STATE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class _MemoryApplyTransport:
    def __init__(self, snapshot: dict[str, object], *, timeout_first_create: bool = False) -> None:
        self.snapshot = snapshot
        self.timeout_first_create = timeout_first_create
        self.operations: list[dict[str, object]] = []
        self._sequence = 0

    def provider(self) -> dict[str, object]:
        return copy.deepcopy(self.snapshot)

    def execute(self, operation: dict[str, object]) -> dict[str, object]:
        self.operations.append(copy.deepcopy(operation))
        self._sequence += 1
        kind = str(operation["kind"])
        target = str(operation["target"])
        if kind.endswith(".create"):
            resource = {"identity": target, "id": operation["input"]["id"], "updated_at": f"2099-01-01T00:00:{self._sequence:02d}Z"}
            self.snapshot["resources"].append(resource)
            if self.timeout_first_create and self._sequence == 1:
                raise AppError("simulated response loss", code=8, category="transport", diagnostics=[])
            return {"id": resource["id"]}
        return {}


class _TimeoutUpdateTransport:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self.snapshot = snapshot
        self.operations: list[dict[str, object]] = []

    def provider(self) -> dict[str, object]:
        return copy.deepcopy(self.snapshot)

    def execute(self, operation: dict[str, object]) -> dict[str, object]:
        self.operations.append(copy.deepcopy(operation))
        raise AppError("simulated update response loss", code=8, category="transport", diagnostics=[])


class PlannerApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.root = copy_consumer_fixture()
        self.config, _ = load_config(self.root)
        feature = parse_feature(self.root, self.root / "specs/001-local-projection")
        self.desired, _ = project_feature(feature, repository_binding(self.config))
        self.binding = RemoteBinding(
            workspace_id="11111111-1111-4111-8111-111111111111",
            team_id="22222222-2222-4222-8222-222222222222",
            team_key="WOR",
            project_label_group_id="33333333-3333-4333-8333-333333333333",
            project_label_group_name="Repository",
            project_label_id="44444444-4444-4444-8444-444444444444",
            project_label_name="sample-repository",
            project_label_parent_id="33333333-3333-4333-8333-333333333333",
            project_view_id="55555555-5555-4555-8555-555555555555",
            project_view_type="project",
            project_view_shared=True,
            issue_view_id="66666666-6666-4666-8666-666666666666",
            issue_view_type="issue",
            issue_view_shared=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _missing_discovery(self) -> RemoteDiscovery:
        feature = self.desired.feature
        adoption = FeatureAdoption(
            feature=feature.identifier,
            project=None,
            tasks={},
            drift=(),
            _expected_tasks=tuple(task.identity for task in feature.tasks),
        )
        return RemoteDiscovery(binding=self.binding, projects=(), features=(adoption,))

    def _complete_discovery(self, *, drift: tuple[Diagnostic, ...] = (), state_ids: dict[str, str] | None = None) -> RemoteDiscovery:
        feature = self.desired.feature
        issues = tuple(
            RemoteIssue(
                id=f"issue-{task.identity}", identifier=f"WOR-{index + 1}", title=task.title, description=task.managed_description,
                updated_at="2099-01-01T00:00:00Z", project_id="project-1",
                parent_id=None, assignee_id="manual-assignee", label_ids=("human-label",), state_id=(state_ids or {}).get(task.identity),
            )
            for index, task in enumerate(feature.tasks)
        )
        project = RemoteProject(
            id="project-1", name=feature.project_title, description=feature.managed_description,
            updated_at="2099-01-01T00:00:00Z", team_ids=(self.binding.team_id,), label_ids=(self.binding.project_label_id,),
            issues=issues, lead_id="manual-lead", member_ids=("manual-member",), content=feature.content_block,
        )
        adoption = FeatureAdoption(
            feature=feature.identifier,
            project=AdoptedResource("feature_project", feature.project_identity, "project-1", project.updated_at),
            tasks={task.identity: AdoptedResource("task_issue", task.identity, f"issue-{task.identity}", "2099-01-01T00:00:00Z") for task in feature.tasks},
            drift=drift,
            _expected_tasks=tuple(task.identity for task in feature.tasks),
        )
        return RemoteDiscovery(binding=self.binding, projects=(project,), features=(adoption,))

    def _push_plan(self, discovery: RemoteDiscovery | None = None) -> dict[str, object]:
        return build_push_plan(self.desired, discovery or self._missing_discovery(), config=self.config)

    def test_plan_is_project_then_issues_and_only_uses_allowlisted_inputs(self) -> None:
        plan = self._push_plan()
        same = self._push_plan()

        self.assertEqual(plan["snapshot"], same["snapshot"])
        self.assertEqual(plan["desired"], same["desired"])
        self.assertEqual(
            [(item["kind"], item["target"], item["reason"]) for item in plan["operations"]],
            [(item["kind"], item["target"], item["reason"]) for item in same["operations"]],
        )
        self.assertEqual(plan["snapshot"]["hash"], snapshot_from_discovery(self._missing_discovery(), self.desired)["hash"])
        # No intermediate level: one Project create, then one Issue create per Txxx.
        self.assertEqual([item["kind"] for item in plan["operations"]], ["project.create", "issue.create", "issue.create", "issue.create"])
        for operation in plan["operations"]:
            self.assertIn(operation["kind"], PUSH_MUTATIONS)
            self.assertEqual(sorted(operation["input"]), operation["allowed_input_fields"])
            self.assertTrue(set(operation["input"]).issubset(ALLOWED_INPUTS[operation["kind"]]))
            self.assertNotIn("assigneeId", operation["input"])
            self.assertNotIn("leadId", operation["input"])
            self.assertNotIn("memberIds", operation["input"])
            self.assertNotIn("projectMilestoneId", operation["input"])
            if operation["kind"].endswith(".create"):
                self.assertEqual(str(uuid.UUID(operation["input"]["id"])).lower(), operation["input"]["id"])
                self.assertEqual(uuid.UUID(operation["input"]["id"]).version, 4)
            else:
                self.assertNotIn("id", operation["input"])
        self.assertEqual(plan["preserved_fields"][:3], ["taskAssigneeId", "projectLead", "projectMembers"])

    def test_issue_creates_reference_the_project_and_nothing_else(self) -> None:
        plan = self._push_plan()
        creates = [item for item in plan["operations"] if item["kind"] == "issue.create"]

        for operation in creates:
            self.assertEqual(operation["input"]["projectId"], {"$ref": "feature:001"})
            self.assertEqual(operation["preconditions"], {"absent": True, "project": "feature:001"})

    def test_updates_keep_remote_id_out_of_graphql_input(self) -> None:
        complete = self._complete_discovery()
        changed_project = replace(complete.projects[0], name="Manually changed title")
        discovery = replace(complete, projects=(changed_project,))
        plan = self._push_plan(discovery)
        update = next(item for item in plan["operations"] if item["kind"] == "project.update")
        self.assertNotIn("id", update["input"])
        self.assertEqual(update["preconditions"]["id"], "project-1")

    def test_apply_revalidates_every_create_and_a_second_plan_is_empty(self) -> None:
        plan = self._push_plan()
        transport = _MemoryApplyTransport(copy.deepcopy(plan["snapshot"]))

        result = apply_plan(plan, snapshot_provider=transport.provider, transport=transport)

        self.assertEqual(result.writes, 4)
        self.assertEqual(len(transport.operations), 4)
        # Idempotence: against the resulting remote state the next plan has
        # nothing left to do.
        self.assertEqual(build_push_plan(self.desired, self._complete_discovery(), config=self.config)["operations"], [])

    def test_a_stale_snapshot_fails_before_any_write(self) -> None:
        plan = self._push_plan()
        transport = _MemoryApplyTransport(copy.deepcopy(plan["snapshot"]))
        transport.snapshot["resources"][0]["id"] = "changed-workspace"

        with self.assertRaises(AppError) as raised:
            apply_plan(plan, snapshot_provider=transport.provider, transport=transport)

        self.assertEqual(raised.exception.code, 6)
        self.assertEqual(raised.exception.diagnostics[0].code, "snapshot_stale")
        self.assertEqual(transport.operations, [])

    def test_post_apply_visibility_failure_uses_code_10(self) -> None:
        plan = self._push_plan()

        class _VanishingCreateTransport(_MemoryApplyTransport):
            def __init__(self, snapshot: dict[str, object], *, total_operations: int) -> None:
                super().__init__(snapshot)
                self._total_operations = total_operations

            def provider(self) -> dict[str, object]:
                result = super().provider()
                # Sabotage only the mandatory read after every operation has
                # already executed (the "final_snapshot" check), not any of
                # the per-operation staleness reads that precede it.
                if len(self.operations) == self._total_operations:
                    result["resources"] = [item for item in result["resources"] if item["identity"] != self.desired_feature_identity]
                return result

        transport = _VanishingCreateTransport(copy.deepcopy(plan["snapshot"]), total_operations=len(plan["operations"]))
        transport.desired_feature_identity = self.desired.feature.project_identity

        with self.assertRaises(AppError) as raised:
            apply_plan(plan, snapshot_provider=transport.provider, transport=transport)

        self.assertEqual(raised.exception.code, 10)
        self.assertEqual(raised.exception.diagnostics[0].code, "post_apply_visibility")

    def test_post_apply_verification_failure_uses_code_10(self) -> None:
        plan = self._push_plan()
        transport = _MemoryApplyTransport(copy.deepcopy(plan["snapshot"]))

        with self.assertRaises(AppError) as raised:
            apply_plan(plan, snapshot_provider=transport.provider, transport=transport, post_verify=lambda _snapshot: False)

        self.assertEqual(raised.exception.code, 10)
        self.assertEqual(raised.exception.diagnostics[0].code, "post_apply_verification")

    def test_ambiguous_timeout_reads_identity_before_any_retry(self) -> None:
        plan = self._push_plan()
        transport = _MemoryApplyTransport(copy.deepcopy(plan["snapshot"]), timeout_first_create=True)

        result = apply_plan(plan, snapshot_provider=transport.provider, transport=transport)

        self.assertEqual(len(result.recovered_operation_ids), 1)
        first_target = transport.operations[0]["target"]
        self.assertEqual(sum(1 for operation in transport.operations if operation["target"] == first_target), 1)

    def test_ambiguous_update_timeout_fails_closed_without_false_recovery(self) -> None:
        complete = self._complete_discovery()
        changed_project = replace(complete.projects[0], name="Manually changed title")
        discovery = replace(complete, projects=(changed_project,))
        plan = self._push_plan(discovery)
        transport = _TimeoutUpdateTransport(copy.deepcopy(plan["snapshot"]))

        with self.assertRaises(AppError) as raised:
            apply_plan(plan, snapshot_provider=transport.provider, transport=transport)

        self.assertEqual(raised.exception.category, "transport")
        self.assertEqual(len(transport.operations), 1)

    def test_duplicate_or_backward_drift_fails_closed_with_no_mutation_path(self) -> None:
        drift = (Diagnostic("remote_marker_duplicate", "duplicate bridge marker"),)
        with self.assertRaises(AppError) as raised:
            self._push_plan(self._complete_discovery(drift=drift))
        self.assertEqual(raised.exception.code, 6)

    def test_manual_assignee_project_lead_and_members_are_preserved(self) -> None:
        discovery = self._complete_discovery()
        project = discovery.projects[0]
        self.assertEqual(project.lead_id, "manual-lead")
        self.assertEqual(project.member_ids, ("manual-member",))
        self.assertTrue(all(issue.assignee_id == "manual-assignee" for issue in project.issues))
        plan = self._push_plan(discovery)
        self.assertEqual(plan["operations"], [])

    def test_lifecycle_state_is_projected_from_the_tasks_md_checkbox(self) -> None:
        config = dict(self.config)
        config["lifecycle"] = {
            "completed_state_id": "77777777-7777-4777-8777-777777777777",
            "open_state_id": "88888888-8888-4888-8888-888888888888",
        }
        plan = build_push_plan(self.desired, self._complete_discovery(), config=config)

        lifecycle_updates = {item["target"]: item["input"]["stateId"] for item in plan["operations"] if item["kind"] == "issue.lifecycle.update"}
        # T002 is the only checked task in the fixture.
        self.assertEqual(lifecycle_updates["task:001:T002"], "77777777-7777-4777-8777-777777777777")
        self.assertEqual(lifecycle_updates["task:001:T001"], "88888888-8888-4888-8888-888888888888")

    def _lifecycle_config(self, **overrides: str) -> dict[str, object]:
        config = dict(self.config)
        lifecycle = {
            "completed_state_id": COMPLETED_STATE_ID,
            "open_state_id": OPEN_STATE_ID,
            "started_state_id": STARTED_STATE_ID,
            "review_state_id": REVIEW_STATE_ID,
        }
        lifecycle.update(overrides)
        config["lifecycle"] = {key: value for key, value in lifecycle.items() if value}
        return config

    def _work_states(self, **states: str) -> dict[str, TaskWorkState]:
        return {f"task:001:{task}": TaskWorkState(state, "test") for task, state in states.items()}

    def test_each_derived_state_projects_onto_its_configured_workflow_state(self) -> None:
        work_states = self._work_states(T001=STATE_STARTED, T002=STATE_COMPLETED, T003=STATE_REVIEW)

        plan = build_push_plan(self.desired, self._complete_discovery(), config=self._lifecycle_config(), work_states=work_states)

        updates = {item["target"]: item["input"]["stateId"] for item in plan["operations"] if item["kind"] == "issue.lifecycle.update"}
        self.assertEqual(updates["task:001:T001"], STARTED_STATE_ID)
        self.assertEqual(updates["task:001:T002"], COMPLETED_STATE_ID)
        self.assertEqual(updates["task:001:T003"], REVIEW_STATE_ID)

    def test_a_team_without_an_in_review_state_degrades_review_onto_in_progress(self) -> None:
        config = self._lifecycle_config(review_state_id="")
        work_states = self._work_states(T001=STATE_REVIEW, T002=STATE_COMPLETED, T003=STATE_UNSTARTED)

        plan = build_push_plan(self.desired, self._complete_discovery(), config=config, work_states=work_states)

        updates = {item["target"]: item["input"]["stateId"] for item in plan["operations"] if item["kind"] == "issue.lifecycle.update"}
        self.assertEqual(updates["task:001:T001"], STARTED_STATE_ID)

    def test_an_unconfigured_intermediate_state_leaves_the_issue_untouched(self) -> None:
        config = self._lifecycle_config(started_state_id="", review_state_id="")
        work_states = self._work_states(T001=STATE_STARTED, T002=STATE_COMPLETED, T003=STATE_REVIEW)

        plan = build_push_plan(self.desired, self._complete_discovery(), config=config, work_states=work_states)

        updates = {item["target"] for item in plan["operations"] if item["kind"] == "issue.lifecycle.update"}
        self.assertEqual(updates, {"task:001:T002"})

    def test_a_second_pass_over_the_derived_states_renders_no_operation_at_all(self) -> None:
        config = self._lifecycle_config()
        work_states = self._work_states(T001=STATE_STARTED, T002=STATE_COMPLETED, T003=STATE_REVIEW)
        settled = self._complete_discovery(
            state_ids={"task:001:T001": STARTED_STATE_ID, "task:001:T002": COMPLETED_STATE_ID, "task:001:T003": REVIEW_STATE_ID}
        )

        plan = build_push_plan(self.desired, settled, config=config, work_states=work_states)

        self.assertEqual(plan["operations"], [])

    def test_a_new_issue_is_created_directly_in_its_derived_state(self) -> None:
        work_states = self._work_states(T001=STATE_REVIEW, T002=STATE_COMPLETED, T003=STATE_STARTED)

        plan = build_push_plan(self.desired, self._missing_discovery(), config=self._lifecycle_config(), work_states=work_states)

        creates = {item["target"]: item["input"]["stateId"] for item in plan["operations"] if item["kind"] == "issue.create"}
        self.assertEqual(creates["task:001:T001"], REVIEW_STATE_ID)
        self.assertEqual(creates["task:001:T003"], STARTED_STATE_ID)

    def test_a_fresh_create_carries_the_content_block(self) -> None:
        plan = self._push_plan()

        create = next(item for item in plan["operations"] if item["kind"] == "project.create")
        self.assertEqual(create["input"]["content"], self.desired.feature.content_block)

    def test_an_unchanged_summary_hash_plans_no_content_write(self) -> None:
        plan = self._push_plan(self._complete_discovery())

        self.assertEqual([item for item in plan["operations"] if item["kind"] == "project.update"], [])

    def test_a_changed_summary_hash_plans_a_content_merge(self) -> None:
        complete = self._complete_discovery()
        stale_content = (
            "<!-- speckit-linear:feature:001 -->\n<!-- speckit-linear:summary-hash:000000000000 -->\n"
            "stale prose\n<!-- /speckit-linear -->"
        )
        changed_project = replace(complete.projects[0], content=stale_content)
        discovery = replace(complete, projects=(changed_project,))

        plan = self._push_plan(discovery)

        update = next(item for item in plan["operations"] if item["kind"] == "project.update")
        self.assertEqual(
            update["input"]["content"],
            merge_managed_block(stale_content, self.desired.feature.project_marker, self.desired.feature.content_block),
        )

    def test_an_empty_summary_with_a_remote_block_plans_its_removal(self) -> None:
        # The spec's Problem/Desired-outcome sections were removed locally --
        # the desired content block is now empty -- but Linear still carries
        # the block from a previous push. A removal that empties the whole
        # document must send " ", not "": Linear treats a content write of
        # "" as a no-op, which would leave the stale block replanning forever.
        desired_without_summary = replace(self.desired, feature=replace(self.desired.feature, content_block="", summary_hash=""))
        complete = self._complete_discovery()

        plan = build_push_plan(desired_without_summary, complete, config=self.config)

        update = next(item for item in plan["operations"] if item["kind"] == "project.update")
        self.assertEqual(update["input"]["content"], " ")

    def test_human_text_outside_the_content_block_survives_the_merge(self) -> None:
        marker = self.desired.feature.project_marker
        stale_block = f"<!-- {marker} -->\n<!-- speckit-linear:summary-hash:000000000000 -->\nstale\n<!-- /speckit-linear -->"
        original = f"Manual introduction\n{stale_block}\nManual closing"
        complete = self._complete_discovery()
        changed_project = replace(complete.projects[0], content=original)
        discovery = replace(complete, projects=(changed_project,))

        plan = self._push_plan(discovery)

        update = next(item for item in plan["operations"] if item["kind"] == "project.update")
        merged = update["input"]["content"]
        self.assertTrue(merged.startswith("Manual introduction\n"))
        self.assertTrue(merged.endswith("\nManual closing"))
        self.assertIn(self.desired.feature.content_block, merged)

    def test_bridge_block_update_preserves_manual_exterior_text(self) -> None:
        marker = self.desired.feature.project_marker
        original = f"Manual introduction\n<!-- {marker} -->\nold bridge text\n<!-- /speckit-linear -->\nManual closing"
        replacement = self.desired.feature.managed_description
        merged = merge_managed_block(original, marker, replacement)
        self.assertTrue(merged.startswith("Manual introduction\n"))
        self.assertTrue(merged.endswith("\nManual closing"))
        self.assertIn(replacement, merged)
        with self.assertRaises(AppError):
            merge_managed_block(f"Manual\n<!-- {marker} -->\nunsafe", marker, replacement)


if __name__ == "__main__":
    unittest.main()
