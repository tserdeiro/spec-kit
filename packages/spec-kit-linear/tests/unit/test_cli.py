from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from spec_kit_linear.cli import _format_feature_context, _format_work_item_context, _is_reconcile_command, main, run_post_tool_use, run_session_start
from spec_kit_linear.config import ROOT_CONFIG_FILENAME, load_config, repository_binding
from spec_kit_linear.errors import AppError, Diagnostic
from spec_kit_linear.github import PullRequest, PullRequestScan
from spec_kit_linear.linear_client import RemoteBinding, RemoteIssue, RemoteProject, RemoteWorkItem
from spec_kit_linear.parser import parse_feature
from spec_kit_linear.projection import project_feature
from spec_kit_linear.reconciler import ApplyResult
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
        content=feature.content_block,
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

    def __init__(self, projects: tuple[RemoteProject, ...] = (), *, default_state: str = "Backlog") -> None:
        super().__init__(projects)
        self.mutations: list[str] = []
        self._created_project: RemoteProject | None = None
        self._created_issues: list[RemoteIssue] = []
        self.default_state = default_state

    def discover_projects(self, _project_label_id: str) -> tuple[RemoteProject, ...]:
        if self._created_project is None:
            return self._projects
        return (replace(self._created_project, issues=tuple(self._created_issues)),)

    def mutation(self, _document: str, variables: dict[str, object], *, operation_kind: str) -> dict[str, object]:
        self.mutations.append(operation_kind)
        input_values = variables.get("input")
        assert isinstance(input_values, dict)
        remote_id = str(variables.get("id") or input_values.get("id"))
        if operation_kind == "project.create":
            self._created_project = RemoteProject(
                id=remote_id,
                name=str(input_values["name"]),
                description=str(input_values["description"]),
                updated_at="2099-01-01T00:00:00Z",
                team_ids=(_sample_binding().team_id,),
                label_ids=(_sample_binding().project_label_id,),
                issues=(),
                content=str(input_values.get("content", "")),
            )
            return {"projectCreate": {"success": True, "project": {"id": remote_id}}}
        if operation_kind == "issue.create":
            default_state = f"state-{self.default_state.lower()}" if "stateId" not in input_values else input_values["stateId"]
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
                    state_id=default_state,
                    state_name=self.default_state if "stateId" not in input_values else None,
                )
            )
            return {"issueCreate": {"success": True, "issue": {"id": remote_id}}}
        if operation_kind == "issue.lifecycle.update":
            remote_id = str(variables["id"])
            state_id = str(variables["input"]["stateId"])
            self._created_issues[:] = [replace(issue, state_id=state_id) if issue.id == remote_id else issue for issue in self._created_issues]
            return {"issueUpdate": {"success": True, "issue": {"id": remote_id}}}
        raise AssertionError(f"unexpected mutation kind: {operation_kind}")


def _write_template_config(root: Path) -> None:
    """Overwrite the fixture config with the shipped, still-placeholder template."""

    template = Path(__file__).parents[2] / "config" / "speckit-linear.template.yml"
    (root / ROOT_CONFIG_FILENAME).write_text(template.read_text(encoding="utf-8"), encoding="utf-8")


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


