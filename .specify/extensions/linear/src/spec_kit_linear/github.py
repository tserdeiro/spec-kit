"""Optional pull-request signal, read once per invocation through the `gh` binary.

Vision steps 5-7 (draft PR, self-review, final review) are observable only on
GitHub, so a task's `In Review` state comes from a pull request whose head
branch follows the `NNN-Txxx` convention. GitHub is deliberately optional:
without `gh`, without authentication, or with output this extension cannot
read, the scan degrades to "no pull request is known" with a single warning,
and the checkbox and branch signals carry the derivation on their own.

One `gh pr list --json` per invocation, never one per task, and never a
GraphQL call of our own: the `gh` binary owns GitHub authentication entirely,
so no GitHub credential is ever read, stored, or logged here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import Diagnostic


GH_JSON_FIELDS = "headRefName,isDraft,state"
GH_PULL_REQUEST_LIMIT = "200"
GH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class PullRequest:
    head_branch: str
    is_draft: bool
    state: str

    @property
    def is_merged(self) -> bool:
        return self.state.upper() == "MERGED"

    @property
    def is_open(self) -> bool:
        return self.state.upper() == "OPEN"


@dataclass(frozen=True)
class PullRequestScan:
    """Every pull request `gh` reported, plus whether the scan happened at all.

    ``available`` is false whenever the derivation must proceed without
    GitHub; ``diagnostics`` then carries exactly one warning explaining why.
    """

    pull_requests: tuple[PullRequest, ...] = ()
    available: bool = True
    diagnostics: tuple[Diagnostic, ...] = ()


def scan_pull_requests(root: Path) -> PullRequestScan:
    """List the repository's pull requests, degrading to an empty scan."""

    if shutil.which("gh") is None:
        return _unavailable(
            "github_cli_missing",
            "`gh` was not found on PATH; pull-request states are not derived (checkbox and branch states still are). Install the GitHub CLI to sync draft/ready/merged states",
        )
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "all", "--limit", GH_PULL_REQUEST_LIMIT, "--json", GH_JSON_FIELDS],
            cwd=str(root),
            check=False,
            text=True,
            capture_output=True,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return _unavailable("github_cli_failed", "`gh pr list` could not be run; pull-request states are not derived")
    if result.returncode != 0:
        # `gh`'s stderr can carry a hostname, an account, or a token hint, so
        # it is never echoed: the remedy is the same whatever it says.
        return _unavailable(
            "github_cli_unavailable",
            "`gh pr list` failed (no GitHub remote, or not authenticated); pull-request states are not derived. Run `gh auth login` in this repository",
        )
    pull_requests = _parse(result.stdout)
    if pull_requests is None:
        return _unavailable("github_cli_malformed", "`gh pr list --json` returned output this extension could not read; pull-request states are not derived")
    return PullRequestScan(pull_requests=pull_requests)


def cli_diagnostic(root: Path, *, offline: bool) -> Diagnostic:
    """`doctor`'s informational check: is `gh` installed, and is it usable here."""

    if shutil.which("gh") is None:
        return Diagnostic(
            "github_cli_missing",
            "`gh` was not found on PATH; push and status derive Linear states from the tasks.md checkbox and Git branches only",
            severity="warning",
        )
    if offline:
        return Diagnostic("github_cli", "`gh` found on PATH; authentication was not checked with --offline", severity="info")
    try:
        result = subprocess.run(["gh", "auth", "status"], cwd=str(root), check=False, text=True, capture_output=True, timeout=GH_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return Diagnostic("github_cli_unauthenticated", "`gh auth status` could not be run; pull-request states will not be derived", severity="warning")
    if result.returncode != 0:
        return Diagnostic("github_cli_unauthenticated", "`gh` is installed but not authenticated; run `gh auth login` to derive pull-request states", severity="warning")
    return Diagnostic("github_cli", "`gh` is installed and authenticated", severity="info")


def _parse(payload: str) -> tuple[PullRequest, ...] | None:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    pull_requests: list[PullRequest] = []
    for item in data:
        if not isinstance(item, dict):
            return None
        head_branch = item.get("headRefName")
        is_draft = item.get("isDraft")
        state = item.get("state")
        if not isinstance(head_branch, str) or not isinstance(is_draft, bool) or not isinstance(state, str):
            return None
        pull_requests.append(PullRequest(head_branch=head_branch, is_draft=is_draft, state=state))
    return tuple(pull_requests)


def _unavailable(code: str, message: str) -> PullRequestScan:
    return PullRequestScan(pull_requests=(), available=False, diagnostics=(Diagnostic(code, message, severity="warning"),))
