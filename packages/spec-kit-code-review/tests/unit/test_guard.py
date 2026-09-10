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

    def test_a_leading_global_option_does_not_hide_a_bad_subject(self) -> None:
        code, stderr = self._run(_bash('git -c core.pager=cat commit -m "bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("type(scope): subject", stderr)

    def test_a_cluster_ending_in_m_takes_its_value_from_the_next_token(self) -> None:
        code, stderr = self._run(_bash('git commit -am "bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("type(scope): subject", stderr)

    def test_a_value_glued_directly_to_dash_m_is_the_subject(self) -> None:
        code, stderr = self._run(_bash('git commit -m"bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("type(scope): subject", stderr)

    def test_a_heredoc_command_substitution_subject_is_checked_not_its_literal_text(self) -> None:
        """The commit form Claude Code agents use by default: the subject is the
        heredoc body's first non-empty line, not the literal `$(cat <<'EOF'`."""

        conventional = 'git commit -m "$(cat <<\'EOF\'\nfeat(x): subject\n\nbody\nEOF\n)"'
        self.assertEqual(self._run(_bash(conventional)), (0, ""))

        non_conventional = 'git commit -m "$(cat <<\'EOF\'\nbad subject\n\nbody\nEOF\n)"'
        code, stderr = self._run(_bash(non_conventional))
        self.assertEqual(code, 2)
        self.assertIn("bad subject", stderr)
        self.assertNotIn("$(cat", stderr)

    def test_a_file_message_is_read_relative_to_the_repository_root(self) -> None:
        self.repository.write("subdir/message.txt", "bad subject\n\nbody\n")
        for command in ("git commit -F subdir/message.txt", "git commit --file=subdir/message.txt"):
            with self.subTest(command=command):
                code, stderr = self._run(_bash(command))
                self.assertEqual(code, 2)
                self.assertIn("bad subject", stderr)

    def test_a_conventional_file_message_is_allowed(self) -> None:
        self.repository.write("message.txt", "feat(x): good\n\nbody\n")
        self.assertEqual(self._run(_bash("git commit -F message.txt")), (0, ""))

    def test_a_missing_or_unreadable_file_message_is_not_checked(self) -> None:
        self.assertEqual(self._run(_bash("git commit -F /no/such/file-ever")), (0, ""))

    def test_a_stdin_message_is_read_from_a_heredoc_in_the_same_command(self) -> None:
        conventional = "git commit -F - <<EOF\nfeat(x): good\nbody\nEOF"
        self.assertEqual(self._run(_bash(conventional)), (0, ""))

        non_conventional = "git commit -F - <<EOF\nbad subject\nbody\nEOF"
        code, stderr = self._run(_bash(non_conventional))
        self.assertEqual(code, 2)
        self.assertIn("bad subject", stderr)

    def test_a_stdin_message_reads_the_heredoc_after_its_own_flag(self) -> None:
        earlier_bad = "cat <<'NOTES'\nbad subject in a note\nNOTES\ngit commit -F - <<EOF\nfeat(x): the real subject\nEOF"
        self.assertEqual(self._run(_bash(earlier_bad)), (0, ""))

        earlier_good = "cat <<'NOTES'\nfeat(x): a note, not the message\nNOTES\ngit commit -F - <<EOF\nbad subject\nEOF"
        code, stderr = self._run(_bash(earlier_good))
        self.assertEqual(code, 2)
        self.assertIn("bad subject", stderr)

    def test_a_redirection_before_the_message_flag_does_not_hide_it(self) -> None:
        code, stderr = self._run(_bash('git commit 2>&1 -m "bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("bad subject", stderr)

    def test_a_value_taking_cluster_flag_swallows_the_rest_of_its_token(self) -> None:
        self.assertEqual(self._run(_bash("git commit -cFETCH_HEAD")), (0, ""))
        code, _stderr = self._run(_bash('git commit -cHEAD -m "bad subject"'))
        self.assertEqual(code, 2)

    def test_a_stdin_message_without_a_heredoc_is_not_checked(self) -> None:
        self.assertEqual(self._run(_bash("git commit -F -")), (0, ""))

    def test_a_multi_line_quoted_message_keeps_its_subject_on_the_first_line(self) -> None:
        self.assertEqual(self._run(_bash('git commit -m "feat(x): s\nbody"')), (0, ""))

    def test_the_long_message_flag_is_checked_like_dash_m(self) -> None:
        code, stderr = self._run(_bash('git commit --message="bad subject"'))
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

    def test_a_leading_global_option_does_not_hide_a_force_push(self) -> None:
        code, stderr = self._run(_bash("git -C . push --force"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_leading_plus_refspec_is_a_force_push(self) -> None:
        code, stderr = self._run(_bash("git push origin +HEAD:main"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_bundled_short_cluster_containing_f_is_a_force_push(self) -> None:
        code, stderr = self._run(_bash("git push -vf origin HEAD"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_mirror_push_is_a_force_push(self) -> None:
        """`--mirror` forces every ref under `refs/` (git-push(1))."""

        code, stderr = self._run(_bash("git push --mirror origin"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_semicolon_glued_to_the_previous_word_still_separates_steps(self) -> None:
        code, stderr = self._run(_bash("true;git push --force origin HEAD"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_bare_newline_separates_steps(self) -> None:
        code, stderr = self._run(_bash("git status\ngit push --force origin HEAD"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_trailing_redirection_does_not_hide_a_force_push(self) -> None:
        code, stderr = self._run(_bash("git push --force origin HEAD 2>&1"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_redirection_before_the_force_flag_does_not_hide_it(self) -> None:
        code, stderr = self._run(_bash("git push origin HEAD 2>&1 --force"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)
        self.assertEqual(self._run(_bash("git push origin HEAD >/dev/null 2>&1")), (0, ""))

    def test_a_subshell_does_not_hide_a_force_push(self) -> None:
        code, stderr = self._run(_bash("(cd x && git push -f)"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_similarly_named_subcommand_never_matches(self) -> None:
        self.assertEqual(self._run(_bash("git pushd")), (0, ""))


class ChainParsingTests(GuardTestCase):
    """Second-audit finding: `#` must not swallow a newline, a leading
    environment assignment or wrapper word must not hide the real
    executable, and a quoted `#` must stay inside its token."""

    def test_stacked_wrappers_and_every_wrapper_word_are_seen_through(self) -> None:
        for command in ("time env git push --force origin HEAD", "nohup git push -f", "exec git push -f", "command git push -f",
                        "FOO=1 time BAR=2 env git push -f", 'time env git commit -m "bad subject"', "time env gh pr merge 1 -d"):
            with self.subTest(command=command):
                self.assertEqual(self._run(_bash(command))[0], 2)

    def test_a_leading_redirection_does_not_hide_the_executable(self) -> None:
        self.assertEqual(self._run(_bash("2>&1 git push --force origin HEAD"))[0], 2)

    def test_an_all_assignment_or_empty_command_is_allowed(self) -> None:
        for command in ("FOO=1", "", "   ", "FOO=1 time"):
            with self.subTest(command=command):
                self.assertEqual(self._run(_bash(command)), (0, ""))

    def test_a_heredoc_body_is_never_read_as_commands(self) -> None:
        self.assertEqual(self._run(_bash("git commit -F - <<'EOF'\nfeat(x): ok\n\ngit push --force origin HEAD\nEOF")), (0, ""))
        self.assertEqual(self._run(_bash("cat <<A <<B\ngit push -f\nA\ngh pr merge 1 -d\nB\ngit status")), (0, ""))
        self.assertEqual(self._run(_bash("cat <<'EOF'\nnot a push\nEOF\ngit push -f"))[0], 2)

    def test_comment_prose_is_never_read_as_flags(self) -> None:
        for command in ("git push origin HEAD # remember: never --force", "git push origin HEAD # use -f if needed",
                        "gh pr merge 1 --merge # do not -d it", 'git commit # -m "not real"', "git commit -m 'feat(x): #12' # ok"):
            with self.subTest(command=command):
                self.assertEqual(self._run(_bash(command)), (0, ""))
        self.assertEqual(self._run(_bash("echo a#b && git push -f"))[0], 2)  # a `#` inside a word is not a comment
        self.assertEqual(self._run(_bash("git push origin '#' -f"))[0], 2)  # nor a quoted one

    def test_a_heredoc_body_with_an_odd_quote_never_hides_what_follows(self) -> None:
        # `don't` unbalances shlex's quotes when the body is tokenized; it never is.
        for command, fix in (("git commit -F - <<'EOF'\nfix(x): don't crash\nEOF\ngit push --force origin HEAD", "--force"),
                             ("git commit -F - <<'EOF'\nfix(x): don't crash\nEOF\ngh pr merge 1 --delete-branch", "--delete-branch"),
                             ("cat <<'EOF'\nit's a test\nEOF\ngit push --force origin HEAD", "--force")):
            with self.subTest(command=command):
                code, stderr = self._run(_bash(command))
                self.assertEqual(code, 2)
                self.assertIn(fix, stderr)
        self.assertEqual(self._run(_bash("git commit -F - <<'EOF'\nfix(x): don't crash\nEOF")), (0, ""))

    def test_a_dash_heredoc_body_loses_its_leading_tabs(self) -> None:
        self.assertEqual(self._run(_bash("git commit -F - <<-'EOF'\n\tfeat(x): ok\n\tEOF")), (0, ""))
        code, stderr = self._run(_bash("git commit -F - <<-'EOF'\n\tbad subject\n\tEOF"))
        self.assertEqual(code, 2)
        self.assertIn("`bad subject`", stderr)
        code, stderr = self._run(_bash("git commit -F - <<-'EOF'\n\tfeat(x): ok\n\tEOF\ngit push --force origin HEAD"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_here_string_is_not_a_heredoc(self) -> None:
        self.assertEqual(self._run(_bash("cat <<< \"it's\" && git push -f"))[0], 2)
        for command in ("cat <<< val\ngit push --force origin HEAD", 'cat <<< "val"\ngit push --force origin HEAD',
                        'diff <<< "$a" <<< "$b"\ngh pr merge 1 -d'):
            with self.subTest(command=command):
                self.assertEqual(self._run(_bash(command))[0], 2)

    def test_a_separator_glued_to_a_redirection_still_separates(self) -> None:
        self.assertEqual(self._run(_bash("cat <; git push --force origin HEAD"))[0], 2)
        self.assertEqual(self._run(_bash("(git status)#comment\ngit push -f"))[0], 2)
        self.assertEqual(self._run(_bash("git push origin HEAD &>/dev/null")), (0, ""))

    def test_a_command_naming_neither_git_nor_gh_is_never_tokenized(self) -> None:
        self.assertEqual(self._run(_bash("echo it's fine")), (0, ""))
        self.assertEqual(self._run(_bash("gitk --all")), (0, ""))

    def test_a_dash_heredoc_ends_at_its_own_delimiter(self) -> None:
        self.assertEqual(self._run(_bash("git commit -F - <<-'EOF'\nfeat(x): ok\n\tEOF\ngit push --force origin HEAD"))[0], 2)
        self.assertEqual(self._run(_bash("cat <<-EOF\n\tgit push -f\n\tEOF\ngit status")), (0, ""))

    def test_a_hash_comment_does_not_swallow_the_following_step(self) -> None:
        code, stderr = self._run(_bash("git status # inspect\ngit push --force origin HEAD"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_hash_comment_does_not_hide_an_otherwise_fine_push(self) -> None:
        self.assertEqual(self._run(_bash("git status # inspect\ngit push origin HEAD")), (0, ""))

    def test_a_quoted_hash_stays_inside_its_token(self) -> None:
        self.assertEqual(self._run(_bash('git commit -m "feat(x): #12"')), (0, ""))

    def test_a_leading_environment_assignment_does_not_hide_a_force_push(self) -> None:
        code, stderr = self._run(_bash("GIT_TRACE=1 git push --force origin HEAD"))
        self.assertEqual(code, 2)
        self.assertIn("--force", stderr)

    def test_a_leading_environment_assignment_does_not_hide_a_delete_branch_merge(self) -> None:
        code, stderr = self._run(_bash("FOO=1 gh pr merge 1 -d"))
        self.assertEqual(code, 2)
        self.assertIn("--delete-branch", stderr)

    def test_a_wrapper_word_and_its_own_assignment_do_not_hide_a_bad_subject(self) -> None:
        code, stderr = self._run(_bash('env GIT_TRACE=1 git commit -m "bad subject"'))
        self.assertEqual(code, 2)
        self.assertIn("type(scope): subject", stderr)


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

    def test_a_leading_global_option_does_not_hide_a_delete_branch_merge(self) -> None:
        code, stderr = self._run(_bash("gh --repo owner/repo pr merge 1 --merge --delete-branch"))
        self.assertEqual(code, 2)
        self.assertIn("--delete-branch", stderr)

    def test_a_lone_global_option_triggers_nothing(self) -> None:
        for command in ("git -C . status", "gh --repo o/r pr view 1"):
            with self.subTest(command=command):
                self.assertEqual(self._run(_bash(command)), (0, ""))

    def test_delete_branch_equals_true_is_blocked(self) -> None:
        code, stderr = self._run(_bash("gh pr merge 1 --delete-branch=true"))
        self.assertEqual(code, 2)
        self.assertIn("--delete-branch", stderr)

    def test_delete_branch_equals_false_requests_nothing(self) -> None:
        self.assertEqual(self._run(_bash("gh pr merge 1 --delete-branch=false")), (0, ""))

    def test_every_false_spelling_cobra_accepts_requests_nothing(self) -> None:
        for spelling in ("0", "f", "F", "False", "FALSE"):
            with self.subTest(spelling=spelling):
                self.assertEqual(self._run(_bash(f"gh pr merge 1 --merge --delete-branch={spelling}")), (0, ""))
        for spelling in ("1", "t", "true"):
            with self.subTest(spelling=spelling):
                self.assertEqual(self._run(_bash(f"gh pr merge 1 --merge --delete-branch={spelling}"))[0], 2)

    def test_the_last_deletion_flag_wins_across_forms(self) -> None:
        self.assertEqual(self._run(_bash("gh pr merge 1 --merge -d --delete-branch=false")), (0, ""))
        self.assertEqual(self._run(_bash("gh pr merge 1 --merge --delete-branch=false -d"))[0], 2)

    def test_a_glued_author_email_is_never_a_deletion_request(self) -> None:
        self.assertEqual(self._run(_bash("gh pr merge 1 --merge -Adave@example.com")), (0, ""))
        self.assertEqual(self._run(_bash("gh pr merge 1 --merge -A dave@example.com")), (0, ""))

    def test_a_redirection_before_the_deletion_flag_does_not_hide_it(self) -> None:
        self.assertEqual(self._run(_bash("gh pr merge 1 --merge 2>&1 --delete-branch"))[0], 2)

    def test_a_cobra_short_cluster_containing_d_is_a_deletion_request(self) -> None:
        code, stderr = self._run(_bash("gh pr merge 1 -dm"))
        self.assertEqual(code, 2)
        self.assertIn("--delete-branch", stderr)


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

    def test_an_unnormalized_path_still_resolves_to_the_protected_path(self) -> None:
        """Finding B: `..`, `.` and an absolute path carrying `..` must all map
        to the same repository-relative path as the plain protected form."""

        self.repository.branch("001-T003-x")
        cases = (
            ("other/../specs/001-x/spec.md", "specs/001-x/spec.md"),
            ("./specs/001-x/spec.md", "specs/001-x/spec.md"),
            (str(self.repository.path / "other" / ".." / "specs" / "001-x" / "spec.md"), "specs/001-x/spec.md"),
            ("other/../.specify/memory/constitution.md", ".specify/memory/constitution.md"),
        )
        for file_path, expected in cases:
            with self.subTest(file_path=file_path):
                code, stderr = self._run(_write(file_path))
                self.assertEqual(code, 2)
                self.assertIn(expected, stderr)


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
