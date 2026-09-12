#!/usr/bin/env python3
"""Report repository settings and effective active rules for delivery branches."""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from _common import delivery_base, run_gh
from github_delivery_rules import (
    CAPABILITY_UNAVAILABLE,
    COMPATIBLE,
    INCOMPATIBLE,
    UNVERIFIED,
    Result,
    RuleRead,
    evaluate_force_push,
    parse_active_rules,
    parse_branch_page_items,
    parse_page_collection,
    shared_branches,
    unknown_branch_result,
)

_SETTINGS = (
    ("deleteBranchOnMerge", "Automatically delete head branches"),
    ("mergeCommitAllowed", "Allow merge commits"),
)


def _safe_detail(value: str) -> str:
    """Keep a bounded, single-line diagnostic without authentication material."""
    detail = re.sub(r"\s+", " ", value).strip()
    detail = re.sub(r"(?i)(authorization|token|password|secret)[=: ]+(?:bearer\s+)?\S+", r"\1=<redacted>", detail)
    detail = re.sub(r"(?:gh[pousr]_\w+|github_pat_[A-Za-z0-9_\-]+)", "<redacted>", detail)
    return detail[:160] or "no diagnostic detail"


def _unknown(cause: str, evidence: str, action: str) -> Result:
    return Result(UNVERIFIED, cause, evidence, action)


def _read_settings(repo_root: Path) -> dict[str, Result]:
    """Read both settings with one GET-only ``gh repo view`` invocation."""
    if shutil.which("gh") is None:
        result = Result(
            CAPABILITY_UNAVAILABLE,
            "github-cli-unavailable",
            "gh was not found on PATH",
            "Install GitHub CLI and authenticate it, then rerun the doctor",
        )
        return {name: result for name, _ in _SETTINGS}

    try:
        completed = run_gh(
            "repo", "view", "--json", "deleteBranchOnMerge,mergeCommitAllowed", cwd=repo_root
        )
    except OSError as error:
        result = _unknown("read-failure", _safe_detail(str(error)), "Retry after confirming gh is available")
        return {name: result for name, _ in _SETTINGS}
    if completed.returncode != 0:
        detail = _safe_detail(completed.stderr)
        result = _unknown(
            "read-failure",
            f"gh repo view failed: {detail}",
            "Retry after checking the repository remote and gh authentication",
        )
        return {name: result for name, _ in _SETTINGS}

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = _unknown("malformed-response", "gh repo view returned invalid JSON", "Retry the read")
        return {name: result for name, _ in _SETTINGS}
    if not isinstance(payload, dict):
        result = _unknown("malformed-response", "gh repo view returned a non-object response", "Retry the read")
        return {name: result for name, _ in _SETTINGS}

    findings: dict[str, Result] = {}
    for name, setting in _SETTINGS:
        value = payload.get(name)
        if type(value) is not bool:
            cause = "missing-field" if name not in payload else "malformed-response"
            evidence = f"{setting} was absent from the response" if cause == "missing-field" else f"{setting} was not a boolean"
            findings[name] = _unknown(cause, evidence, "Retry the read and inspect the repository settings in GitHub")
        elif value:
            findings[name] = Result(COMPATIBLE, "", "observed true", "")
        else:
            findings[name] = Result(
                INCOMPATIBLE,
                "conflicting-configuration",
                "observed false",
                f"In GitHub, enable Settings → General → Pull Requests → {setting}",
            )
    return findings


@dataclass(frozen=True)
class _RemoteRead:
    complete: bool
    payload: object = None
    cause: str = ""
    evidence: str = ""


def _api_read(repo_root: Path, endpoint: str) -> _RemoteRead:
    """Read a paginated REST collection through an explicit GET only."""
    try:
        result = run_gh("api", "--method", "GET", "--paginate", "--slurp", endpoint, cwd=repo_root)
    except OSError as error:
        return _RemoteRead(False, cause="read-failure", evidence=_safe_detail(str(error)))
    if result.returncode != 0:
        detail = _safe_detail(result.stderr or result.stdout)
        cause = "branch-disappeared" if re.search(r"branch\s+(?:was\s+)?not found|branch disappeared", detail, re.I) else "read-failure"
        return _RemoteRead(False, cause=cause, evidence=detail or "GitHub returned an unsuccessful response")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _RemoteRead(False, cause="malformed-response", evidence="GitHub returned invalid JSON")
    if parse_page_collection(payload) is None:
        return _RemoteRead(False, cause="malformed-response", evidence="GitHub returned an invalid page collection")
    return _RemoteRead(True, payload=payload)


