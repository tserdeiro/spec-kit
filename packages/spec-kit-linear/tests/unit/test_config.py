from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_linear.config import (
    ROOT_CONFIG_FILENAME,
    dump_yaml_subset,
    hooks_gate,
    lifecycle_state_ids,
    load_config,
    load_yaml_subset,
    resolve_config_path,
)
from spec_kit_linear.errors import AppError
from tests.support.fixtures import copy_consumer_fixture


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture_root = copy_consumer_fixture()
        self.config_path = self.fixture_root / ROOT_CONFIG_FILENAME

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _append(self, text: str) -> None:
        self.config_path.write_text(self.config_path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def test_shared_config_rejects_secrets(self) -> None:
        self._append("\nlinear_api_key: forbidden\n")

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "config_secret")

    def test_shared_config_rejects_an_operator_identity(self) -> None:
        self._append('\nlocal:\n  operator_id: "someone"\n')

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "config_secret")

    def test_missing_config_says_the_repository_is_not_linked_and_names_onboard(self) -> None:
        self.config_path.unlink()

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.category, "configuration")
        self.assertIn("not linked", str(raised.exception))
        self.assertIn("onboard", str(raised.exception))
        self.assertIn("onboard", raised.exception.diagnostics[0].message)

    def test_the_shipped_template_is_rejected_as_still_the_template(self) -> None:
        template = Path(__file__).parents[2] / "config" / "speckit-linear.template.yml"
        self.config_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.category, "configuration")
        self.assertIn("still the template", str(raised.exception))
        self.assertIn("onboard", str(raised.exception))
        self.assertEqual(raised.exception.diagnostics[0].code, "config_placeholder")

    def test_one_leftover_placeholder_id_is_enough_to_be_rejected(self) -> None:
        text = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            text.replace("66666666-6666-4666-8666-666666666666", "00000000-0000-0000-0000-000000000000"),
            encoding="utf-8",
        )

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.diagnostics[0].code, "config_placeholder")
        self.assertIn("repository.issue_view_id", raised.exception.diagnostics[0].message)

    def test_the_valid_fixture_config_still_loads(self) -> None:
        config, path = load_config(self.fixture_root)

        self.assertEqual(path, self.config_path.resolve())
        self.assertEqual(config["repository"]["slug"], "sample-repository")

    def test_lifecycle_section_is_optional_and_absent_by_default(self) -> None:
        config, _ = load_config(self.fixture_root)

        self.assertIsNone(lifecycle_state_ids(config))

    def test_lifecycle_section_requires_both_state_ids_together(self) -> None:
        self._append('\nlifecycle:\n  completed_state_id: "77777777-7777-4777-8777-777777777777"\n')

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "config_required")

    def test_lifecycle_section_rejects_non_uuid_state_ids(self) -> None:
        self._append('\nlifecycle:\n  completed_state_id: "not-a-uuid"\n  open_state_id: "88888888-8888-4888-8888-888888888888"\n')

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "config_uuid")

    def test_lifecycle_section_with_both_ids_is_accepted_and_exposed(self) -> None:
        self._append(
            '\nlifecycle:\n  completed_state_id: "77777777-7777-4777-8777-777777777777"\n'
            '  open_state_id: "88888888-8888-4888-8888-888888888888"\n'
        )

        config, _ = load_config(self.fixture_root)

        self.assertEqual(
            lifecycle_state_ids(config),
            ("77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888"),
        )

    def test_hooks_section_accepts_two_booleans(self) -> None:
        self._append("\nhooks:\n  lifecycle_enabled: false\n  auto_apply: false\n")

        config, _ = load_config(self.fixture_root)

        self.assertEqual(config["hooks"], {"lifecycle_enabled": False, "auto_apply": False})

    def test_hooks_section_rejects_non_boolean_values(self) -> None:
        self._append('\nhooks:\n  lifecycle_enabled: "yes"\n')

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "config_bool")

    def test_hooks_auto_apply_is_a_plain_boolean_not_a_tri_state(self) -> None:
        self._append('\nhooks:\n  auto_apply: "updates"\n')

        with self.assertRaises(AppError) as raised:
            load_config(self.fixture_root)

        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(raised.exception.diagnostics[0].code, "config_bool")

    def test_hooks_section_rejects_removed_and_unknown_keys(self) -> None:
        for key in ("git_enabled", "git_async", "webhook_enabled"):
            with self.subTest(key=key):
                original = self.config_path.read_text(encoding="utf-8")
                self._append(f"\nhooks:\n  {key}: true\n")
                try:
                    with self.assertRaises(AppError) as raised:
                        load_config(self.fixture_root)
                finally:
                    self.config_path.write_text(original, encoding="utf-8")
                self.assertEqual(raised.exception.code, 3)
                self.assertEqual(raised.exception.diagnostics[0].code, "config_hooks_key")

    def test_hooks_gate_defaults_to_sync_on_when_the_section_is_absent(self) -> None:
        self.assertTrue(hooks_gate({}, "lifecycle_enabled"))
        self.assertTrue(hooks_gate({}, "auto_apply"))
        self.assertTrue(hooks_gate({"hooks": {"auto_apply": False}}, "lifecycle_enabled"))

    def test_hooks_gate_reads_configured_values(self) -> None:
        config = {"hooks": {"lifecycle_enabled": False, "auto_apply": False}}
        self.assertFalse(hooks_gate(config, "lifecycle_enabled"))
        self.assertFalse(hooks_gate(config, "auto_apply"))

    def test_dump_yaml_subset_round_trips_the_fixture_shared_config(self) -> None:
        original = load_yaml_subset(self.config_path)

        dumped = dump_yaml_subset(original)
        self.config_path.write_text(dumped, encoding="utf-8")
        reloaded = load_yaml_subset(self.config_path)

        self.assertEqual(reloaded, original)

    def test_dump_yaml_subset_quotes_strings_and_leaves_booleans_bare(self) -> None:
        rendered = dump_yaml_subset({"repository": {"slug": "spec-kit", "flag": True, "off": False, "empty": {}}})

        self.assertEqual(
            rendered,
            'repository:\n  slug: "spec-kit"\n  flag: true\n  off: false\n  empty:\n',
        )

    def test_dump_yaml_subset_escapes_quotes_and_backslashes(self) -> None:
        rendered = dump_yaml_subset({"note": 'has "quotes" and \\backslash'})

        self.assertEqual(rendered, 'note: "has \\"quotes\\" and \\\\backslash"\n')

    def test_dump_yaml_subset_round_trip_via_disk_for_special_characters(self) -> None:
        config_path = self.fixture_root / "special.yml"
        data = {"section": {"value": 'has "quotes" and #hash and \\backslash'}}
        config_path.write_text(dump_yaml_subset(data), encoding="utf-8")

        reloaded = load_yaml_subset(config_path)

        self.assertEqual(reloaded, data)

    def test_load_yaml_subset_unescapes_double_quoted_backslashes_and_quotes(self) -> None:
        config_path = self.fixture_root / "escaped.yml"
        config_path.write_text('note: "has \\"quotes\\" and \\\\backslash"\n', encoding="utf-8")

        loaded = load_yaml_subset(config_path)

        self.assertEqual(loaded, {"note": 'has "quotes" and \\backslash'})