@contextmanager
def _subprocess_fake_gh(tmp_path: Path, *, stdout: str, returncode: int = 0, sleep: float = 0, log_path: Path | None = None) -> object:
    """Install a real executable so scanner tests cross the subprocess boundary."""

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "gh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, time\n"
        f"time.sleep({sleep!r})\n"
        + (f"open({str(log_path)!r}, 'a').write(__import__('os').getcwd() + '|' + ' '.join(sys.argv[1:]) + '\\n')\n" if log_path else "")
        + f"sys.stdout.write({stdout!r})\n"
        + f"sys.exit({returncode})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
        yield script


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
    def test_public_failure_renders_partial_evidence_and_nonzero_exit(self) -> None:
        first = ApplyResult(("first",), (), 1)
        failed = ApplyResult(("second",), (), 1, "third", "issue.create", "task:002", ("fourth", "work-item"), "mutation", "unconfirmed")
        error = AppError("later plan failed", code=8, category="mutation", diagnostics=[Diagnostic("mutation_failed", "later plan failed")], apply_results=[first, failed])
        with patch("spec_kit_linear.cli.run_push", side_effect=error):
            output = StringIO()
            with redirect_stdout(output):
                code = main(["push", "--root", str(self.fixture_root), "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 8)
        self.assertEqual(payload["apply"][0]["applied_operation_ids"], ["first"])
        self.assertEqual(payload["apply"][1]["unattempted_operation_ids"], ["fourth", "work-item"])
        self.assertEqual(payload["failure_status"], "unconfirmed")
        human = StringIO()
        with patch("spec_kit_linear.cli.run_push", side_effect=error), redirect_stderr(human):
            self.assertEqual(main(["push", "--root", str(self.fixture_root)]), 8)
        human_text = human.getvalue()
        self.assertIn("applied [first]", human_text)
        self.assertIn("unattempted [fourth,work-item]", human_text)
        self.assertIn("failure mutation (unconfirmed)", human_text)
        self.assertIn("failed third issue.create task:002", human_text)
        self.assertNotIn("failure None (None)", human_text)

    def test_real_push_aggregates_prior_failed_and_later_plan_evidence(self) -> None:
        plans = [{"snapshot": {"resources": []}, "operations": [{"id": name}]} for name in ("first", "second", "third")]
        failure = AppError("second failed", code=8, category="mutation", diagnostics=[], apply_results=[ApplyResult((), (), 0, "second", "issue.create", "task:002", (), "mutation", "unconfirmed")])
        work_plan = {"snapshot": {"resources": []}, "operations": [{"id": "work-item"}]}
        with patch("spec_kit_linear.cli._select_feature_directories", return_value=(self.fixture_root / "specs/001-local-projection",) * 3), patch("spec_kit_linear.cli._observe", return_value=({}, (), PullRequestScan("complete"))), patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()), patch("spec_kit_linear.cli.build_push_plan", side_effect=plans), patch("spec_kit_linear.cli._remote_work_items", return_value={}), patch("spec_kit_linear.cli.build_work_item_plan", return_value=(work_plan, ())), patch("spec_kit_linear.cli._apply_push_plan", side_effect=[ApplyResult(("first",), (), 1), failure]):
            output = StringIO()
            with redirect_stdout(output):
                code = main(["push", "--root", str(self.fixture_root), "--apply", "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 8)
        self.assertEqual([item["applied_operation_ids"] for item in payload["apply"]], [["first"], []])
        self.assertEqual(payload["apply"][-1]["unattempted_operation_ids"], ["third", "work-item"])

    def test_dry_run_renders_project_then_issues_and_writes_nothing(self) -> None:
        before = self._files()

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual([item["kind"] for item in payload["operations"]], ["project.create", "issue.create", "issue.create", "issue.create"])
        self.assertEqual(self._files(), before)

    def test_dry_run_on_a_feature_without_tasks_md_plans_only_the_project(self) -> None:
        (self.fixture_root / "specs/001-local-projection/tasks.md").unlink()

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])

        self.assertEqual(result, 0)
        self.assertEqual([item["kind"] for item in payload["operations"]], ["project.create"])
        self.assertIn("tasks_pending", [item["code"] for item in payload["diagnostics"]])

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
        self.assertIn("not linked", payload["message"])
        self.assertIn("onboard", payload["message"])

    def test_push_on_the_template_placeholder_config_names_onboard_before_any_network_call(self) -> None:
        _write_template_config(self.fixture_root)

        # No `_linear_client` patch and no credential in the environment. The
        # zeroed IDs already failed the UUID checks pre-network; what this
        # asserts is the diagnosis itself — the "still the template" message
        # naming onboard instead of a bare "must be a UUID".
        result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 3)
        self.assertEqual(payload["category"], "configuration")
        self.assertIn("still the template", payload["message"])
        self.assertIn("onboard", payload["message"])

    def test_hook_no_ops_cleanly_on_the_template_placeholder_config(self) -> None:
        _write_template_config(self.fixture_root)

        result, payload = self._invoke(["push", "--hook", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 0)
        self.assertTrue(payload["hook_noop"])

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
    def test_status_on_a_missing_configuration_names_onboard(self) -> None:
        (self.fixture_root / ROOT_CONFIG_FILENAME).unlink()

        result, payload = self._invoke(["status", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 3)
        self.assertEqual(payload["category"], "configuration")
        self.assertIn("not linked", payload["message"])
        self.assertIn("onboard", payload["message"])

    def test_status_on_the_template_placeholder_config_names_onboard_before_any_network_call(self) -> None:
        _write_template_config(self.fixture_root)

        # No `_linear_client` patch and no credential in the environment: the
        # guard has to fire before status could even authenticate.
        result, payload = self._invoke(["status", "--root", str(self.fixture_root), "--json"])

        self.assertEqual(result, 3)
        self.assertEqual(payload["category"], "configuration")
        self.assertIn("still the template", payload["message"])
        self.assertIn("onboard", payload["message"])

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

    def test_json_reports_zero_task_rows_and_the_pending_diagnostic_without_tasks_md(self) -> None:
        (self.fixture_root / "specs/001-local-projection/tasks.md").unlink()

        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            result, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])

        self.assertEqual(result, 0)
        task_rows = payload["status"]["task_rows"]
        self.assertEqual(task_rows[0]["tasks"], [])
        self.assertIn("tasks_pending", [item["code"] for item in payload["diagnostics"]])

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
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan or PullRequestScan("complete", pull_requests)):
                    return self._invoke(arguments)

    def _lifecycle_updates(self, payload: dict[str, object]) -> dict[str, str]:
        return {item["target"]: item["input"]["stateId"] for item in payload["operations"] if item["kind"] == "issue.lifecycle.update"}

    def _large_pr_payload(self) -> str:
        rows = [{"number": number, "head": {"ref": f"unrelated-{number}"}, "draft": False, "state": "closed", "merged_at": None} for number in range(1, 299)]
        rows.extend([
            {"number": 299, "head": {"ref": "001-T001-history"}, "draft": False, "state": "closed", "merged_at": "2026-01-01T00:00:00Z"},
            {"number": 300, "head": {"ref": "001-T002-review"}, "draft": False, "state": "open", "merged_at": None},
            {"number": 301, "head": {"ref": "001-T003-finished"}, "draft": False, "state": "closed", "merged_at": "2026-01-01T00:00:00Z"},
            {"number": 302, "head": {"ref": "001-T001-late-draft"}, "draft": True, "state": "open", "merged_at": None},
            {"number": 303, "head": {"ref": "WOR-41-bug"}, "draft": False, "state": "open", "merged_at": None},
            {"number": 304, "head": {"ref": "WOR-42-chore"}, "draft": True, "state": "open", "merged_at": None},
            # An identical record may occur when a paginated listing overlaps.
            {"number": 302, "head": {"ref": "001-T001-late-draft"}, "draft": True, "state": "open", "merged_at": None},
        ])
        pages = [rows[index:index + 100] for index in range(0, len(rows), 100)]
        return json.dumps(pages)

    def _init_branches(self, *names: str) -> None:
        subprocess.run(["git", "-C", str(self.fixture_root), "init", "-q", "-b", "main"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.fixture_root), "config", "user.email", "test@example.com"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.fixture_root), "config", "user.name", "Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.fixture_root), "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.fixture_root), "commit", "-qm", "fixture"], check=True, capture_output=True, text=True)
        for name in names:
            subprocess.run(["git", "-C", str(self.fixture_root), "branch", name], check=True, capture_output=True, text=True)

    def test_cli_uses_all_paginated_prs_for_tasks_bugs_and_chores(self) -> None:
        self._configure_lifecycle()
        self._init_branches("WOR-41-bug", "WOR-42-chore")
        project = _matching_remote_project(self._desired())
        with _subprocess_fake_gh(Path(self.temporary.name), stdout=self._large_pr_payload()):
            with patch("spec_kit_linear.cli._linear_client", return_value=_WorkItemClient((project,))):
                status_code, status_payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])
            with patch("spec_kit_linear.cli._linear_client", return_value=_WorkItemClient((project,), work_items=(_remote_work_item("WOR-41"), _remote_work_item("WOR-42")))):
                push_code, push_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])

        self.assertEqual((status_code, push_code), (0, 0))
        tasks = {row["task"]: row for row in status_payload["status"]["task_rows"][0]["tasks"]}
        self.assertEqual({key: tasks[key]["derived_state"] for key in ("T001", "T002", "T003")}, {"T001": "started", "T002": "review", "T003": "completed"})
        self.assertEqual({row["identifier"]: row["derived_state"] for row in status_payload["status"]["work_items"]}, {"WOR-41": "review", "WOR-42": "started"})
        updates = self._lifecycle_updates(push_payload)
        self.assertEqual(updates["task:001:T001"], STARTED_STATE_ID)
        self.assertEqual(updates["task:001:T002"], REVIEW_STATE_ID)
        self.assertEqual(updates["task:001:T003"], COMPLETED_STATE_ID)
        self.assertEqual(updates["workitem:WOR-41"], REVIEW_STATE_ID)
        self.assertEqual(updates["workitem:WOR-42"], STARTED_STATE_ID)

    def test_uncertain_subprocess_observation_preserves_existing_states_and_scope(self) -> None:
        self._configure_lifecycle()
        self._init_branches("WOR-99-absent-from-prefix")
        prefix = json.dumps([[{"number": 1, "head": {"ref": "unrelated"}, "draft": False, "state": "closed", "merged_at": None}]])
        project = _matching_remote_project(self._desired())
        project = replace(project, issues=tuple(replace(issue, state_id=COMPLETED_STATE_ID, state_name="Done") for issue in project.issues))
        remote_item = replace(_remote_work_item("WOR-99", state_id=COMPLETED_STATE_ID), state_name="Done")
        with _subprocess_fake_gh(Path(self.temporary.name), stdout=prefix, returncode=1):
            with patch("spec_kit_linear.cli._linear_client", return_value=_WorkItemClient((project,), work_items=(remote_item,))):
                status_code, status_payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])
                code, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])
        row = status_payload["status"]["work_items"][0]
        self.assertEqual((status_code, row["known_remotely"], row["remote_state"], row["derived_state"]), (0, True, "Done", None))
        self.assertEqual(code, 0)
        self.assertEqual(payload["observation"]["outcome"], "failed")
        self.assertEqual(self._lifecycle_updates(payload), {})
        self.assertIn("absent from partial output", " ".join(item["message"] for item in payload["diagnostics"]))

    def test_malformed_later_page_and_contradictory_duplicate_are_incomplete(self) -> None:
        self._configure_lifecycle()
        self._init_branches("WOR-7-work")
        malformed = json.dumps([[{"number": 1, "head": {"ref": "WOR-7-work"}, "draft": False, "state": "open", "merged_at": None}], ["bad-page"]])
        project = _matching_remote_project(self._desired())
        contradictory = json.dumps([[{"number": 1, "head": {"ref": "WOR-7-work"}, "draft": False, "state": "open", "merged_at": None}, {"number": 1, "head": {"ref": "WOR-7-work"}, "draft": True, "state": "open", "merged_at": None}]])
        remote_item = _remote_work_item("WOR-7", state_id=COMPLETED_STATE_ID)
        for response in (malformed, contradictory):
            with self.subTest(response=response):
                with _subprocess_fake_gh(Path(self.temporary.name), stdout=response):
                    with patch("spec_kit_linear.cli._linear_client", return_value=_WorkItemClient((project,), work_items=(remote_item,))):
                        code, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])
                        push_code, push_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])
                self.assertEqual(code, 0)
                self.assertEqual(push_code, 0)
                self.assertEqual(payload["observation"]["outcome"], "incomplete")
                self.assertIsNone(payload["status"]["work_items"][0]["derived_state"])
                self.assertEqual(self._lifecycle_updates(push_payload), {})

    def test_timeout_and_truncated_json_never_become_empty_complete_scans(self) -> None:
        project = _matching_remote_project(self._desired())
        cases = (("timeout", "[]", 0, 0.05), ("truncated", "[[{\"number\": 1", 0, 0))
        for name, output, returncode, delay in cases:
            with self.subTest(name=name):
                with _subprocess_fake_gh(Path(self.temporary.name), stdout=output, returncode=returncode, sleep=delay):
                    timeout_patch = patch("spec_kit_linear.github.GH_TIMEOUT_SECONDS", 0.01) if name == "timeout" else patch("spec_kit_linear.github.GH_TIMEOUT_SECONDS", 30)
                    with timeout_patch, patch("spec_kit_linear.cli._linear_client", return_value=_WorkItemClient((project,))):
                        code, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])
                self.assertEqual(code, 0)
                self.assertEqual(payload["observation"]["outcome"], "failed" if name == "timeout" else "incomplete")

    def test_identical_feature_numbers_use_each_repository_cwd(self) -> None:
        second_root = Path(self.temporary.name) / "consumer-two"
        shutil.copytree(self.fixture_root, second_root)
        log_path = Path(self.temporary.name) / "gh-cwds.log"
        responses = (json.dumps([[{"number": 9, "head": {"ref": "001-T001"}, "draft": True, "state": "open", "merged_at": None}]]), json.dumps([[{"number": 9, "head": {"ref": "001-T001"}, "draft": False, "state": "open", "merged_at": None}]]))
        for root, response, expected in zip((self.fixture_root, second_root), responses, ("started", "review")):
            with _subprocess_fake_gh(Path(self.temporary.name), stdout=response, log_path=log_path):
                with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((_matching_remote_project(self._desired()),))):
                    code, payload = self._invoke(["status", "--root", str(root), "--feature", "001", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"]["task_rows"][0]["tasks"][0]["derived_state"], expected)
        entries = [line.strip().split("|", 1) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({Path(entry[0]).resolve() for entry in entries}, {self.fixture_root.resolve(), second_root.resolve()})
        for _cwd, argv in entries:
            self.assertIn("api repos/{owner}/{repo}/pulls", argv)
            self.assertIn("--paginate", argv)

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

    def test_status_reopens_remote_done_from_open_work_and_reports_next_action(self) -> None:
        self._configure_lifecycle()
        base = _matching_remote_project(self._desired())
        project = replace(base, issues=tuple(replace(issue, state_id=COMPLETED_STATE_ID, state_name="Done") for issue in base.issues))
        for draft, expected_state, expected_next in ((True, "started", "/speckit.code-review 17"), (False, "review", "wait for the human merge")):
            with self.subTest(draft=draft):
                scan = PullRequestScan("complete", (PullRequest("001-T001-old", False, "MERGED", 3), PullRequest("001-T001", draft, "OPEN", 17)))
                with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((project,))), patch("spec_kit_linear.cli.known_branches", return_value=()), patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan):
                    code, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])
                    push_code, push_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"])
                row = next(row for row in payload["status"]["task_rows"][0]["tasks"] if row["task"] == "T001")
                self.assertEqual((code, row["derived_state"], row["next"]), (0, expected_state, expected_next))
                self.assertEqual((push_code, self._lifecycle_updates(push_payload)["task:001:T001"]), (0, STARTED_STATE_ID if draft else REVIEW_STATE_ID))

    def test_push_degrades_to_the_started_state_when_the_team_has_no_review_state(self) -> None:
        self._configure_lifecycle(review_state_id="")

        _result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            pull_requests=(PullRequest("001-T001", False, "OPEN"),),
        )

        self.assertEqual(self._lifecycle_updates(payload)["task:001:T001"], STARTED_STATE_ID)

    def test_push_without_gh_preserves_states_and_warns_once(self) -> None:
        self._configure_lifecycle()
        scan = PullRequestScan("failed", diagnostics=(Diagnostic("github_cli_missing", "`gh` was not found on PATH", severity="warning"),))

        _result, payload = self._observe(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            branches=("001-T001",),
            scan=scan,
        )

        codes = [item["code"] for item in payload["diagnostics"]]
        self.assertEqual(codes.count("github_cli_missing"), 1)
        self.assertEqual(self._lifecycle_updates(payload), {})

    def test_human_uncertain_creation_preview_explains_the_linear_default(self) -> None:
        scan = PullRequestScan("incomplete", diagnostics=(Diagnostic("github_cli_unavailable", "GitHub unavailable", severity="warning"),))
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()), patch("spec_kit_linear.cli.known_branches", return_value=()), patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan):
            code, output = self._invoke_text(["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("Linear will apply its configured default workflow state", output)

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
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan("complete")):
                    result, payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])

        self.assertEqual(result, 0)
        self.assertEqual(payload["operations"], [])

    def test_status_shows_each_task_derived_state_and_where_it_came_from(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient((_matching_remote_project(self._desired()),))):
            with patch("spec_kit_linear.cli.known_branches", return_value=("001-T003-render",)):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan("complete", (PullRequest("001-T001", False, "OPEN"),))):
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

    def test_status_exposes_unknown_observation_separately_from_remote_state(self) -> None:
        project = _matching_remote_project(self._desired())
        client = _FakeClient((replace(project, issues=tuple(replace(issue, state_name="Todo") for issue in project.issues)),))
        scan = PullRequestScan("incomplete", diagnostics=(Diagnostic("github_cli_unavailable", "GitHub unavailable", severity="warning"),))
        with patch("spec_kit_linear.cli._linear_client", return_value=client), patch("spec_kit_linear.cli.known_branches", return_value=("001-T001",)), patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan):
            code, payload = self._invoke(["status", "--root", str(self.fixture_root), "--feature", "001", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(payload["observation"]["outcome"], "incomplete")
        self.assertIn("selected features [001]", " ".join(item["message"] for item in payload["diagnostics"]))
        row = payload["status"]["task_rows"][0]["tasks"][0]
        self.assertIsNone(row["derived_state"])
        self.assertEqual(row["remote_state"], "Todo")

    def test_uncertain_create_uses_linear_default_then_recovery_converges_once(self) -> None:
        self._configure_lifecycle()
        for default in ("Backlog", "Triage"):
            with self.subTest(default=default):
                client = _ApplyingClient(default_state=default)
                uncertain = PullRequestScan("incomplete", diagnostics=(Diagnostic("github_cli_unavailable", "GitHub unavailable", severity="warning"),))
                with patch("spec_kit_linear.cli._linear_client", return_value=client), patch("spec_kit_linear.cli.known_branches", return_value=()), patch("spec_kit_linear.cli.scan_pull_requests", side_effect=[uncertain, PullRequestScan("complete"), PullRequestScan("complete")]):
                    first, first_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])
                    recovered, recovered_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])
                    repeated, repeated_payload = self._invoke(["push", "--root", str(self.fixture_root), "--feature", "001", "--apply", "--json"])
                self.assertEqual((first, recovered, repeated), (0, 0, 0))
                self.assertNotIn("stateId", first_payload["operations"][1]["input"])
                self.assertEqual(len([item for item in recovered_payload["operations"] if item["kind"] == "issue.lifecycle.update"]), 3)
                self.assertEqual(repeated_payload["operations"], [])

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
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=scan or PullRequestScan("complete", pull_requests)):
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

    def test_without_gh_a_branch_derived_work_item_preserves_state_and_warns_once(self) -> None:
        self._configure_lifecycle()
        client = self._matching_client(_remote_work_item("WOR-123", state_id=OPEN_STATE_ID))
        scan = PullRequestScan("failed", diagnostics=(Diagnostic("github_cli_missing", "`gh` was not found on PATH", severity="warning"),))

        _result, payload = self._observe_work_items(
            ["push", "--root", str(self.fixture_root), "--feature", "001", "--dry-run", "--json"],
            client=client,
            branches=("wor-123-fix-crash",),
            scan=scan,
        )

        self.assertEqual([item["code"] for item in payload["diagnostics"]].count("github_cli_missing"), 1)
        self.assertEqual(self._work_item_updates(payload), {})

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


