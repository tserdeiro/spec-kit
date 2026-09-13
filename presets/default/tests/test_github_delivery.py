"""Focused tests for the read-only GitHub delivery settings report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import github_delivery

SCRIPT = Path(github_delivery.__file__)


def _fake_gh(tmp_path: Path, monkeypatch, response: str = "{}", fail: bool = False) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$GH_CALLS_LOG\"\n"
        "if [ \"$GH_FAIL\" = 1 ]; then echo 'fake read failed' >&2; exit 1; fi\n"
        "if [ \"$*\" != 'repo view --json deleteBranchOnMerge,mergeCommitAllowed' ]; then\n"
        "  echo 'write or unexpected argv rejected' >&2; exit 9\n"
        "fi\n"
        "printf '%s' \"$GH_RESPONSE\"\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    log = tmp_path / "gh-argv.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("GH_CALLS_LOG", str(log))
    monkeypatch.setenv("GH_RESPONSE", response)
    monkeypatch.setenv("GH_FAIL", "1" if fail else "0")
    return log


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, text=True, capture_output=True)


def test_true_settings_are_reported_but_scope_stays_unverified(tmp_path: Path, monkeypatch) -> None:
    log = _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "deleteBranchOnMerge: compatible (observed true)" in result.stdout
    assert "mergeCommitAllowed: compatible (observed true)" in result.stdout
    assert "force-push protection: unverified" in result.stdout
    assert "Overall: unverified" in result.stdout
    assert "Inspect GitHub Settings → Rules → Rulesets" in result.stdout
    assert "T001" not in result.stdout
    assert log.read_text(encoding="utf-8") == "repo view --json deleteBranchOnMerge,mergeCommitAllowed\n"


def test_false_setting_has_configuration_remediation(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": False, "mergeCommitAllowed": False}))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "deleteBranchOnMerge: incompatible" in result.stdout
    assert "Automatically delete head branches" in result.stdout
    assert "mergeCommitAllowed: incompatible" in result.stdout
    assert "Allow merge commits" in result.stdout
    assert "cause=conflicting-configuration" in result.stdout


def test_missing_field_is_unverified_instead_of_false(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True}))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "deleteBranchOnMerge: compatible" in result.stdout
    assert "mergeCommitAllowed: unverified" in result.stdout
    assert "cause=missing-field" in result.stdout
    assert "incompatible" not in result.stdout


def test_failed_read_keeps_both_settings_unverified(tmp_path: Path, monkeypatch) -> None:
    log = _fake_gh(tmp_path, monkeypatch, fail=True)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("unverified") >= 4
    assert "cause=read-failure" in result.stdout
    assert "fake read failed" in result.stdout
    assert log.read_text(encoding="utf-8") == "repo view --json deleteBranchOnMerge,mergeCommitAllowed\n"


def test_absent_gh_is_capability_unavailable_without_a_call(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    log = tmp_path / "calls.log"
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setenv("GH_CALLS_LOG", str(log))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "capability-unavailable" in result.stdout
    assert "github-cli-unavailable" in result.stdout
    assert "GitHub CLI" in result.stdout
    assert not log.exists()


def test_malformed_response_is_unverified(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, "[]")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("cause=malformed-response") == 2
    assert "unverified" in result.stdout


def test_helper_rejects_mutation_flags_without_invoking_gh(tmp_path: Path, monkeypatch) -> None:
    log = _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
    result = subprocess.run([sys.executable, str(SCRIPT), "--fix"], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 2
    assert "usage: github_delivery.py" in result.stderr
    assert log.read_text(encoding="utf-8") == ""


def test_report_does_not_modify_consumer_files(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / ".gitignore"
    marker.write_text("consumer state\n", encoding="utf-8")
    _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
    assert _run(tmp_path).returncode == 1
    assert marker.read_text(encoding="utf-8") == "consumer state\n"
