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


def _batch_resolver(
    repo: Path,
    *,
    proposed: str = "wor-123-new-title",
    branches: dict[str, tuple[str, str | None]] | None = None,
    prs: dict[str, tuple[str, str | None]] | None = None,
    include_affected: bool = True,
) -> None:
    context = {
        "identifier": "WOR-123", "title": "Current title", "description": "context",
        "branch_name": proposed, "url": "",
    }
    branches, prs = branches or {}, prs or {}
    path = repo / ".specify/extensions/linear/scripts/python/resolve_work_item.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import json, sys\n"
        f"context = {context!r}\n"
        f"branches = {branches!r}\n"
        f"prs = {prs!r}\n"
        "raw = json.load(sys.stdin)\n"
        "if 'issue_key' in raw:\n"
        "    print(json.dumps({'status': 'resolved', 'resolution': context}))\n"
        "else:\n"
        "    rows = []\n"
        "    for branch in raw.get('branch_names', []):\n"
        "        status, identifier = branches.get(branch, ('unresolved', None))\n"
        "        resolution = dict(context, identifier=identifier) if identifier else None\n"
        "        row = {'observation': {'kind': 'branch', 'value': branch}, 'status': status, 'resolution': resolution, 'diagnostics': []}\n"
        f"        if {include_affected!r}: row['affected_issue_keys'] = [identifier] if identifier else []\n"
        "        rows.append(row)\n"
        "    for item in raw.get('pull_requests', []):\n"
        "        branch = item['head_branch']\n"
        "        status, identifier = prs.get(branch, ('unresolved', None))\n"
        "        resolution = dict(context, identifier=identifier) if identifier else None\n"
        "        row = {'observation': {'kind': 'pull_request', 'value': branch}, 'status': status, 'resolution': resolution, 'diagnostics': []}\n"
        f"        if {include_affected!r}: row['affected_issue_keys'] = [identifier] if identifier else []\n"
        "        rows.append(row)\n"
        "    print(json.dumps({'status': 'partial', 'observations': rows}))\n",
        encoding="utf-8",
    )


def _pr(branch: str, *, state: str = "OPEN", body: str = "", fork: bool = False) -> dict[str, object]:
    repo_name = "other/repo" if fork else "acme/spec-kit"
    return {
        "number": 7, "state": state, "body": body,
        "head": {"ref": branch, "repo": {"full_name": repo_name}},
        "base": {"ref": "main", "repo": {"full_name": "acme/spec-kit"}},
    }


def _set_prs(monkeypatch: pytest.MonkeyPatch, prs: list[dict[str, object]]) -> None:
    monkeypatch.setenv("GH_PR_API_JSON", json.dumps(prs))


def _branch(repo: Path) -> str:
    return subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()


def _set_trunk(repo: Path) -> None:
    config = repo / ".specify/extensions/git/git-config.yml"
    config.parent.mkdir(parents=True)
    config.write_text('trunk: "main"\n', encoding="utf-8")


def _push_branch(repo: Path, name: str) -> None:
    subprocess.run(["git", "switch", "-q", "-c", name, "origin/003-feature"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", f"work: {name}"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-q", "003-feature"], cwd=repo, check=True, capture_output=True)


def _existing(repo: Path, monkeypatch: pytest.MonkeyPatch, branch: str, *, proposed: str = "wor-123-new-title", branches: dict[str, tuple[str, str | None]] | None = None, prs: dict[str, tuple[str, str | None]] | None = None) -> None:
    _set_trunk(repo)
    _push_branch(repo, branch)
    _batch_resolver(repo, proposed=proposed, branches=branches, prs=prs)
    _set_prs(monkeypatch, [])


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


def test_repeated_start_adopts_existing_head_after_native_name_changes(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(feature_repo, monkeypatch, "users/alice/old-title", proposed="003-feature", branches={"users/alice/old-title": ("resolved", "WOR-123")})
    old = subprocess.run(["git", "rev-parse", "users/alice/old-title"], cwd=feature_repo, text=True, capture_output=True, check=True).stdout.strip()
    context = task_base.work_item(feature_repo, "WOR-123")
    assert context.branch_name == "users/alice/old-title"
    assert _branch(feature_repo) == context.branch_name
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=feature_repo, text=True, capture_output=True, check=True).stdout.strip() == old