def _command_flags(parser) -> dict[str, list[str]]:
    """``{subcommand: [long flags]}`` -- introspects the parser tree directly,
    now that `completions` (and its own tree-walker) is gone."""

    import argparse

    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {
        name: sorted(o for act in sub._actions for o in act.option_strings if o.startswith("--"))
        for name, sub in action.choices.items()
    }


class LauncherTests(unittest.TestCase):
    """Both launchers run uv quietly, so a parsed `--json` starts with the JSON (dogfooding entry 56)."""

    def test_both_launchers_pass_q_to_uv(self) -> None:
        package_root = Path(__file__).resolve().parents[2]
        for launcher in ("scripts/bash/run.sh", "scripts/powershell/run.ps1"):
            with self.subTest(launcher=launcher):
                text = (package_root / launcher).read_text(encoding="utf-8")
                self.assertIn("uv run --frozen --offline --project", text)
                self.assertIn(" -q python -m spec_kit_linear.cli", text)


class CommandSurfaceTests(CliTestCase):
    def test_only_six_commands_exist(self) -> None:
        from spec_kit_linear.cli import build_parser

        tree = _command_flags(build_parser())

        self.assertEqual(set(tree), {"onboard", "push", "status", "doctor", "session-start", "post-tool-use"})

    def test_the_whole_package_exposes_at_most_fifteen_user_flags(self) -> None:
        from spec_kit_linear.cli import build_parser

        tree = _command_flags(build_parser())
        flags = {flag for flags in tree.values() for flag in flags if flag != "--help"}

        self.assertLessEqual(len(flags), 15, sorted(flags))

    def test_removed_commands_are_rejected(self) -> None:
        for command in ("install", "seed", "pull", "propose", "start", "upgrade", "completions"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit) as raised:
                    main([command, "--root", str(self.fixture_root)])
                self.assertEqual(raised.exception.code, 2)


