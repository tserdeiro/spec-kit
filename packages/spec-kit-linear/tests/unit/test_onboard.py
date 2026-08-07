from __future__ import annotations

import inspect
import json
import tempfile
import unittest

from tests.support.fixtures import isolate_operator_global_env
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spec_kit_linear import cli as cli_module
from spec_kit_linear.cli import main
from spec_kit_linear.config import load_yaml_subset
from spec_kit_linear.linear_client import (
    RemoteBinding,
    RemoteGitAutomationState,
    RemoteProjectLabel,
    RemoteSharedView,
    RemoteTeamSummary,
    RemoteWorkflowState,
)


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
TEAM_ID = "22222222-2222-4222-8222-222222222222"
GROUP_ID = "33333333-3333-4333-8333-333333333333"
LABEL_ID = "44444444-4444-4444-8444-444444444444"
PROJECT_VIEW_ID = "55555555-5555-4555-8555-555555555555"
ISSUE_VIEW_ID = "66666666-6666-4666-8666-666666666666"
COMPLETED_STATE_ID = "77777777-7777-4777-8777-777777777777"
OPEN_STATE_ID = "88888888-8888-4888-8888-888888888888"
STARTED_STATE_ID = "99999999-9999-4999-8999-999999999999"
REVIEW_STATE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SLUG = "spec-kit"


def _full_binding() -> RemoteBinding:
    return RemoteBinding(
        workspace_id=WORKSPACE_ID,
        team_id=TEAM_ID,
        team_key="WOR",
        project_label_group_id=GROUP_ID,
        project_label_group_name="Repository",
        project_label_id=LABEL_ID,
        project_label_name=SLUG,
        project_label_parent_id=GROUP_ID,
        project_view_id=PROJECT_VIEW_ID,
        project_view_type="project",
        project_view_shared=True,
        issue_view_id=ISSUE_VIEW_ID,
        issue_view_type="issue",
        issue_view_shared=True,
    )


