"""Fixtures for the preset's script tests: sys.path for ``_common``, a
temporary git repository, and a fake gh recording every call."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "python"))

_FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys

argv = sys.argv[1:]
with open(os.environ["GH_CALLS_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")
if argv == ["repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]:
    sys.stdout.write(os.environ.get("GH_DEFAULT_BRANCH", "main") + "\\n")
else:
    sys.stderr.write(f"fake gh: unexpected argv: {argv}\\n")
    sys.exit(1)
'''

@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway, initialized git repository."""
    root = tmp_path / "repo"
    root.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    calls = (["init", "--initial-branch=main", "-q"], ["config", "user.email", "t@example.invalid"],
             ["config", "user.name", "spec-kit tests"], ["config", "commit.gpgsign", "false"])
    for args in calls:
        subprocess.run(["git", *args], cwd=root, check=True, env=env, capture_output=True)
    return root

@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake gh, first on PATH, recording every call's argv as one JSON line."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    script = bin_dir / "gh"
    script.write_text(_FAKE_GH, encoding="utf-8")
    script.chmod(0o755)
    calls_log = tmp_path / "gh-calls.jsonl"
    calls_log.write_text("", encoding="utf-8")
    monkeypatch.setenv("GH_CALLS_LOG", str(calls_log))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return calls_log
