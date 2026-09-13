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
from pathlib import Path

argv = sys.argv[1:]
with open(os.environ["GH_CALLS_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")
fail_on = os.environ.get("GH_FAIL_ON")
if fail_on and fail_on in " ".join(argv):
    sys.stderr.write(f"fake gh: forced failure on {argv}\\n")
    sys.exit(1)
if argv == ["repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]:
    sys.stdout.write(os.environ.get("GH_DEFAULT_BRANCH", "main") + "\\n")
elif argv == ["pr", "list", "--state", "open", "--limit", "1000", "--json", "headRefName,baseRefName,isDraft"]:
    sys.stdout.write(os.environ.get("GH_PR_LIST_JSON", "[]"))
elif argv == ["pr", "list", "--state", "open", "--limit", "1000", "--json", "number,headRefName,baseRefName,isDraft"]:
    sys.stdout.write(os.environ.get("GH_PR_LIST_JSON", "[]"))
elif len(argv) == 6 and argv[0:3] == ["api", "-X", "PATCH"] and argv[3].startswith("repos/") and argv[4] == "-f":
    number = argv[3].rsplit("/", 1)[-1]
    if os.environ.get("GH_PATCH_FAIL") == number:
        sys.stderr.write(f"fake gh: forced PATCH failure for #{number}\\n")
        sys.exit(1)
elif len(argv) == 4 and argv[0] == "api" and argv[1].startswith("repos/") and argv[2] == "--jq" and argv[3] == ".base.ref":
    number = argv[1].rsplit("/", 1)[-1]
    if os.environ.get("GH_BASE_FAIL") == number:
        sys.stderr.write(f"fake gh: forced base read failure for #{number}\\n")
        sys.exit(1)
    state_path = os.environ.get("GH_BASE_STATE")
    sequences = json.loads(Path(state_path).read_text()) if state_path else {}
    if number in sequences and sequences[number]:
        value = sequences[number].pop(0)
        if state_path:
            Path(state_path).write_text(json.dumps(sequences))
        if value == "__FAIL__":
            sys.stderr.write(f"fake gh: forced base read failure for #{number}\\n")
            sys.exit(1)
        sys.stdout.write(f"{value}\\n")
    else:
        prs = json.loads(os.environ.get("GH_PR_LIST_JSON", "[]"))
        pr = next((item for item in prs if str(item["number"]) == number), None)
        if pr is None:
            sys.stderr.write(f"fake gh: unknown pull request #{number}\\n")
            sys.exit(1)
        sys.stdout.write(f"{pr['baseRefName']}\\n")
elif len(argv) == 4 and argv[0:2] == ["pr", "merge"] and argv[3] == "--merge":
    pass
else:
    sys.stderr.write(f"fake gh: unexpected argv: {argv}\\n")
    sys.exit(1)
'''

_DELIVERY_FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
from urllib.parse import unquote

argv = sys.argv[1:]
with open(os.environ["GH_CALLS_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")

def reject(message):
    sys.stderr.write("fake gh: " + message + "\\n")
    raise SystemExit(13)

if argv and argv[0] == "api" and argv[1:3] != ["--method", "GET"]:
    reject("write API calls are forbidden")
if argv[:2] in (["repo", "edit"], ["pr", "merge"]) or argv[:1] in (["push"], ["merge"]):
    reject("write commands are forbidden")

case = os.environ.get("GH_DELIVERY_CASE", "compatible")
if argv == ["repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]:
    sys.stdout.write("main\\n")
elif argv == ["repo", "view", "--json", "deleteBranchOnMerge,mergeCommitAllowed"]:
    if case == "failed-read":
        sys.stderr.write("transport failure while reading repository settings\\n")
        raise SystemExit(1)
    sys.stdout.write(json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
elif argv and argv[-1] == "repos/{owner}/{repo}/branches?per_page=100":
    sys.stdout.write(json.dumps([[{"name": "main"}, {"name": "001-feature"}, {"name": "001-T001-task"}]]))
elif argv and "/rules/branches/" in argv[-1]:
    if case == "permission-denied":
        sys.stdout.write(json.dumps({"message": "resource not accessible due to insufficient permissions"}))
        sys.stderr.write("HTTP 403: Resource not accessible; permissions required\\n")
        raise SystemExit(1)
    sys.stdout.write("[[]]")
elif argv and "/protection" in argv[-1]:
    branch = unquote(argv[-1].split("/branches/", 1)[1].rsplit("/protection", 1)[0])
    allow_deletions = case != "cleanup-blocked" or branch == "main"
    sys.stdout.write(json.dumps({
        "allow_force_pushes": {"enabled": False}, "enforce_admins": {"enabled": True},
        "allow_deletions": {"enabled": allow_deletions}, "lock_branch": {"enabled": False},
        "required_linear_history": {"enabled": False},
    }))
else:
    reject("unexpected read argv")
'''

_CHECK_PREREQUISITES = """#!/bin/sh
printf 'BRANCH: 003-feature\\n'
printf 'FEATURE_DIR: specs/003-feature\\n'
"""

def install_fake_linear(repo: Path) -> Path:
    """A fake linear extension whose ``run.sh`` appends its argv to the returned log file."""
    run_sh = repo / ".specify/extensions/linear/scripts/bash/run.sh"
    run_sh.parent.mkdir(parents=True)
    calls = repo / "linear-calls.txt"
    run_sh.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{calls}"\n', encoding="utf-8")
    run_sh.chmod(0o755)
    return calls

def install_fake_delivery_gh(root: Path) -> tuple[Path, Path]:
    """Install a read-only fake GitHub CLI for installed-helper tests."""
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    gh = bin_dir / "gh"
    gh.write_text(_DELIVERY_FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    calls = root / "gh-calls.jsonl"
    calls.write_text("", encoding="utf-8")
    return bin_dir, calls

@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway, initialized git repository. Every later git call this
    process makes also sees the isolated config, not only these calls, since
    monkeypatch mutates the process environment rather than a local dict."""
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    calls = (["init", "--initial-branch=main", "-q"], ["config", "user.email", "t@example.invalid"],
             ["config", "user.name", "spec-kit tests"], ["config", "commit.gpgsign", "false"])
    for args in calls:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root

@pytest.fixture
def feature_repo(repo: Path, tmp_path: Path) -> Path:
    """``repo`` with a bare ``origin`` remote, ``003-feature`` pushed, and a
    fake check-prerequisites.sh reporting that branch and feature directory."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True, capture_output=True)
    setup = (["remote", "add", "origin", str(origin)], ["commit", "--allow-empty", "-q", "-m", "chore: initial"],
             ["push", "-q", "origin", "main"], ["switch", "-q", "-c", "003-feature"],
             ["push", "-q", "-u", "origin", "003-feature"])
    for args in setup:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    prerequisites = repo / ".specify/scripts/bash/check-prerequisites.sh"
    prerequisites.parent.mkdir(parents=True)
    prerequisites.write_text(_CHECK_PREREQUISITES, encoding="utf-8")
    prerequisites.chmod(0o755)
    return repo

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