def _task_row(
    task: str,
    *,
    local_complete: bool,
    derived_state: str | None = None,
    state_source: str | None = None,
    next: str | None = None,
    pr_number: int | None = None,
    remote_state: str | None = None,
) -> dict[str, object]:
    return {
        "task": task,
        "local_complete": local_complete,
        "derived_state": derived_state,
        "state_source": state_source,
        "pr_number": pr_number,
        "next": next,
        "remote_state": remote_state,
    }


class SessionStartContextFormatterTests(unittest.TestCase):
    """FR-003's context-line formatter, table-driven over both branch shapes."""

    def test_feature_branch_without_open_prs(self) -> None:
        tasks = [
            _task_row("T001", local_complete=True, derived_state="completed", state_source="checkbox"),
            _task_row("T002", local_complete=False, derived_state="started", state_source="branch", next="/speckit.pr"),
        ]

        line = _format_feature_context("005-T002-thing", "005", tasks)

        self.assertEqual(line, "Linear: 005 on 005-T002-thing — next T002 (unchecked); next: /speckit.pr")

    def test_unknown_feature_state_shows_remote_state_without_next_action(self) -> None:
        tasks = [_task_row("T001", local_complete=True, derived_state=None, state_source="unknown", next=None, remote_state="Triage")]
        line = _format_feature_context("005-T001-thing", "005", tasks)
        self.assertIn("state unknown (remote: Triage)", line)
        self.assertNotIn("next:", line)

    def test_feature_branch_with_open_prs(self) -> None:
        tasks = [
            _task_row("T001", local_complete=False, derived_state="review", state_source="pr", next="wait for the human merge"),
            _task_row("T002", local_complete=False, derived_state="started", state_source="branch", next="/speckit.pr"),
        ]

        line = _format_feature_context("005-T001-thing", "005", tasks)

        self.assertEqual(
            line,
            "Linear: 005 on 005-T001-thing — next T001 (unchecked); open task PRs: T001 (review); "
            "next: wait for the human merge",
        )

    def test_a_merged_task_pr_is_excluded_from_open_task_prs(self) -> None:
        tasks = [_task_row("T001", local_complete=True, derived_state="completed", state_source="pr")]

        line = _format_feature_context("005-developer-experience", "005", tasks)

        self.assertEqual(line, "Linear: 005 on 005-developer-experience")

    def test_feature_branch_with_nothing_unchecked_omits_the_task_and_command(self) -> None:
        tasks = [_task_row("T001", local_complete=True, derived_state="completed", state_source="checkbox")]

        line = _format_feature_context("005-developer-experience", "005", tasks)

        self.assertEqual(line, "Linear: 005 on 005-developer-experience")

    def test_an_all_checked_stack_still_in_review_names_the_pr_number_and_the_wait_sentence(self) -> None:
        """The reported finding: checking a task before its PR is ready for review
        used to leave `next` empty because it was read only from the first
        unchecked task. With every task checked, `next` must fall back to the
        open PR's own next action, and the PR clause must name its number."""

        tasks = [
            _task_row(
                "T001",
                local_complete=True,
                derived_state="review",
                state_source="pr",
                next="wait for the human merge",
                pr_number=101,
            )
        ]

        line = _format_feature_context("005-T001-thing", "005", tasks)

        self.assertEqual(
            line,
            "Linear: 005 on 005-T001-thing; open task PRs: T001 (review, #101); "
            "next: wait for the human merge",
        )

    def test_a_checked_task_with_a_still_draft_pr_names_the_code_review_command(self) -> None:
        tasks = [
            _task_row(
                "T001",
                local_complete=True,
                derived_state="started",
                state_source="pr",
                next="/speckit.code-review 101",
                pr_number=101,
            )
        ]

        line = _format_feature_context("005-T001-thing", "005", tasks)

        self.assertEqual(
            line,
            "Linear: 005 on 005-T001-thing; open task PRs: T001 (started, #101); "
            "next: /speckit.code-review 101",
        )

    def test_an_unchecked_task_already_merged_yields_the_first_open_prs_next(self) -> None:
        # A checkbox lagging a merge derives `completed` with no next of its
        # own (next_action's documented edge); the open PR's next still lands.
        tasks = [
            _task_row("T001", local_complete=False, derived_state="completed", state_source="pr", next=None, pr_number=100),
            _task_row("T002", local_complete=True, derived_state="review", state_source="pr", next="wait for the human merge", pr_number=101),
        ]

        line = _format_feature_context("005-T002-thing", "005", tasks)

        self.assertEqual(line, "Linear: 005 on 005-T002-thing — next T001 (unchecked); open task PRs: T002 (review, #101); next: wait for the human merge")

    def test_a_checked_task_in_review_alongside_an_unchecked_task_prefers_the_unchecked_next(self) -> None:
        tasks = [
            _task_row(
                "T001",
                local_complete=True,
                derived_state="review",
                state_source="pr",
                next="wait for the human merge",
                pr_number=101,
            ),
            _task_row("T002", local_complete=False, derived_state="unstarted", state_source="none", next="/speckit.implement 005"),
        ]

        line = _format_feature_context("005-T002-thing", "005", tasks)

        self.assertEqual(
            line,
            "Linear: 005 on 005-T002-thing — next T002 (unchecked); open task PRs: T001 (review, #101); "
            "next: /speckit.implement 005",
        )

    def test_an_open_task_pr_with_an_unknown_number_omits_the_hash(self) -> None:
        tasks = [
            _task_row("T001", local_complete=True, derived_state="review", state_source="pr", next="wait for the human merge")
        ]

        line = _format_feature_context("005-T001-thing", "005", tasks)

        self.assertEqual(
            line,
            "Linear: 005 on 005-T001-thing; open task PRs: T001 (review); next: wait for the human merge",
        )

    def test_work_item_branch(self) -> None:
        row = {"identifier": "WOR-123", "derived_state": "started", "next": "/speckit.pr"}

        self.assertEqual(_format_work_item_context(row), "Linear: WOR-123 (started) — next: /speckit.pr")

    def test_work_item_branch_with_no_next_omits_the_clause(self) -> None:
        row = {"identifier": "WOR-123", "derived_state": "completed", "next": None}

        self.assertEqual(_format_work_item_context(row), "Linear: WOR-123 (completed)")

    def test_unknown_work_item_state_shows_remote_state_without_next_action(self) -> None:
        row = {"identifier": "WOR-123", "derived_state": None, "state_source": "unknown", "remote_state": "Backlog", "next": None}
        self.assertEqual(_format_work_item_context(row), "Linear: WOR-123 (unknown (unverified)); remote: Backlog")


