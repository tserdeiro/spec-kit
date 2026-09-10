"""Tests for the preset's stack_propagate script: a two-hop chain, a
conflict on the first hop, and an empty chain, against feature_repo/
fake_gh from conftest.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import install_fake_linear

import stack_propagate

def _git_out(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return result.stdout.strip()

def _push_branch(repo: Path, name: str, from_ref: str = "origin/003-feature") -> None:
    subprocess.run(["git", "switch", "-q", "-c", name, from_ref], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-q", "003-feature"], cwd=repo, check=True, capture_output=True)

def _commit(repo: Path, path: str, content: str) -> None:
    full = repo / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "test: change file"], cwd=repo, check=True, capture_output=True)

_CHAIN_PRS = json.dumps([
    {"headRefName": "003-T002-y", "baseRefName": "003-T001-x", "isDraft": False},
    {"headRefName": "003-T003-z", "baseRefName": "003-T002-y", "isDraft": False},
])

def test_two_hop_chain_merges_and_pushes_in_stack_order(feature_repo: Path, fake_gh: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    _push_branch(feature_repo, "003-T001-x")
    _push_branch(feature_repo, "003-T002-y", "origin/003-T001-x")
    _push_branch(feature_repo, "003-T003-z", "origin/003-T002-y")
    _git_out(feature_repo, "switch", "-q", "003-T001-x")
    _commit(feature_repo, "fix.txt", "fixed\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-T001-x")
    monkeypatch.setenv("GH_PR_LIST_JSON", _CHAIN_PRS)
    monkeypatch.chdir(feature_repo)
    assert stack_propagate.main(["003-T001-x"]) == 0
    assert _git_out(feature_repo, "branch", "--show-current") == "003-T001-x"
    for branch, task in (("003-T002-y", "T002"), ("003-T003-z", "T003")):
        subject = f"merge(task): carry the T001 fix into {task}"
        assert _git_out(feature_repo, "log", branch, "-1", "--format=%s") == subject
        assert _git_out(feature_repo, "log", f"origin/{branch}", "-1", "--format=%s") == subject

def test_conflict_on_the_first_hop_aborts_before_the_second(feature_repo: Path, fake_gh: Path,
                                                              monkeypatch: pytest.MonkeyPatch,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    _commit(feature_repo, "conflict.txt", "base\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-feature")
    _push_branch(feature_repo, "003-T001-x")
    _push_branch(feature_repo, "003-T002-y", "origin/003-T001-x")
    _push_branch(feature_repo, "003-T003-z", "origin/003-T002-y")
    _git_out(feature_repo, "switch", "-q", "003-T002-y")
    _commit(feature_repo, "conflict.txt", "from T002\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-T002-y")
    _git_out(feature_repo, "switch", "-q", "003-T001-x")
    _commit(feature_repo, "conflict.txt", "from the fix\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-T001-x")
    monkeypatch.setenv("GH_PR_LIST_JSON", _CHAIN_PRS)
    calls = install_fake_linear(feature_repo)
    with pytest.raises(SystemExit) as excinfo:
        stack_propagate.propagate(feature_repo, "003-T001-x")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: merge conflict carrying the fix into 003-T002-y\n"
    assert _git_out(feature_repo, "branch", "--show-current") == "003-T002-y"
    subject = _git_out(feature_repo, "log", "origin/003-T003-z", "-1", "--format=%s")
    assert subject != "merge(task): carry the T001 fix into T003"
    assert not calls.exists()  # nothing was pushed: nothing to reconcile

def test_a_conflict_on_the_second_hop_still_reconciles_the_first_push(feature_repo: Path, fake_gh: Path,
                                                                        monkeypatch: pytest.MonkeyPatch,
                                                                        capsys: pytest.CaptureFixture[str]) -> None:
    _commit(feature_repo, "conflict.txt", "base\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-feature")
    _push_branch(feature_repo, "003-T001-x")
    _push_branch(feature_repo, "003-T002-y", "origin/003-T001-x")
    _push_branch(feature_repo, "003-T003-z", "origin/003-T002-y")
    _git_out(feature_repo, "switch", "-q", "003-T003-z")
    _commit(feature_repo, "conflict.txt", "from T003\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-T003-z")
    _git_out(feature_repo, "switch", "-q", "003-T001-x")
    _commit(feature_repo, "conflict.txt", "from the fix\n")
    _git_out(feature_repo, "push", "-q", "origin", "003-T001-x")
    monkeypatch.setenv("GH_PR_LIST_JSON", _CHAIN_PRS)
    calls = install_fake_linear(feature_repo)
    with pytest.raises(SystemExit) as excinfo:
        stack_propagate.propagate(feature_repo, "003-T001-x")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: merge conflict carrying the fix into 003-T003-z\n"
    assert _git_out(feature_repo, "log", "origin/003-T002-y", "-1", "--format=%s") == "merge(task): carry the T001 fix into T002"
    assert calls.read_text(encoding="utf-8") == "push --hook\n"  # T002 was pushed: reconciled once

def test_empty_chain_reports_and_exits_0_without_touching_git(feature_repo: Path, fake_gh: Path,
                                                                 monkeypatch: pytest.MonkeyPatch,
                                                                 capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    assert stack_propagate.propagate(feature_repo, "003-T001-x") == 0
    assert capsys.readouterr().out == "nothing stacked on 003-T001-x\n"
    assert _git_out(feature_repo, "branch", "--show-current") == "003-feature"

def test_reconciles_linear_once_after_propagating(feature_repo: Path, fake_gh: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _push_branch(feature_repo, "003-T001-x")
    _push_branch(feature_repo, "003-T002-y", "origin/003-T001-x")
    _push_branch(feature_repo, "003-T003-z", "origin/003-T002-y")
    monkeypatch.setenv("GH_PR_LIST_JSON", _CHAIN_PRS)
    calls = install_fake_linear(feature_repo)
    assert stack_propagate.propagate(feature_repo, "003-T001-x") == 0
    assert calls.read_text(encoding="utf-8").strip() == "push --hook"

def test_reconcile_not_called_on_the_empty_chain(feature_repo: Path, fake_gh: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    calls = install_fake_linear(feature_repo)
    assert stack_propagate.propagate(feature_repo, "003-T001-x") == 0
    assert not calls.exists()

def test_reconcile_is_a_silent_no_op_without_the_extension(feature_repo: Path, fake_gh: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _push_branch(feature_repo, "003-T001-x")
    _push_branch(feature_repo, "003-T002-y", "origin/003-T001-x")
    _push_branch(feature_repo, "003-T003-z", "origin/003-T002-y")
    monkeypatch.setenv("GH_PR_LIST_JSON", _CHAIN_PRS)
    assert stack_propagate.propagate(feature_repo, "003-T001-x") == 0
    assert not (feature_repo / ".specify/extensions/linear").exists()
