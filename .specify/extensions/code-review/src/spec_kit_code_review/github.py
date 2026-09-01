"""Read-only ``gh`` wrapper: pull-request metadata, auth status, and identity."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .allowlist import EventConditions, Ledger, assert_never_approves, authorize
from .errors import (
    EXIT_AUTHENTICATION,
    EXIT_CANDIDATE,
    EXIT_ENGINE,
    EXIT_PREREQUISITE,
    EXIT_PUBLICATION,
    AppError,
    Diagnostic,
)
from .process import CommandResult, resolve_executable, run_command
from .redaction import redact_text


NUMBER_RE = re.compile(r"^[0-9]+$")
SHA1_RE = re.compile(r"[0-9a-f]{40}")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
PR_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9._-]+)/(?P<name>[A-Za-z0-9._-]+)/pull/(?P<number>[0-9]+)(?:[/?#].*)?$"
)

# Doc "Reglas de resolucion" rule 1: the exact field set the candidate
# resolution asks for, and the only pull-request read this stage performs.
PR_VIEW_FIELDS = (
    "number,baseRefName,baseRefOid,headRefOid,headRepositoryOwner,headRepository,"
    # `author` and `labels` are mutable metadata the packet's section 0 has to
    # report, and the author decides whether REQUEST_CHANGES is even possible:
    # GitHub refuses it on your own pull request.
    "isCrossRepository,state,url,title,body,author,labels"
)


@dataclass(frozen=True)
class PullRequest:
    """The pull-request snapshot ``gh pr view`` returned."""

    number: int
    repository: str
    base_branch: str
    base_commit: str
    head_commit: str
    head_repository: str | None
    cross_repository: bool
    state: str
    url: str
    title: str
    body: str
    author: str = ""
    labels: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "author": self.author,
            "labels": list(self.labels),
            "number": self.number,
            "repository": self.repository,
            "base_branch": self.base_branch,
            "base_commit": self.base_commit,
            "head_commit": self.head_commit,
            "head_repository": self.head_repository,
            "cross_repository": self.cross_repository,
            "state": self.state,
            "url": self.url,
        }


@dataclass(frozen=True)
class AuthStatus:
    """The outcome of ``gh auth status``, with the scopes it reported."""

    authenticated: bool
    detail: str
    scopes: tuple[str, ...]


class GitHub:
    """Every ``gh`` invocation Stage 1 makes; all of them read-only."""

    def __init__(self, executable: Path | str = "gh", *, timeout: int = 300) -> None:
        self.executable = str(executable)
        self.timeout = timeout

    def run(self, *arguments: str) -> CommandResult:
        return run_command([self.executable, *arguments], timeout=self.timeout)

    def auth_status(self) -> AuthStatus:
        result = self.run("auth", "status")
        text = f"{result.stdout}\n{result.stderr}".strip()
        scopes: tuple[str, ...] = ()
        match = re.search(r"[Tt]oken scopes:\s*(.+)", text)
        if match:
            scopes = tuple(
                scope.strip().strip("'\"")
                for scope in match.group(1).split(",")
                if scope.strip().strip("'\"")
            )
        return AuthStatus(authenticated=result.ok, detail=text, scopes=scopes)

    # -- the allowlisted API surface ------------------------------------
    #
    # Doc "Allowlist de operaciones remotas": every one of these goes through
    # `allowlist.authorize` before `gh` is invoked, and nothing else in this
    # package calls `gh api` at all.

    def api(
        self,
        method: str,
        path: str,
        *,
        fields: Mapping[str, Any] | None = None,
        event: str | None = None,
        conditions: EventConditions | None = None,
        ledger: Ledger | None = None,
        paginate: bool = False,
    ) -> Any:
        """One authorized API call, with its JSON parsed.

        The body is passed with ``--input -`` rather than as ``-f`` pairs: a
        review carries nested comment objects, and flattening them into field
        assignments would both mangle the structure and give a finding's text a
        second chance to be read as syntax.
        """

        operation = authorize(method, path, event=event, conditions=conditions, ledger=ledger)
        arguments = ["api", "--method", operation.method, path.lstrip("/")]
        if paginate:
            arguments.append("--paginate")
        payload: str | None = None
        if fields is not None:
            body = dict(fields)
            if event is not None:
                body["event"] = event
            assert_never_approves(body)
            payload = json.dumps(body)
            arguments.extend(["--input", "-"])
        result = run_command(
            [self.executable, *arguments],
            timeout=self.timeout,
            stdin=payload,
        )
        if not result.ok:
            detail = redact_text((result.stderr or result.stdout or "").strip()) or "gh api reported no detail"
            lowered = detail.lower()
            # An expired token and a rejected write are different problems with
            # different remedies, and the exit code is how a caller tells them
            # apart. `_pull_request_error` already classifies this way.
            authentication = any(
                marker in lowered
                for marker in ("http 401", "bad credentials", "http 403", "requires authentication", "must authenticate")
            )
            raise AppError(
                f"the GitHub API call failed: {operation.method} {path}",
                code=EXIT_AUTHENTICATION if authentication else EXIT_PUBLICATION,
                diagnostics=[
                    Diagnostic(
                        "github_authentication_failed" if authentication else "github_api_failed",
                        detail
                        + (
                            ". Re-authenticate with `gh auth login`; this extension never manages tokens of its own."
                            if authentication
                            else ""
                        ),
                        path,
                    )
                ],
            )
        text = result.stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if paginate:
                # `--paginate` concatenates one JSON document per page; the API
                # surfaces this extension reads are all arrays, so the pages are
                # joined rather than guessed at.
                items: list[Any] = []
                decoder = json.JSONDecoder()
                index = 0
                while index < len(text):
                    while index < len(text) and text[index].isspace():
                        index += 1
                    if index >= len(text):
                        break
                    document, index = decoder.raw_decode(text, index)
                    items.extend(document if isinstance(document, list) else [document])
                return items
            raise AppError(
                f"the GitHub API returned output that is not JSON: {operation.method} {path}",
                code=EXIT_PUBLICATION,
                diagnostics=[Diagnostic("github_api_unparseable", "expected a JSON document")],
            ) from None

    def authenticated_user(self, *, ledger: Ledger | None = None) -> str | None:
        """``GET /user``, through the allowlist like every other remote call.

        It decides whether ``REQUEST_CHANGES`` is even possible, so it is exactly
        the call that must not sit outside the perimeter.
        """

        try:
            payload = self.api("GET", "user", ledger=ledger)
        except AppError:
            return None
        if isinstance(payload, dict):
            login = str(payload.get("login") or "").strip()
            return login or None
        return None

    def pull_request(self, number: int, *, repository: str | None = None, ledger: Ledger | None = None) -> PullRequest:
        validate_number(str(number))
        # `gh pr view` is a different *client* surface for the same allowlisted
        # read, so it is authorized as one: the perimeter is about which remote
        # operations happen, not about which gh subcommand performs them.
        if repository is not None:
            validate_repository(repository)
            owner, _, name = repository.partition("/")
            authorize("GET", f"repos/{owner}/{name}/pulls/{number}", ledger=ledger)
        arguments = ["pr", "view", str(number), "--json", PR_VIEW_FIELDS]
        if repository is not None:
            arguments.extend(["--repo", repository])
        result = self.run(*arguments)
        if not result.ok:
            raise _pull_request_error(number, repository, result)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AppError(
                f"gh pr view returned output that is not JSON for pull request {number}",
                code=EXIT_ENGINE,
                diagnostics=[Diagnostic("gh_output_unparseable", "unexpected `gh pr view --json` output")],
            ) from error
        return _pull_request_from_payload(payload, fallback_repository=repository)


def _author(value: object) -> str:
    """The login of the pull request's author, whatever shape gh reported it in."""

    if isinstance(value, dict):
        return str(value.get("login") or value.get("name") or "")
    return str(value or "")


