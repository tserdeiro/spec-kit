"""Tests for the preset's pr_create script: feature/work-item base
resolution and the task case's branch-identity check and stack-aware
base, against feature_repo/fake_gh from conftest.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import pr_create

LEDGER = "- [x] T001 Sample\n- [ ] T002 Sample\n"

def _set_trunk(repo: Path, branch: str) -> None:
    config = repo / ".specify/extensions/git/git-config.yml"
    config.parent.mkdir(parents=True)
    config.write_text(f'trunk: "{branch}"\n', encoding="utf-8")

def _write_ledger(repo: Path, text: str) -> None:
    path = repo / "specs/003-feature/tasks.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")

def _switch(repo: Path, branch: str, from_ref: str | None = None) -> None:
    args = ["switch", "-q", "-c", branch] + ([from_ref] if from_ref else [])
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

def _push_branch(repo: Path, name: str) -> None:
    _switch(repo, name)
    subprocess.run(["git", "push", "-q", "origin", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-q", "003-feature"], cwd=repo, check=True, capture_output=True)

@pytest.mark.parametrize("kind", ["feature", "work-item"])
def test_main_prints_the_configured_trunk(feature_repo: Path, kind: str, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    _set_trunk(feature_repo, "release")
    monkeypatch.chdir(feature_repo)
    assert pr_create.main([kind]) == 0
    assert capsys.readouterr().out == "base=release\n"

def test_feature_or_work_item_falls_back_to_the_github_default(feature_repo: Path, fake_gh: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_DEFAULT_BRANCH", "trunk-main")
    assert pr_create.feature_or_work_item(feature_repo) == "trunk-main"

def test_task_with_no_open_pr_uses_the_feature_branch(feature_repo: Path, fake_gh: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    _write_ledger(feature_repo, LEDGER)
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    _switch(feature_repo, "003-T002-slug")
    assert pr_create.task(feature_repo, "") == "003-feature"

def test_task_stacks_on_the_open_non_draft_prs_head(feature_repo: Path, fake_gh: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    _write_ledger(feature_repo, LEDGER)
    _push_branch(feature_repo, "003-T001-x")
    _switch(feature_repo, "003-T002-slug", "003-T001-x")
    monkeypatch.setenv("GH_PR_LIST_JSON", json.dumps(
        [{"headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": False}]))
    assert pr_create.task(feature_repo, "") == "003-T001-x"

def test_task_named_task_overrides_the_ledger(feature_repo: Path, fake_gh: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    _write_ledger(feature_repo, LEDGER)  # first unchecked is T002
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    _switch(feature_repo, "003-T003-slug")
    assert pr_create.task(feature_repo, "T003") == "003-feature"

def test_task_branch_mismatch_exits_2(feature_repo: Path) -> None:
    _write_ledger(feature_repo, LEDGER)  # first unchecked is T002
    _switch(feature_repo, "003-T003-slug")
    with pytest.raises(SystemExit) as excinfo:
        pr_create.task(feature_repo, "")
    assert excinfo.value.code == 2

def test_task_no_unchecked_task_exits_2(feature_repo: Path) -> None:
    _write_ledger(feature_repo, "- [x] T001 Sample\n")
    _switch(feature_repo, "003-T002-slug")
    with pytest.raises(SystemExit) as excinfo:
        pr_create.task(feature_repo, "")
    assert excinfo.value.code == 2