def _read_inventory(repo_root: Path) -> _RemoteRead:
    if shutil.which("gh") is None:
        return _RemoteRead(False, cause="github-cli-unavailable", evidence="gh was not found on PATH")
    read = _api_read(repo_root, "repos/{owner}/{repo}/branches?per_page=100")
    if not read.complete and read.cause in {"read-failure", "branch-disappeared"}:
        return _RemoteRead(False, cause="partial-inventory", evidence=read.evidence)
    return read


def _read_branch_rules(repo_root: Path, branch: str) -> RuleRead:
    endpoint = "repos/{owner}/{repo}/rules/branches/" + quote(branch, safe="") + "?per_page=100"
    read = _api_read(repo_root, endpoint)
    if not read.complete:
        if read.cause == "read-failure" and "page" in read.evidence.lower():
            return RuleRead(False, cause="partial-rules", evidence=read.evidence)
        return RuleRead(False, cause=read.cause, evidence=read.evidence)
    rules = parse_active_rules(read.payload)
    if rules is None:
        return RuleRead(False, cause="malformed-response", evidence="effective branch rules had invalid fields")
    return RuleRead(True, rules=rules)


def _partial_branch_finding(name: str, read: _RemoteRead) -> Result:
    cause = read.cause or "partial-inventory"
    evidence = read.evidence or "remote branch inventory was not completely observed"
    return Result(
        UNVERIFIED,
        cause,
        f"{name}: {evidence}",
        "Retry the GitHub branch inventory after confirming access to repository metadata",
    )


def _branch_findings(repo_root: Path) -> tuple[tuple[str, Result], ...]:
    """Observe the complete remote inventory, then effective rules per shared branch."""
    try:
        trunk = delivery_base(repo_root).strip()
    except (SystemExit, OSError):
        trunk = ""
    if not trunk:
        finding = unknown_branch_result("trunk-unresolved")
        return (("force-push protection", finding), ("merge commits", finding), ("cleanup", finding))

    inventory = _read_inventory(repo_root)
    if not inventory.complete:
        finding = _partial_branch_finding(trunk, inventory)
        return ((f"force-push protection [{trunk} (trunk)]", finding),
                (f"merge commits [{trunk} (trunk)]", unknown_branch_result(inventory.cause or "partial-inventory")),
                (f"cleanup [{trunk} (trunk)]", unknown_branch_result(inventory.cause or "partial-inventory")))

    pages = parse_page_collection(inventory.payload)
    names = parse_branch_page_items(pages or ())
    if names is None:
        finding = unknown_branch_result("malformed-response")
        return ((f"force-push protection [{trunk} (trunk)]", finding),
                (f"merge commits [{trunk} (trunk)]", finding), (f"cleanup [{trunk} (trunk)]", finding))

    branches = shared_branches(names, trunk)
    results: list[tuple[str, Result]] = []
    for name, role in branches:
        if name not in names:
            rules = RuleRead(False, cause="branch-missing", evidence="the delivery base was absent from the remote inventory")
        else:
            rules = _read_branch_rules(repo_root, name)
        force = evaluate_force_push(name, rules)
        label = f"force-push protection [{name} ({role})]"
        results.append((label, force))
        results.append((f"merge commits [{name} ({role})]", unknown_branch_result("merge-evaluation-pending")))
        results.append((f"cleanup [{name} ({role})]", unknown_branch_result("cleanup-evaluation-pending")))
    return tuple(results)


def diagnose(repo_root: Path) -> tuple[dict[str, Result], tuple[tuple[str, Result], ...]]:
    settings = _read_settings(repo_root)
    return settings, _branch_findings(repo_root)


def render(settings: dict[str, Result], branch: tuple[tuple[str, Result], ...]) -> str:
    scope = "repository settings and observed shared-branch inventory; each result states its evidence and coverage."
    lines = ["GitHub delivery diagnosis", f"Scope: {scope}"]
    for name, setting in _SETTINGS:
        finding = settings[name]
        suffix = f"; cause={finding.cause}" if finding.cause else ""
        line = f"{name}: {finding.state} ({finding.evidence}{suffix})"
        if finding.next_action:
            line += f" — next: {finding.next_action}"
        lines.append(line)
    for name, finding in branch:
        suffix = f"; cause={finding.cause}" if finding.cause else ""
        lines.append(f"{name}: {finding.state} ({finding.evidence}{suffix}) — next: {finding.next_action}")
    lines.append("Overall: unverified (classic protection, merge, cleanup, or complete rule coverage remains unverified).")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv:
        print("usage: github_delivery.py", file=sys.stderr)
        return 2
    settings, branch = diagnose(Path.cwd())
    print(render(settings, branch))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
