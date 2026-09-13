#!/usr/bin/env python3
"""Report repository settings and effective active rules for delivery branches."""

from __future__ import annotations

import json
import re
import shutil
import sys
from contextlib import redirect_stderr
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.parse import quote

from _common import delivery_base, run_gh
from github_delivery_rules import (
    CAPABILITY_UNAVAILABLE,
    COMPATIBLE,
    INCOMPATIBLE,
    UNVERIFIED,
    ClassicProtection,
    Result,
    RuleRead,
    RulesetDetail,
    evaluate_force_push,
    parse_active_rules,
    parse_branch_page_items,
    parse_classic_protection,
    parse_page_collection,
    parse_ruleset_detail,
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


def _remote_error(result: object) -> str:
    """Keep only bounded stderr and a JSON error message, never an error payload."""
    parts = [_safe_detail(getattr(result, "stderr", ""))]
    try:
        payload = json.loads(getattr(result, "stdout", ""))
    except (json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        parts.append(_safe_detail(payload["message"]))
    return "; ".join(part for part in parts if part and part != "no diagnostic detail") or "GitHub returned an unsuccessful response"


def _is_branch_not_protected(result: object) -> bool:
    """Recognize GitHub's documented absence response without trusting arbitrary 404s."""
    candidates = [getattr(result, "stderr", "")]
    try:
        payload = json.loads(getattr(result, "stdout", ""))
    except (json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        candidates.append(payload["message"])
    for candidate in candidates:
        value = re.sub(r"^gh:\s*", "", candidate.strip(), flags=re.I)
        if re.fullmatch(r"(?:HTTP 404:\s*)?Branch not protected(?:\s*\(HTTP 404\))?", value, re.I):
            return True
    return False


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
    documented_absence: bool = False


def _api_read(repo_root: Path, endpoint: str) -> _RemoteRead:
    """Read a paginated REST collection through an explicit GET only."""
    try:
        result = run_gh("api", "--method", "GET", "--paginate", "--slurp", endpoint, cwd=repo_root)
    except OSError as error:
        return _RemoteRead(False, cause="read-failure", evidence=_safe_detail(str(error)))
    if result.returncode != 0:
        detail = _remote_error(result)
        cause = "branch-disappeared" if re.search(r"branch\s+(?:was\s+)?not found|branch disappeared", detail, re.I) else "read-failure"
        return _RemoteRead(False, cause=cause, evidence=detail or "GitHub returned an unsuccessful response")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _RemoteRead(False, cause="malformed-response", evidence="GitHub returned invalid JSON")
    if parse_page_collection(payload) is None:
        return _RemoteRead(False, cause="malformed-response", evidence="GitHub returned an invalid page collection")
    return _RemoteRead(True, payload=payload)


def _api_object_read(repo_root: Path, endpoint: str) -> _RemoteRead:
    """Read one REST object with an explicit GET, without pagination wrapping."""
    try:
        result = run_gh("api", "--method", "GET", endpoint, cwd=repo_root)
    except OSError as error:
        return _RemoteRead(False, cause="read-failure", evidence=_safe_detail(str(error)))
    if result.returncode != 0:
        detail = _remote_error(result)
        return _RemoteRead(False, cause="read-failure", evidence=detail, documented_absence=_is_branch_not_protected(result))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _RemoteRead(False, cause="malformed-response", evidence="GitHub returned invalid JSON")
    if not isinstance(payload, dict):
        return _RemoteRead(False, cause="malformed-response", evidence="GitHub returned a non-object response")
    return _RemoteRead(True, payload=payload)


def _read_inventory(repo_root: Path) -> _RemoteRead:
    if shutil.which("gh") is None:
        return _RemoteRead(False, cause="github-cli-unavailable", evidence="gh was not found on PATH")
    read = _api_read(repo_root, "repos/{owner}/{repo}/branches?per_page=100")
    if not read.complete and read.cause in {"read-failure", "branch-disappeared"}:
        return _RemoteRead(False, cause="partial-inventory", evidence=read.evidence)
    return read


def _read_classic_protection(repo_root: Path, branch: str) -> ClassicProtection:
    endpoint = "repos/{owner}/{repo}/branches/" + quote(branch, safe="") + "/protection"
    read = _api_object_read(repo_root, endpoint)
    if not read.complete:
        if read.documented_absence:
            return ClassicProtection(True, False, evidence="GitHub reported Branch not protected")
        return ClassicProtection(False, None, cause=read.cause, evidence=read.evidence)
    parsed = parse_classic_protection(read.payload)
    if parsed is None:
        return ClassicProtection(False, None, cause="malformed-response", evidence="classic protection had invalid fields")
    return parsed


def _read_ruleset_detail(
    repo_root: Path,
    rule: object,
    cache: dict[tuple[str, str, int], tuple[RulesetDetail | None, str, str]],
) -> tuple[RulesetDetail | None, str, str]:
    identity = rule.identity
    if identity in cache:
        return cache[identity]
    endpoint = "repos/{owner}/{repo}/rulesets/" + str(rule.ruleset_id) + "?includes_parents=true"
    read = _api_object_read(repo_root, endpoint)
    if not read.complete:
        value = (None, read.cause, read.evidence)
    else:
        detail = parse_ruleset_detail(read.payload)
        if detail is None:
            value = (None, "malformed-response", "ruleset detail had invalid fields")
        elif detail.identity != identity:
            value = (None, "malformed-response", "ruleset detail identity did not match active rules")
        else:
            value = (detail, "", "")
    cache[identity] = value
    return value


def _read_branch_rules(
    repo_root: Path,
    branch: str,
    detail_cache: dict[tuple[str, str, int], tuple[RulesetDetail | None, str, str]] | None = None,
) -> RuleRead:
    endpoint = "repos/{owner}/{repo}/rules/branches/" + quote(branch, safe="") + "?per_page=100"
    read = _api_read(repo_root, endpoint)
    classic = _read_classic_protection(repo_root, branch)
    if not read.complete:
        if read.cause == "read-failure" and "page" in read.evidence.lower():
            return RuleRead(False, cause="partial-rules", evidence=read.evidence, classic=classic)
        return RuleRead(False, cause=read.cause, evidence=read.evidence, classic=classic)
    rules = parse_active_rules(read.payload)
    if rules is None:
        return RuleRead(False, cause="malformed-response", evidence="effective branch rules had invalid fields", classic=classic)
    cache = detail_cache if detail_cache is not None else {}
    details: list[RulesetDetail] = []
    detail_errors: list[tuple[str, str]] = []
    for rule in rules:
        detail, cause, evidence = _read_ruleset_detail(repo_root, rule, cache)
        if detail is not None:
            details.append(detail)
        else:
            detail_errors.append((cause, evidence))
    first_error = detail_errors[0] if detail_errors else ("", "")
    return RuleRead(
        True,
        rules=rules,
        classic=classic,
        details=tuple(details),
        details_complete=not detail_errors,
        details_cause=first_error[0],
        details_evidence=first_error[1],
    )


def _branch_findings(repo_root: Path) -> tuple[tuple[str, Result], ...]:
    """Observe the complete remote inventory, then effective rules per shared branch."""
    try:
        with redirect_stderr(StringIO()):
            trunk = delivery_base(repo_root).strip()
    except (SystemExit, OSError):
        trunk = ""
    if not trunk:
        finding = unknown_branch_result("trunk-unresolved")
        return (("force-push protection", finding), ("merge commits", finding), ("cleanup", finding))

    inventory = _read_inventory(repo_root)
    if not inventory.complete:
        finding = _unknown(
            inventory.cause or "partial-inventory",
            f"{trunk}: {inventory.evidence or 'remote branch inventory was not completely observed'}",
            "Retry the GitHub branch inventory after confirming access to repository metadata",
        )
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
    detail_cache: dict[tuple[str, str, int], tuple[RulesetDetail | None, str, str]] = {}
    for name, role in branches:
        if name not in names:
            rules = RuleRead(False, cause="branch-missing", evidence="the delivery base was absent from the remote inventory")
        else:
            rules = _read_branch_rules(repo_root, name, detail_cache)
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