class SessionStartTests(CliTestCase):
    """The `session-start` subcommand's own exit-0 contract: no live Linear, no live `gh`."""

    def _run(self, branch: str) -> tuple[int, str]:
        with patch("spec_kit_linear.cli._current_branch", return_value=branch):
            output = StringIO()
            with redirect_stdout(output):
                code = run_session_start(SimpleNamespace(root=str(self.fixture_root)))
        return code, output.getvalue()

    def test_a_branch_matching_neither_shape_prints_nothing(self) -> None:
        with patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            code, output = self._run("main")

        self.assertEqual(code, 0)
        self.assertEqual(output, "")

    def test_no_configuration_prints_nothing_and_never_raises(self) -> None:
        (self.fixture_root / ROOT_CONFIG_FILENAME).unlink()

        errors = StringIO()
        with redirect_stderr(errors), patch("spec_kit_linear.cli.run_status") as status:
            code, output = self._run("001-T001-parse-artifacts")

        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertEqual(errors.getvalue(), "")
        status.assert_not_called()

    def test_disabled_configuration_skips_context_without_warning(self) -> None:
        self._set_hooks(lifecycle_enabled=False)
        errors = StringIO()
        with redirect_stderr(errors), patch("spec_kit_linear.cli.run_status") as status:
            code, output = self._run("001-T001-parse-artifacts")
        self.assertEqual((code, output, errors.getvalue()), (0, "", ""))
        status.assert_not_called()

    def test_malformed_configuration_warns_once_and_skips_context(self) -> None:
        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        config_path.write_text(config_path.read_text(encoding="utf-8") + "\nhooks:\n  lifecycle_enabled: [\n", encoding="utf-8")
        errors = StringIO()
        with redirect_stderr(errors), patch("spec_kit_linear.cli.run_status") as status:
            code, output = self._run("001-T001-parse-artifacts")
        self.assertEqual((code, output), (0, ""))
        self.assertIn("configuration", errors.getvalue())
        status.assert_not_called()

    def test_configuration_io_error_is_nonblocking_and_generic(self) -> None:
        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        config_path.unlink()
        config_path.mkdir()
        errors = StringIO()
        with redirect_stderr(errors), patch("spec_kit_linear.cli.run_status") as status:
            code, output = self._run("001-T001-parse-artifacts")
        self.assertEqual((code, output), (0, ""))
        self.assertIn("unexpected configured I/O error", errors.getvalue())
        status.assert_not_called()

    def test_an_unexpected_failure_still_exits_zero_with_no_output(self) -> None:
        output = StringIO()
        with patch("spec_kit_linear.cli._current_branch", side_effect=RuntimeError("boom")), patch("spec_kit_linear.cli._linear_client", return_value=_FakeClient()):
            with redirect_stdout(output):
                code = run_session_start(SimpleNamespace(root=str(self.fixture_root)))

        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "")

    def test_a_feature_branch_reconciles_and_prints_one_line(self) -> None:
        client = _ApplyingClient()
        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            with patch("spec_kit_linear.cli.known_branches", return_value=("001-T001-parse-artifacts",)):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan("complete")):
                    code, output = self._run("001-T001-parse-artifacts")

        self.assertEqual(code, 0)
        lines = output.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "Linear: 001 on 001-T001-parse-artifacts — next T001 (unchecked); next: /speckit.pr")
        # `push --current --hook`'s own reconcile ran first.
        self.assertEqual(client.mutations, ["project.create", "issue.create", "issue.create", "issue.create"])

    def test_a_work_item_branch_prints_one_line(self) -> None:
        client = _WorkItemClient((_matching_remote_project(self._desired()),), work_items=(_remote_work_item("WOR-123"),))
        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            with patch("spec_kit_linear.cli.known_branches", return_value=("wor-123-fix-crash",)):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan("complete")):
                    code, output = self._run("wor-123-fix-crash")

        self.assertEqual(code, 0)
        self.assertEqual(output, "Linear: WOR-123 (started) — next: /speckit.pr\n")

    def test_a_work_item_branch_with_no_feature_directory_still_prints_one_line(self) -> None:
        shutil.rmtree(self.fixture_root / "specs")
        (self.fixture_root / ".specify" / "feature.json").unlink()
        client = _WorkItemClient(work_items=(_remote_work_item("WOR-123"),))
        with patch("spec_kit_linear.cli._linear_client", return_value=client):
            with patch("spec_kit_linear.cli.known_branches", return_value=("wor-123-fix-crash",)):
                with patch("spec_kit_linear.cli.scan_pull_requests", return_value=PullRequestScan("complete")):
                    code, output = self._run("wor-123-fix-crash")

        self.assertEqual(code, 0)
        self.assertEqual(output, "Linear: WOR-123 (started) — next: /speckit.pr\n")

    def test_configured_github_uncertainty_warns_on_stderr_and_keeps_stdout_context(self) -> None:
        self._set_hooks(lifecycle_enabled=True)
        result = {"diagnostics": [{"code": "observation_unknown", "severity": "warning", "message": "Authorization: Bearer secret", "path": "specs/006/tasks.md?token=secret", "line": 17}], "observation": {"outcome": "failed"}}
        output, errors = StringIO(), StringIO()
        with patch("spec_kit_linear.cli._current_branch", return_value="main"), patch("spec_kit_linear.cli.run_push", return_value=result), redirect_stdout(output), redirect_stderr(errors):
            code = run_session_start(SimpleNamespace(root=str(self.fixture_root)))
        self.assertEqual((code, output.getvalue()), (0, ""))
        self.assertIn("GitHub observation failed", errors.getvalue())
        self.assertIn("specs/006/tasks.md?token=[REDACTED]:17", errors.getvalue())
        self.assertNotIn("secret", errors.getvalue())

    def test_configured_partial_failure_warns_with_sanitized_evidence(self) -> None:
        self._set_hooks(lifecycle_enabled=True)
        error = AppError(
            "write failed Authorization: Bearer secret-value", code=8, category="mutation",
            diagnostics=[Diagnostic("mutation_failed", "WOR-1", "specs/006/tasks.md?token=secret", 23)],
            apply_results=[ApplyResult(("ok",), (), 1, "id?token=secret-value", "issue.update", "WOR-1", (), "mutation", "unconfirmed")],
        )
        errors = StringIO()
        with patch("spec_kit_linear.cli._current_branch", return_value="main"), patch("spec_kit_linear.cli.run_push", side_effect=error), redirect_stderr(errors):
            code = run_session_start(SimpleNamespace(root=str(self.fixture_root)))
        self.assertEqual(code, 0)
        self.assertIn("issue.update WOR-1", errors.getvalue())
        self.assertIn("specs/006/tasks.md?token=[REDACTED]:23", errors.getvalue())
        self.assertIn("failure mutation (unconfirmed)", errors.getvalue())
        self.assertNotIn("secret-value", errors.getvalue())