class _OnboardClient:
    """Fake client for `onboard`'s resolution and its single remote write.

    `mutation` asserts the operation kind: anything but the three additive
    onboard creates (automation mapping, repository label, shared view)
    fails the test — the structural guarantee of onboard's write surface."""

    def __init__(
        self,
        *,
        workspace_id: str = WORKSPACE_ID,
        teams: tuple[RemoteTeamSummary, ...] = (),
        project_labels: tuple[RemoteProjectLabel, ...] = (),
        shared_views: tuple[RemoteSharedView, ...] = (),
        workflow_states: tuple[RemoteWorkflowState, ...] = (),
        binding: RemoteBinding | None = None,
        git_automation_states: tuple[RemoteGitAutomationState, ...] = (),
        github_integration: bool = True,
    ) -> None:
        self.workspace_id = workspace_id
        self._teams_by_id = {team.id: team for team in teams}
        self._teams_by_key: dict[str, list[RemoteTeamSummary]] = {}
        for team in teams:
            self._teams_by_key.setdefault(team.key, []).append(team)
        self._project_labels = project_labels
        self._shared_views = shared_views
        self._workflow_states = workflow_states
        self._binding = binding
        self._git_automation_states = git_automation_states
        self._github_integration = github_integration
        self.inspect_binding_calls = 0
        self.find_workflow_states_by_team_calls: list[str] = []
        self.find_git_automation_states_calls: list[str] = []
        self.mutations: list[tuple[str, dict[str, object]]] = []

    def find_git_automation_states(self, team_id: str) -> tuple[RemoteGitAutomationState, ...]:
        self.find_git_automation_states_calls.append(team_id)
        return self._git_automation_states

    def has_github_integration(self) -> bool:
        return self._github_integration

    _MUTATION_RESULTS = {
        "team.automation.create": ("gitAutomationStateCreate", "gitAutomationState"),
        "project.label.create": ("projectLabelCreate", "projectLabel"),
        "view.create": ("customViewCreate", "customView"),
    }

    def mutation(self, document: str, variables: dict[str, object], operation_kind: str | None = None) -> dict[str, object]:
        if operation_kind not in self._MUTATION_RESULTS:
            raise AssertionError(f"onboard may only create bindings and PR-automation mappings, got {operation_kind!r}")
        self.mutations.append((operation_kind, variables))
        result_key, resource_key = self._MUTATION_RESULTS[operation_kind]
        return {result_key: {"success": True, resource_key: {"id": f"created-{len(self.mutations)}"}}}

    def resolve_workspace_id(self) -> str:
        return self.workspace_id

    def resolve_team_by_id(self, team_id: str) -> RemoteTeamSummary:
        return self._teams_by_id[team_id]

    def find_team_by_key(self, key: str) -> tuple[RemoteTeamSummary, ...]:
        return tuple(self._teams_by_key.get(key, ()))

    def find_project_labels_by_name(self, name: str) -> tuple[RemoteProjectLabel, ...]:
        return tuple(item for item in self._project_labels if item.name == name)

    def find_shared_views_by_name(self, name: str) -> tuple[RemoteSharedView, ...]:
        return tuple(item for item in self._shared_views if item.name == name)

    def find_workflow_states_by_team(self, team_id: str) -> tuple[RemoteWorkflowState, ...]:
        self.find_workflow_states_by_team_calls.append(team_id)
        return self._workflow_states

    def inspect_binding(self, config: object) -> RemoteBinding:
        self.inspect_binding_calls += 1
        if self._binding is not None:
            return self._binding
        if self.mutations:
            # The remote now holds exactly what onboard just created: echo
            # the config back as the freshly-inspectable binding.
            repository = config["repository"]  # type: ignore[index]
            linear = config["linear"]  # type: ignore[index]
            return RemoteBinding(
                workspace_id=linear["workspace_id"],
                team_id=linear["team_id"],
                team_key=linear["team_key"],
                project_label_group_id=repository["project_label_group_id"],
                project_label_group_name="Repository",
                project_label_id=repository["project_label_id"],
                project_label_name=repository["slug"],
                project_label_parent_id=repository["project_label_group_id"],
                project_view_id=repository["project_view_id"],
                project_view_type="project",
                project_view_shared=True,
                issue_view_id=repository["issue_view_id"],
                issue_view_type="issue",
                issue_view_shared=True,
            )
        raise AssertionError("inspect_binding should not have been called with a partial repository binding")


def _full_fixture_client(
    team: RemoteTeamSummary,
    *,
    workflow_states: tuple[RemoteWorkflowState, ...] = (),
    git_automation_states: tuple[RemoteGitAutomationState, ...] = (),
    github_integration: bool = True,
) -> _OnboardClient:
    group = RemoteProjectLabel(id=GROUP_ID, name="Repository", is_group=True, updated_at="2099-01-01T00:00:00Z", parent_id=None)
    label = RemoteProjectLabel(id=LABEL_ID, name=SLUG, is_group=False, updated_at="2099-01-01T00:00:00Z", parent_id=GROUP_ID)
    views = (
        RemoteSharedView(id=PROJECT_VIEW_ID, name=f"{SLUG} / Features", type="project", shared=True),
        RemoteSharedView(id=ISSUE_VIEW_ID, name=f"{SLUG} / Work", type="issue", shared=True),
    )
    return _OnboardClient(
        teams=(team,),
        project_labels=(group, label),
        shared_views=views,
        workflow_states=workflow_states,
        binding=_full_binding(),
        git_automation_states=git_automation_states,
        github_integration=github_integration,
    )


class OnboardTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _invoke(self, arguments: list[str]) -> tuple[int, dict[str, object]]:
        output = StringIO()
        with redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_onboard_requires_repository(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _OnboardClient(teams=(team,))

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--json"])

        self.assertEqual(result, 2)
        self.assertEqual(payload["diagnostics"][0]["code"], "onboard_repository_required")

    def test_onboard_requires_team(self) -> None:
        client = _OnboardClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["onboard", "--root", str(self.root), "--repository", SLUG, "--json"])

        self.assertEqual(result, 2)
        self.assertEqual(payload["diagnostics"][0]["code"], "onboard_team_required")

    def test_onboard_apply_writes_the_committed_root_config(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 0)
        self.assertFalse(payload["dry_run"])
        shared_path = Path(payload["changes"]["config_path"])
        self.assertEqual(shared_path.name, "speckit-linear.yml")
        self.assertTrue(shared_path.exists())
        written = load_yaml_subset(shared_path)
        self.assertEqual(written["repository"]["slug"], SLUG)
        self.assertEqual(written["repository"]["project_label_group_id"], GROUP_ID)
        self.assertEqual(written["repository"]["project_label_id"], LABEL_ID)
        self.assertEqual(written["repository"]["project_view_id"], PROJECT_VIEW_ID)
        self.assertEqual(written["repository"]["issue_view_id"], ISSUE_VIEW_ID)
        self.assertEqual(payload["changes"]["missing_remote_resources"], [])
        self.assertEqual(client.inspect_binding_calls, 1)

    def test_onboard_dry_run_writes_nothing(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--dry-run", "--json"]
            )

        self.assertEqual(result, 0)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(Path(payload["changes"]["config_path"]).exists())
        self.assertFalse((self.root / ".gitignore").exists())

    def test_onboard_never_configures_the_shared_config_as_gitignored(self) -> None:
        # The shared speckit-linear.yml is committed by default; onboard must
        # only ever gitignore .speckit-linear.env -- never the shared config,
        # and never a consumer's own project .env.
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 0)
        gitignore_content = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".speckit-linear.env", gitignore_content)
        self.assertNotIn("speckit-linear.yml", gitignore_content)
        self.assertNotIn(".env\n", gitignore_content.replace(".speckit-linear.env", ""))
        self.assertEqual(payload["changes"]["gitignore_entries_added"], [".speckit-linear.env"])

    def test_onboard_preserves_an_already_present_gitignore(self) -> None:
        (self.root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            self._invoke(["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"])

        content = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("node_modules/", content)
        self.assertIn(".speckit-linear.env", content)

    def test_onboard_zero_matches_reports_what_is_missing_in_linear(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _OnboardClient(teams=(team,))

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--dry-run", "--json"]
            )

        self.assertEqual(result, 0)
        self.assertEqual(client.mutations, [])
        self.assertEqual(len(payload["changes"]["binding_operations"]), 4)
        missing = payload["changes"]["missing_remote_resources"]
        self.assertIn("project_label_group", missing)
        self.assertIn("project_label", missing)
        self.assertIn("project_view", missing)
        self.assertIn("issue_view", missing)
        warning = next(item for item in payload["diagnostics"] if item["code"] == "onboard_missing_remote")
        self.assertEqual(warning["severity"], "warning")
        self.assertIn("onboard creates them when it applies", warning["message"])
        # Nothing was created remotely and no side artifact was written.
        self.assertEqual(client.inspect_binding_calls, 0)

    def test_onboard_ambiguous_label_group_aborts(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        groups = (
            RemoteProjectLabel(id="a", name="Repository", is_group=True, updated_at="2099-01-01T00:00:00Z", parent_id=None),
            RemoteProjectLabel(id="b", name="Repository", is_group=True, updated_at="2099-01-01T00:00:00Z", parent_id=None),
        )
        client = _OnboardClient(teams=(team,), project_labels=groups)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 6)
        self.assertEqual(payload["diagnostics"][0]["code"], "project_label_group_ambiguous")

    def test_onboard_ambiguous_shared_view_aborts(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        views = (
            RemoteSharedView(id="a", name=f"{SLUG} / Features", type="project", shared=True),
            RemoteSharedView(id="b", name=f"{SLUG} / Features", type="project", shared=True),
        )
        client = _OnboardClient(teams=(team,), shared_views=views)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 6)
        self.assertEqual(payload["diagnostics"][0]["code"], "shared_view_ambiguous")

    def test_onboard_only_mutates_team_automations(self) -> None:
        # The fake's `mutation` raises on any kind other than
        # `team.automation.create`; a full apply exercising every onboard
        # path is therefore the structural proof of the write surface.
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, _ = self._invoke(["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--apply", "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(all(kind == "team.automation.create" for kind, _ in client.mutations))

    def test_onboard_is_idempotent_on_rerun(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            first_result, first_payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )
            second_result, second_payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(first_result, 0)
        self.assertEqual(second_result, 0)
        first_written = load_yaml_subset(Path(first_payload["changes"]["config_path"]))
        second_written = load_yaml_subset(Path(second_payload["changes"]["config_path"]))
        self.assertEqual(first_written, second_written)
        # A rerun with the same flags reports no further config diff.
        self.assertEqual(second_payload["changes"]["config_changes"], [])
        self.assertEqual(second_payload["changes"]["gitignore_entries_added"], [])

    def test_onboard_source_never_calls_the_mutation_transport(self) -> None:
        # Static, structural guarantee alongside the scripted-transport check
        # above (a fake client with no `mutation` method): onboard's own
        # source, and every helper it calls, contains no literal
        # `.mutation(` call anywhere -- the same guarantee doc "onboard"
        # requires ("performs NO GraphQL mutations, ever").
        for function in (cli_module.run_onboard, cli_module._resolve_repository_label, cli_module._resolve_lifecycle):
            source = inspect.getsource(function)
            self.assertNotIn(".mutation(", source)

    def test_onboard_default_resolves_lowest_position_state(self) -> None:
        # No flags at all: installing the extension means sync is on by
        # default, so lifecycle resolution now runs unconditionally.
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        states = (
            RemoteWorkflowState(id="c1111111-1111-4111-8111-111111111111", name="Done", type="completed", updated_at="2099-01-01T00:00:00Z", position=2.0),
            RemoteWorkflowState(id="c2222222-2222-4222-8222-222222222222", name="Merged", type="completed", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id="c3333333-3333-4333-8333-333333333333", name="Todo", type="unstarted", updated_at="2099-01-01T00:00:00Z", position=0.0),
        )
        client = _full_fixture_client(team, workflow_states=states)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 0)
        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(written["lifecycle"]["completed_state_id"], "c2222222-2222-4222-8222-222222222222")
        self.assertEqual(written["lifecycle"]["open_state_id"], "c3333333-3333-4333-8333-333333333333")
        self.assertEqual(client.find_workflow_states_by_team_calls, [TEAM_ID])

    def test_onboard_default_tied_position_warns_and_continues(self) -> None:
        # Behavior change: an ambiguous default resolution must never fail
        # onboarding -- it warns (candidates listed) and continues without a
        # lifecycle section, exit 0. This scenario used to fail closed under
        # the now-removed --with-lifecycle flag.
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        states = (
            RemoteWorkflowState(id="c1111111-1111-4111-8111-111111111111", name="Done", type="completed", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id="c2222222-2222-4222-8222-222222222222", name="Merged", type="completed", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id="c3333333-3333-4333-8333-333333333333", name="Todo", type="unstarted", updated_at="2099-01-01T00:00:00Z", position=0.0),
        )
        client = _full_fixture_client(team, workflow_states=states)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 0)
        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertNotIn("lifecycle", written)
        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertIn("lifecycle_state_ambiguous", codes)
        self.assertIn("lifecycle_skipped", codes)
        ambiguous = next(item for item in payload["diagnostics"] if item["code"] == "lifecycle_state_ambiguous")
        self.assertEqual(ambiguous["severity"], "warning")

    def test_onboard_default_missing_type_warns_and_continues(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        states = (RemoteWorkflowState(id="c3333333-3333-4333-8333-333333333333", name="Todo", type="unstarted", updated_at="2099-01-01T00:00:00Z", position=0.0),)
        client = _full_fixture_client(team, workflow_states=states)

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"]
            )

        self.assertEqual(result, 0)
        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertNotIn("lifecycle", written)
        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertIn("lifecycle_state_missing", codes)
        self.assertIn("lifecycle_skipped", codes)

    def _lifecycle_states(self, *states: RemoteWorkflowState) -> tuple[RemoteWorkflowState, ...]:
        return (
            RemoteWorkflowState(id=COMPLETED_STATE_ID, name="Done", type="completed", updated_at="2099-01-01T00:00:00Z", position=3.0),
            RemoteWorkflowState(id=OPEN_STATE_ID, name="Todo", type="unstarted", updated_at="2099-01-01T00:00:00Z", position=0.0),
            *states,
        )

    def _onboard_with(self, states: tuple[RemoteWorkflowState, ...]) -> dict[str, object]:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team, workflow_states=states)
        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json"])
        self.assertEqual(result, 0)
        return payload

    def test_onboard_resolves_the_started_and_review_states_by_name(self) -> None:
        states = self._lifecycle_states(
            RemoteWorkflowState(id=STARTED_STATE_ID, name="In Progress", type="started", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id=REVIEW_STATE_ID, name="In Review", type="started", updated_at="2099-01-01T00:00:00Z", position=2.0),
        )

        payload = self._onboard_with(states)

        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(written["lifecycle"]["started_state_id"], STARTED_STATE_ID)
        self.assertEqual(written["lifecycle"]["review_state_id"], REVIEW_STATE_ID)
        self.assertEqual(written["lifecycle"]["completed_state_id"], COMPLETED_STATE_ID)
        self.assertEqual(written["lifecycle"]["open_state_id"], OPEN_STATE_ID)
        self.assertEqual(payload["changes"]["missing_remote_resources"], [])

    def test_onboard_reports_a_missing_in_review_state_and_keeps_the_rest(self) -> None:
        states = self._lifecycle_states(
            RemoteWorkflowState(id=STARTED_STATE_ID, name="In Progress", type="started", updated_at="2099-01-01T00:00:00Z", position=1.0),
        )

        payload = self._onboard_with(states)

        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(written["lifecycle"]["started_state_id"], STARTED_STATE_ID)
        self.assertNotIn("review_state_id", written["lifecycle"])
        self.assertEqual(payload["changes"]["missing_remote_resources"], ["review_state"])
        warning = next(item for item in payload["diagnostics"] if item["code"] == "lifecycle_review_state_missing")
        self.assertEqual(warning["severity"], "warning")
        self.assertIn("In Review", warning["message"])

    def test_onboard_never_resolves_in_progress_onto_the_in_review_state(self) -> None:
        # A Team that calls its in-progress state something else still
        # resolves positionally, but the state reserved by name for review
        # must never be handed to both fields.
        states = self._lifecycle_states(
            RemoteWorkflowState(id=STARTED_STATE_ID, name="Doing", type="started", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id=REVIEW_STATE_ID, name="In Review", type="started", updated_at="2099-01-01T00:00:00Z", position=2.0),
        )

        payload = self._onboard_with(states)

        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(written["lifecycle"]["started_state_id"], STARTED_STATE_ID)
        self.assertEqual(written["lifecycle"]["review_state_id"], REVIEW_STATE_ID)

    def test_onboard_reports_both_intermediate_states_missing_without_failing(self) -> None:
        payload = self._onboard_with(self._lifecycle_states())

        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(set(written["lifecycle"]), {"completed_state_id", "open_state_id"})
        self.assertEqual(payload["changes"]["missing_remote_resources"], ["started_state", "review_state"])

    def test_onboard_is_still_idempotent_with_the_four_workflow_states(self) -> None:
        states = self._lifecycle_states(
            RemoteWorkflowState(id=STARTED_STATE_ID, name="In Progress", type="started", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id=REVIEW_STATE_ID, name="In Review", type="started", updated_at="2099-01-01T00:00:00Z", position=2.0),
        )

        first = self._onboard_with(states)
        second = self._onboard_with(states)

        self.assertEqual(
            load_yaml_subset(Path(first["changes"]["config_path"])),
            load_yaml_subset(Path(second["changes"]["config_path"])),
        )
        self.assertEqual(second["changes"]["config_changes"], [])

    def test_onboard_dry_run_rejects_combination_with_apply(self) -> None:
        client = _OnboardClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(
                ["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--dry-run", "--apply", "--json"]
            )

        self.assertEqual(result, 2)
        self.assertEqual(payload["diagnostics"][0]["code"], "onboard_mode")


