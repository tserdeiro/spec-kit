from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from spec_kit_linear.cli import main
from spec_kit_linear.config import ROOT_CONFIG_FILENAME, load_config, repository_binding
from spec_kit_linear.errors import Diagnostic
from spec_kit_linear.github import PullRequest, PullRequestScan
from spec_kit_linear.linear_client import RemoteBinding, RemoteIssue, RemoteProject, RemoteWorkItem
from spec_kit_linear.parser import parse_feature
from spec_kit_linear.projection import project_feature
from tests.support.fixtures import copy_consumer_fixture, isolate_operator_global_env


def _sample_binding() -> RemoteBinding:
    return RemoteBinding(
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


def _matching_remote_project(desired: object) -> RemoteProject:
    """A RemoteProject that exactly matches ``desired``, so a rendered push
    plan against it has zero operations unless the caller mutates the result.
    """

    feature = desired.feature  # type: ignore[attr-defined]
    issues = tuple(
        RemoteIssue(
            id=f"issue-{task.identity}",
            identifier=f"WOR-{index + 1}",
            title=task.title,
            description=task.managed_description,
            updated_at="2099-01-01T00:00:00Z",
            project_id="project-1",
            parent_id=None,
            assignee_id=None,
            label_ids=(),
            state_id=None,
        )
        for index, task in enumerate(feature.tasks)
    )
    return RemoteProject(
        id="project-1",
        name=feature.project_title,
        description=feature.managed_description,
        updated_at="2099-01-01T00:00:00Z",
        team_ids=(_sample_binding().team_id,),
        label_ids=(_sample_binding().project_label_id,),
        issues=issues,
    )


class _FakeClient:
    """Read-only fake. Deliberately has no `mutation` method unless asked for
    one: any attempt to write fails with AttributeError, which is the
    structural "never mutates" guarantee the read-only commands need."""

    def __init__(self, projects: tuple[RemoteProject, ...] = ()) -> None:
        self.credentials = SimpleNamespace(scheme="api_key")
        self._projects = projects

    def inspect_binding(self, _config: object) -> RemoteBinding:
        return _sample_binding()

    def discover_projects(self, _project_label_id: str) -> tuple[RemoteProject, ...]:
        return self._projects


class _ApplyingClient(_FakeClient):
    """Materializes creates so a second discovery reflects the applied state."""

    def __init__(self, projects: tuple[RemoteProject, ...] = ()) -> None:
        super().__init__(projects)
        self.mutations: list[str] = []
        self._created_project: RemoteProject | None = None
        self._created_issues: list[RemoteIssue] = []

    def discover_projects(self, _project_label_id: str) -> tuple[RemoteProject, ...]:
        if self._created_project is None:
            return self._projects
        return (replace(self._created_project, issues=tuple(self._created_issues)),)

    def mutation(self, _document: str, variables: dict[str, object], *, operation_kind: str) -> dict[str, object]:
        self.mutations.append(operation_kind)
        input_values = variables.get("input")
        assert isinstance(input_values, dict)
        remote_id = str(input_values["id"])
        if operation_kind == "project.create":
            self._created_project = RemoteProject(
                id=remote_id,
                name=str(input_values["name"]),
                description=str(input_values["description"]),
                updated_at="2099-01-01T00:00:00Z",
                team_ids=(_sample_binding().team_id,),
                label_ids=(_sample_binding().project_label_id,),
                issues=(),
            )
            return {"projectCreate": {"success": True, "project": {"id": remote_id}}}
        if operation_kind == "issue.create":
            self._created_issues.append(
                RemoteIssue(
                    id=remote_id,
                    identifier=f"WOR-{len(self._created_issues) + 1}",
                    title=str(input_values["title"]),
                    description=str(input_values["description"]),
                    updated_at="2099-01-01T00:00:00Z",
                    project_id=str(input_values["projectId"]),
                    parent_id=None,
                    assignee_id=input_values.get("assigneeId"),
                    label_ids=(),
                    state_id=input_values.get("stateId"),
                )
            )
            return {"issueCreate": {"success": True, "issue": {"id": remote_id}}}
        raise AssertionError(f"unexpected mutation kind: {operation_kind}")


@contextmanager
def _fake_gh(*, installed: bool = True, returncode: int = 0, stdout: str = "[]"):
    """Answer for `gh` and nothing else.

    `shutil` and `subprocess` are shared module objects, so patching
    `spec_kit_linear.github.subprocess.run` would also replace the `git` calls
    doctor makes. Every other lookup and process is delegated to the real one;
    the yielded list records the `gh` invocations that happened.
    """

    real_which, real_run = shutil.which, subprocess.run
    calls: list[list[str]] = []

    def which(name, *args, **kwargs):
        if name == "gh":
            return "/usr/bin/gh" if installed else None
        return real_which(name, *args, **kwargs)

    def run(arguments, *args, **kwargs):
        if list(arguments)[:1] == ["gh"]:
            calls.append(list(arguments))
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
        return real_run(arguments, *args, **kwargs)

    with patch("shutil.which", side_effect=which), patch("subprocess.run", side_effect=run):
        yield calls


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary, self.fixture_root = copy_consumer_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _invoke(self, arguments: list[str]) -> tuple[int, dict[str, object]]:
        output = StringIO()
        with redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def _invoke_text(self, arguments: list[str]) -> tuple[int, str]:
        output = StringIO()
        with redirect_stdout(output):
            code = main(arguments)
        return code, output.getvalue()

    def _desired(self):
        config, _ = load_config(self.fixture_root)
        feature = parse_feature(self.fixture_root, self.fixture_root / "specs/001-local-projection")
        return project_feature(feature, repository_binding(config))[0]

    def _files(self) -> dict[Path, bytes]:
        return {path: path.read_bytes() for path in self.fixture_root.rglob("*") if path.is_file()}

    def _set_hooks(self, **gates: bool) -> None:
        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        lines = "".join(f"  {key}: {'true' if value else 'false'}\n" for key, value in gates.items())
        config_path.write_text(config_path.read_text(encoding="utf-8") + "\nhooks:\n" + lines, encoding="utf-8")


class PushTests(CliTestCase):
    def test_dry_run_renders_project_then_issues_and_writes_nothing(self) -> None:
        before = self._files()

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual([item["kind"] for item in payload["operations"]], ["project.create", "issue.create", "issue.create", "issue.create"])
        self.assertEqual(self._files(), before)

    def test_preview_is_the_default_without_a_mode_flag(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["dry_run"])
        self.assertNotIn("apply", payload)

    def test_dry_run_and_apply_together_are_a_usage_error(self) -> None:
        result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--apply", "--json"])

        self.assertEqual(result, 2)
        self.assertEqual(payload["diagnostics"][0]["code"], "push_mode")

    def test_push_requires_credentials_and_fails_closed_without_them(self) -> None:
        # No `_linear_client` patch and no credential in the environment:
        # there is no offline preview path, so this must fail rather than
        # print a plan it could not have computed.
        result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])

        self.assertEqual(result, 4)
        self.assertEqual(payload["category"], "prerequisite")

    def test_apply_writes_the_rendered_operations_and_a_rerun_is_a_no_op(self) -> None:
        client = _ApplyingClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            first_code, first_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])
            second_code, second_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])

        self.assertEqual((first_code, second_code), (0, 0))
        self.assertFalse(first_payload["dry_run"])
        self.assertEqual(client.mutations, ["project.create", "issue.create", "issue.create", "issue.create"])
        # Idempotent: the second apply has nothing left to do and issues no
        # further mutation.
        self.assertEqual(second_payload["operations"], [])
        self.assertEqual(client.mutations, ["project.create", "issue.create", "issue.create", "issue.create"])

    def test_apply_never_touches_consumer_files(self) -> None:
        before = self._files()

        with patch("spec_kit_linear.cli._linear_client", return_value=_ApplyingClient()):
            self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])

        self.assertEqual(self._files(), before)

    def test_human_render_lists_each_operation(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, text = self._invoke_text(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run"])

        self.assertEqual(result, 0)
        self.assertIn("push preview: 4 operation(s)", text)
        self.assertIn("project.create", text)
        self.assertIn("issue.create", text)

    def test_hook_no_ops_when_lifecycle_is_disabled(self) -> None:
        self._set_hooks(lifecycle_enabled=False)

        result, payload = self._invoke(["push", "--hook", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["hook_noop"])
        self.assertIn("hooks.lifecycle_enabled is false", payload["message"])

    def test_hook_no_ops_cleanly_when_no_configuration_exists(self) -> None:
        (self.fixture_root / ROOT_CONFIG_FILENAME).unlink()

        result, payload = self._invoke(["push", "--hook", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["hook_noop"])

    def test_without_hook_a_missing_configuration_still_raises(self) -> None:
        (self.fixture_root / ROOT_CONFIG_FILENAME).unlink()

        result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 3)
        self.assertEqual(payload["category"], "configuration")

    def test_hook_applies_by_default(self) -> None:
        client = _ApplyingClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["push", "--hook", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["hook_invocation"])
        self.assertEqual(client.mutations, ["project.create", "issue.create", "issue.create", "issue.create"])

    def test_hook_only_previews_when_auto_apply_is_disabled(self) -> None:
        self._set_hooks(auto_apply=False)
        client = _ApplyingClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["push", "--hook", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(client.mutations, [])
        self.assertIn("hook_auto_apply_disabled", [item["code"] for item in payload["diagnostics"]])

    def test_hook_dry_run_never_applies_whatever_the_gate_says(self) -> None:
        client = _ApplyingClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["push", "--hook", "--dry-run", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(client.mutations, [])


class StatusTests(CliTestCase):
    def test_human_mode_renders_a_fixed_width_task_table(self) -> None:
        base_project = _matching_remote_project(self._desired())
        updated_issues = tuple(
            replace(issue, identifier="WOR-21", assignee_name="Jane Doe", state_name="Done")
            if issue.id == "issue-task:001:T001"
            else replace(issue, identifier="WOR-22", state_name="Todo")
            if issue.id == "issue-task:001:T002"
            else issue
            for issue in base_project.issues
        )
        project = replace(base_project, issues=updated_issues)

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((project,))):
            result, text = self._invoke_text(["status", "--root", str(self.fixture_root), "--feature", "001"])

        self.assertEqual(result, 0)
        self.assertIn("Feature 001", text)
        self.assertNotIn("no remote Feature Project yet", text)
        header_line = next(line for line in text.splitlines() if "TASK" in line)
        for column in ("TASK", "DONE", "ISSUE", "STATE", "ASSIGNEE"):
            self.assertIn(column, header_line)
        self.assertIn("WOR-21", text)
        self.assertIn("Jane Doe", text)
        self.assertIn("Done", text)
        # T002 is `[x]` in tasks.md; T001/T003 are `[ ]`.
        self.assertIn("[x]", text)
        self.assertIn("[ ]", text)

    def test_human_mode_notes_a_feature_with_no_remote_project_yet(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, text = self._invoke_text(["status", "--root", str(self.fixture_root), "--feature", "001"])

        self.assertEqual(result, 0)
        self.assertIn("no remote Feature Project yet", text)
        for task in ("T001", "T002", "T003"):
            self.assertIn(task, text)

    def test_quiet_suppresses_the_task_table(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, text = self._invoke_text(["status", "--root", str(self.fixture_root), "--feature", "001", "--quiet"])

        self.assertEqual(result, 0)
        self.assertEqual(text, "")

    def test_json_exposes_the_same_task_rows_structurally(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        task_rows = payload["status"]["task_rows"]
        self.assertEqual(len(task_rows), 1)
        self.assertEqual(task_rows[0]["feature"], "001")
        self.assertFalse(task_rows[0]["has_remote_project"])
        self.assertEqual([row["task"] for row in task_rows[0]["tasks"]], ["T001", "T002", "T003"])
        self.assertEqual([row["local_complete"] for row in task_rows[0]["tasks"]], [False, True, False])

    def _project_with_unmanaged_issue(self) -> RemoteProject:
        base_project = _matching_remote_project(self._desired())
        unmanaged = RemoteIssue(
            id="issue-bug-report",
            identifier="WOR-99",
            title="Users report a login redirect loop",
            description="Filed directly from a customer report; no bridge marker here at all.",
            updated_at="2099-01-01T00:00:00Z",
            project_id=base_project.id,
            parent_id=None,
            assignee_id="user-1",
            label_ids=(),
            state_id="state-todo",
            assignee_name="Jane Doe",
            state_name="Todo",
            url="https://linear.app/example/issue/WOR-99",
        )
        return replace(base_project, issues=base_project.issues + (unmanaged,))

    def test_human_mode_renders_a_remote_only_issues_section(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((self._project_with_unmanaged_issue(),))):
            result, text = self._invoke_text(["status", "--root", str(self.fixture_root), "--feature", "001"])

        self.assertEqual(result, 0)
        self.assertIn("Remote-only issues", text)
        self.assertIn("WOR-99", text)
        self.assertIn("Users report a login redirect loop", text)

    def test_human_mode_omits_the_remote_only_section_when_there_are_none(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((_matching_remote_project(self._desired()),))):
            result, text = self._invoke_text(["status", "--root", str(self.fixture_root), "--feature", "001"])

        self.assertEqual(result, 0)
        self.assertNotIn("Remote-only issues", text)

    def test_json_exposes_remote_only_issues(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((self._project_with_unmanaged_issue(),))):
            result, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        remote_only = payload["status"]["remote_only_issues"]
        self.assertEqual(len(remote_only), 1)
        self.assertEqual(remote_only[0]["issues"][0]["identifier"], "WOR-99")

    def test_status_is_read_only_and_changes_no_consumer_file(self) -> None:
        before = self._files()
        client = _FakeClient()

        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            result, payload = self._invoke(["status", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        self.assertEqual(self._files(), before)
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["status"]["remote_operations"]["writes"], 0)
        self.assertFalse(hasattr(client, "mutation"))


class DoctorTests(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        # doctor validates that the consumer root is a Git worktree.
        for args in (("init", "-q"), ("config", "user.email", "test@example.com"), ("config", "user.name", "Test")):
            subprocess.run(["git", "-C", str(self.fixture_root), *args], check=True, capture_output=True, text=True)

    def test_offline_never_requires_a_key(self) -> None:
        result, payload = self._invoke(["doctor", "--offline", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        self.assertEqual(payload["message"], "offline doctor checks passed")

    def test_warns_when_lifecycle_sync_is_unconfigured(self) -> None:
        _result, payload = self._invoke(["doctor", "--offline", "--root", str(self.fixture_root), "--json"])

        lifecycle = next(item for item in payload["diagnostics"] if item["code"] == "lifecycle_disabled")
        self.assertEqual(lifecycle["severity"], "warning")

    def test_reports_lifecycle_enabled_when_configured(self) -> None:
        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            + '\nlifecycle:\n  completed_state_id: "77777777-7777-4777-8777-777777777777"\n'
            '  open_state_id: "88888888-8888-4888-8888-888888888888"\n',
            encoding="utf-8",
        )

        _result, payload = self._invoke(["doctor", "--offline", "--root", str(self.fixture_root), "--json"])

        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertIn("lifecycle", codes)
        self.assertNotIn("lifecycle_disabled", codes)

    def test_warns_when_the_github_cli_is_missing(self) -> None:
        with _fake_gh(installed=False) as gh_calls:
            _result, payload = self._invoke(["doctor", "--offline", "--root", str(self.fixture_root), "--json"])

        warning = next(item for item in payload["diagnostics"] if item["code"] == "github_cli_missing")
        self.assertEqual(warning["severity"], "warning")
        self.assertEqual(gh_calls, [])

    def test_offline_doctor_reports_gh_presence_without_checking_authentication(self) -> None:
        with _fake_gh() as gh_calls:
            _result, payload = self._invoke(["doctor", "--offline", "--root", str(self.fixture_root), "--json"])

        self.assertIn("github_cli", [item["code"] for item in payload["diagnostics"]])
        self.assertEqual(gh_calls, [])

    def test_warns_when_gh_is_installed_but_unauthenticated(self) -> None:
        with _fake_gh(returncode=1):
            with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
                _result, payload = self._invoke(["doctor", "--root", str(self.fixture_root), "--json"])

        warning = next(item for item in payload["diagnostics"] if item["code"] == "github_cli_unauthenticated")
        self.assertEqual(warning["severity"], "warning")

    def test_a_repository_that_only_tracks_bugs_and_chores_still_passes(self) -> None:
        shutil.rmtree(self.fixture_root / "specs")

        result, payload = self._invoke(["doctor", "--offline", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        artifacts = next(item for item in payload["diagnostics"] if item["code"] == "artifacts")
        self.assertEqual(artifacts["severity"], "info")

    def test_online_doctor_validates_the_binding_without_writing(self) -> None:
        before = self._files()

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["doctor", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        self.assertEqual(payload["message"], "online doctor checks passed")
        self.assertEqual(self._files(), before)


COMPLETED_STATE_ID = "77777777-7777-4777-8777-777777777777"
OPEN_STATE_ID = "88888888-8888-4888-8888-888888888888"
STARTED_STATE_ID = "99999999-9999-4999-8999-999999999999"
REVIEW_STATE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class WorkStateTests(CliTestCase):
    """The Stage 3 derivation, end to end through the CLI: what a `push`
    observes in Git and GitHub is what it reconciles in Linear."""

    def _configure_lifecycle(self, **overrides: str) -> None:
        fields = {
            "completed_state_id": COMPLETED_STATE_ID,
            "open_state_id": OPEN_STATE_ID,
            "started_state_id": STARTED_STATE_ID,
            "review_state_id": REVIEW_STATE_ID,
        }
        fields.update(overrides)
        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        body = "".join(f'  {key}: "{value}"\n' for key, value in fields.items() if value)
        config_path.write_text(config_path.read_text(encoding="utf-8") + "\nlifecycle:\n" + body, encoding="utf-8")

    def _observe(self, arguments: list[str], *, branches: tuple[str, ...] = (), pull_requests: tuple[PullRequest, ...] = (), scan: PullRequestScan | None = None):
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((_matching_remote_project(self._desired()),))):
            with patch("spec_kit_linear.cli.known_branches", return_value=branches):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan or PullRequestScan(pull_requests=pull_requests)):
                    return self._invoke(arguments)

    def _lifecycle_updates(self, payload: dict[str, object]) -> dict[str, str]:
        return {item["target"]: item["input"]["stateId"] for item in payload["operations"] if item["kind"] == "issue.lifecycle.update"}

    def test_push_derives_started_from_a_branch_and_completed_from_the_checkbox(self) -> None:
        self._configure_lifecycle()

        result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            branches=("main", "001-T001-parse-artifacts"),
        )

        self.assertEqual(result, 0)
        updates = self._lifecycle_updates(payload)
        self.assertEqual(updates["task:001:T001"], STARTED_STATE_ID)
        self.assertEqual(updates["task:001:T002"], COMPLETED_STATE_ID)
        self.assertEqual(updates["task:001:T003"], OPEN_STATE_ID)

    def test_push_derives_review_from_a_ready_pull_request_and_started_from_a_draft(self) -> None:
        self._configure_lifecycle()

        _result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            pull_requests=(PullRequest("001-T001", False, "OPEN"), PullRequest("001-T003-render", True, "OPEN")),
        )

        updates = self._lifecycle_updates(payload)
        self.assertEqual(updates["task:001:T001"], REVIEW_STATE_ID)
        self.assertEqual(updates["task:001:T003"], STARTED_STATE_ID)

    def test_push_degrades_to_the_started_state_when_the_team_has_no_review_state(self) -> None:
        self._configure_lifecycle(review_state_id="")

        _result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            pull_requests=(PullRequest("001-T001", False, "OPEN"),),
        )

        self.assertEqual(self._lifecycle_updates(payload)["task:001:T001"], STARTED_STATE_ID)

    def test_push_without_gh_still_derives_from_the_checkbox_and_branches_and_warns_once(self) -> None:
        self._configure_lifecycle()
        scan = PullRequestScan(available=False, diagnostics=(Diagnostic("github_cli_missing", "`gh` was not found on PATH", severity="warning"),))

        _result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            branches=("001-T001",),
            scan=scan,
        )

        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertEqual(codes.count("github_cli_missing"), 1)
        updates = self._lifecycle_updates(payload)
        self.assertEqual(updates["task:001:T001"], STARTED_STATE_ID)
        self.assertEqual(updates["task:001:T002"], COMPLETED_STATE_ID)

    def test_a_branch_that_only_looks_like_the_convention_moves_nothing(self) -> None:
        self._configure_lifecycle()

        _result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            branches=("T001", "001-T001x", "002-T001"),
        )

        self.assertEqual(self._lifecycle_updates(payload)["task:001:T001"], OPEN_STATE_ID)

    def test_a_second_push_over_settled_derived_states_is_a_no_op(self) -> None:
        self._configure_lifecycle()
        base = _matching_remote_project(self._desired())
        settled = replace(
            base,
            issues=tuple(
                replace(issue, state_id=STARTED_STATE_ID if issue.id == "issue-task:001:T001" else COMPLETED_STATE_ID if issue.id == "issue-task:001:T002" else OPEN_STATE_ID)
                for issue in base.issues
            ),
        )

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((settled,))):
            with patch("spec_kit_linear.cli.known_branches", return_value=("001-T001",)):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan()):
                    result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])

        self.assertEqual(result, 0)
        self.assertEqual(payload["operations"], [])

    def test_status_shows_each_task_derived_state_and_where_it_came_from(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((_matching_remote_project(self._desired()),))):
            with patch("spec_kit_linear.cli.known_branches", return_value=("001-T003-render",)):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan(pull_requests=(PullRequest("001-T001", False, "OPEN"),))):
                    text_code, text = self._invoke_text(["status", "--root", str(self.fixture_root), "--feature", "001"])
                    json_code, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual((text_code, json_code), (0, 0))
        header_line = next(line for line in text.splitlines() if "TASK" in line)
        for column in ("TASK", "DONE", "DERIVED", "FROM", "ISSUE", "STATE", "ASSIGNEE"):
            self.assertIn(column, header_line)
        self.assertIn("review", text)
        self.assertIn("branch", text)
        rows = {row["task"]: row for row in payload["status"]["task_rows"][0]["tasks"]}
        self.assertEqual((rows["T001"]["derived_state"], rows["T001"]["state_source"]), ("review", "pr"))
        self.assertEqual((rows["T002"]["derived_state"], rows["T002"]["state_source"]), ("completed", "checkbox"))
        self.assertEqual((rows["T003"]["derived_state"], rows["T003"]["state_source"]), ("started", "branch"))

    def test_status_never_writes_while_deriving(self) -> None:
        before = self._files()

        result, payload = self._observe(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"], branches=("001-T001",))

        self.assertEqual(result, 0)
        self.assertEqual(self._files(), before)
        self.assertEqual(payload["status"]["remote_operations"]["writes"], 0)


class _WorkItemClient(_FakeClient):
    """Resolves observed Issue keys and materializes their lifecycle updates.

    Only ``issue.lifecycle.update`` is ever accepted: a bug or chore Issue is
    human-authored, so any other mutation reaching this fake is a defect.
    """

    def __init__(self, projects: tuple[RemoteProject, ...] = (), *, work_items: tuple[RemoteWorkItem, ...] = ()) -> None:
        super().__init__(projects)
        self._work_items = {item.identifier: item for item in work_items}
        self.number_lookups: list[tuple[str, tuple[int, ...]]] = []
        self.mutations: list[str] = []

    def find_issues_by_numbers(self, team_id: str, numbers) -> tuple[RemoteWorkItem, ...]:
        self.number_lookups.append((team_id, tuple(numbers)))
        wanted = {int(number) for number in numbers}
        return tuple(item for item in self._work_items.values() if int(item.identifier.rsplit("-", 1)[-1]) in wanted)

    def mutation(self, _document: str, variables: dict[str, object], *, operation_kind: str) -> dict[str, object]:
        assert operation_kind == "issue.lifecycle.update", operation_kind
        self.mutations.append(operation_kind)
        remote_id = str(variables["id"])
        state_id = str(variables["input"]["stateId"])  # type: ignore[index]
        for identifier, item in self._work_items.items():
            if item.id == remote_id:
                self._work_items[identifier] = replace(item, state_id=state_id, updated_at="2099-01-02T00:00:00Z")
                return {"issueUpdate": {"success": True, "issue": {"id": remote_id}}}
        raise AssertionError(f"unknown remote issue: {remote_id}")


def _remote_work_item(identifier: str, *, state_id: str | None = None) -> RemoteWorkItem:
    return RemoteWorkItem(
        id=f"issue-{identifier}",
        identifier=identifier,
        title=f"{identifier} title",
        updated_at="2099-01-01T00:00:00Z",
        state_id=state_id,
        state_name="Todo",
        url=f"https://linear.app/example/issue/{identifier}",
    )


class WorkItemTests(WorkStateTests):
    """Stage 5: bugs and chores, observed from `<TEAM>-<number>` branches.

    The fixture binds team key `WOR`, which is where the convention comes
    from -- nothing in the derivation knows that string.
    """

    def _observe_work_items(
        self,
        arguments: list[str],
        *,
        client,
        branches: tuple[str, ...] = (),
        pull_requests: tuple[PullRequest, ...] = (),
        scan: PullRequestScan | None = None,
        text: bool = False,
    ):
        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            with patch("spec_kit_linear.cli.known_branches", return_value=branches):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan or PullRequestScan(pull_requests=pull_requests)):
                    return self._invoke_text(arguments) if text else self._invoke(arguments)

    def _work_item_updates(self, payload: dict[str, object]) -> dict[str, str]:
        return {item["target"]: item["input"]["stateId"] for item in payload["operations"] if str(item["target"]).startswith("workitem:")}

    def _matching_client(self, *work_items: RemoteWorkItem) -> _WorkItemClient:
        return _WorkItemClient((_matching_remote_project(self._desired()),), work_items=work_items)

    def _settled_client(self, *work_items: RemoteWorkItem) -> _WorkItemClient:
        """A remote where the feature's own tasks already agree with Linear.

        With no `NNN-Txxx` branch observed, T002 (`[x]`) is completed and
        T001/T003 are open, so the feature plan is empty and anything the
        apply writes came from a work item alone.
        """

        base = _matching_remote_project(self._desired())
        settled = replace(
            base,
            issues=tuple(replace(issue, state_id=COMPLETED_STATE_ID if issue.id == "issue-task:001:T002" else OPEN_STATE_ID) for issue in base.issues),
        )
        return _WorkItemClient((settled,), work_items=work_items)

    def test_a_branch_named_after_an_issue_key_projects_that_issue_as_started(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))

        result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("main", "wor-123-fix-crash"),
        )

        self.assertEqual(result, 0)
        self.assertEqual(self._work_item_updates(payload), {"workitem:WOR-123": STARTED_STATE_ID})

    def test_pull_requests_drive_review_merged_and_draft_without_any_checkbox(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(
            _remote_work_item("WOR-1", state_id=OPEN_STATE_ID),
            _remote_work_item("WOR-2", state_id=OPEN_STATE_ID),
            _remote_work_item("WOR-3", state_id=OPEN_STATE_ID),
        )

        _result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            pull_requests=(PullRequest("wor-1-fix", False, "OPEN"), PullRequest("WOR-2", False, "MERGED"), PullRequest("wor-3-chore", True, "OPEN")),
        )

        self.assertEqual(
            self._work_item_updates(payload),
            {"workitem:WOR-1": REVIEW_STATE_ID, "workitem:WOR-2": COMPLETED_STATE_ID, "workitem:WOR-3": STARTED_STATE_ID},
        )

    def test_every_observed_key_is_resolved_in_exactly_one_query(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(*(_remote_work_item(f"WOR-{number}", state_id=OPEN_STATE_ID) for number in (1, 2, 3)))

        self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("wor-3", "wor-1-a", "wor-2-b"),
        )

        self.assertEqual(client.number_lookups, [("22222222-2222-4222-8222-222222222222", (1, 2, 3))])

    def test_no_issue_key_branch_means_no_query_at_all(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client()

        self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("main", "001-T001-parse"),
        )

        self.assertEqual(client.number_lookups, [])

    def test_a_branch_naming_an_issue_that_does_not_exist_warns_without_any_operation(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client()

        _result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("wor-999-typo",),
        )

        self.assertEqual(self._work_item_updates(payload), {})
        warning = next(item for item in payload["diagnostics"] if item["code"] == "work_item_unknown")
        self.assertEqual(warning["severity"], "warning")
        self.assertIn("WOR-999", warning["message"])

    def test_tasks_and_work_items_are_reconciled_by_the_same_push(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))

        _result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("001-T001-parse-artifacts", "wor-123-fix-crash"),
        )

        self.assertEqual(self._lifecycle_updates(payload)["task:001:T001"], STARTED_STATE_ID)
        self.assertEqual(self._work_item_updates(payload), {"workitem:WOR-123": STARTED_STATE_ID})

    def test_push_all_reconciles_work_items_too(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))

        result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--all", "--dry-run", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
        )

        self.assertEqual(result, 0)
        self.assertEqual(self._work_item_updates(payload), {"workitem:WOR-123": STARTED_STATE_ID})

    def test_a_repository_with_no_feature_at_all_still_reconciles_work_items(self) -> None:
        self._configure_lifecycle()
        shutil.rmtree(self.fixture_root / "specs")
        client = _WorkItemClient(work_items=(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID),))

        result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--dry-run", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
        )

        self.assertEqual(result, 0)
        self.assertEqual(self._work_item_updates(payload), {"workitem:WOR-123": STARTED_STATE_ID})

    def test_an_explicit_feature_that_does_not_exist_is_still_a_usage_error(self) -> None:
        shutil.rmtree(self.fixture_root / "specs")

        result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "007", "--json"])

        self.assertEqual(result, 4)
        self.assertEqual(payload["category"], "prerequisite")

    def test_apply_writes_the_lifecycle_update_and_a_second_pass_is_a_no_op(self) -> None:
        self._configure_lifecycle()
        client = self._settled_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))

        first_code, first_payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
        )
        second_code, second_payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
        )

        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(client.mutations, ["issue.lifecycle.update"])
        self.assertEqual(self._work_item_updates(first_payload), {"workitem:WOR-123": STARTED_STATE_ID})
        self.assertEqual(second_payload["operations"], [])

    def test_apply_never_touches_a_consumer_file(self) -> None:
        self._configure_lifecycle()
        before = self._files()
        client = self._settled_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))

        self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
        )

        self.assertEqual(self._files(), before)

    def test_without_gh_a_branch_derived_work_item_still_projects_and_warns_once(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))
        scan = PullRequestScan(available=False, diagnostics=(Diagnostic("github_cli_missing", "`gh` was not found on PATH", severity="warning"),))

        _result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
            scan=scan,
        )

        self.assertEqual([item["code"] for item in payload["diagnostics"]].count("github_cli_missing"), 1)
        self.assertEqual(self._work_item_updates(payload), {"workitem:WOR-123": STARTED_STATE_ID})

    def test_status_reports_the_observed_work_items(self) -> None:
        client = self._matching_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))

        text_code, text = self._observe_work_items(
            ["status", "--root", str(self.fixture_root), "--feature", "001"],
            client=client,
            branches=("wor-123-fix-crash",),
            text=True,
        )
        json_code, payload = self._observe_work_items(
            ["status", "--root", str(self.fixture_root), "--feature", "001", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
        )

        self.assertEqual((text_code, json_code), (0, 0))
        self.assertIn("Work items", text)
        self.assertIn("WOR-123", text)
        self.assertIn("wor-123-fix-crash", text)
        rows = payload["status"]["work_items"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["identifier"], rows[0]["derived_state"], rows[0]["state_source"], rows[0]["known_remotely"], rows[0]["remote_state"]),
            ("WOR-123", "started", "branch", True, "Todo"),
        )
        self.assertEqual(payload["status"]["remote_operations"]["writes"], 0)

    def test_status_omits_the_work_item_section_when_nothing_was_observed(self) -> None:
        client = self._matching_client()

        _code, text = self._observe_work_items(
            ["status", "--root", str(self.fixture_root), "--feature", "001"],
            client=client,
            branches=("main", "001-T001-parse"),
            text=True,
        )

        self.assertNotIn("Work items", text)


class CommandSurfaceTests(CliTestCase):
    def test_only_five_commands_exist(self) -> None:
        from spec_kit_linear.cli import build_parser
        from spec_kit_linear.completions import collect_completion_tree

        tree = collect_completion_tree(build_parser())

        self.assertEqual(set(tree), {"onboard", "push", "status", "doctor", "completions"})

    def test_the_whole_package_exposes_at_most_fifteen_user_flags(self) -> None:
        from spec_kit_linear.cli import build_parser
        from spec_kit_linear.completions import collect_completion_tree

        tree = collect_completion_tree(build_parser())
        flags = {flag for flags in tree.values() for flag in flags if flag != "--help"}

        self.assertLessEqual(len(flags), 15, sorted(flags))

    def test_removed_commands_are_rejected(self) -> None:
        for command in ("install", "seed", "pull", "propose", "start", "upgrade"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit) as raised:
                    main([command, "--root", str(self.fixture_root)])
                self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
