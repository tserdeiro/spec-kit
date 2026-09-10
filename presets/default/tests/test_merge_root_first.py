"""Tests for the preset's merge_root_first script: root-first order over a
three-PR stack listed out of order, a mid-stack merge failure, and the
empty case, against feature_repo/fake_gh from conftest.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import install_fake_linear

import merge_root_first

def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

_LIST_CALL = ["pr", "list", "--state", "open", "--limit", "1000",
              "--json", "number,headRefName,baseRefName,isDraft"]

_STACK_PRS = json.dumps([
    {"number": 3, "headRefName": "003-T003-z", "baseRefName": "003-T002-y", "isDraft": False},
    {"number": 1, "headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": False},
    {"number": 2, "headRefName": "003-T002-y", "baseRefName": "003-T001-x", "isDraft": False},
])

def test_three_pr_stack_merges_root_first_in_order(feature_repo: Path, fake_gh: Path,
                                                     monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _STACK_PRS)
    monkeypatch.chdir(feature_repo)
    assert merge_root_first.main([]) == 0
    assert capsys.readouterr().out == "merged #1 003-T001-x\nmerged #2 003-T002-y\nmerged #3 003-T003-z\n"
    calls = _calls(fake_gh)
    assert calls == [
        _LIST_CALL,
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/1", "-f", "base=003-feature"],
        ["pr", "merge", "1", "--merge"],
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/2", "-f", "base=003-feature"],
        ["pr", "merge", "2", "--merge"],
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/3", "-f", "base=003-feature"],
        ["pr", "merge", "3", "--merge"],
    ]
    assert not any("--delete-branch" in arg for call in calls for arg in call)

def test_mid_stack_merge_failure_stops_before_the_next_retarget(feature_repo: Path, fake_gh: Path,
                                                                  monkeypatch: pytest.MonkeyPatch,
                                                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _STACK_PRS)
    monkeypatch.setenv("GH_FAIL_ON", "pr merge 2 --merge")
    with pytest.raises(SystemExit) as excinfo:
        merge_root_first.merge_root_first(feature_repo)
    assert excinfo.value.code == 2
    assert capsys.readouterr().err.startswith("error: #2:")
    assert _calls(fake_gh) == [
        _LIST_CALL,
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/1", "-f", "base=003-feature"],
        ["pr", "merge", "1", "--merge"],
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/2", "-f", "base=003-feature"],
        ["pr", "merge", "2", "--merge"],
    ]

def test_empty_stack_reports_and_exits_0(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    assert merge_root_first.merge_root_first(feature_repo) == 0
    assert capsys.readouterr().out == "nothing to merge on 003-feature\n"
    assert _calls(fake_gh) == [_LIST_CALL]

def test_reconciles_linear_once_after_merging(feature_repo: Path, fake_gh: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _STACK_PRS)
    calls = install_fake_linear(feature_repo)
    assert merge_root_first.merge_root_first(feature_repo) == 0
    assert calls.read_text(encoding="utf-8").strip() == "push --hook"

def test_reconcile_not_called_on_the_empty_stack(feature_repo: Path, fake_gh: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    calls = install_fake_linear(feature_repo)
    assert merge_root_first.merge_root_first(feature_repo) == 0
    assert not calls.exists()

def test_reconcile_is_a_silent_no_op_without_the_extension(feature_repo: Path, fake_gh: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _STACK_PRS)
    assert merge_root_first.merge_root_first(feature_repo) == 0
    assert not (feature_repo / ".specify/extensions/linear").exists()