class ConfigResolutionOrderTests(unittest.TestCase):
    """Explicit --config, then SPECKIT_LINEAR_CONFIG, then the root default.

    There is no legacy path and no local overlay: one file, at the root.
    """

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _write_root_config(self) -> Path:
        root_path = self.root / ROOT_CONFIG_FILENAME
        root_path.write_text(
            'schema_version: "1.0"\n'
            "linear:\n"
            '  workspace_id: "11111111-1111-4111-8111-111111111111"\n'
            '  team_id: "22222222-2222-4222-8222-222222222222"\n'
            '  team_key: "WOR"\n'
            "repository:\n"
            '  slug: "spec-kit"\n',
            encoding="utf-8",
        )
        return root_path

    def test_defaults_to_the_root_config(self) -> None:
        self.assertEqual(resolve_config_path(self.root, None), self.root / ROOT_CONFIG_FILENAME)

    def test_explicit_config_flag_wins_over_the_root_default(self) -> None:
        self._write_root_config()
        explicit = self.root / "custom" / "explicit-config.yml"

        self.assertEqual(resolve_config_path(self.root, str(explicit)), explicit)

    def test_speckit_linear_config_env_var_wins_over_the_root_default(self) -> None:
        self._write_root_config()
        env_path = self.root / "custom" / "from-env.yml"

        try:
            os.environ["SPECKIT_LINEAR_CONFIG"] = str(env_path)
            resolved = resolve_config_path(self.root, None)
        finally:
            del os.environ["SPECKIT_LINEAR_CONFIG"]

        self.assertEqual(resolved, env_path)

    def test_explicit_config_flag_wins_over_the_env_var(self) -> None:
        explicit = self.root / "flag.yml"
        try:
            os.environ["SPECKIT_LINEAR_CONFIG"] = str(self.root / "env.yml")
            resolved = resolve_config_path(self.root, str(explicit))
        finally:
            del os.environ["SPECKIT_LINEAR_CONFIG"]

        self.assertEqual(resolved, explicit)

    def test_load_config_reads_the_root_default(self) -> None:
        root_path = self._write_root_config()

        config, resolved_path = load_config(self.root, allow_unbound_repository=True)

        self.assertEqual(resolved_path, root_path.resolve())
        self.assertEqual(config["repository"]["slug"], "spec-kit")

    def test_a_legacy_extension_config_is_never_read(self) -> None:
        legacy_path = self.root / ".specify/extensions/linear/linear-config.yml"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text('schema_version: "1.0"\n', encoding="utf-8")

        self.assertEqual(resolve_config_path(self.root, None), self.root / ROOT_CONFIG_FILENAME)


