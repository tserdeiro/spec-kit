"""The `pre_tool_use` guard: the four hard rules, and their exemptions (FR-007, FR-008, plan D5)."""

from __future__ import annotations

import json
import unittest
from contextlib import redirect_stderr
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from spec_kit_code_review.cli import run_guard
from tests.support.repo import TemporaryRepository


def _bash(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _write(path: str) -> str:
    return json.dumps({"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}})


def _edit(path: str) -> str:
    return json.dumps({"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": "a", "new_string": "b"}})


class GuardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.repository.commit("README.md", "seed\n", "seed")

    def _run(self, stdin_text: str) -> tuple[int, str]:
        output = StringIO()
        with patch("sys.stdin", StringIO(stdin_text)), redirect_stderr(output):
            code = run_guard(SimpleNamespace(root=str(self.repository.path)))
        return code, output.getvalue()


class CommitSubjectTests(GuardTestCase):
    """FR-007's first rule: `git commit -m`'s subject must be `type(scope): subject`."""

    def test_a_non_conventional_subject_is_blocked(self) -> None:
        code, stderr = self._run(_bash('git commit -m "bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("type(scope): subject", stderr)

    def test_conventional_subjects_are_allowed(self) -> None:
        for command in (
            'git commit -m "fix(x): good"',
            'git commit -m "merge(task): carry the T001 fix into T003"',
            'git commit -m "revert(scope): subject"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self._run(_bash(command)), (0, ""))

    def test_a_commit_without_a_message_flag_is_not_checked(self) -> None:
        self.assertEqual(self._run(_bash("git commit")), (0, ""))

    def test_a_bad_subject_is_caught_inside_a_chained_command(self) -> None:
        code, stderr = self._run(_bash('echo hi && git commit -m "bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("type(scope): subject", stderr)


class ForcePushTests(GuardTestCase):
    """FR-007's second rule: no form of `git push --force`."""

    def test_every_force_form_is_blocked(self) -> None:
        for flag in ("--force", "-f", "--force-with-lease", "--force-if-includes"):
            with self.subTest(flag=flag):
                code, stderr = self._run(_bash(f"git push {flag} origin HEAD"))
                self.assertEqual(code, 2)
                self.assertIn("--force", stderr)

    def test_a_plain_push_is_allowed(self) -> None:
        self.assertEqual(self._run(_bash("git push origin HEAD")), (0, ""))


class DeleteBranchMergeTests(GuardTestCase):
    """FR-007's third rule: no `gh pr merge ... --delete-branch`."""

    def test_delete_branch_forms_are_blocked(self) -> None:
        for flag in ("--delete-branch", "-d"):
            with self.subTest(flag=flag):
                code, stderr = self._run(_bash(f"gh pr merge 1 --merge {flag}"))
                self.assertEqual(code, 2)
                self.assertIn("--delete-branch", stderr)

    def test_a_plain_merge_is_allowed(self) -> None:
        self.assertEqual(self._run(_bash("gh pr merge 1 --merge")), (0, ""))


class ProtectedPathTests(GuardTestCase):
    """FR-008: a protected-path write blocks only on a task branch."""

    def test_a_protected_write_is_blocked_on_a_task_branch(self) -> None:
        self.repository.branch("001-T003-x")
        absolute = str(self.repository.path / "specs/001-x/spec.md")
        for stdin_text in (_write(absolute), _edit("specs/001-x/spec.md")):
            with self.subTest(stdin_text=stdin_text):
                code, stderr = self._run(stdin_text)
                self.assertEqual(code, 2)
                self.assertIn("specs/001-x/spec.md", stderr)

    def test_a_protected_write_is_exempt_off_a_task_branch(self) -> None:
        for branch in ("001-feature", "wor-12-x", "main"):
            with self.subTest(branch=branch):
                self.repository.checkout("main")
                if branch != "main":
                    self.repository.branch(branch)
                self.assertEqual(self._run(_write("specs/001-x/spec.md")), (0, ""))

    def test_an_unprotected_write_is_allowed_on_a_task_branch(self) -> None:
        self.repository.branch("001-T003-x")
        self.assertEqual(self._run(_write("README.md")), (0, ""))


class MalformedInputTests(GuardTestCase):
    """C-002: a guard must never block by accident."""

    def test_missing_file_path_non_json_and_unknown_tool_all_exit_zero(self) -> None:
        payloads = (
            json.dumps({"tool_name": "Edit", "tool_input": {"old_string": "a", "new_string": "b"}}),
            "{not json",
            "",
            json.dumps({"tool_name": "Read", "tool_input": {"file_path": "specs/001-x/spec.md"}}),
        )
        for stdin_text in payloads:
            with self.subTest(stdin_text=stdin_text):
                self.assertEqual(self._run(stdin_text), (0, ""))


if __name__ == "__main__":
    unittest.main()