def _bash_payload(command: str) -> str:
    return json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": command}})


# The payload matcher table (dogfooding-style, D4/T012): every stdin this
# handler must reconcile on, and every one it must silently ignore. Includes
# leading global options on both `git` and `gh` (with an attached `=value`,
# a separate value token, or no value at all), plus the quoting, comment,
# redirection, subshell, and wrapper-word cases a tokenizer must get right
# where a plain regex cannot (it cannot see shell quoting: a quoted value
# with a space defeats it, and shell metacharacters sitting inside a quoted
# argument produce a spurious match).
_RECONCILING_STDIN = [
    _bash_payload(c)
    for c in (
        "git push origin HEAD",
        "git push -u origin x",
        "gh pr create",
        "gh pr ready",
        "gh pr merge",
        "git commit -m 'fix(x): y' && git push",
        "git -C . push origin HEAD",
        "git -c core.x=y push",
        "git --git-dir=/x push",
        "git --no-pager push",
        "gh --repo o/r pr ready 1",
        "gh -R o/r pr merge 1",
        "gh --hostname h pr create",
        "git commit -m 'fix(x): y' && git -C x push",
        "git fetch; git push",
        "git fetch || git push",
        "git status\ngit push origin HEAD",
        "(cd sub && git push)",
        "git push 2>&1 | tail -1",
        "GIT_TRACE=1 git push",
        "cd x && GH_TOKEN=t GH_HOST=h gh pr merge 1",
        "time env FOO=1 git push",
        "git commit -F - <<'EOF'\nnot a push\nEOF\ngit push",
        "cat <<-'EOF'\n\tnot a push\n\tEOF\ngit push",
        "git commit -F - <<'EOF'\nfix(x): don't crash\nEOF\ngit push",
        "cat <<A <<B\nit's\nA\nwon't\nB\ngit push origin HEAD",
        "cat <<< val\ngit push origin HEAD",
        "cat <; git push origin HEAD",
        "(git status)#note\ngit push",
        'git -C "a b" push origin HEAD',
        r"git -C \; push origin HEAD",
        "git status # note\ngit push",
        "git \\\npush origin HEAD",
        "env FOO=1 gh pr ready 1",
        "cd x && git push 2>&1 | tail -1",
        "(cd x && git push)",
    )
]
_SILENT_STDIN = [
    _bash_payload(c)
    for c in (
        "gh pr view 99",
        "git pushd /tmp",
        "gitk push",
        "gh pr view",
        "gh pr list",
        "echo git push",
        'echo "a;git push origin HEAD"',
        r"echo \; git push origin HEAD",
        "git commit -m 'x; gh pr ready'",
        'git push "unterminated',
        "git commit -F - <<'EOF'\ngit push\nEOF",
        "cat <<A <<B\ngit push\nA\ngh pr ready\nB",
        "git commit -F - <<'EOF'\nfix(x): don't crash\nEOF",
        "cat <<EOF | tee x\ngit push\nEOF",
    )
] + [
    json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "x"}}),
    "{not json",
    "",
]


