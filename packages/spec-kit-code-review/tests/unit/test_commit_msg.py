from __future__ import annotations

import os
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
            result = subprocess.run(
                ["sh", str(LAUNCHER), str(message)],
                cwd=root,
                env={"PATH": os.environ["PATH"]},
                text=True,
                capture_output=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("type(scope): subject", result.stderr)


if __name__ == "__main__":
    unittest.main()
