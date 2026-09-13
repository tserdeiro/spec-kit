"""Optional pull-request observation, read once per invocation through `gh`.

Only a complete GitHub observation supplies pull-request evidence for state
derivation. Missing, failed, or unreadable observations remain unverified and
preserve existing Linear states; they never fall back to checkbox or branch
signals. One paginated `gh api` call serves the invocation, and `gh` owns
GitHub authentication so no credential is read, stored, or logged here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import Diagnostic


GH_API_VERSION = "2022-11-28"
GH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class PullRequest:
    head_branch: str
    is_draft: bool
    state: str
    # The PR's own number, e.g. for `/speckit.code-review <n>` (D6, T013).
    # Defaulted so a caller that only needs derivation, not next_action's
    # command text, keeps constructing this unchanged.
    number: int | None = None
    # The body is retained for canonical `Tracker: Fixes TEAM-number` linkage.
    body: str = ""

    @property
    def is_merged(self) -> bool:
        return self.state.upper() == "MERGED"

    @property
    def is_open(self) -> bool:
        return self.state.upper() == "OPEN"


@dataclass(frozen=True)
class PullRequestScan:
    """Every pull request `gh` reported, plus whether the scan happened at all.

    ``outcome`` is always ``complete``, ``failed``, or ``incomplete``;
    diagnostics explain every non-complete result.
    """

    outcome: str
    pull_requests: tuple[PullRequest, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


def scan_pull_requests(root: Path) -> PullRequestScan:
    """List every repository pull request, preserving uncertainty."""

    if shutil.which("gh") is None:
        return _unavailable(
            "github_cli_missing",
            "`gh` was not found on PATH; GitHub observation is unverified and existing Linear states are preserved. Install the GitHub CLI to observe draft/ready/merged states",
        )
    try:
        result = subprocess.run(
            [
                "gh", "api", "repos/{owner}/{repo}/pulls", "--paginate", "--slurp",
                "--method", "GET", "-H", f"X-GitHub-Api-Version: {GH_API_VERSION}",
                "-f", "state=all", "-f", "per_page=100",
            ],
            cwd=str(root),
            check=False,
            text=True,
            capture_output=True,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return _unavailable("github_cli_failed", "`gh api` could not be run; GitHub observation is unverified and existing Linear states are preserved")
    if result.returncode != 0:
        # `gh`'s stderr can carry a hostname, an account, or a token hint, so
        # it is never echoed: the remedy is the same whatever it says.
        return _unavailable(
            "github_cli_unavailable",
            "`gh api` failed (no GitHub remote, or not authenticated); GitHub observation is unverified and existing Linear states are preserved. Check the remote or run `gh auth login` as appropriate",
        )
    pull_requests = _parse_pages(result.stdout)
    if pull_requests is None:
        return PullRequestScan(
            outcome="incomplete",
            diagnostics=(Diagnostic("github_cli_malformed", "`gh api` returned output this extension could not read; GitHub observation is unverified and existing Linear states are preserved", severity="warning"),),
        )
    return PullRequestScan("complete", pull_requests)


def cli_diagnostic(root: Path, *, offline: bool) -> Diagnostic:
    """`doctor`'s informational check: is `gh` installed, and is it usable here."""

    if shutil.which("gh") is None:
        return Diagnostic(
            "github_cli_missing",
            "`gh` was not found on PATH; GitHub observation is unverified and existing Linear states are preserved. Install the GitHub CLI to observe pull-request states",
            severity="warning",
        )
    if offline:
        return Diagnostic("github_cli", "`gh` found on PATH; authentication was not checked with --offline", severity="info")
    try:
        result = subprocess.run(["gh", "auth", "status"], cwd=str(root), check=False, text=True, capture_output=True, timeout=GH_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return Diagnostic("github_cli_unauthenticated", "`gh auth status` could not be run; GitHub observation is unverified and existing Linear states are preserved", severity="warning")
    if result.returncode != 0:
        return Diagnostic("github_cli_unauthenticated", "`gh` is installed but not authenticated; GitHub observation is unverified and existing Linear states are preserved. Run `gh auth login` to observe pull-request states", severity="warning")
    return Diagnostic("github_cli", "`gh` is installed and authenticated", severity="info")


def _parse_pages(payload: str) -> tuple[PullRequest, ...] | None:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list) or not data or any(not isinstance(page, list) for page in data):
        return None
    pull_requests: list[PullRequest] = []
    by_number: dict[int, PullRequest] = {}
    for page in data:
        for item in page:
            if not isinstance(item, dict):
                return None
            number = item.get("number")
            head = item.get("head")
            head_branch = head.get("ref") if isinstance(head, dict) else None
            is_draft = item.get("draft")
            state = item.get("state")
            if "merged_at" not in item:
                return None
            merged_at = item["merged_at"]
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                return None
            if not isinstance(head_branch, str) or not head_branch:
                return None
            if not isinstance(is_draft, bool) or state not in ("open", "closed"):
                return None
            body = item.get("body")
            if body is not None and not isinstance(body, str):
                return None
            if merged_at is not None and (not isinstance(merged_at, str) or not merged_at):
                return None
            if merged_at is not None and state != "closed":
                return None
            if merged_at is not None:
                state = "MERGED"
            observed = PullRequest(head_branch=head_branch, is_draft=is_draft, state=state, number=number, body=body or "")
            previous = by_number.get(number)
            if previous is not None and previous != observed:
                return None
            if previous is None:
                by_number[number] = observed
                pull_requests.append(observed)
    return tuple(pull_requests)


def _unavailable(code: str, message: str) -> PullRequestScan:
    return PullRequestScan("failed", diagnostics=(Diagnostic(code, message, severity="warning"),))
