"""Focused first-start cases for configured and unconfigured work items."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import task_base
import work_item_start


def _resolver(repo: Path, payload: dict[str, object], code: int = 0) -> None:
    path = repo / ".specify/extensions/linear/scripts/python/resolve_work_item.py"
    path.parent.mkdir(parents=True)
    body = json.dumps(payload)
    path.write_text(
        "import json, sys\n"
        f"print({body!r})\n"
        f"raise SystemExit({code})\n",
        encoding="utf-8",
    )


def _branch(repo: Path) -> str:
    return subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()


def _set_trunk(repo: Path) -> None:
    config = repo / ".specify/extensions/git/git-config.yml"
    config.parent.mkdir(parents=True)
    config.write_text('trunk: "main"\n', encoding="utf-8")


def _install_loader(repo: Path) -> None:
    source = Path(__file__).parents[3] / "packages/spec-kit-linear/src/spec_kit_linear"
    shutil.copytree(source, repo / ".specify/extensions/linear/src/spec_kit_linear")


def test_unconfigured_start_derives_default_and_requires_title(feature_repo: Path) -> None:
    context = work_item_start.start(feature_repo, "WOR-123", "Fix parser crash")
    assert (context.branch_name, context.title, context.configured) == ("wor-123-fix-parser-crash", "Fix parser crash", False)
    with pytest.raises(SystemExit):
        work_item_start.start(feature_repo, "WOR-124")


@pytest.mark.parametrize("selected", [False, True])
def test_configured_install_without_resolver_does_not_fallback(feature_repo: Path, selected: bool) -> None:
    _install_loader(feature_repo)
    if selected:
        (feature_repo / ".speckit-linear.env").write_text("SPECKIT_LINEAR_CONFIG=selected.yml\n", encoding="utf-8")
        (feature_repo / "selected.yml").write_text("", encoding="utf-8")
    else:
        (feature_repo / "speckit-linear.yml").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        work_item_start.start(feature_repo, "WOR-124", "Fallback title")


@pytest.mark.parametrize("scope", ["local", "main", "global"])
def test_selected_env_without_extension_is_configured_failure(
    feature_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    root = feature_repo
    if scope == "main":
        root = tmp_path / "worktree"
        subprocess.run(["git", "worktree", "add", "--detach", "-q", str(root), "003-feature"], cwd=feature_repo, check=True)
        env_path = feature_repo / ".speckit-linear.env"
    elif scope == "global":
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        env_path = Path.home() / ".config/speckit-linear/env"
    else:
        env_path = feature_repo / ".speckit-linear.env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("SPECKIT_LINEAR_CONFIG=selected.yml\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        work_item_start.start(root, "WOR-125", "Fallback title")


@pytest.mark.parametrize("mode", ["broken", "empty", "malformed"])
def test_config_evidence_does_not_fallback(feature_repo: Path, mode: str) -> None:
    if mode == "broken":
        os.symlink(feature_repo / "missing.yml", feature_repo / "speckit-linear.yml")
    elif mode == "empty":
        (feature_repo / ".speckit-linear.env").write_text("SPECKIT_LINEAR_CONFIG=\n", encoding="utf-8")
        (feature_repo / "speckit-linear.yml").write_text("", encoding="utf-8")
    else:
        (feature_repo / ".speckit-linear.env").write_text("SPECKIT_LINEAR_CONFIG\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        work_item_start.start(feature_repo, "WOR-126", "Fallback title")


def test_configured_start_returns_exact_native_context(feature_repo: Path) -> None:
    _set_trunk(feature_repo)
    _resolver(feature_repo, {"status": "resolved", "resolution": {
        "identifier": "WOR-123", "title": "Native title", "description": "Native context",
        "branch_name": "users/alice/003-T001-task", "url": "https://linear.example/WOR-123",
    }})
    context = task_base.work_item(feature_repo, "WOR-123")
    assert (context.branch_name, context.title, context.description, context.configured) == (
        "users/alice/003-T001-task", "Native title", "Native context", True
    )
    assert _branch(feature_repo) == "users/alice/003-T001-task"


@pytest.mark.parametrize("branch", ["003-feature", "003-T001-task", "@{-1}"])
def test_configured_start_rejects_reserved_or_expanding_names(feature_repo: Path, branch: str) -> None:
    _resolver(feature_repo, {"status": "resolved", "resolution": {
        "identifier": "WOR-123", "title": "Native title", "description": "",
        "branch_name": branch, "url": "",
    }})
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123")
    assert _branch(feature_repo) == "003-feature"


def test_configured_failure_does_not_fallback_or_switch(feature_repo: Path) -> None:
    _resolver(feature_repo, {"status": "error", "message": "Linear unavailable"}, 6)
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "Fallback title")
    assert _branch(feature_repo) == "003-feature"