def _labels(value: object) -> tuple[str, ...]:
    """Label names only; the rest of the label object is of no use here."""

    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                names.append(str(name))
        elif item:
            names.append(str(item))
    return tuple(names)


def _pull_request_from_payload(payload: object, *, fallback_repository: str | None) -> PullRequest:
    if not isinstance(payload, dict):
        raise AppError(
            "gh pr view returned an unexpected JSON shape",
            code=EXIT_ENGINE,
            diagnostics=[Diagnostic("gh_output_shape", "expected a JSON object from `gh pr view --json`")],
        )
    url = str(payload.get("url") or "")
    repository = fallback_repository
    url_match = PR_URL_RE.match(url)
    if url_match:
        repository = f"{url_match.group('owner')}/{url_match.group('name')}"
    if repository is None:
        raise AppError(
            "could not determine the repository of this pull request",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("pr_repository_unknown", "pass --repository OWNER/NAME to disambiguate")],
        )
    head_owner = payload.get("headRepositoryOwner")
    head_name = payload.get("headRepository")
    head_repository: str | None = None
    if isinstance(head_owner, dict) and isinstance(head_name, dict):
        owner_login = head_owner.get("login") or head_owner.get("name")
        name_value = head_name.get("name")
        if owner_login and name_value:
            head_repository = f"{owner_login}/{name_value}"
    for field in ("baseRefName", "baseRefOid", "headRefOid"):
        if not payload.get(field):
            raise AppError(
                f"gh pr view did not report {field}",
                code=EXIT_CANDIDATE,
                diagnostics=[Diagnostic("pr_field_missing", f"missing {field} in the pull-request payload")],
            )
    # The object ids come from outside this process, and they are propagated
    # into `git fetch` and every later invocation. Anything that is not a full
    # SHA-1 stops here rather than being handed to git as a "ref".
    for field in ("baseRefOid", "headRefOid"):
        value = str(payload[field])
        if not SHA1_RE.fullmatch(value):
            raise AppError(
                f"gh pr view reported a {field} that is not a full SHA-1: {value!r}",
                code=EXIT_CANDIDATE,
                diagnostics=[
                    Diagnostic(
                        "pr_oid_invalid",
                        "expected 40 hexadecimal characters; the value is never passed to git",
                        field,
                    )
                ],
            )
    return PullRequest(
        number=int(payload.get("number") or 0),
        repository=repository,
        base_branch=str(payload["baseRefName"]),
        base_commit=str(payload["baseRefOid"]),
        head_commit=str(payload["headRefOid"]),
        head_repository=head_repository,
        cross_repository=bool(payload.get("isCrossRepository")),
        state=str(payload.get("state") or "UNKNOWN").upper(),
        url=url,
        author=_author(payload.get("author")),
        labels=_labels(payload.get("labels")),
        title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""),
    )


