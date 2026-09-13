"""Tests for the preset's task_base script: refresh, task, and work-item
modes, against a real git repository (with a bare `origin`) and the fake
`gh` from conftest.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import install_fake_linear

import task_base

def _set_trunk(repo: Path, branch: str) -> None:
    config = repo / ".specify/extensions/git/git-config.yml"
    config.parent.mkdir(parents=True)
    config.write_text(f'trunk: "{branch}"\n', encoding="utf-8")

def _push_branch(repo: Path, name: str, from_ref: str = "origin/003-feature") -> None:
    subprocess.run(["git", "switch", "-q", "-c", name, from_ref], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-q", "003-feature"], cwd=repo, check=True, capture_output=True)

def test_refresh_merges_and_pushes_the_delivery_base(feature_repo: Path, product_gate_pass) -> None:
    _set_trunk(feature_repo, "main")
    calls = install_fake_linear(feature_repo)
    task_base.refresh(feature_repo)
    log = subprocess.run(["git", "log", "origin/003-feature", "-1", "--format=%s"],
                          cwd=feature_repo, text=True, capture_output=True, check=True)
    assert log.stdout.strip() == "chore: initial"  # fast-forward: nothing new to merge
    assert not calls.exists()  # refresh creates no branch: nothing to reconcile

def test_refresh_rejects_the_wrong_current_branch(feature_repo: Path) -> None:
    subprocess.run(["git", "switch", "-q", "-c", "003-other"], cwd=feature_repo, check=True, capture_output=True)
    with pytest.raises(SystemExit) as excinfo:
        task_base.refresh(feature_repo)
    assert excinfo.value.code == 2

def test_task_branches_from_the_feature_branch_with_no_open_pr(feature_repo: Path, fake_gh: Path,
                                                                 monkeypatch: pytest.MonkeyPatch, capsys,
                                                                 product_gate_pass) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    task_base.task(feature_repo, "003-T002-slug")
    assert capsys.readouterr().out == "base=003-feature\n"
    branches = subprocess.run(["git", "branch", "--show-current"], cwd=feature_repo, text=True,
                               capture_output=True, check=True)
    assert branches.stdout.strip() == "003-T002-slug"

def test_task_branches_from_the_open_stacks_top(feature_repo: Path, fake_gh: Path,
                                                  monkeypatch: pytest.MonkeyPatch, capsys,
                                                  product_gate_pass) -> None:
    _push_branch(feature_repo, "003-T001-x")
    monkeypatch.setenv("GH_PR_LIST_JSON", json.dumps(
        [{"headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": False}]))
    task_base.task(feature_repo, "003-T002-slug")
    assert capsys.readouterr().out == "base=003-T001-x\n"

def test_task_stops_on_a_draft_task_pr(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch,
                                       product_gate_pass) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", json.dumps(
        [{"headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": True}]))
    with pytest.raises(SystemExit) as excinfo:
        task_base.task(feature_repo, "003-T002-slug")
    assert excinfo.value.code == 2

def test_task_stops_on_two_open_stacks(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch,
                                       product_gate_pass) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", json.dumps([
        {"headRefName": "003-T001-x", "baseRefName": "003-feature", "isDraft": False},
        {"headRefName": "003-T001-z", "baseRefName": "003-feature", "isDraft": False},
    ]))
    with pytest.raises(SystemExit) as excinfo:
        task_base.task(feature_repo, "003-T002-slug")
    assert excinfo.value.code == 2

def test_work_item_branches_from_the_delivery_base(feature_repo: Path) -> None:
    _set_trunk(feature_repo, "main")
    task_base.work_item(feature_repo, "wor-123-short-slug")
    branches = subprocess.run(["git", "branch", "--show-current"], cwd=feature_repo, text=True,
                               capture_output=True, check=True)
    assert branches.stdout.strip() == "wor-123-short-slug"

def test_reconcile_calls_the_installed_linear_extension_when_present(feature_repo: Path) -> None:
    _set_trunk(feature_repo, "main")
    calls = install_fake_linear(feature_repo)
    task_base.work_item(feature_repo, "wor-124-other-slug")
    assert calls.read_text(encoding="utf-8").strip() == "push --hook"

def test_reconcile_is_a_silent_no_op_without_the_extension(feature_repo: Path) -> None:
    _set_trunk(feature_repo, "main")
    task_base.work_item(feature_repo, "wor-125-third-slug")  # no .specify/extensions/linear: no error
    assert not (feature_repo / ".specify/extensions/linear").exists()


def test_task_gate_runs_before_stack_observation_or_branch_creation(feature_repo: Path, fake_gh: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(task_base.product_gate, "check", lambda _repo: events.append("gate"))
    original = task_base._git

    def record(repo: Path, *args: str):
        events.append("git:" + args[0])
        return original(repo, *args)

    monkeypatch.setattr(task_base, "_git", record)
    monkeypatch.setenv("GH_PR_LIST_JSON", "[]")
    task_base.task(feature_repo, "003-T002-slug")
    assert events[0] == "gate"
    assert "git:switch" in events


def test_task_gate_failure_preserves_checkout_and_skips_mutation(feature_repo: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_base.product_gate, "check", lambda _repo: (_ for _ in ()).throw(SystemExit(2)))
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=feature_repo, text=True,
                            capture_output=True, check=True).stdout
    with pytest.raises(SystemExit) as excinfo:
        task_base.task(feature_repo, "003-T002-slug")
    assert excinfo.value.code == 2
    assert subprocess.run(["git", "branch", "--show-current"], cwd=feature_repo, text=True,
                          capture_output=True, check=True).stdout.strip() == "003-feature"
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=feature_repo, text=True,
                          capture_output=True, check=True).stdout == before
