from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_linear import env_files
from spec_kit_linear.env_files import REPO_ENV_FILENAME, load_dotenv_files


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
