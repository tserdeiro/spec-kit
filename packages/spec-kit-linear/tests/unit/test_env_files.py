from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_linear import env_files
from spec_kit_linear.env_files import REPO_ENV_FILENAME, load_dotenv_files
from tests.support.fixtures import isolate_operator_global_env


class EnvFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # Point the operator-global file at a location inside the fixture so
        # tests never touch the real ~/.config/speckit-linear/env, and so
        # each test starts from "file does not exist" instead of leaking
        # global state from the developer's own machine.
        self._global_env_path = self.root / "global-env"
        self._patch_global_path(self._global_env_path)

    def _patch_global_path(self, path: Path) -> None:
        original = env_files.OPERATOR_GLOBAL_ENV_PATH
        env_files.OPERATOR_GLOBAL_ENV_PATH = path
        self.addCleanup(setattr, env_files, "OPERATOR_GLOBAL_ENV_PATH", original)

    def test_repo_env_filename_is_the_dedicated_tooling_file(self) -> None:
        self.assertEqual(REPO_ENV_FILENAME, ".speckit-linear.env")

    def test_loads_only_allowlisted_prefixes(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text(
            "LINEAR_API_KEY=from-repo-env\n"
            "SPECKIT_LINEAR_OPERATOR_ID=operator-1\n"
            "SOME_OTHER_VAR=ignored\n"
            "PATH=should-never-be-touched\n",
            encoding="utf-8",
        )
        environment: dict[str, str] = {}

        diagnostics = load_dotenv_files(self.root, environment)

        self.assertEqual(environment, {"LINEAR_API_KEY": "from-repo-env", "SPECKIT_LINEAR_OPERATOR_ID": "operator-1"})
        self.assertEqual(diagnostics, [])

    def test_real_environment_always_wins_over_repo_env(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text("LINEAR_API_KEY=from-repo-env\n", encoding="utf-8")
        environment = {"LINEAR_API_KEY": "already-set"}

        load_dotenv_files(self.root, environment)

        self.assertEqual(environment["LINEAR_API_KEY"], "already-set")

    def test_repo_env_wins_over_operator_global(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text("LINEAR_API_KEY=from-repo\n", encoding="utf-8")
        self._global_env_path.write_text("LINEAR_API_KEY=from-global\n", encoding="utf-8")
        environment: dict[str, str] = {}

        load_dotenv_files(self.root, environment)

        self.assertEqual(environment["LINEAR_API_KEY"], "from-repo")

    def test_operator_global_fills_in_when_repo_env_is_silent(self) -> None:
        self._global_env_path.write_text("SPECKIT_LINEAR_OPERATOR_ID=global-operator\n", encoding="utf-8")
        environment: dict[str, str] = {}

        load_dotenv_files(self.root, environment)

        self.assertEqual(environment["SPECKIT_LINEAR_OPERATOR_ID"], "global-operator")

    def test_a_generic_project_dotenv_is_never_read(self) -> None:
        # The whole point of the dedicated .speckit-linear.env filename: a
        # consumer repository's own project .env must never be mixed with
        # this extension's values, and must never be read at all.
        (self.root / ".env").write_text("LINEAR_API_KEY=from-project-dotenv\n", encoding="utf-8")
        environment: dict[str, str] = {}

        load_dotenv_files(self.root, environment)

        self.assertEqual(environment, {})

    def test_missing_files_are_a_silent_no_op(self) -> None:
        environment: dict[str, str] = {}

        diagnostics = load_dotenv_files(self.root, environment)

        self.assertEqual(environment, {})
        self.assertEqual(diagnostics, [])

    def test_malformed_lines_are_diagnostics_not_crashes(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text(
            "not-a-valid-line\n"
            "1INVALID=nope\n"
            "# a comment\n"
            "\n"
            "LINEAR_API_KEY=still-loaded\n",
            encoding="utf-8",
        )
        environment: dict[str, str] = {}

        diagnostics = load_dotenv_files(self.root, environment)

        self.assertEqual(environment["LINEAR_API_KEY"], "still-loaded")
        codes = [diagnostic.code for diagnostic in diagnostics]
        self.assertEqual(codes.count("env_file_malformed"), 2)
        for diagnostic in diagnostics:
            self.assertNotIn("still-loaded", diagnostic.message)

    def test_quoted_values_are_unwrapped(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text(
            'LINEAR_API_KEY="quoted-value"\n' "SPECKIT_LINEAR_OPERATOR_ID='single-quoted'\n",
            encoding="utf-8",
        )
        environment: dict[str, str] = {}

        load_dotenv_files(self.root, environment)

        self.assertEqual(environment["LINEAR_API_KEY"], "quoted-value")
        self.assertEqual(environment["SPECKIT_LINEAR_OPERATOR_ID"], "single-quoted")

    def test_no_shell_interpolation_is_performed(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text("LINEAR_API_KEY=$HOME/literal\n", encoding="utf-8")
        environment: dict[str, str] = {}

        load_dotenv_files(self.root, environment)

        self.assertEqual(environment["LINEAR_API_KEY"], "$HOME/literal")


if __name__ == "__main__":
    unittest.main()


class PersistProcessCredentialTests(EnvFilesTests):
    def _load(self, environment: dict[str, str]) -> None:
        load_dotenv_files(self.root, environment)

    def test_persists_an_inline_api_key_to_the_repo_file(self) -> None:
        environment = {"LINEAR_API_KEY": "lin_api_inline"}
        self._load(environment)

        written = env_files.persist_process_credential(self.root, environment)

        assert written is not None
        self.assertEqual(written, self.root / REPO_ENV_FILENAME)
        content = written.read_text(encoding="utf-8")
        self.assertIn("LINEAR_API_KEY=lin_api_inline\n", content)
        self.assertTrue(content.startswith("#"))
        self.assertEqual(written.stat().st_mode & 0o777, 0o600)

    def test_never_touches_an_existing_repo_file(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text("# mine\n", encoding="utf-8")
        environment = {"LINEAR_API_KEY": "lin_api_inline"}
        self._load(environment)

        self.assertIsNone(env_files.persist_process_credential(self.root, environment))
        self.assertEqual((self.root / REPO_ENV_FILENAME).read_text(encoding="utf-8"), "# mine\n")

    def test_never_shadows_a_credential_a_file_already_defines(self) -> None:
        self._global_env_path.parent.mkdir(parents=True, exist_ok=True)
        self._global_env_path.write_text("LINEAR_API_KEY=lin_api_global\n", encoding="utf-8")
        environment = {"LINEAR_API_KEY": "lin_api_inline"}
        self._load(environment)

        self.assertIsNone(env_files.persist_process_credential(self.root, environment))
        self.assertFalse((self.root / REPO_ENV_FILENAME).exists())

    def test_a_file_loaded_credential_is_not_re_persisted(self) -> None:
        (self.root / "other").mkdir()
        self._global_env_path.parent.mkdir(parents=True, exist_ok=True)
        self._global_env_path.write_text("LINEAR_API_KEY=lin_api_global\n", encoding="utf-8")
        environment: dict[str, str] = {}
        self._load(environment)

        self.assertIsNone(env_files.persist_process_credential(self.root, environment))
        self.assertFalse((self.root / REPO_ENV_FILENAME).exists())

    def test_an_oauth_token_is_never_persisted(self) -> None:
        environment = {"LINEAR_OAUTH_ACCESS_TOKEN": "oauth-token"}
        self._load(environment)

        self.assertIsNone(env_files.persist_process_credential(self.root, environment))
        self.assertFalse((self.root / REPO_ENV_FILENAME).exists())


class EnvFilesWorktreeResolutionTests(unittest.TestCase):
    """Real `git init` + `git worktree add` fixtures for plan D3 (FR-011, SC-007).

    The per-repo env file is per-checkout by design; a worktree shares its
    repository's common Git dir, so `repo_env_path`/`load_dotenv_files` fall
    back to the main checkout's copy only when the worktree has none of its
    own.
    """

    def setUp(self) -> None:
        isolate_operator_global_env(self)
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

    def test_worktree_without_its_own_env_file_resolves_the_main_checkouts(self) -> None:
        main_env = self.main_root / REPO_ENV_FILENAME
        main_env.write_text("LINEAR_API_KEY=from-main\n", encoding="utf-8")
        worktree_root = self._add_worktree()

        self.assertEqual(env_files.repo_env_path(worktree_root), main_env)

        environment: dict[str, str] = {}
        load_dotenv_files(worktree_root, environment)
        self.assertEqual(environment["LINEAR_API_KEY"], "from-main")

    def test_worktree_local_env_file_wins_over_the_main_checkouts(self) -> None:
        (self.main_root / REPO_ENV_FILENAME).write_text("LINEAR_API_KEY=from-main\n", encoding="utf-8")
        worktree_root = self._add_worktree()
        local_env = worktree_root / REPO_ENV_FILENAME
        local_env.write_text("LINEAR_API_KEY=from-worktree\n", encoding="utf-8")

        self.assertEqual(env_files.repo_env_path(worktree_root), local_env)

        environment: dict[str, str] = {}
        load_dotenv_files(worktree_root, environment)
        self.assertEqual(environment["LINEAR_API_KEY"], "from-worktree")

    def test_main_checkout_is_unaffected_by_the_worktree_fallback(self) -> None:
        main_env = self.main_root / REPO_ENV_FILENAME
        main_env.write_text("LINEAR_API_KEY=from-main\n", encoding="utf-8")

        self.assertEqual(env_files.repo_env_path(self.main_root), main_env)

    def test_a_non_git_directory_is_unaffected(self) -> None:
        plain = self.base / "plain"
        plain.mkdir()

        self.assertEqual(env_files.repo_env_path(plain), plain / REPO_ENV_FILENAME)
