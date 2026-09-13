from __future__ import annotations

import os
import shutil
import stat
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
            self.skipTest("unmet prerequisite: Git >= 2.54 is required for native hook tests")
        self.git = Git(executable, root=self.root)
        if self.git.version().parts < (2, 54):
            self.skipTest(f"unmet prerequisite: native hook tests require Git >= 2.54, found {self.git.version().text}")
        payload = self.root / ".specify/extensions/code-review"
        (payload / "scripts/bash").mkdir(parents=True)
        (payload / "src/spec_kit_code_review").mkdir(parents=True)
        for source, destination in (
            (PACKAGE / "scripts/bash/commit-msg.sh", payload / "scripts/bash/commit-msg.sh"),
            (PACKAGE / "src/spec_kit_code_review/commit_msg.py", payload / "src/spec_kit_code_review/commit_msg.py"),
            (PACKAGE / "src/spec_kit_code_review/commit_policy.py", payload / "src/spec_kit_code_review/commit_policy.py"),
        ):
            destination.write_bytes(source.read_bytes())

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
        self.repo.git("config", "set", "hook.commit-msg.enabled", "false")
        config = self.root / ".git/config"
        original = config.read_bytes()
        self.assertIn("git_hooks_disabled", {item.code for item in hook_diagnostics(self.root, self.git)})
        repair = install_native_hook(self.root, self.git)
        self.assertTrue(repair.diagnostics)
        self.assertEqual(config.read_bytes(), original)
        hook = self.root / ".git/hooks/commit-msg"
        hook.write_text("#!/bin/sh\n# call commit-msg.sh manually\n", encoding="utf-8")
        self.repo.git("config", "unset", "hook.commit-msg.enabled")
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
        config.write_text(config.read_text(encoding="utf-8") + '[hook "other"]\ncommand = sh .specify/extensions/code-review/scripts/bash/commit-msg.sh\nevent = commit-msg\n', encoding="utf-8")
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
