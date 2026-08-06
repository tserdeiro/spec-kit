"""Tests for `doctor --fix`.

`--fix` covers exactly one mechanical, local-only remediation: adding the
missing `.gitignore` entry for `.speckit-linear.env`, the only file this
extension owns that can carry a credential. Every scenario also proves
`--fix` never issues any GraphQL mutation (there is no Linear client involved
anywhere in this file) and that "nothing to fix" is a byte-for-byte no-op.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from spec_kit_linear.cli import main
from spec_kit_linear.config import ROOT_CONFIG_FILENAME
from spec_kit_linear.env_files import REPO_ENV_FILENAME
from tests.support.fixtures import isolate_operator_global_env


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


class DoctorFixTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "consumer"
        fixture = Path(__file__).parents[1] / "fixtures" / "consumer"
        shutil.copytree(fixture, self.root)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "test@example.com")
        _git(self.root, "config", "user.name", "Test")

    def _invoke(self, arguments: list[str]) -> tuple[int, dict[str, object]]:
        output = StringIO()
        with redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def _doctor(self, *extra: str) -> tuple[int, dict[str, object]]:
        return self._invoke(["doctor", "--offline", "--root", str(self.root), "--json", *extra])

    def _codes(self, payload: dict[str, object]) -> list[str]:
        return [item["code"] for item in payload["diagnostics"]]

    def test_reports_a_missing_gitignore_entry_without_fix(self) -> None:
        code, payload = self._doctor()

        self.assertEqual(code, 0)
        self.assertIn("gitignore_missing_entries", self._codes(payload))
        self.assertFalse((self.root / ".gitignore").exists())

    def test_fix_adds_the_missing_gitignore_entry_additively(self) -> None:
        (self.root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

        code, payload = self._doctor("--fix")

        self.assertEqual(code, 0)
        self.assertIn("fixed_gitignore", self._codes(payload))
        content = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("node_modules/", content)
        self.assertIn(REPO_ENV_FILENAME, content)
        # The committed shared config is never gitignored.
        self.assertNotIn(ROOT_CONFIG_FILENAME, content)

    def test_fix_with_nothing_to_fix_is_a_clean_noop(self) -> None:
        (self.root / ".gitignore").write_text(f"{REPO_ENV_FILENAME}\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file() and ".git/" not in path.as_posix()}

        code, payload = self._doctor("--fix")

        self.assertEqual(code, 0)
        after = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file() and ".git/" not in path.as_posix()}
        self.assertEqual(before, after)
        self.assertNotIn("fixed_gitignore", self._codes(payload))
        self.assertNotIn("gitignore_missing_entries", self._codes(payload))

    def test_doctor_outside_a_git_worktree_fails_as_a_prerequisite(self) -> None:
        shutil.rmtree(self.root / ".git")

        code, payload = self._doctor()

        self.assertEqual(code, 4)
        self.assertEqual(payload["diagnostics"][0]["code"], "git_root")


if __name__ == "__main__":
    unittest.main()
