from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.commit_msg import main
from spec_kit_code_review.commit_policy import is_valid_commit_subject


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = PACKAGE_ROOT / "scripts" / "bash" / "commit-msg.sh"


class CommitMessageTests(unittest.TestCase):
    def _message(self, raw: bytes) -> Path:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "message with spaces.txt"
        path.write_bytes(raw)
        return path

    def _run_launcher(self, root: Path, message: Path, *, environment: dict[str, str] | None = None, launcher: Path = LAUNCHER) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/sh", str(launcher), str(message)],
            cwd=root,
            env=environment or {"PATH": os.environ["PATH"]},
            text=True,
            capture_output=True,
        )

    def _copy_launcher(self, root: Path, *, policy: bool) -> Path:
        extension = root / "extension" / "scripts" / "bash"
        package = extension.parent.parent / "src" / "spec_kit_code_review"
        extension.mkdir(parents=True)
        package.mkdir(parents=True)
        shutil.copy2(LAUNCHER, extension / "commit-msg.sh")
        shutil.copy2(PACKAGE_ROOT / "src/spec_kit_code_review/commit_msg.py", package / "commit_msg.py")
        if policy:
            shutil.copy2(PACKAGE_ROOT / "src/spec_kit_code_review/commit_policy.py", package / "commit_policy.py")
        return extension / "commit-msg.sh"

    def test_valid_and_invalid_subjects_use_the_shared_policy(self) -> None:
        for subject in ("feat(x): add it", "fix(scope-name): solución", "bad subject", "feat(X): no"):
            with self.subTest(subject=subject):
                path = self._message((subject + "\nbody\n").encode())
                self.assertEqual(main([str(path)]), 0 if is_valid_commit_subject(subject) else 1)

    def test_first_line_handles_crlf_multiline_and_invalid_utf8(self) -> None:
        path = self._message(b"feat(x): ok\r\nbody\n")
        original = path.read_bytes()
        self.assertEqual(main([str(path)]), 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(main([str(self._message(b"bad subject\r\nbody"))]), 1)
        self.assertEqual(main([str(self._message(b"feat(x): \xff\n"))]), 0)

    def test_missing_file_and_wrong_arguments_are_prerequisite_failures(self) -> None:
        self.assertEqual(main(["/no/such/commit-message-file"]), 4)
        self.assertEqual(main([]), 4)
        self.assertEqual(main(["one", "two"]), 4)

    def test_launcher_runs_without_review_or_engine_setup(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "message file"
            message.write_text("bad subject\n", encoding="utf-8")
            result = self._run_launcher(root, message)
        self.assertEqual(result.returncode, 1)
        self.assertIn("type(scope): subject", result.stderr)

    def test_launcher_rejects_a_payload_missing_the_shared_policy(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "message"
            message.write_text("feat(x): ok\n", encoding="utf-8")
            launcher = self._copy_launcher(root, policy=False)
            result = self._run_launcher(root, message, launcher=launcher)
        self.assertEqual(result.returncode, 4)
        self.assertIn("runtime is incomplete", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_launcher_reports_a_missing_python3(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "message"
            message.write_text("feat(x): ok\n", encoding="utf-8")
            path = root / "path"
            path.mkdir()
            dirname = shutil.which("dirname")
            self.assertIsNotNone(dirname)
            (path / "dirname").symlink_to(dirname)
            result = self._run_launcher(root, message, environment={"PATH": str(path)})
        self.assertEqual(result.returncode, 4)
        self.assertIn("install python3 or create .venv/bin/python", result.stderr)

    def test_launcher_reports_a_non_executable_consumer_interpreter(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "message"
            message.write_text("feat(x): ok\n", encoding="utf-8")
            interpreter = root / ".venv/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("not executable\n", encoding="utf-8")
            interpreter.chmod(stat.S_IRUSR | stat.S_IWUSR)
            result = self._run_launcher(root, message)
        self.assertEqual(result.returncode, 4)
        self.assertIn("cannot execute", result.stderr)

    def test_launcher_prefers_the_consumer_venv_interpreter(self) -> None:
        selected = ""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "message"
            message.write_text("bad subject\n", encoding="utf-8")
            marker = root / "selected-interpreter"
            interpreter = root / ".venv/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text(
                "#!/bin/sh\n"
                f"printf 'used\\n' >> {shlex.quote(str(marker))}\n"
                f"exec {shlex.quote(sys.executable)} \"$@\"\n",
                encoding="utf-8",
            )
            interpreter.chmod(interpreter.stat().st_mode | stat.S_IXUSR)
            result = self._run_launcher(root, message)
            selected = marker.read_text(encoding="utf-8") if marker.exists() else ""
        self.assertEqual(result.returncode, 1)
        self.assertGreaterEqual(len(selected.splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
