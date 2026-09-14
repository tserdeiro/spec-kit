#!/usr/bin/env python3
"""pr-create: resolve and print the PR base for a delivery kind.

Prints ``base=<name>`` only and never runs ``gh pr create`` itself -- the
command composes the title and body and runs that call with the base
this script printed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from _common import check_prerequisites, delivery_base, die, first_unchecked, open_task_prs, parse_ledger, run_git
from work_item_start import _configured, _same_issue, pull_requests

def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run_git(*args, cwd=repo_root)
    if result.returncode != 0:
        die(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result

def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return run_git("merge-base", "--is-ancestor", ancestor, descendant, cwd=repo_root).returncode == 0

def _validate_work_item_identity(repo_root: Path) -> None:
    """Require the installed resolver to confirm the complete native PR identity."""

    branch = _git(repo_root, "branch", "--show-current").stdout.strip()
    if not branch:
        die("work-item PR routing requires a checked-out branch")
    script = repo_root / ".specify" / "extensions" / "linear" / "scripts" / "python" / "resolve_work_item.py"
    if not script.is_file():
        return
    configured = _configured(repo_root)
    matching_prs = tuple(item for item in pull_requests(repo_root) if item.head_branch == branch) if configured else ()
    request: dict[str, object] = {"branch_names": [branch]}
    if configured:
        request["pull_requests"] = [
            {"head_branch": item.head_branch, "body": item.body}
            for item in matching_prs
        ]
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(repo_root)],
        cwd=repo_root,
        input=json.dumps(request),
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("configured Linear work-item resolver returned invalid JSON")
    if result.returncode != 0 or not isinstance(payload, dict) or payload.get("status") == "error":
        message = payload.get("message") if isinstance(payload, dict) else None
        die(f"configured Linear work-item resolution failed: {message or 'resolver failed'}")
    if payload.get("status") == "absent":
        return
    observations = payload.get("observations")
    if not isinstance(observations, list) or len(observations) != len(matching_prs) + 1:
        die(f"configured Linear work-item resolver returned incomplete identity for {branch}")
    if not all(isinstance(item, dict) for item in observations):
        die(f"configured Linear work-item resolver returned malformed identity for {branch}")

    branch_observation = observations[0]
    pr_observations = observations[1:]
    branch_status = branch_observation.get("status")
    if branch_status not in {"resolved", "unresolved"}:
        die(f"configured Linear work-item identity is {branch_status or 'unknown'}; PR routing stopped for {branch}")
    resolved = [
        item for item in observations
        if item.get("status") == "resolved"
        and isinstance(item.get("resolution"), dict)
        and isinstance(item["resolution"].get("identifier"), str)
    ]
    if not resolved:
        status = branch_observation.get("status", payload.get("status", "unknown"))
        die(f"configured Linear work-item identity is {status}; PR routing stopped for {branch}")
    if any(item.get("status") != "resolved" for item in pr_observations):
        status = next(item.get("status", "unknown") for item in pr_observations if item.get("status") != "resolved")
        die(f"configured Linear work-item PR identity is {status}; PR routing stopped for {branch}")
    if branch_status != "resolved" and not pr_observations:
        status = branch_status
        die(f"configured Linear work-item identity is {status}; PR routing stopped for {branch}")
    identifiers = [item["resolution"]["identifier"] for item in resolved]
    if any(not _same_issue(identifier, identifiers[0]) for identifier in identifiers[1:]):
        die(f"configured Linear work-item identity is conflicting; PR routing stopped for {branch}")

def feature_or_work_item(repo_root: Path) -> str:
    base = delivery_base(repo_root)
    _git(repo_root, "check-ref-format", "--branch", base)
    return base

def task(repo_root: Path, named_task: str) -> str:
    paths = check_prerequisites(repo_root)
    feature_branch = paths["BRANCH"]
    feature_number = feature_branch.rsplit("/", 1)[-1].split("-", 1)[0]
    current = _git(repo_root, "branch", "--show-current").stdout.strip()
    match = re.match(r"^[0-9]+-(T[0-9]{3})-", current.rsplit("/", 1)[-1])
    branch_task = match.group(1) if match else ""
    tasks_file = Path(paths["FEATURE_DIR"]) / "tasks.md"
    full_path = repo_root / tasks_file
    if not full_path.is_file():
        die(f"task ledger not found: {tasks_file}")
    unchecked = first_unchecked(parse_ledger(full_path.read_text(encoding="utf-8")))
    expected_task = named_task or (unchecked.id if unchecked else "")
    if not expected_task:
        die(f"no unchecked task found in {tasks_file}")
    if branch_task != expected_task:
        die(f"branch {current} delivers {branch_task} but the task to deliver is {expected_task}")
    _git(repo_root, "fetch", "origin")
    prs = open_task_prs(repo_root, feature_number, "headRefName,baseRefName,isDraft")
    heads = [pr["headRefName"] for pr in prs if not pr["isDraft"]]
    base = feature_branch
    for head in heads:
        if not _is_ancestor(repo_root, f"origin/{head}", "HEAD"):
            continue
        if base == feature_branch or _is_ancestor(repo_root, f"origin/{base}", f"origin/{head}"):
            base = head
    return base

def main(argv: list[str]) -> int:
    if not argv:
        die("usage: pr_create.py <feature|task|work-item> [named-task]")
    kind, rest = argv[0], argv[1:]
    repo_root = Path.cwd()
    if kind in ("feature", "work-item"):
        if kind == "work-item":
            _validate_work_item_identity(repo_root)
        base = feature_or_work_item(repo_root)
    elif kind == "task":
        base = task(repo_root, rest[0] if rest else "")
    else:
        die(f"unknown delivery kind: {kind}")
    print(f"base={base}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