def test_old_title_pr_tracker_adopts_open_head_when_native_branch_is_null(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(feature_repo, monkeypatch, "users/alice/old-title", branches={"users/alice/old-title": ("unresolved", None)}, prs={"users/alice/old-title": ("resolved", "WOR-123")})
    monkeypatch.setenv("GH_PR_API_JSON", json.dumps([[_pr("users/alice/old-title", body="## Work item\n\n- Tracker: Fixes WOR-123\n")]]))
    context = task_base.work_item(feature_repo, "WOR-123")
    assert context.branch_name == "users/alice/old-title"


def test_unconfigured_title_only_tracker_adopts_open_head(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "users/alice/old-title")
    _set_prs(monkeypatch, [_pr("users/alice/old-title", body="## Work item\n\n- Tracker: Fixes WOR-123\n")])
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "users/alice/old-title"


@pytest.mark.parametrize(
    "body",
    [
        "## Work item\n\n- Tracker: Fixes WOR-123\n- Tracker: Fixes N/A\n",
        "## Work item\n\n- Tracker: Fixes WOR-123\n- Tracker: Fixes WOR-124\n",
    ],
)
def test_unconfigured_malformed_or_conflicting_tracker_blocks_adoption(
    feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "users/alice/old-title")
    _set_prs(monkeypatch, [_pr("users/alice/old-title", body=body)])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_unconfigured_strict_head_disagreement_blocks_adoption(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "WOR-999-old-title")
    _set_prs(monkeypatch, [_pr("WOR-999-old-title", body="## Work item\n\n- Tracker: Fixes WOR-123\n")])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_unconfigured_matching_tracker_resolves_multi_key_head(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "WOR-123-WOR-999-fix")
    _set_prs(monkeypatch, [_pr("WOR-123-WOR-999-fix", body="## Work item\n\n- Tracker: Fixes WOR-123\n")])
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "WOR-123-WOR-999-fix"


def test_unconfigured_multi_key_head_without_tracker_blocks_creation(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "WOR-123-WOR-999-fix")
    _set_prs(monkeypatch, [_pr("WOR-123-WOR-999-fix")])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_unconfigured_same_head_tracker_conflict_blocks_all_candidates(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "old-title")
    _set_prs(
        monkeypatch,
        [
            _pr("old-title", body="## Work item\n\n- Tracker: Fixes WOR-123\n"),
            _pr("old-title", body="## Work item\n\n- Tracker: Fixes WOR-124\n"),
        ],
    )
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_unconfigured_reserved_head_tracker_is_excluded(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _set_prs(monkeypatch, [_pr("009-T001-name", body="## Work item\n\n- Tracker: Fixes WOR-123\n")])
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "wor-123-new-title"


def test_unconfigured_tracker_outside_section_or_code_is_ignored(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    body = (
        "- Tracker: Fixes WOR-123\n\n"
        "## Work item\n\n"
        "```markdown\n- Tracker: Fixes WOR-123\n```\n\n"
        "    - Tracker: Fixes WOR-123\n"
    )
    _set_prs(monkeypatch, [_pr("old-title", body=body)])
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "wor-123-new-title"


def test_remote_head_is_tracked_and_history_is_preserved(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(feature_repo, monkeypatch, "users/alice/remote", branches={"users/alice/remote": ("resolved", "WOR-123")})
    commit = subprocess.run(["git", "rev-parse", "users/alice/remote"], cwd=feature_repo, text=True, capture_output=True, check=True).stdout.strip()
    subprocess.run(["git", "branch", "-D", "users/alice/remote"], cwd=feature_repo, check=True, capture_output=True)
    task_base.work_item(feature_repo, "WOR-123")
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=feature_repo, text=True, capture_output=True, check=True).stdout.strip() == commit
    assert subprocess.run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], cwd=feature_repo, text=True, capture_output=True, check=True).stdout.strip() == "origin/users/alice/remote"


def test_multiple_remote_heads_same_name_stop_before_adoption(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "users/alice/collision")
    subprocess.run(["git", "remote", "add", "backup", str(feature_repo / ".git")], cwd=feature_repo, check=True, capture_output=True)
    _batch_resolver(feature_repo, branches={"users/alice/collision": ("resolved", "WOR-123")})
    _set_prs(monkeypatch, [])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123")
    assert _branch(feature_repo) == "003-feature"


def test_multiple_existing_candidates_stop_before_switch(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "users/alice/one")
    _push_branch(feature_repo, "users/alice/two")
    _batch_resolver(feature_repo, branches={"users/alice/one": ("resolved", "WOR-123"), "users/alice/two": ("resolved", "WOR-123")})
    _set_prs(monkeypatch, [])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123")
    assert _branch(feature_repo) == "003-feature"


def test_fork_open_head_is_rejected(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _batch_resolver(feature_repo, prs={"forked": ("resolved", "WOR-123")})
    _set_prs(monkeypatch, [_pr("forked", fork=True)])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123")
    assert _branch(feature_repo) == "003-feature"


def test_closed_unmerged_pr_alone_does_not_adopt_or_complete(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _batch_resolver(feature_repo, prs={"closed": ("resolved", "WOR-123")})
    _set_prs(monkeypatch, [_pr("closed", state="CLOSED")])
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "wor-123-new-title"


def test_open_pr_with_unavailable_head_stops_before_creation(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _batch_resolver(feature_repo, prs={"missing": ("resolved", "WOR-123")})
    _set_prs(monkeypatch, [_pr("missing")])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_title_only_tracker_conflict_blocks_selected_issue(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _batch_resolver(feature_repo, prs={"old-title": ("conflict", "WOR-123")})
    _set_prs(monkeypatch, [_pr("old-title")])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_unrelated_conflicting_head_does_not_poison_selected_issue(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _batch_resolver(feature_repo, prs={"unrelated": ("conflict", "WOR-999")})
    _set_prs(monkeypatch, [_pr("unrelated")])
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "wor-123-new-title"


def test_configured_empty_affected_keys_are_authoritative(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(
        feature_repo,
        monkeypatch,
        "WOR-123-fix-WOR-999",
        branches={"WOR-123-fix-WOR-999": ("unresolved", None)},
    )
    context = task_base.work_item(feature_repo, "WOR-123", "New title")
    assert context.branch_name == "wor-123-new-title"


def test_configured_observations_require_affected_issue_keys(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_trunk(feature_repo)
    _push_branch(feature_repo, "users/alice/old-title")
    _batch_resolver(
        feature_repo,
        branches={"users/alice/old-title": ("unresolved", None)},
        include_affected=False,
    )
    _set_prs(monkeypatch, [])
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123", "New title")
    assert _branch(feature_repo) == "003-feature"


def test_dirty_files_are_preserved_when_adopting_existing_work(feature_repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(feature_repo, monkeypatch, "users/alice/dirty", branches={"users/alice/dirty": ("resolved", "WOR-123")})
    dirty = feature_repo / "keep-me.txt"
    dirty.write_text("uncommitted\n", encoding="utf-8")
    task_base.work_item(feature_repo, "WOR-123")
    assert dirty.read_text(encoding="utf-8") == "uncommitted\n"


def test_branch_checked_out_in_another_worktree_is_rejected(feature_repo: Path, tmp_path: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(feature_repo, monkeypatch, "users/alice/elsewhere", branches={"users/alice/elsewhere": ("resolved", "WOR-123")})
    other = tmp_path / "other-worktree"
    subprocess.run(["git", "worktree", "add", "-q", str(other), "users/alice/elsewhere"], cwd=feature_repo, check=True, capture_output=True)
    with pytest.raises(SystemExit):
        task_base.work_item(feature_repo, "WOR-123")
    assert _branch(feature_repo) == "003-feature"
