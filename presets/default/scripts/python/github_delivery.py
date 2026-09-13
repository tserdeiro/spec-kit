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
    evaluate_cleanup,
    evaluate_force_push,
    evaluate_merge,
    parse_active_rules,
    parse_branch_page_items,
    parse_classic_protection,
    parse_page_collection,
    parse_ruleset_detail,
    shared_branches,
    cause_action,
    unknown_branch_result,
)

_SETTINGS = (
    ("deleteBranchOnMerge", "Automatically delete head branches"),
    ("mergeCommitAllowed", "Allow merge commits"),
)

_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_PLAN_PATTERNS = (
    re.compile(r"(?i)\b(?:not available|unavailable|unsupported)\b.{0,50}\b(?:your|current|this|the current)\s+(?:github\s+)?(?:plan|tier)\b"),
    re.compile(r"(?i)\b(?:not available|unavailable|unsupported)\b.{0,50}\b(?:github\s+)?(?:free|pro|team|enterprise|paid|premium|advanced)\s+(?:plan|tier)\b"),
    re.compile(r"(?i)\b(?:requires?|upgrade(?:\s+to)?|available only (?:on|for))\s+(?:a\s+)?github\s+enterprise(?:\s+(?:plan|tier))?\b"),
    re.compile(r"(?i)\b(?:requires?|upgrade\s+to)\s+github\s+(?:free|pro|team|enterprise)\b"),
    re.compile(r"(?i)\b(?:requires?|upgrade(?:\s+to)?|available only (?:on|for))\s+(?:a\s+)?(?:github\s+)?(?:free|pro|team|paid|premium|advanced)\s+(?:plan|tier)\b"),
    re.compile(r"(?i)\b(?:your|current|this)\s+(?:github\s+)?(?:plan|tier)\b.{0,70}\b(?:does not|doesn't|cannot|can't)\s+(?:support|include)\b"),
)
_AUTH_RE = re.compile(r"(?i)\b(?:http\s*)?401\b|bad credentials|requires? authentication|not logged in|gh auth login|invalid token|authentication failed")
_PERMISSION_RE = re.compile(r"(?i)\b(?:permission|permissions|access)\s+(?:denied|forbidden|required|needed)\b|access denied|insufficient (?:access|scope)|resource .*not accessible|must have .*access|requires? .{0,50}\bpermissions?\b|\b(?:due to|because of) .{0,20}\bpermissions?\b")
_RATE_RE = re.compile(r"(?i)\b(?:http\s*)?429\b|too many requests|\b(?:http\s*)?403\b.{0,80}(?:rate|abuse)|rate limit|secondary rate|abuse detection")


def _safe_detail(value: str) -> str:
    """Keep a bounded, single-line diagnostic without authentication material."""
    detail = _ANSI_RE.sub(" ", str(value))
    detail = "".join(char if char in "\t\n\r" or ord(char) >= 32 else " " for char in detail)
    detail = re.sub(r"(?i)\b(bearer|basic)\s+[^,;}\]\r\n]+", r"\1 <redacted>", detail)
    detail = re.sub(r"(?i)(\b(?:authorization|api[_\-\s]?key|access[_-]?token|client[_-]?secret|token|password|secret|credential)s?\b\s*[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;\"'}]+)", r"\1<redacted>", detail)
    detail = re.sub(r"(?i)\b(?:api[_\-\s]?key|access[_-]?token|client[_-]?secret|token|password|secret|credential)s?\s+[^,;}\]\r\n]+", "<redacted>", detail)
    detail = re.sub(r"(?:gh[pousr]_\w+|github_pat_[A-Za-z0-9_\-]+)", "<redacted>", detail)
    detail = re.sub(r"\s+", " ", detail).strip()
    return detail[:160] or "no diagnostic detail"


def _unknown(cause: str, evidence: str, action: str) -> Result:
    return Result(UNVERIFIED, cause, evidence, action)


