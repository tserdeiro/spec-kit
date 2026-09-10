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
_ONE_PR = json.dumps([{"number": 1, "headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": False}])

def _base_sequence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: list[str]) -> None:
    state = tmp_path / "base-sequence.json"
    state.write_text(json.dumps({"1": values}), encoding="utf-8")
    monkeypatch.setenv("GH_BASE_STATE", str(state))

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
        ["api", "repos/{owner}/{repo}/pulls/1", "--jq", ".base.ref"],
        ["pr", "merge", "1", "--merge"],
        ["api", "repos/{owner}/{repo}/pulls/2", "--jq", ".base.ref"],
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/2", "-f", "base=003-feature"],
        ["pr", "merge", "2", "--merge"],
        ["api", "repos/{owner}/{repo}/pulls/3", "--jq", ".base.ref"],
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
        ["api", "repos/{owner}/{repo}/pulls/1", "--jq", ".base.ref"],
        ["pr", "merge", "1", "--merge"],
        ["api", "repos/{owner}/{repo}/pulls/2", "--jq", ".base.ref"],
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

def test_a_mid_stack_failure_still_reconciles_the_merges_made(feature_repo: Path, fake_gh: Path,
                                                               monkeypatch: pytest.MonkeyPatch,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _STACK_PRS)
    monkeypatch.setenv("GH_FAIL_ON", "pr merge 2 --merge")
    calls = install_fake_linear(feature_repo)
    with pytest.raises(SystemExit) as excinfo:
        merge_root_first.merge_root_first(feature_repo)
    assert excinfo.value.code == 2
    assert capsys.readouterr().err.startswith("error: #2:")
    assert calls.read_text(encoding="utf-8") == "push --hook\n"  # #1 was merged: reconciled once

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

def test_correct_base_skips_patch(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _ONE_PR)
    _base_sequence(fake_gh.parent, monkeypatch, ["003-feature"])
    assert merge_root_first.merge_root_first(feature_repo) == 0
    assert _calls(fake_gh) == [_LIST_CALL,
        ["api", "repos/{owner}/{repo}/pulls/1", "--jq", ".base.ref"],
        ["pr", "merge", "1", "--merge"]]

def test_patch_race_accepts_verified_auto_retarget(feature_repo: Path, fake_gh: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _ONE_PR)
    _base_sequence(fake_gh.parent, monkeypatch, ["003-T001-old", "003-feature"])
    monkeypatch.setenv("GH_PATCH_FAIL", "1")
    assert merge_root_first.merge_root_first(feature_repo) == 0
    assert _calls(fake_gh) == [_LIST_CALL,
        ["api", "repos/{owner}/{repo}/pulls/1", "--jq", ".base.ref"],
        ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/1", "-f", "base=003-feature"],
        ["api", "repos/{owner}/{repo}/pulls/1", "--jq", ".base.ref"],
        ["pr", "merge", "1", "--merge"]]

def test_patch_failure_with_wrong_base_preserves_error(feature_repo: Path, fake_gh: Path,
                                                        monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _ONE_PR)
    _base_sequence(fake_gh.parent, monkeypatch, ["003-T001-old", "003-T001-old"])
    monkeypatch.setenv("GH_PATCH_FAIL", "1")
    with pytest.raises(SystemExit):
        merge_root_first.merge_root_first(feature_repo)
    assert "forced PATCH failure" in capsys.readouterr().err

def test_initial_base_read_failure_does_not_patch_or_merge(feature_repo: Path, fake_gh: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _ONE_PR)
    monkeypatch.setenv("GH_BASE_STATE", str(fake_gh.parent / "missing-state.json"))
    with pytest.raises(SystemExit):
        merge_root_first.merge_root_first(feature_repo)
    assert _calls(fake_gh) == [_LIST_CALL, ["api", "repos/{owner}/{repo}/pulls/1", "--jq", ".base.ref"]]

@pytest.mark.parametrize("verification_response", ["", "__FAIL__"])
def test_patch_race_verification_failure_preserves_original_error(feature_repo: Path, fake_gh: Path,
                                                                   monkeypatch: pytest.MonkeyPatch,
                                                                   capsys: pytest.CaptureFixture[str],
                                                                   verification_response: str) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", _ONE_PR)
    _base_sequence(fake_gh.parent, monkeypatch, ["003-T001-old", verification_response])
    monkeypatch.setenv("GH_PATCH_FAIL", "1")
    with pytest.raises(SystemExit) as excinfo:
        merge_root_first.merge_root_first(feature_repo)
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: #1: fake gh: forced PATCH failure for #1\n"
    assert not any(call[:2] == ["pr", "merge"] for call in _calls(fake_gh))

def test_retarget_read_failure_after_merge_reconciles_partial_work(feature_repo: Path, fake_gh: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    prs = json.dumps([
        {"number": 1, "headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": False},
        {"number": 2, "headRefName": "003-T002-y", "baseRefName": "003-T001-x", "isDraft": False},
    ])
    monkeypatch.setenv("GH_PR_LIST_JSON", prs)
    monkeypatch.setenv("GH_BASE_FAIL", "2")
    calls = install_fake_linear(feature_repo)
    with pytest.raises(SystemExit):
        merge_root_first.merge_root_first(feature_repo)
    assert calls.read_text(encoding="utf-8") == "push --hook\n"
