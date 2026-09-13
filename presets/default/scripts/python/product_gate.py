#!/usr/bin/env python3
"""Validate the active feature's published product handoff."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import _fence_end, _fence_start, check_prerequisites, delivery_base, die, run_gh, run_git

FIELDS = (
    "url,state,isDraft,isCrossRepository,headRepository,headRepositoryOwner,"
    "headRefName,baseRefName,headRefOid"
)
_TASK = re.compile(r"^(\s*-\s+\[)[ xX](\]\s+T[0-9]{3}\b)")
_EVIDENCE = re.compile(r"^(\s*-\s+\*\*Completion evidence\*\*:)[ \t]*")
_FIELD = re.compile(r"^\s*-\s+\*\*[^*]+\*\*:")
_REQUIRED = {"spec.md", "plan.md", "tasks.md"}


def _pending(message: str) -> None:
    die(f"product close pending: {message}")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run_git(*args, cwd=repo)
    if result.returncode:
        _pending(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result


def _gh_json(repo: Path, *args: str) -> Any:
    result = run_gh(*args, cwd=repo)
    if result.returncode:
        detail = result.stderr.strip() or f"gh {' '.join(args)} failed"
        _pending(f"cannot observe published gate: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        _pending(f"cannot observe published gate: invalid JSON ({error})")


def _origin(repo: Path) -> str:
    result = run_git("remote", "get-url", "origin", cwd=repo)
    if result.returncode or not result.stdout.strip():
        _pending("origin is unavailable; configure the publication remote")
    return result.stdout.strip()


def _repository(repo: Path, origin: str) -> str:
    value = _gh_json(repo, "repo", "view", origin, "--json", "nameWithOwner")
    name = value.get("nameWithOwner") if isinstance(value, dict) else None
    if not isinstance(name, str) or not name:
        _pending("GitHub repository identity is empty")
    return name


def _repository_url(repo: Path, origin: str) -> str:
    value = _gh_json(repo, "repo", "view", origin, "--json", "url")
    url = value.get("url") if isinstance(value, dict) else None
    if not isinstance(url, str) or not url:
        _pending("GitHub repository URL is empty")
    return url


def _check_push_destinations(repo: Path, expected_url: str) -> None:
    result = run_git("remote", "get-url", "--push", "--all", "origin", cwd=repo)
    push_urls = [url for url in result.stdout.splitlines() if url]
    if result.returncode or not push_urls:
        _pending("cannot read origin push URLs; configure and verify every origin push destination, then rerun the product gate")
    for push_url in push_urls:
        if _repository_url(repo, push_url) != expected_url:
            _pending("origin push URL targets another repository")


def _feature_branch(repo: Path, feature: str, origin: str) -> str:
    current = _git(repo, "branch", "--show-current").stdout.strip()
    candidates = _gh_json(repo, "pr", "list", "--repo", origin, "--state", "open", "--limit", "1000", "--json", "headRefName")
    if not isinstance(candidates, list) or len(candidates) >= 1000:
        _pending("published feature refs could not be observed without truncation")
    names = sorted({p.get("headRefName", "") for p in candidates if isinstance(p, dict)
                    and p.get("headRefName", "").rsplit("/", 1)[-1] == feature})
    if current.rsplit("/", 1)[-1] == feature:
        if not names:
            return current
        if len(names) == 1:
            return names[0]
        _pending("ambiguous published feature refs: " + ", ".join(names))
    if len(names) == 1:
        return names[0]
    if len(names) > 1:
        _pending("ambiguous published feature refs: " + ", ".join(names))
    _pending(f"current branch does not identify feature {feature}; use the published feature branch")


def _pr(repo: Path, origin: str, branch: str) -> dict[str, Any]:
    result = run_gh("pr", "view", branch, "--repo", origin, "--json", FIELDS, cwd=repo)
    if result.returncode:
        detail = result.stderr.strip() or f"gh pr view {branch} failed"
        if "no pull requests found for branch" in detail:
            _pending("feature gate is missing; publish the approved product handoff with /speckit.pr")
        _pending(f"cannot observe published gate: {detail}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        _pending(f"cannot observe published gate: invalid JSON ({error})")
    if not isinstance(value, dict):
        _pending("published gate returned a non-object response")
    return value


def _feature_paths(repo: Path, feature_path: Path) -> tuple[Path, str]:
    repo_path = Path(os.path.abspath(repo))
    candidate = Path(os.path.abspath(feature_path))
    try:
        relative = candidate.relative_to(repo_path)
    except ValueError:
        _pending("the active feature directory is outside the repository")
    component = repo_path
    for part in relative.parts:
        component /= part
        if component.is_symlink():
            _pending("the active feature directory contains a symlinked path")
    try:
        if not candidate.resolve().is_relative_to(repo_path.resolve()):
            _pending("the active feature directory resolves outside the repository")
    except OSError as error:
        _pending(f"cannot resolve the active feature directory: {error}")
    return candidate, relative.as_posix()


def _check_identity(pr: dict[str, Any], expected_repo: str, expected_branch: str,
                    expected_base: str) -> None:
    if pr.get("state") != "OPEN":
        _pending(f"feature gate is {pr.get('state', 'unreadable')}; reopen or publish a new approved handoff")
    if pr.get("isCrossRepository") is not False:
        _pending("feature gate is a cross-repository pull request")
    head_repo = pr.get("headRepository")
    observed_repo = head_repo.get("nameWithOwner") if isinstance(head_repo, dict) else None
    if observed_repo != expected_repo:
        _pending("feature gate head repository does not match origin")
    if pr.get("headRefName") != expected_branch:
        _pending("feature gate head branch does not match the published feature ref")
    if pr.get("baseRefName") != expected_base:
        _pending(f"feature gate base is {pr.get('baseRefName')!r}; expected {expected_base!r}")
    if not isinstance(pr.get("headRefOid"), str) or not pr["headRefOid"]:
        _pending("feature gate has no advertised head OID")


def _remote_oid(repo: Path, origin: str, branch: str, expected: str) -> str:
    result = run_git("ls-remote", "--heads", origin, branch, cwd=repo)
    if result.returncode:
        _pending("cannot observe the published feature ref")
    rows = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) < 2:
        _pending("published feature ref is missing")
    oid = rows[0][0]
    if rows[0][1] != f"refs/heads/{branch}" or oid != expected:
        _pending("published feature ref OID differs from the feature gate; re-observe and reconcile the feature PR, rerun product analysis, and obtain fresh approval/publication before implementation")
    fetched = run_git("fetch", "--no-tags", origin, branch, cwd=repo)
    if fetched.returncode:
        _pending(fetched.stderr.strip() or "cannot fetch the published feature ref")
    fetched_oid = _git(repo, "rev-parse", "FETCH_HEAD").stdout.strip()
    if fetched_oid != oid:
        _pending("fetched feature ref OID differs from the observed remote OID; re-observe and reconcile the feature PR, rerun product analysis, and obtain fresh approval/publication before implementation")
    return oid


def _blob(repo: Path, oid: str) -> bytes:
    result = subprocess.run(["git", "cat-file", "blob", oid], cwd=repo, capture_output=True)
    if result.returncode:
        _pending(result.stderr.decode(errors="replace").strip() or "cannot read a product artifact blob")
    return result.stdout


def _tree(repo: Path, ref: str, feature: str) -> dict[str, tuple[str, str, bytes]]:
    result = _git(repo, "ls-tree", "-r", "-z", ref, "--", feature)
    entries: dict[str, tuple[str, str, bytes]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        header, path = record.split("\t", 1)
        mode, kind, oid = header.split()
        if kind != "blob":
            _pending(f"unsupported product artifact type at {path}")
        relative = path[len(feature) + 1:] if path.startswith(feature + "/") else path
        entries[relative] = (mode, kind, _blob(repo, oid))
    return entries


def _index(repo: Path, feature: str) -> dict[str, tuple[str, str, bytes]]:
    conflicts = _git(repo, "ls-files", "-u", "-z", "--", feature).stdout
    if conflicts:
        _pending("the product artifact index has conflicted entries")
    result = _git(repo, "ls-files", "--stage", "-z", "--", feature)
    entries: dict[str, tuple[str, str, bytes]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        header, path = record.split("\t", 1)
        mode, oid, stage = header.split()
        if stage != "0":
            _pending(f"the product artifact index has conflicted entries at {path}")
        relative = path[len(feature) + 1:] if path.startswith(feature + "/") else path
        entries[relative] = (mode, "blob", _blob(repo, oid))
    return entries


def _worktree(repo: Path, feature_path: Path) -> dict[str, tuple[str, str, bytes]]:
    if feature_path.is_symlink() or not feature_path.is_dir():
        _pending("the active feature directory is missing or replaced by a symlink")
    entries: dict[str, tuple[str, str, bytes]] = {}

    def visit(directory: Path, prefix: str = "") -> None:
        try:
            children = list(os.scandir(directory))
        except OSError as error:
            _pending(f"cannot inventory the feature worktree: {error}")
        for child in children:
            relative = f"{prefix}/{child.name}" if prefix else child.name
            path = Path(child.path)
            try:
                if child.is_symlink():
                    data = os.readlink(path).encode("utf-8", "surrogateescape")
                    entries[relative] = ("120000", "blob", data)
                elif child.is_dir(follow_symlinks=False):
                    visit(path, relative)
                elif child.is_file(follow_symlinks=False):
                    mode = "100755" if child.stat(follow_symlinks=False).st_mode & 0o111 else "100644"
                    entries[relative] = (mode, "blob", path.read_bytes())
                else:
                    _pending(f"unsupported product artifact at {relative}")
            except OSError as error:
                _pending(f"cannot read product artifact {relative}: {error}")

    visit(feature_path)
    return entries


def _normalise_tasks(data: bytes) -> bytes:
    text = data.decode("utf-8", "surrogateescape")
    output: list[str] = []
    fence: tuple[str, int] | None = None
    continuation_indent: int | None = None
    in_task = False
    for line in text.splitlines(keepends=True):
        raw = line.rstrip("\r\n")
        if fence is not None:
            output.append(line)
            if _fence_end(raw, *fence):
                fence = None
            continue
        started = _fence_start(raw)
        if started is not None:
            continuation_indent = None
            fence = started
            output.append(line)
            continue
        if continuation_indent is not None:
            indent = len(raw) - len(raw.lstrip(" "))
            if not raw.strip() or (indent > continuation_indent and not _TASK.match(raw) and not _FIELD.match(raw)):
                continue
            continuation_indent = None
        match = _TASK.match(raw)
        if match:
            in_task = True
            line = line[:match.start()] + match.group(1) + " " + line[match.start(2):]
        elif raw and not raw.startswith(" "):
            in_task = False
        evidence = _EVIDENCE.match(line.rstrip("\r\n")) if in_task else None
        if evidence:
            ending = line[len(line.rstrip("\r\n")):]
            line = evidence.group(1) + ending
            continuation_indent = len(raw) - len(raw.lstrip(" "))
        output.append(line)
    if fence is not None:
        _pending("tasks.md contains an unclosed fenced block")
    return "".join(output).encode("utf-8", "surrogateescape")


def _canonical(entries: dict[str, tuple[str, str, bytes]]) -> dict[str, tuple[str, str, bytes]]:
    return {path: (mode, kind, _normalise_tasks(data) if path == "tasks.md" else data)
            for path, (mode, kind, data) in entries.items()}


def _compare(remote: dict[str, tuple[str, str, bytes]], sources: list[tuple[str, dict[str, tuple[str, str, bytes]]]]) -> None:
    required = _REQUIRED
    remote_canonical = _canonical(remote)
    for name, entries in [("published tree", remote)] + sources:
        missing = sorted(required - entries.keys())
        if missing:
            _pending(f"{name} is missing required product artifacts: {', '.join(missing)}")
        symlinks = sorted(path for path in required & entries.keys() if entries[path][0] == "120000")
        if symlinks:
            _pending(f"{name} has symlinked required product artifacts: {', '.join(symlinks)}")
        canonical = _canonical(entries)
        if canonical != remote_canonical:
            if name == "HEAD":
                reason = "committed product changes are unpublished"
            elif name == "index":
                reason = "staged product changes are unpublished"
            else:
                reason = "working-tree product changes are unpublished"
            _pending(f"{reason}; rerun product analysis and obtain approval before publication")


def check(repo: Path | None = None) -> None:
    repo = repo or Path.cwd()
    paths = check_prerequisites(repo)
    feature_path = Path(paths["FEATURE_DIR"])
    if not feature_path.is_absolute():
        feature_path = repo / feature_path
    feature_path, feature_rel = _feature_paths(repo, feature_path)
    feature = feature_rel.rsplit("/", 1)[-1]
    origin = _origin(repo)
    expected_repo = _repository(repo, origin)
    expected_url = _repository_url(repo, origin)
    _check_push_destinations(repo, expected_url)
    branch = _feature_branch(repo, feature, origin)
    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        _pending(f"checked-out branch {current or '<detached>'!r} does not match published feature ref {branch!r}")
    try:
        expected_base = delivery_base(repo, origin)
    except SystemExit:
        _pending("cannot observe the delivery base")
    first = _pr(repo, origin, branch)
    _check_identity(first, expected_repo, branch, expected_base)
    remote_oid = _remote_oid(repo, origin, branch, first["headRefOid"])
    remote = _tree(repo, remote_oid, feature_rel)
    head = _tree(repo, "HEAD", feature_rel)
    index = _index(repo, feature_rel)
    worktree = _worktree(repo, feature_path)
    _compare(remote, [("HEAD", head), ("index", index), ("worktree", worktree)])
    final = _pr(repo, origin, branch)
    if any(final.get(field) != first.get(field) for field in FIELDS.split(",")):
        _pending("feature gate changed while its published artifacts were being checked; re-observe and reconcile the feature PR, rerun product analysis, and obtain fresh approval/publication before implementation")
    if final.get("headRefOid") != remote_oid:
        _pending("feature gate head changed after the published ref was checked; re-observe and reconcile the feature PR, rerun product analysis, and obtain fresh approval/publication before implementation")
    print(f"product gate: {final.get('url', branch)} head={remote_oid}")


def main(argv: list[str]) -> int:
    if argv:
        die("usage: product_gate.py")
    check()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