def _pull_request_error(number: int, repository: str | None, result: CommandResult) -> AppError:
    stderr = (result.stderr or "").strip()
    lowered = stderr.lower()
    target = f"{repository}#{number}" if repository else f"#{number}"
    if "authentication" in lowered or "not logged" in lowered or "401" in lowered or "403" in lowered:
        return AppError(
            f"gh is not authenticated for {target}",
            code=EXIT_AUTHENTICATION,
            diagnostics=[Diagnostic("gh_auth", "run `gh auth login` yourself; this extension never manages tokens")],
        )
    return AppError(
        f"pull request not resolvable: {target}",
        code=EXIT_CANDIDATE,
        diagnostics=[Diagnostic("pr_unresolvable", stderr or "gh pr view failed")],
    )


def validate_repository(value: str) -> str:
    if not REPOSITORY_RE.match(value or ""):
        raise AppError(
            f"invalid repository identity: {value}",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("repository_invalid", "expected OWNER/NAME", value)],
        )
    return value


def validate_number(value: str) -> int:
    if not NUMBER_RE.match(value or ""):
        raise AppError(
            f"invalid pull request number: {value}",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("pr_number_invalid", "expected a positive integer", value)],
        )
    return int(value)


def open_github(*, override: str | None = None, forbidden_roots: tuple[Path, ...] = (), timeout: int = 300) -> GitHub | None:
    """Resolve the ``gh`` executable safely; ``None`` when it is not installed."""

    executable = resolve_executable("gh", override=override, forbidden_roots=forbidden_roots)
    if executable is None:
        return None
    return GitHub(executable, timeout=timeout)


def require_github(*, override: str | None = None, forbidden_roots: tuple[Path, ...] = (), timeout: int = 300) -> GitHub:
    """``open_github`` for the paths that cannot proceed without it.

    A pull-request selector needs ``gh``; ``--base``/``--head`` is the offline
    path and needs nothing. This never installs anything.
    """

    client = open_github(override=override, forbidden_roots=forbidden_roots, timeout=timeout)
    if client is None:
        raise AppError(
            "gh is required to resolve a pull-request selector and was not found on PATH",
            code=EXIT_PREREQUISITE,
            diagnostics=[
                Diagnostic(
                    "gh_missing",
                    "install the GitHub CLI yourself, or use --base/--head for the offline path",
                )
            ],
        )
    return client