class OnboardBindingCreationTests(unittest.TestCase):
    """The staged creates: group -> label -> views, each id feeding the next."""

    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _run(self, client: _OnboardClient, *extra: str) -> dict[str, object]:
        output = StringIO()
        with patch("spec_kit_linear.cli._linear_client", return_value=client), redirect_stdout(output):
            code = main(["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json", *extra])
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_onboard_creates_the_four_missing_bindings_in_dependency_order(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _OnboardClient(teams=(team,))

        payload = self._run(client)

        kinds = [kind for kind, _ in client.mutations]
        self.assertEqual(kinds, ["project.label.create", "project.label.create", "view.create", "view.create"])
        group_input = client.mutations[0][1]["input"]
        self.assertEqual((group_input["name"], group_input["isGroup"]), ("Repository", True))
        label_input = client.mutations[1][1]["input"]
        self.assertEqual((label_input["name"], label_input["parentId"]), (SLUG, "created-1"))
        features_input = client.mutations[2][1]["input"]
        self.assertEqual(features_input["name"], f"{SLUG} / Features")
        self.assertEqual(features_input["projectFilterData"], {"labels": {"some": {"id": {"eq": "created-2"}}}})
        self.assertTrue(features_input["shared"])
        work_input = client.mutations[3][1]["input"]
        self.assertEqual(work_input["name"], f"{SLUG} / Work")
        self.assertEqual(work_input["filterData"], {"project": {"labels": {"some": {"id": {"eq": "created-2"}}}}})
        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(written["repository"]["project_label_group_id"], "created-1")
        self.assertEqual(written["repository"]["project_label_id"], "created-2")
        self.assertEqual(written["repository"]["project_view_id"], "created-3")
        self.assertEqual(written["repository"]["issue_view_id"], "created-4")
        self.assertEqual(payload["changes"]["missing_remote_resources"], [])
        self.assertIn("binding_created", [item["code"] for item in payload["diagnostics"]])

    def test_onboard_creates_only_what_resolution_left_missing(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        group = RemoteProjectLabel(id=GROUP_ID, name="Repository", is_group=True, updated_at="2099-01-01T00:00:00Z", parent_id=None)
        label = RemoteProjectLabel(id=LABEL_ID, name=SLUG, is_group=False, updated_at="2099-01-01T00:00:00Z", parent_id=GROUP_ID)
        client = _OnboardClient(teams=(team,), project_labels=(group, label))

        payload = self._run(client)

        kinds = [kind for kind, _ in client.mutations]
        self.assertEqual(kinds, ["view.create", "view.create"])
        features_input = client.mutations[0][1]["input"]
        self.assertEqual(features_input["projectFilterData"], {"labels": {"some": {"id": {"eq": LABEL_ID}}}})
        written = load_yaml_subset(Path(payload["changes"]["config_path"]))
        self.assertEqual(written["repository"]["project_label_id"], LABEL_ID)
        self.assertEqual(written["repository"]["project_view_id"], "created-1")

    def test_onboard_creates_nothing_when_every_binding_resolves(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team)

        payload = self._run(client)

        self.assertEqual([kind for kind, _ in client.mutations], [])
        self.assertEqual(payload["changes"]["binding_operations"], [])


class OnboardAutomationTests(unittest.TestCase):
    """The single remote write: missing Team PR-automation mappings."""

    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _full_states(self) -> tuple[RemoteWorkflowState, ...]:
        return (
            RemoteWorkflowState(id=COMPLETED_STATE_ID, name="Done", type="completed", updated_at="2099-01-01T00:00:00Z", position=3.0),
            RemoteWorkflowState(id=OPEN_STATE_ID, name="Todo", type="unstarted", updated_at="2099-01-01T00:00:00Z", position=0.0),
            RemoteWorkflowState(id=STARTED_STATE_ID, name="In Progress", type="started", updated_at="2099-01-01T00:00:00Z", position=1.0),
            RemoteWorkflowState(id=REVIEW_STATE_ID, name="In Review", type="started", updated_at="2099-01-01T00:00:00Z", position=2.0),
        )

    def _run(self, client: _OnboardClient, *extra: str) -> dict[str, object]:
        output = StringIO()
        with patch("spec_kit_linear.cli._linear_client", return_value=client), redirect_stdout(output):
            code = main(["onboard", "--root", str(self.root), "--team-id", TEAM_ID, "--repository", SLUG, "--json", *extra])
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_onboard_creates_the_missing_automation_mappings(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team, workflow_states=self._full_states())

        payload = self._run(client)

        created = {variables["input"]["event"]: variables["input"]["stateId"] for _, variables in client.mutations}
        self.assertEqual(
            created,
            {"draft": STARTED_STATE_ID, "start": REVIEW_STATE_ID, "merge": COMPLETED_STATE_ID},
        )
        self.assertEqual(len(payload["changes"]["automation_operations"]), 3)
        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertIn("automation_applied", codes)

    def test_onboard_dry_run_plans_the_mappings_but_never_writes(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team, workflow_states=self._full_states())

        payload = self._run(client, "--dry-run")

        self.assertEqual(client.mutations, [])
        self.assertEqual(len(payload["changes"]["automation_operations"]), 3)

    def test_onboard_is_idempotent_over_a_complete_mapping(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        existing = (
            RemoteGitAutomationState(id="ga-1", event="draft", state_id=STARTED_STATE_ID, state_name="In Progress", target_branch_id=None),
            RemoteGitAutomationState(id="ga-2", event="start", state_id=REVIEW_STATE_ID, state_name="In Review", target_branch_id=None),
            RemoteGitAutomationState(id="ga-3", event="merge", state_id=COMPLETED_STATE_ID, state_name="Done", target_branch_id=None),
        )
        client = _full_fixture_client(team, workflow_states=self._full_states(), git_automation_states=existing)

        payload = self._run(client)

        self.assertEqual(client.mutations, [])
        self.assertEqual(payload["changes"]["automation_operations"], [])
        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertIn("automation_complete", codes)

    def test_onboard_never_overwrites_a_different_human_mapping(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        existing = (
            RemoteGitAutomationState(id="ga-1", event="draft", state_id=OPEN_STATE_ID, state_name="Todo", target_branch_id=None),
        )
        client = _full_fixture_client(team, workflow_states=self._full_states(), git_automation_states=existing)

        payload = self._run(client)

        created_events = [variables["input"]["event"] for _, variables in client.mutations]
        self.assertEqual(created_events, ["start", "merge"])
        conflict = next(item for item in payload["diagnostics"] if item["code"] == "automation_conflict")
        self.assertEqual(conflict["severity"], "warning")
        self.assertIn("draft", conflict["message"])

    def test_onboard_ignores_branch_scoped_rules(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        existing = (
            RemoteGitAutomationState(id="ga-1", event="draft", state_id=OPEN_STATE_ID, state_name="Todo", target_branch_id="branch-rule"),
        )
        client = _full_fixture_client(team, workflow_states=self._full_states(), git_automation_states=existing)

        payload = self._run(client)

        created_events = [variables["input"]["event"] for _, variables in client.mutations]
        self.assertEqual(created_events, ["draft", "start", "merge"])
        self.assertNotIn("automation_conflict", [item["code"] for item in payload["diagnostics"]])

    def test_onboard_warns_when_the_github_integration_is_missing(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team, workflow_states=self._full_states(), github_integration=False)

        payload = self._run(client)

        self.assertEqual(len(client.mutations), 3)
        warning = next(item for item in payload["diagnostics"] if item["code"] == "github_integration_missing")
        self.assertEqual(warning["severity"], "warning")

    def test_onboard_skips_automation_when_the_lifecycle_is_unresolved(self) -> None:
        team = RemoteTeamSummary(id=TEAM_ID, key="WOR", name="Work")
        client = _full_fixture_client(team, workflow_states=())

        payload = self._run(client)

        self.assertEqual(client.find_git_automation_states_calls, [])
        self.assertEqual(client.mutations, [])
        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertIn("automation_skipped", codes)


if __name__ == "__main__":
    unittest.main()