class ConfigWorktreeResolutionTests(unittest.TestCase):
    """Real `git init` + `git worktree add` fixtures for plan D3 (FR-011, SC-007).

    The two files a worktree may lack are per-checkout by design; a worktree
    shares its repository's common Git dir, so `resolve_config_path` falls
    back to the main checkout's copy only when the worktree has none of its
    own.
    """

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Resolved once up front so every path built from it agrees with
        # main_worktree_root's own resolved return value (macOS routes /tmp
        # through a /private symlink `git` itself resolves).
        self.base = Path(self.temporary.name).resolve()
        self.main_root = self.base / "main"
        self.main_root.mkdir()
        self._git(self.main_root, "init", "-q")
        self._git(self.main_root, "config", "user.email", "test@example.com")
        self._git(self.main_root, "config", "user.name", "Test")
        (self.main_root / "README.md").write_text("# sample\n", encoding="utf-8")
        self._git(self.main_root, "add", "README.md")
        self._git(self.main_root, "commit", "-q", "-m", "init")

    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)

    def _add_worktree(self, name: str = "wt") -> Path:
        worktree_root = self.base / name
        self._git(self.main_root, "worktree", "add", "-q", "-b", f"{name}-branch", str(worktree_root), "HEAD")
        return worktree_root

    def _write_config(self, root: Path, slug: str) -> Path:
        path = root / ROOT_CONFIG_FILENAME
        path.write_text(
            'schema_version: "1.0"\n'
            "linear:\n"
            '  workspace_id: "11111111-1111-4111-8111-111111111111"\n'
            '  team_id: "22222222-2222-4222-8222-222222222222"\n'
            '  team_key: "WOR"\n'
            "repository:\n"
            f'  slug: "{slug}"\n',
            encoding="utf-8",
        )
        return path

    def test_worktree_without_its_own_config_resolves_the_main_checkouts(self) -> None:
        main_config = self._write_config(self.main_root, "main-repo")
        worktree_root = self._add_worktree()

        self.assertEqual(resolve_config_path(worktree_root, None), main_config)

    def test_worktree_local_config_wins_over_the_main_checkouts(self) -> None:
        self._write_config(self.main_root, "main-repo")
        worktree_root = self._add_worktree()
        local_config = self._write_config(worktree_root, "worktree-repo")

        self.assertEqual(resolve_config_path(worktree_root, None), local_config)

    def test_main_checkout_is_unaffected_by_the_worktree_fallback(self) -> None:
        main_config = self._write_config(self.main_root, "main-repo")

        self.assertEqual(resolve_config_path(self.main_root, None), main_config)

    def test_a_non_git_directory_is_unaffected(self) -> None:
        plain = self.base / "plain"
        plain.mkdir()

        self.assertEqual(resolve_config_path(plain, None), plain / ROOT_CONFIG_FILENAME)


if __name__ == "__main__":
    unittest.main()
