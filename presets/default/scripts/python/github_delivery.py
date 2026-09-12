#!/usr/bin/env python3
"""Report the repository settings used by the delivery workflow.

This first delivery slice deliberately leaves branch guarantees unverified;
the later rules evaluator owns that observation.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from _common import run_gh

COMPATIBLE = "compatible"
INCOMPATIBLE = "incompatible"
CAPABILITY_UNAVAILABLE = "capability-unavailable"
UNVERIFIED = "unverified"

_SETTINGS = (
    ("deleteBranchOnMerge", "Automatically delete head branches"),
    ("mergeCommitAllowed", "Allow merge commits"),
)
_BRANCH_GUARANTEES = (
    ("force-push protection", "inspect GitHub Settings → Rules → Rulesets and branch protection for shared-branch update restrictions"),
    ("merge commits", "inspect GitHub Settings → Rules → Rulesets and branch protection for merge restrictions"),
    ("cleanup", "inspect GitHub Settings → Rules → Rulesets and branch protection for deletion restrictions"),
)


@dataclass(frozen=True)
class Result:
    state: str
    cause: str
    evidence: str
    next_action: str


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


def diagnose(repo_root: Path) -> tuple[dict[str, Result], tuple[tuple[str, Result], ...]]:
    settings = _read_settings(repo_root)
    branch = tuple(
        (
            name,
            _unknown(
                "partial-scope",
                "branch inventory and effective branch rules are not observed by this report",
                f"{action[0].upper() + action[1:]}",
            ),
        )
        for name, action in _BRANCH_GUARANTEES
    )
    return settings, branch


def render(settings: dict[str, Result], branch: tuple[tuple[str, Result], ...]) -> str:
    lines = [
        "GitHub delivery diagnosis",
        "Scope: repository settings observed; branch inventory and effective rules remain unverified.",
    ]
    for name, setting in _SETTINGS:
        finding = settings[name]
        suffix = f"; cause={finding.cause}" if finding.cause else ""
        line = f"{name}: {finding.state} ({finding.evidence}{suffix})"
        if finding.next_action:
            line += f" — next: {finding.next_action}"
        lines.append(line)
    for name, finding in branch:
        lines.append(f"{name}: {finding.state} ({finding.evidence}) — next: {finding.next_action}")
    lines.append("Overall: unverified (branch inventory and effective rules are not observed yet).")
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
