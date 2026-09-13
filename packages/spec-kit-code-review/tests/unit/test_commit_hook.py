from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spec_kit_code_review.commit_hook import (
    HOOK_COMMAND,
    HOOK_EVENT,
    HOOK_NAME,
    hook_diagnostics,
    install_native_hook,
    observe_native_hook,
)
from spec_kit_code_review.git import Git
from spec_kit_code_review.process import CommandResult
from tests.support.repo import TemporaryRepository


PACKAGE = Path(__file__).resolve().parents[2]


class NativeHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        self.repo = TemporaryRepository(self.root)
        self.addCleanup(self.repo.cleanup)
        self.repo.commit("file", "content\n", "feat(x): init")
        executable = os.environ.get("SPECKIT_TEST_GIT254") or shutil.which("git")
        if executable is None:
            self.skipTest("unmet acceptance prerequisite: select a Git >= 2.54 executable with SPECKIT_TEST_GIT254")
        self.git = Git(executable, root=self.root)
        if self.git.version().parts < (2, 54):
            self.skipTest(f"unmet acceptance prerequisite: selected Git must be >= 2.54, found {self.git.version().text}")
        self.native_env = os.environ.copy()
        self.native_env.update({"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"})
        self.invocations = Path(self.tmp.name) / "python invocations.log"
        self._install_payload(self.root)

    def _install_payload(self, root: Path) -> None:
        payload = root / ".specify/extensions/code-review"
        (payload / "scripts/bash").mkdir(parents=True, exist_ok=True)
        (payload / "src/spec_kit_code_review").mkdir(parents=True, exist_ok=True)
        for relative in (
            "scripts/bash/commit-msg.sh",
            "src/spec_kit_code_review/__init__.py",
            "src/spec_kit_code_review/commit_msg.py",
            "src/spec_kit_code_review/commit_policy.py",
        ):
            (payload / relative).write_bytes((PACKAGE / relative).read_bytes())
        python = root / ".venv/bin/python"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(self.invocations))}\n"
            f"exec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        python.chmod(0o755)

    def _native(self, *arguments: str, cwd: Path | None = None, check: bool = True):
        result = self.git.run(*arguments, cwd=cwd, env=self.native_env)
        if check and not result.ok:
            self.fail(f"native Git failed: {' '.join(arguments)}\n{result.stderr}")
        return result

    def _commit(self, message: str, *, cwd: Path | None = None, check: bool = True):
        root = cwd or self.root
        self._native("add", "--all", cwd=root)
        return self._native("commit", "-m", message, cwd=root, check=check)

    def _validator_invocations(self) -> list[str]:
        return [
            line
            for line in self.invocations.read_text(encoding="utf-8").splitlines()
            if "spec_kit_code_review.commit_msg" in line
        ]

    def _payload_module_origin(self, root: Path) -> Path:
        source = root / ".specify/extensions/code-review/src"
        environment = {**self.native_env, "PYTHONPATH": str(source)}
        result = subprocess.run(
            [sys.executable, "-c", "import spec_kit_code_review.commit_msg as module; print(module.__file__)"],
            cwd=root,
            env=environment,
            check=True,
            text=True,
            capture_output=True,
        )
        return Path(result.stdout.strip()).resolve()

    def _traditional_hook(self, hooks: Path, action: str, trace: Path) -> tuple[bytes, int]:
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "commit-msg"
        hook.write_text(
            "#!/bin/sh\n"
            f"printf '%s|%s\\n' \"$#\" \"$1\" >> {shlex.quote(str(trace))}\n"
            f"{action}\n",
            encoding="utf-8",
        )
        hook.chmod(0o751)
        return hook.read_bytes(), stat.S_IMODE(hook.stat().st_mode)

    def test_real_git_composes_default_custom_absolute_relative_and_symlink_paths(self) -> None:
        target = Path(self.tmp.name) / "absolute hooks with spaces"
        link = self.root / "hooks-link"
        link.symlink_to(target, target_is_directory=True)
        arrangements = (
            (None, self.root / ".git/hooks"),
            ("hooks with spaces", self.root / "hooks with spaces"),
            (str(target), target),
            (str(link.relative_to(self.root)), target),
        )
        for index, (configured, hooks) in enumerate(arrangements):
            if configured is not None:
                self._native("config", "core.hooksPath", configured)
            trace = Path(self.tmp.name) / f"traditional-{index}.log"
            original, mode = self._traditional_hook(hooks, ":", trace)
            self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
            observed = observe_native_hook(self.root, self.git)
            self.assertEqual(observed.hooks_path, (hooks / "commit-msg").resolve())
            self.repo.write("file", f"matrix-{index}\n")
            result = self._commit(f"feat(matrix-{index}): native path")
            self.assertTrue(result.ok, result.stderr)
            hook = hooks / "commit-msg"
            self.assertEqual(hook.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(hook.stat().st_mode), mode)
            self.assertEqual(trace.read_text(encoding="utf-8").count("|"), 1)
            self.assertEqual(len(self._validator_invocations()), index + 1)

    def test_native_payload_imports_commit_validator_from_the_consumer_fixture(self) -> None:
        expected = self.root / ".specify/extensions/code-review/src/spec_kit_code_review/commit_msg.py"
        self.assertEqual(self._payload_module_origin(self.root), expected.resolve())

    def test_native_named_hook_runs_before_traditional_hook_and_preserves_arguments(self) -> None:
        trace = Path(self.tmp.name) / "native order.log"
        traditional, mode = self._traditional_hook(self.root / ".git/hooks", ":", trace)
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        probe = Path(self.tmp.name) / "native probe with spaces.sh"
        probe.write_text(
            "#!/bin/sh\n"
            f"printf 'named\\n' >> {shlex.quote(str(trace))}\n",
            encoding="utf-8",
        )
        probe.chmod(0o755)
        self._native("config", "set", "hook.probe.command", f"sh {shlex.quote(str(probe))}")
        self._native("config", "set", "hook.probe.event", HOOK_EVENT)
        self.repo.write("file", "ordered\n")
        self.assertTrue(self._commit("feat(order): native first").ok)
        entries = trace.read_text(encoding="utf-8").splitlines()
        self.assertEqual(entries[0], "named")
        self.assertEqual(entries[1].split("|", 1)[0], "1")
        self.assertEqual((self.root / ".git/hooks/commit-msg").read_bytes(), traditional)
        self.assertEqual(stat.S_IMODE((self.root / ".git/hooks/commit-msg").stat().st_mode), mode)

    def test_previous_rejection_blocks_commit_after_one_native_invocation(self) -> None:
        trace = Path(self.tmp.name) / "reject.log"
        original, mode = self._traditional_hook(self.root / ".git/hooks", "exit 17", trace)
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        before = self.repo.head()
        self.repo.write("file", "rejected\n")
        result = self._commit("feat(reject): previous hook", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.repo.head(), before)
        self.assertEqual(len(self._validator_invocations()), 1)
        hook = self.root / ".git/hooks/commit-msg"
        self.assertEqual(hook.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(hook.stat().st_mode), mode)
        self.assertIn("1|", trace.read_text(encoding="utf-8"))

    def test_later_traditional_rewrite_is_reported_as_a_native_limit(self) -> None:
        trace = Path(self.tmp.name) / "rewrite.log"
        original, mode = self._traditional_hook(self.root / ".git/hooks", 'printf "rewritten\\n" > "$1"', trace)
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        self.repo.write("file", "rewritten\n")
        result = self._commit("feat(rewrite): accepted before later rewrite")
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(self._native("log", "-1", "--format=%s").stdout.strip(), "rewritten")
        self.assertEqual(len(self._validator_invocations()), 1)
        hook = self.root / ".git/hooks/commit-msg"
        self.assertEqual(hook.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(hook.stat().st_mode), mode)

    def test_message_file_is_preserved_and_invalid_subject_creates_no_commit(self) -> None:
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        message = Path(self.tmp.name) / "message file.txt"
        message.write_bytes("feat(file): valid\nbody\n".encode())
        before = message.read_bytes()
        self.repo.write("file", "file message\n")
        result = self._native("add", "--all")
        self.assertTrue(result.ok)
        result = self._native("commit", "-F", str(message))
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(message.read_bytes(), before)
        self.repo.write("file", "invalid message\n")
        invalid = Path(self.tmp.name) / "invalid message.txt"
        invalid.write_text("invalid subject\n", encoding="utf-8")
        self._native("add", "--all")
        before = self.repo.head()
        result = self._native("commit", "-F", str(invalid), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.repo.head(), before)

    def test_shared_registration_requires_every_linked_worktree_payload(self) -> None:
        sibling = Path(self.tmp.name) / "linked worktree"
        self._native("worktree", "add", "--detach", str(sibling))
        self.addCleanup(lambda: self._native("worktree", "remove", "--force", str(sibling), check=False))
        config = self.root / ".git/config"
        original = config.read_bytes()
        missing = install_native_hook(self.root, self.git)
        self.assertIn("git_hooks_payload_missing", {item.code for item in missing.diagnostics})
        self.assertEqual(config.read_bytes(), original)
        self._install_payload(sibling)
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        sibling_git = Git(self.git.executable, root=sibling)
        self.assertEqual(observe_native_hook(sibling, sibling_git).state, "installed")
        self.repo.write("file", "main worktree\n")
        self.assertTrue(self._commit("feat(worktree): main").ok)
        (sibling / "sibling.txt").write_text("linked\n", encoding="utf-8")
        sibling_git.run("add", "--all", env=self.native_env)
        result = sibling_git.run("commit", "-m", "feat(worktree): linked", env=self.native_env)
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(len(self._validator_invocations()), 2)

    def test_git255_per_event_disabling_is_observed_without_repair(self) -> None:
        executable = os.environ.get("SPECKIT_TEST_GIT255")
        if executable is None:
            self.skipTest("unmet optional acceptance prerequisite: set SPECKIT_TEST_GIT255 for Git 2.55 disabling evidence")
        git = Git(executable, root=self.root)
        if git.version().parts < (2, 55):
            self.skipTest(f"unmet optional acceptance prerequisite: selected Git 2.55 required, found {git.version().text}")
        self.assertEqual(install_native_hook(self.root, git).diagnostics, ())
        config = self.root / ".git/config"
        result = git.run("config", "set", "hook.commit-msg.enabled", "false", env=self.native_env)
        self.assertTrue(result.ok, result.stderr)
        after_disable = config.read_bytes()
        observation = observe_native_hook(self.root, git)
        self.assertEqual(observation.state, "disabled")
        self.assertTrue(any(name == HOOK_NAME and is_disabled for name, is_disabled in observation.listed))
        self.assertIn("git_hooks_disabled", {item.code for item in hook_diagnostics(self.root, git)})
        self.assertTrue(install_native_hook(self.root, git).diagnostics)
        self.assertEqual(config.read_bytes(), after_disable)

    def test_linked_worktree_with_existing_worktree_config_keeps_registration_local(self) -> None:
        self._native("config", "set", "extensions.worktreeConfig", "true")
        sibling = Path(self.tmp.name) / "worktree-config sibling"
        self._native("worktree", "add", "--detach", str(sibling))
        self.addCleanup(lambda: self._native("worktree", "remove", "--force", str(sibling), check=False))
        worktree_config = self.root / ".git/config.worktree"
        self._native("config", "set", "--worktree", f"hook.{HOOK_NAME}.event", HOOK_EVENT)
        shared = self.root / ".git/config"
        shared_before = shared.read_bytes()
        self.assertEqual(observe_native_hook(self.root, self.git).config_scope, "worktree")
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        self.assertEqual(shared.read_bytes(), shared_before)
        self.assertIn(HOOK_COMMAND.encode(), worktree_config.read_bytes())
        self.assertEqual(observe_native_hook(self.root, self.git).state, "installed")
        self.repo.write("file", "worktree config\n")
        self.assertTrue(self._commit("feat(worktree): config scope").ok)

    def test_symlinked_config_destination_is_left_untouched(self) -> None:
        config = self.root / ".git/config"
        target = Path(self.tmp.name) / "config target"
        target.write_bytes(config.read_bytes())
        config.unlink()
        config.symlink_to(target)
        before = target.read_bytes()
        repair = install_native_hook(self.root, self.git)
        self.assertIn("git_hooks_unsafe_config", {item.code for item in repair.diagnostics})
        self.assertEqual(target.read_bytes(), before)

    def test_installed_symlinked_config_is_reported_and_left_untouched(self) -> None:
        config = self.root / ".git/config"
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        target = Path(self.tmp.name) / "installed config target"
        target.write_bytes(config.read_bytes())
        config.unlink()
        config.symlink_to(target)
        before = target.read_bytes()
        self.assertIn("git_hooks_unsafe_config", {item.code for item in hook_diagnostics(self.root, self.git)})
        repair = install_native_hook(self.root, self.git)
        self.assertIn("git_hooks_unsafe_config", {item.code for item in repair.diagnostics})
        self.assertEqual(target.read_bytes(), before)

    def test_first_repair_is_native_and_second_repair_is_a_noop(self) -> None:
        before = observe_native_hook(self.root, self.git)
        self.assertEqual(before.state, "missing")
        self.assertIn("git_hooks_missing", {item.code for item in hook_diagnostics(self.root, self.git)})
        repair = install_native_hook(self.root, self.git)
        self.assertEqual(repair.diagnostics, ())
        config = self.root / ".git/config"
        installed = config.read_bytes()
        mode = stat.S_IMODE(config.stat().st_mode)
        self.assertEqual(observe_native_hook(self.root, self.git).state, "installed")
        self.assertIn(HOOK_COMMAND.encode(), installed)
        self.assertEqual(install_native_hook(self.root, self.git), repair.__class__())
        self.assertEqual(config.read_bytes(), installed)
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), mode)

    def test_disabled_event_and_manual_dispatcher_are_preserved(self) -> None:
        self.repo.git("config", "set", "hook.commit-msg.enabled", "")
        config = self.root / ".git/config"
        original = config.read_bytes()
        self.assertIn("git_hooks_disabled", {item.code for item in hook_diagnostics(self.root, self.git)})
        repair = install_native_hook(self.root, self.git)
        self.assertTrue(repair.diagnostics)
        self.assertEqual(config.read_bytes(), original)
        hook = self.root / ".git/hooks/commit-msg"
        hook.write_text("#!/bin/sh\nsh scripts/commit-msg.sh\n", encoding="utf-8")
        self.repo.git("config", "unset", "hook.commit-msg.enabled")
        self.assertNotIn("git_hooks_duplicate", {item.code for item in hook_diagnostics(self.root, self.git)})
        hook.write_text(f"#!/bin/sh\n{HOOK_COMMAND.replace('sh ', 'bash ', 1)}\n", encoding="utf-8")
        self.assertIn("git_hooks_duplicate", {item.code for item in hook_diagnostics(self.root, self.git)})

    def test_read_only_config_and_missing_sibling_payload_refuse_repair(self) -> None:
        worktree = Path(self.tmp.name) / "sibling"
        self.repo.git("worktree", "add", "--detach", str(worktree))
        sibling = worktree / ".specify/extensions/code-review"
        self.assertFalse(sibling.exists())
        repair = install_native_hook(self.root, self.git)
        self.assertIn("git_hooks_payload_missing", {item.code for item in repair.diagnostics})
        shutil.copytree(self.root / ".specify/extensions/code-review", sibling)
        config = self.root / ".git/config"
        config.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.addCleanup(lambda: config.chmod(0o644))
        self.assertIn("git_hooks_config_read_only", {item.code for item in install_native_hook(self.root, self.git).diagnostics})

    def test_included_owned_entry_is_foreign_and_other_names_are_duplicates(self) -> None:
        included = Path(self.tmp.name) / "included.cfg"
        included.write_text(
            f'[hook "{HOOK_NAME}"]\ncommand = {HOOK_COMMAND}\nevent = {HOOK_EVENT}\n', encoding="utf-8"
        )
        config = self.root / ".git/config"
        config.write_text(config.read_text(encoding="utf-8") + f"[include]\npath = {included}\n", encoding="utf-8")
        original = config.read_bytes()
        self.assertIn("git_hooks_foreign_scope", {item.code for item in hook_diagnostics(self.root, self.git)})
        self.assertTrue(install_native_hook(self.root, self.git).diagnostics)
        self.assertEqual(config.read_bytes(), original)
        config.write_text(config.read_text(encoding="utf-8") + '[hook "Other"]\ncommand = sh .specify/extensions/code-review/scripts/bash/commit-msg.sh\nevent = commit-msg\n', encoding="utf-8")
        self.assertIn("git_hooks_duplicate", {item.code for item in hook_diagnostics(self.root, self.git)})

    def test_lock_and_stale_snapshot_refuse_without_touching_config(self) -> None:
        config = self.root / ".git/config"
        lock = config.with_name("config.lock")
        lock.write_text("held", encoding="utf-8")
        self.addCleanup(lambda: lock.unlink(missing_ok=True))
        original = config.read_bytes()
        self.assertIn("git_hooks_config_locked", {item.code for item in install_native_hook(self.root, self.git).diagnostics})
        calls = 0
        from spec_kit_code_review import commit_hook
        observed = commit_hook.observe_native_hook

        def race(root: Path, git: Git):
            nonlocal calls
            calls += 1
            if calls == 2:
                config.write_bytes(config.read_bytes() + b"\n[core]\nrace = true\n")
                config.chmod(0o600)
            return observed(root, git)

        lock.unlink()
        with mock.patch.object(commit_hook, "observe_native_hook", side_effect=race):
            self.assertIn("git_hooks_stale_snapshot", {item.code for item in install_native_hook(self.root, self.git).diagnostics})
        self.assertNotIn(HOOK_COMMAND.encode(), config.read_bytes())
        self.assertEqual(calls, 2)

    def test_late_direct_config_edit_is_preserved_before_replacement(self) -> None:
        config = self.root / ".git/config"
        original = config.read_bytes()
        marker = b"\n[consumer]\n\tconcurrent = keep-me\n"
        real_run = self.git.run
        injected = False

        def edit_during_temp_preparation(*arguments: str, **kwargs):
            nonlocal injected
            if not injected and arguments[:2] == ("config", "set") and "--file" in arguments:
                injected = True
                config.write_bytes(config.read_bytes() + marker)
            return real_run(*arguments, **kwargs)

        with mock.patch.object(self.git, "run", side_effect=edit_during_temp_preparation):
            repair = install_native_hook(self.root, self.git)
        self.assertTrue(injected)
        self.assertIn("git_hooks_stale_snapshot", {item.code for item in repair.diagnostics})
        self.assertIsNone(repair.applied)
        self.assertEqual(config.read_bytes(), original + marker)
        self.assertNotIn(HOOK_COMMAND.encode(), config.read_bytes())

    def test_readback_recovery_does_not_overwrite_a_new_config_edit(self) -> None:
        from spec_kit_code_review import commit_hook

        config = self.root / ".git/config"
        marker = b"\n[consumer]\n\tconcurrent = keep-me\n"
        observed = commit_hook.observe_native_hook
        real_fsync = commit_hook.os.fsync
        calls = 0
        fsync_calls = 0

        def fail_readback(root: Path, git: Git):
            nonlocal calls
            calls += 1
            observation = observed(root, git)
            if calls == 4:
                observation.list_ok = False
                observation.list_error = "synthetic readback failure"
            return observation

        def edit_during_restore_temp(fd: int) -> None:
            nonlocal fsync_calls
            real_fsync(fd)
            fsync_calls += 1
            if fsync_calls == 2:
                config.write_bytes(config.read_bytes() + marker)

        with (
            mock.patch.object(commit_hook, "observe_native_hook", side_effect=fail_readback),
            mock.patch.object(commit_hook.os, "fsync", side_effect=edit_during_restore_temp),
        ):
            repair = install_native_hook(self.root, self.git)
        self.assertIn("git_hooks_readback_failed", {item.code for item in repair.diagnostics})
        self.assertIn("restoration was not applied", repair.diagnostics[0].message)
        self.assertIn("during restoration", repair.diagnostics[0].message)
        self.assertIn(marker, config.read_bytes())
        self.assertIn(HOOK_COMMAND.encode(), config.read_bytes())

    def test_partial_owned_entry_is_normalized_to_one_event(self) -> None:
        self.repo.git("config", "set", f"hook.{HOOK_NAME}.command", HOOK_COMMAND)
        self.repo.git("config", "set", f"hook.{HOOK_NAME}.event", "pre-commit")
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        self.assertEqual(self.repo.git("config", "--get-all", f"hook.{HOOK_NAME}.command"), HOOK_COMMAND)
        self.assertEqual(self.repo.git("config", "--get-all", f"hook.{HOOK_NAME}.event"), HOOK_EVENT)

    def test_event_only_entry_is_repaired_after_git_list_rejects_it(self) -> None:
        self.repo.git("config", "set", f"hook.{HOOK_NAME}.event", HOOK_EVENT)
        self.assertEqual(observe_native_hook(self.root, self.git).state, "partial")
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        self.assertEqual(observe_native_hook(self.root, self.git).state, "installed")

    def test_duplicate_owned_values_are_normalized(self) -> None:
        for field, value in (("command", HOOK_COMMAND), ("event", HOOK_EVENT)):
            key = f"hook.{HOOK_NAME}.{field}"
            self.repo.git("config", "set", key, value)
            self.repo.git("config", "set", "--append", key, value)
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        self.assertEqual(self.repo.git("config", "--get-all", f"hook.{HOOK_NAME}.command"), HOOK_COMMAND)
        self.assertEqual(self.repo.git("config", "--get-all", f"hook.{HOOK_NAME}.event"), HOOK_EVENT)

    def test_multiline_owned_command_is_a_conflict(self) -> None:
        self.repo.git("config", "set", f"hook.{HOOK_NAME}.command", f"{HOOK_COMMAND}\ntrue")
        self.repo.git("config", "set", f"hook.{HOOK_NAME}.event", HOOK_EVENT)
        self.assertEqual(observe_native_hook(self.root, self.git).state, "conflict")
        self.assertIn("git_hooks_name_conflict", {item.code for item in hook_diagnostics(self.root, self.git)})

    def test_valueless_worktree_config_uses_worktree_file_and_preserves_shared_config(self) -> None:
        config = self.root / ".git/config"
        shared_before = config.read_bytes()
        config.write_bytes(shared_before + b"\n[extensions]\n\tworktreeConfig\n")
        worktree_config = self.root / ".git/config.worktree"
        worktree_config.write_text(
            f'[hook "{HOOK_NAME}"]\nevent = {HOOK_EVENT}\n', encoding="utf-8"
        )
        observation = observe_native_hook(self.root, self.git)
        self.assertEqual(observation.config_scope, "worktree")
        self.assertEqual(observation.config_path, worktree_config.resolve())
        self.assertEqual(install_native_hook(self.root, self.git).diagnostics, ())
        self.assertEqual(config.read_bytes(), shared_before + b"\n[extensions]\n\tworktreeConfig\n")
        self.assertEqual(observe_native_hook(self.root, self.git).state, "installed")

    def test_temporary_edit_and_atomic_write_fail_without_changing_config(self) -> None:
        from spec_kit_code_review import commit_hook
        config = self.root / ".git/config"
        original = config.read_bytes()
        real_run = self.git.run

        def reject_edit(*arguments: str, **kwargs):
            if arguments[:2] == ("config", "set") and "--file" in arguments:
                return CommandResult(tuple(arguments), 1, "", "synthetic temp edit failure")
            return real_run(*arguments, **kwargs)

        with mock.patch.object(self.git, "run", side_effect=reject_edit):
            self.assertIn("git_hooks_temp_config_failed", {item.code for item in install_native_hook(self.root, self.git).diagnostics})
        self.assertEqual(config.read_bytes(), original)
        with mock.patch.object(commit_hook.os, "replace", side_effect=OSError("synthetic write failure")):
            self.assertIn("git_hooks_write_failed", {item.code for item in install_native_hook(self.root, self.git).diagnostics})
        self.assertEqual(config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