class PostToolUseTests(CliTestCase):
    """The `post-tool-use` subcommand's payload matcher: exit 0, no stdout, ever."""

    def _run(self, stdin_text: str) -> tuple[int, str, MagicMock]:
        output = StringIO()
        with patch("spec_kit_linear.cli.run_push") as run_push, patch("sys.stdin", StringIO(stdin_text)), redirect_stdout(output):
            code = run_post_tool_use(SimpleNamespace(root=str(self.fixture_root)))
        return code, output.getvalue(), run_push

    def test_quoted_punctuation_only_argument_is_not_a_command_separator(self) -> None:
        self.assertFalse(_is_reconcile_command('git commit -m ";" git push'))

    def test_shell_continuations_and_quote_escape_semantics(self) -> None:
        self.assertTrue(_is_reconcile_command("git \\\npush origin HEAD"))
        self.assertFalse(_is_reconcile_command("git '\\\npush' origin HEAD"))
        self.assertTrue(_is_reconcile_command('git -C "\\;" push origin HEAD'))

    def test_matching_bash_commands_reconcile(self) -> None:
        for stdin_text in _RECONCILING_STDIN:
            with self.subTest(stdin_text=stdin_text):
                code, output, run_push = self._run(stdin_text)
                self.assertEqual((code, output), (0, ""))
                run_push.assert_called_once()

    def test_non_matching_or_malformed_input_never_reconciles(self) -> None:
        for stdin_text in _SILENT_STDIN:
            with self.subTest(stdin_text=stdin_text):
                code, output, run_push = self._run(stdin_text)
                self.assertEqual((code, output), (0, ""))
                run_push.assert_not_called()

    def test_configured_partial_failure_warns_with_operation_and_sanitized_evidence(self) -> None:
        self._set_hooks(lifecycle_enabled=True)
        error = AppError(
            "write failed Authorization: Bearer secret-value",
            code=8,
            category="mutation",
            diagnostics=[Diagnostic("mutation_failed", "target?token=secret-value", "specs/006/tasks.md?token=secret-value", 31)],
            apply_results=[ApplyResult(("ok",), (), 1, "id?api_key=secret-value", "issue.update", "WOR-1", ("later",), "mutation", "unconfirmed")],
        )
        output, errors = StringIO(), StringIO()
        with patch("spec_kit_linear.cli.run_push", side_effect=error), patch("sys.stdin", StringIO(_bash_payload("git push"))), redirect_stdout(output), redirect_stderr(errors):
            code = run_post_tool_use(SimpleNamespace(root=str(self.fixture_root)))
        text = errors.getvalue()
        self.assertEqual((code, output.getvalue()), (0, ""))
        self.assertIn("issue.update WOR-1", text)
        self.assertIn("specs/006/tasks.md?token=[REDACTED]:31", text)
        self.assertIn("unattempted [later]", text)
        self.assertNotIn("secret-value", text)

    def test_disabled_hooks_and_successful_reconciliation_are_quiet(self) -> None:
        self._set_hooks(lifecycle_enabled=True)
        output, errors = StringIO(), StringIO()
        with patch("spec_kit_linear.cli.run_push", return_value={"diagnostics": [{"code": "ok", "severity": "info", "message": "done"}]}), patch("sys.stdin", StringIO(_bash_payload("git push"))), redirect_stdout(output), redirect_stderr(errors):
            code = run_post_tool_use(SimpleNamespace(root=str(self.fixture_root)))
        self.assertEqual((code, output.getvalue(), errors.getvalue()), (0, "", ""))

        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        text = config_path.read_text(encoding="utf-8")
        config_path.write_text(text.rsplit("hooks:\n", 1)[0] + "hooks:\n  lifecycle_enabled: false\n", encoding="utf-8")
        output, errors = StringIO(), StringIO()
        with patch("spec_kit_linear.cli.run_push", side_effect=AssertionError("disabled hook ran")), patch("sys.stdin", StringIO(_bash_payload("git push"))), redirect_stdout(output), redirect_stderr(errors):
            code = run_post_tool_use(SimpleNamespace(root=str(self.fixture_root)))
        self.assertEqual((code, output.getvalue(), errors.getvalue()), (0, "", ""))

    def test_main_manual_error_remains_nonzero(self) -> None:
        error = AppError("manual failure", code=8, category="mutation")
        with patch("spec_kit_linear.cli.run_push", side_effect=error):
            code = main(["push", "--root", str(self.fixture_root)])
        self.assertEqual(code, 8)

    def test_configuration_io_error_is_nonblocking_for_post_tool_use(self) -> None:
        config_path = self.fixture_root / ROOT_CONFIG_FILENAME
        config_path.unlink()
        config_path.mkdir()
        errors = StringIO()
        with patch("sys.stdin", StringIO(_bash_payload("git push"))), redirect_stderr(errors):
            code = run_post_tool_use(SimpleNamespace(root=str(self.fixture_root)))
        self.assertEqual(code, 0)
        self.assertIn("unexpected configured I/O error", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
