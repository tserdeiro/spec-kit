"""Product-gate normalization, identity, and real Git observation tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import product_gate


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)


def test_added_task_is_not_a_completion_continuation() -> None:
    base = b"- [ ] T001 Work\n  - **Completion evidence**: Pending\n"
    for added in (base + b"    - [ ] T002 Added scope\n",
                  base + b"    - **Delivery**: single PR (~999 lines)\n",
                  base + b"    - **Unreviewed field**: changes task intent\n"):
        assert product_gate._normalise_tasks(base) != product_gate._normalise_tasks(added)


def test_unclosed_tasks_fence_fails_closed() -> None:
    with pytest.raises(SystemExit) as error:
        product_gate._normalise_tasks(b"- [ ] T001 Work\n```md\n- [ ] T002 Sample\n")
    assert error.value.code == 2


def test_missing_pr_names_the_product_close_action(monkeypatch: pytest.MonkeyPatch,
                                                   tmp_path: Path,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(product_gate, "run_gh", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 1, "", "no pull requests found for branch \"003-feature\""))
    with pytest.raises(SystemExit) as error:
        product_gate._pr(tmp_path, "origin", "003-feature")
    assert error.value.code == 2
    assert "publish the approved product handoff" in capsys.readouterr().err


@pytest.mark.parametrize("refs,current,expected", [
    (["jdoe/web/008-guided-tour"], "jdoe/web/008-guided-tour", "jdoe/web/008-guided-tour"),
    (["jdoe/web/008-guided-tour"], "008-guided-tour", "jdoe/web/008-guided-tour"),
    (["jdoe/web/008-guided-tour", "other/008-guided-tour"], "008-guided-tour", None),
])
def test_namespaced_feature_ref_is_unique_or_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                      refs: list[str], current: str, expected: str | None) -> None:
    monkeypatch.setattr(product_gate, "_git", lambda repo, *args: subprocess.CompletedProcess(
        ["git", *args], 0, current + "\n", ""))
    monkeypatch.setattr(product_gate, "_gh_json", lambda *args: [{"headRefName": ref} for ref in refs])
    if expected:
        assert product_gate._feature_branch(tmp_path, "008-guided-tour", "origin") == expected
    else:
        with pytest.raises(SystemExit):
            product_gate._feature_branch(tmp_path, "008-guided-tour", "origin")


@pytest.fixture
def published(feature_repo: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, object]]:
    feature = feature_repo / "specs/003-feature"
    feature.mkdir(parents=True)
    for name, text in {"spec.md": "spec\n", "plan.md": "plan\n",
                       "tasks.md": "- [ ] T001 Work\n  - **Completion evidence**: Pending\n"}.items():
        (feature / name).write_text(text, encoding="utf-8")
    _git(feature_repo, "add", "specs/003-feature")
    _git(feature_repo, "commit", "-q", "-m", "docs: publish feature")
    _git(feature_repo, "push", "-q", "origin", "003-feature")
    oid = _git(feature_repo, "rev-parse", "HEAD").stdout.strip()
    origin = _git(feature_repo, "remote", "get-url", "origin").stdout.strip()
    state: dict[str, object] = {"oid": oid, "state": "OPEN", "base": "main", "refs": True, "missing": False,
                                "repositories": {origin: ("org/repo", "https://github.com/org/repo")}, "gh_writes": []}
    monkeypatch.setattr(product_gate, "delivery_base", lambda *_: "main")
    runs: list[list[str]] = []
    original_run = product_gate.subprocess.run
    def record_run(command, *args, **kwargs):
        runs.append(command)
        return original_run(command, *args, **kwargs)
    monkeypatch.setattr(product_gate.subprocess, "run", record_run)
    state["runs"] = runs

    def gh(*args):
        read_only = (args[:2] == ("repo", "view") and args[-2:] in (("--json", "nameWithOwner"), ("--json", "url")) or
                     args == ("pr", "list", "--repo", origin, "--state", "open", "--limit", "1000",
                              "--json", "headRefName") or
                     args == ("pr", "view", "003-feature", "--repo", origin, "--json", product_gate.FIELDS))
        if not read_only:
            state["gh_writes"].append(args)
            product_gate._pending(f"unexpected GitHub mutation: {' '.join(args)}")
        if args[0:2] == ("repo", "view"):
            name, url = state["repositories"].get(args[2], ("org/repo", "https://github.com/org/repo"))
            return {"nameWithOwner": name, "url": url}
        if args[0:2] == ("pr", "list"):
            return [{"headRefName": "003-feature"}] if state["refs"] else []
        if state["missing"]:
            product_gate._pending("no published feature gate")
        return {"url": "https://example.invalid/pr/1", "state": state["state"], "isDraft": True,
                "isCrossRepository": False, "headRepository": {"nameWithOwner": "org/repo"},
                "headRepositoryOwner": {"login": "org"}, "headRefName": "003-feature",
                "baseRefName": state["base"], "headRefOid": state["oid"]}
    monkeypatch.setattr(product_gate, "_gh_json", lambda _repo, *args: gh(*args))
    original_gh = product_gate.run_gh
    def run_gh(*args, **kwargs):
        if args[0:2] == ("pr", "view"):
            return subprocess.CompletedProcess(args, 0, json.dumps(gh(*args)), "")
        return original_gh(*args, **kwargs)
    monkeypatch.setattr(product_gate, "run_gh", run_gh)
    return feature_repo, state


def _snapshot(repo: Path) -> tuple[str, ...]:
    return (_git(repo, "branch", "--show-current").stdout,
            _git(repo, "rev-parse", "HEAD").stdout,
            _git(repo, "diff", "--cached", "--binary").stdout,
            _git(repo, "diff", "--binary").stdout,
            _git(repo, "ls-remote", "--heads", "origin", "003-feature").stdout)


def _write_calls(commands: list[list[str]]) -> list[list[str]]:
    git_writes = {"add", "commit", "checkout", "merge", "push", "reset", "switch", "update-index", "update-ref"}
    linear_writes = {"push", "--apply"}
    writes = [command for command in commands if command[0] == "gh" or
            (command[0] == "bash" and "extensions/linear" in " ".join(command) and
             any(part in linear_writes for part in command)) or
            (command[0] == "git" and len(command) > 1 and command[1] in git_writes)]
    return writes + [command for command in commands if command[:2] == ["git", "branch"] and
                     "--show-current" not in command[2:]]


def test_write_spy_preserves_branch_query_and_catches_branch_and_ref_creation() -> None:
    commands = [["git", "branch", "--show-current"], ["git", "branch", "010-T004"],
                ["git", "update-ref", "refs/heads/010-T004", "deadbeef"]]
    assert {tuple(command) for command in _write_calls(commands)} == {tuple(command) for command in commands[1:]}


def _reject(repo: Path, state: dict[str, object]) -> None:
    before = _snapshot(repo)
    runs = state["runs"]
    start = len(runs)
    with pytest.raises(SystemExit) as error:
        product_gate.check(repo)
    assert error.value.code == 2 and _snapshot(repo) == before and not _write_calls(runs[start:])
    assert not state["gh_writes"]


def test_check_validates_real_published_tree(published: tuple[Path, dict[str, object]],
                                             capsys: pytest.CaptureFixture[str]) -> None:
    repo, state = published
    start = len(state["runs"])
    product_gate.check(repo)
    (repo / "specs/003-feature/tasks.md").write_text(
        "- [x] T001 Work\n  - **Completion evidence**: done\n", encoding="utf-8")
    product_gate.check(repo)
    assert not _write_calls(state["runs"][start:])
    assert not state["gh_writes"]
    assert "product gate:" in capsys.readouterr().out


@pytest.mark.parametrize("status", ["CLOSED", "MERGED"])
def test_closed_or_merged_gate_stops(published: tuple[Path, dict[str, object]], status: str) -> None:
    repo, state = published
    state["state"] = status
    _reject(repo, state)


@pytest.mark.parametrize("key,value", [("missing", True), ("base", "other")])
def test_missing_or_mismatched_gate_stops(published: tuple[Path, dict[str, object]], key: str,
                                          value: object) -> None:
    repo, state = published
    state[key] = value
    _reject(repo, state)


def test_fetch_failure_stops_before_artifact_reads(published: tuple[Path, dict[str, object]],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _state = published
    original = product_gate.run_git
    def fail_fetch(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "fetch failed", "") if args and args[0] == "fetch" else original(*args, **kwargs)
    monkeypatch.setattr(product_gate, "run_git", fail_fetch)
    _reject(repo, published[1])


def test_mismatched_origin_push_destination_stops(published: tuple[Path, dict[str, object]]) -> None:
    repo, state = published
    external = repo.parent / "external-push.git"
    _git(repo, "init", "--bare", "-q", str(external))
    origin = _git(repo, "remote", "get-url", "origin").stdout.strip()
    _git(repo, "remote", "set-url", "--add", "--push", "origin", origin)
    _git(repo, "remote", "set-url", "--add", "--push", "origin", str(external))
    state["repositories"][str(external)] = ("org/repo", "https://ghe.example/org/repo")
    _reject(repo, state)


def test_unreadable_push_destinations_name_recovery(monkeypatch: pytest.MonkeyPatch,
                                                     tmp_path: Path,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(product_gate, "run_git", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 1, "", "push URLs unavailable"))
    with pytest.raises(SystemExit) as error:
        product_gate._check_push_destinations(tmp_path, "https://github.com/org/repo")
    assert error.value.code == 2
    assert "configure and verify every origin push destination" in capsys.readouterr().err


@pytest.mark.parametrize("scope", ["published", "HEAD", "index", "worktree"])
def test_required_product_artifact_symlink_stops(published: tuple[Path, dict[str, object]],
                                                 scope: str) -> None:
    repo, state = published
    path = repo / "specs/003-feature/spec.md"
    path.unlink()
    os.symlink("plan.md", path)
    if scope != "worktree":
        _git(repo, "add", str(path))
    if scope in ("HEAD", "published"):
        _git(repo, "commit", "-q", "-m", "docs: replace required artifact")
    if scope == "published":
        _git(repo, "push", "-q", "origin", "003-feature")
        state["oid"] = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _reject(repo, state)


def test_stale_remote_oid_names_recovery(published: tuple[Path, dict[str, object]],
                                         capsys: pytest.CaptureFixture[str]) -> None:
    repo, state = published
    state["oid"] = "0" * 40
    _reject(repo, state)
    assert "re-observe and reconcile the feature PR" in capsys.readouterr().err


def test_stale_fetch_oid_names_recovery(published: tuple[Path, dict[str, object]],
                                        monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    repo, state = published
    original = product_gate.run_git
    def stale_fetch(*args, **kwargs):
        if args == ("rev-parse", "FETCH_HEAD"):
            return subprocess.CompletedProcess(args, 0, "0" * 40 + "\n", "")
        return original(*args, **kwargs)
    monkeypatch.setattr(product_gate, "run_git", stale_fetch)
    _reject(repo, state)
    assert "re-observe and reconcile the feature PR" in capsys.readouterr().err


@pytest.mark.parametrize("scope", ["worktree", "index", "HEAD"])
def test_unpublished_scope_drift_stops_and_keeps_state(published: tuple[Path, dict[str, object]], scope: str) -> None:
    repo, _state = published
    path = repo / "specs/003-feature/spec.md"
    path.write_text("changed\n", encoding="utf-8")
    if scope in ("index", "HEAD"):
        _git(repo, "add", str(path))
    if scope == "HEAD":
        _git(repo, "commit", "-q", "-m", "docs: drift")
    _reject(repo, published[1])


def test_symlinked_feature_parent_stops(published: tuple[Path, dict[str, object]]) -> None:
    repo, state = published
    external = repo.parent / "external-specs"
    (repo / "specs").rename(external)
    os.symlink(external, repo / "specs", target_is_directory=True)
    _reject(repo, state)


@pytest.mark.parametrize("command", [("switch", "-c", "unrelated"), ("switch", "--detach")])
def test_gate_requires_the_published_feature_checkout(published: tuple[Path, dict[str, object]],
                                                      command: tuple[str, ...]) -> None:
    repo, state = published
    _git(repo, *command)
    _reject(repo, state)