def _remote_error(result: object) -> str:
    """Keep only bounded stderr and a JSON error message, never an error payload."""
    raw_stderr = getattr(result, "stderr", "")
    try:
        stderr_payload = json.loads(raw_stderr)
        raw_stderr = stderr_payload.get("message", "") if isinstance(stderr_payload, dict) else ""
    except (json.JSONDecodeError, TypeError):
        pass
    parts = [_safe_detail(raw_stderr)]
    try:
        payload = json.loads(getattr(result, "stdout", ""))
    except (json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        parts.append(_safe_detail(payload["message"]))
    return "; ".join(part for part in parts if part and part != "no diagnostic detail") or "GitHub returned an unsuccessful response"


def _failure_cause(result: object, endpoint: str = "") -> str:
    """Classify only positive evidence; bare HTTP 403/404 stays ambiguous."""
    stderr = str(getattr(result, "stderr", ""))
    stdout = str(getattr(result, "stdout", ""))
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        payload = None
    message = payload.get("message", "") if isinstance(payload, dict) else ""
    text = (stderr[:2000] + " " + str(message)[:2000]).strip()
    if any(pattern.search(text) for pattern in _PLAN_PATTERNS):
        return "plan-limitation"
    if _RATE_RE.search(text):
        return "rate-limited"
    if _AUTH_RE.search(text):
        return "authentication-failure"
    if _PERMISSION_RE.search(text):
        return "insufficient-permissions"
    if re.search(r"(?i)branch\s+(?:was\s+)?not found|branch disappeared", text) and "/branches/" in endpoint:
        return "branch-disappeared"
    if re.search(r"(?i)\b(?:http\s*)?(?:403|404)\b", text):
        return "ambiguous-read"
    return "read-failure"


def _failure_result(result: object, target: str) -> Result:
    cause = _failure_cause(result)
    detail = _remote_error(result)
    state = CAPABILITY_UNAVAILABLE if cause == "plan-limitation" else UNVERIFIED
    return Result(state, cause, f"{target} read failed: {detail}", cause_action(cause, target))


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
        value = re.sub(r"^gh:\s*", "", str(candidate).strip(), flags=re.I)
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
        result = _failure_result(completed, "repository settings")
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
    next_action: str = ""


def _api_read(repo_root: Path, endpoint: str) -> _RemoteRead:
    """Read a paginated REST collection through an explicit GET only."""
    try:
        result = run_gh("api", "--method", "GET", "--paginate", "--slurp", endpoint, cwd=repo_root)
    except OSError as error:
        return _RemoteRead(False, cause="read-failure", evidence=_safe_detail(str(error)))
    if result.returncode != 0:
        cause = _failure_cause(result, endpoint)
        detail = _remote_error(result)
        try:
            partial_payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            partial_payload = None
        return _RemoteRead(False, payload=partial_payload, cause=cause, evidence=detail, next_action=cause_action(cause, "GitHub API"))
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
        documented = _is_branch_not_protected(result)
        cause = "read-failure" if documented else _failure_cause(result, endpoint)
        target = "ruleset detail" if "/rulesets/" in endpoint else "classic protection"
        return _RemoteRead(False, cause=cause, evidence=detail, documented_absence=documented, next_action=cause_action(cause, target))
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
    if not read.complete and read.cause == "read-failure":
        return _RemoteRead(False, payload=read.payload, cause="partial-inventory", evidence=read.evidence, next_action="Retry the GitHub branch inventory after confirming access to repository metadata")
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
        payload = read.payload if isinstance(read.payload, dict) else {}
        missing = [name for name in ("allow_force_pushes", "enforce_admins") if name not in payload]
        cause = "hidden-fields" if missing else "malformed-response"
        evidence = f"classic protection omitted fields: {', '.join(missing)}" if missing else "classic protection had invalid fields"
        return ClassicProtection(False, None, cause=cause, evidence=evidence)
    missing = [name for name in ("allow_deletions", "lock_branch", "required_linear_history") if name not in read.payload]
    if missing:
        return ClassicProtection(
            True, True, parsed.allow_force_pushes, parsed.enforce_admins,
            parsed.allow_deletions, parsed.lock_branch, parsed.required_linear_history,
            "hidden-fields", f"classic protection omitted fields: {', '.join(missing)}",
        )
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
            payload = read.payload if isinstance(read.payload, dict) else {}
            missing = [name for name in ("id", "source_type", "source", "enforcement") if name not in payload]
            cause = "hidden-fields" if missing else "malformed-response"
            evidence = f"ruleset detail omitted fields: {', '.join(missing)}" if missing else "ruleset detail had invalid fields"
            value = (None, cause, evidence)
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
        rules = parse_active_rules(read.payload) if read.payload is not None else ()
        cause = "partial-rules" if read.cause == "read-failure" else read.cause
        return RuleRead(False, rules=rules or (), cause=cause, evidence=read.evidence, classic=classic)
    rules = parse_active_rules(read.payload)
    if rules is None:
        pages = parse_page_collection(read.payload)
        missing = any(
            isinstance(item, dict) and any(name not in item for name in ("type", "ruleset_source_type", "ruleset_source", "ruleset_id"))
            for page in pages or () for item in page
        )
        cause = "hidden-fields" if missing else "malformed-response"
        return RuleRead(False, cause=cause, evidence="effective branch rules had missing or invalid fields", classic=classic)
    cache = detail_cache if detail_cache is not None else {}
    details: list[RulesetDetail] = []
    detail_errors: list[tuple[tuple[str, str, int], tuple[str, str]]] = []
    for rule in rules:
        detail, cause, evidence = _read_ruleset_detail(repo_root, rule, cache)
        if detail is not None:
            details.append(detail)
        else:
            detail_errors.append((rule.identity, (cause, evidence)))
    return RuleRead(
        True,
        rules=rules,
        classic=classic,
        details=tuple(details),
        detail_errors=tuple(detail_errors),
    )


def _branch_findings(
    repo_root: Path,
    settings: dict[str, Result] | None = None,
) -> tuple[tuple[str, Result], ...]:
    """Observe the complete remote inventory, then effective rules per shared branch."""
    captured = StringIO()
    try:
        with redirect_stderr(captured):
            trunk = delivery_base(repo_root).strip()
    except (SystemExit, OSError):
        trunk = ""
    trunk_error = _safe_detail(captured.getvalue()) if not trunk else ""
    settings = settings or {}
    if not trunk:
        finding = _unknown("trunk-unresolved", trunk_error or "the configured delivery base could not be resolved", "Resolve the delivery base and retry the GitHub diagnosis")
        return (("force-push protection", finding), ("merge commits", finding), ("cleanup", finding))

    inventory = _read_inventory(repo_root)
    if not inventory.complete:
        state = CAPABILITY_UNAVAILABLE if inventory.cause in {"plan-limitation", "github-cli-unavailable"} else UNVERIFIED
        finding = Result(
            state,
            inventory.cause or "partial-inventory",
            f"{trunk}: {inventory.evidence or 'remote branch inventory was not completely observed'}",
            inventory.next_action or cause_action(inventory.cause, "GitHub branch inventory"),
        )
        return ((f"force-push protection [{trunk} (trunk)]", finding),
                (f"merge commits [{trunk} (trunk)]", finding),
                (f"cleanup [{trunk} (trunk)]", finding))

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
        merge = evaluate_merge(name, rules, settings.get("mergeCommitAllowed"))
        cleanup = evaluate_cleanup(name, rules, settings.get("deleteBranchOnMerge"), role=role)
        results.append((f"merge commits [{name} ({role})]", merge))
        results.append((f"cleanup [{name} ({role})]", cleanup))
    return tuple(results)


def diagnose(repo_root: Path) -> tuple[dict[str, Result], tuple[tuple[str, Result], ...]]:
    settings = _read_settings(repo_root)
    return settings, _branch_findings(repo_root, settings)


def overall_result(settings: dict[str, Result], branch: tuple[tuple[str, Result], ...]) -> Result:
    """Summarize only the observed snapshot; future branches remain out of scope."""
    results = [*settings.values(), *(finding for _, finding in branch)]
    coverage_complete = all(setting in settings for setting, _ in _SETTINGS) and bool(branch)
    if coverage_complete and all(result.state == COMPATIBLE for result in results):
        return Result(COMPATIBLE, "", "all required guarantees verified within the observed branch snapshot", "")
    incompatible = next((result for result in results if result.state == INCOMPATIBLE), None)
    if incompatible is not None:
        return Result(INCOMPATIBLE, incompatible.cause, "one or more observed guarantees are incompatible", incompatible.next_action)
    unavailable = next((result for result in results if result.state == CAPABILITY_UNAVAILABLE), None)
    if unavailable is not None:
        return Result(CAPABILITY_UNAVAILABLE, unavailable.cause, "a required GitHub capability was unavailable", unavailable.next_action)
    return Result(UNVERIFIED, "incomplete-observation", "one or more required guarantees remain unverified", "Retry the GitHub diagnosis after confirming access")


def render(settings: dict[str, Result], branch: tuple[tuple[str, Result], ...]) -> str:
    scope = "repository settings and the current snapshot of existing shared branches; future branches are not certified."
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
    summary = overall_result(settings, branch)
    lines.append(f"Overall: {summary.state} ({summary.evidence}).")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv:
        print("usage: github_delivery.py", file=sys.stderr)
        return 2
    settings, branch = diagnose(Path.cwd())
    print(render(settings, branch))
    return 0 if overall_result(settings, branch).state == COMPATIBLE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
