"""The only door to GitHub, and it is a closed list.

Doc "Allowlist de operaciones remotas". Every remote call this extension makes
passes through `authorize` first, and an operation that is not on the list fails
closed -- not "is refused later", not "is unlikely to be reached": there is no
code path from this package to `gh api` that does not go through here.

The list is written as data rather than as branching logic for one reason: a
reader can check it against the contract line by line, and a test can assert the
whole product of methods and paths without depending on which caller happens to
exist today.

`APPROVE` is not an unlisted value that happens to be rejected. It is not
representable: `review_operation` accepts two events and raises on anything else,
and the write operation for reviews carries the event in its own field precisely
so the check cannot be bypassed by building the payload elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .errors import EXIT_PUBLICATION, AppError, Diagnostic


READ = "read"
WRITE = "write"

EVENT_COMMENT = "COMMENT"
EVENT_REQUEST_CHANGES = "REQUEST_CHANGES"
PERMITTED_EVENTS: tuple[str, ...] = (EVENT_COMMENT, EVENT_REQUEST_CHANGES)
# Named so the prohibition is greppable and testable. It is never a valid value
# of anything in this package.
FORBIDDEN_EVENT = "APPROVE"

_OWNER = r"[A-Za-z0-9._-]+"
_NAME = r"[A-Za-z0-9._-]+"
_NUMBER = r"[0-9]+"


@dataclass(frozen=True)
class Operation:
    """One remote operation this extension is allowed to perform."""

    method: str
    pattern: str
    kind: str
    purpose: str

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(f"^{self.pattern}$")

    def as_dict(self) -> dict[str, Any]:
        return {"method": self.method, "path": self.pattern, "kind": self.kind, "purpose": self.purpose}


# Doc "Allowlist de operaciones remotas", transcribed. Nothing else is reachable.
ALLOWED: tuple[Operation, ...] = (
    Operation("GET", rf"repos/{_OWNER}/{_NAME}/pulls/{_NUMBER}", READ, "read the pull request and its refs"),
    Operation(
        "GET",
        rf"repos/{_OWNER}/{_NAME}/pulls/{_NUMBER}/files",
        READ,
        "file metadata of the pull request; never a source of anchor positions",
    ),
    Operation(
        "GET",
        rf"repos/{_OWNER}/{_NAME}/issues/{_NUMBER}/comments",
        READ,
        "detect this extension's own summary comment for this candidate",
    ),
    Operation(
        "GET",
        rf"repos/{_OWNER}/{_NAME}/pulls/{_NUMBER}/reviews",
        READ,
        "detect a previous review of this candidate by this extension",
    ),
    Operation("GET", r"user", READ, "the authenticated identity"),
    Operation(
        "POST",
        rf"repos/{_OWNER}/{_NAME}/pulls/{_NUMBER}/reviews",
        WRITE,
        "create a review, with event COMMENT or REQUEST_CHANGES",
    ),
    Operation(
        "POST",
        rf"repos/{_OWNER}/{_NAME}/issues/{_NUMBER}/comments",
        WRITE,
        "the per-candidate summary comment",
    ),
)

# Written out so the refusal can name what was attempted rather than only that
# something was. These are the operations the contract forbids **always**.
FORBIDDEN_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("PUT", "repos/o/r/pulls/1/merge"),
    ("PATCH", "repos/o/r/pulls/1"),
    ("PATCH", "repos/o/r/issues/comments/1"),
    ("DELETE", "repos/o/r/issues/comments/1"),
    ("PUT", "repos/o/r/pulls/1/reviews/1/events"),
    ("DELETE", "repos/o/r/pulls/1/reviews/1"),
    ("POST", "repos/o/r/git/refs"),
    ("PATCH", "repos/o/r/git/refs/heads/main"),
    ("POST", "repos/o/r/releases"),
    ("GET", "repos/o/r/collaborators"),
)


@dataclass(frozen=True)
class EventConditions:
    """The four conditions the contract attaches to ``REQUEST_CHANGES``.

    They live *inside* the perimeter rather than beside it: a future caller that
    assembles the event somewhere else would otherwise pass a check that has
    already been made elsewhere. Each is necessary and none is sufficient --
    the configuration can only permit, the invocation can only use what is
    permitted, the verdict has to warrant it, and GitHub itself refuses
    ``REQUEST_CHANGES`` from the author of the pull request.
    """

    ceiling: str
    requested: bool
    verdict: str
    author_is_authenticated_user: bool

    def unmet(self) -> list[str]:
        reasons: list[str] = []
        if self.ceiling != "request-changes":
            reasons.append(f"the repository's publish.event ceiling is {self.ceiling!r}")
        if not self.requested:
            reasons.append("--request-changes was not passed")
        if self.verdict != "changes-requested":
            reasons.append(f"the verdict is {self.verdict!r}, not changes-requested")
        if self.author_is_authenticated_user:
            reasons.append("the authenticated user is the author of the pull request")
        return reasons


@dataclass
class Ledger:
    """Every operation authorized in this process, in order.

    Kept because "what did it actually do to GitHub?" must be answerable from
    the evidence without reading a log, and because the tests assert the exact
    sequence rather than the mere absence of forbidden calls.
    """

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, operation: Operation, path: str, *, event: str | None = None, outcome: str = "authorized") -> None:
        entry: dict[str, Any] = {"method": operation.method, "path": path, "kind": operation.kind, "outcome": outcome}
        if event is not None:
            entry["event"] = event
        self.entries.append(entry)

    @property
    def writes(self) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry["kind"] == WRITE]

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.entries)


def _refuse(method: str, path: str, detail: str) -> AppError:
    return AppError(
        f"refused: {method} {path} is not an allowed GitHub operation",
        code=EXIT_PUBLICATION,
        diagnostics=[
            Diagnostic(
                "allowlist_refused",
                f"{detail} This extension performs only the operations its contract enumerates, and an operation "
                "that is not on the list fails closed rather than being attempted.",
                path,
            )
        ],
    )


# A query string is not part of the identity of an operation, but it must not be
# able to smuggle a different path either -- and what is checked has to be what
# is sent, so the split is validated rather than merely discarded.
_QUERY_RE = re.compile(r"^[A-Za-z0-9_.,=&%+:-]*$")


def split_endpoint(path: str) -> tuple[str, str]:
    """The endpoint and its query, both validated as ordinary API syntax."""

    normalized = path.strip().lstrip("/")
    endpoint, separator, query = normalized.partition("?")
    if separator and not _QUERY_RE.match(query):
        raise _refuse("?", path, "the query string is not plain API syntax.")
    return endpoint, query


def find(method: str, path: str) -> Operation | None:
    """The allowed operation matching this call, if there is one."""

    endpoint, _query = split_endpoint(path)
    for operation in ALLOWED:
        if operation.method == method.upper() and operation.regex.match(endpoint):
            return operation
    return None


def authorize(
    method: str,
    path: str,
    *,
    event: str | None = None,
    conditions: EventConditions | None = None,
    ledger: Ledger | None = None,
) -> Operation:
    """Authorize one remote operation, or fail closed.

    Every argument is checked, including the event and -- when the event is
    ``REQUEST_CHANGES`` -- the four conditions the contract attaches to it. A
    review whose event is not one of the two permitted values is refused here,
    so `APPROVE` cannot be reached by assembling the payload somewhere this
    module does not see.
    """

    normalized = path.strip().lstrip("/")
    if ".." in normalized or normalized.startswith("http"):
        # A path that traverses or names a host is not a GitHub API path at all;
        # matching it against the patterns would be answering the wrong question.
        raise _refuse(method, path, "the path is not a plain GitHub API endpoint.")
    # `split_endpoint` validates the query as well, so the string that is checked
    # is exactly the string the caller will send.
    split_endpoint(normalized)
    operation = find(method, normalized)
    if operation is None:
        raise _refuse(method, path, "no allowed operation matches this method and path.")
    creates_review = operation.kind == WRITE and operation.pattern.endswith("/reviews")
    if not creates_review and event is not None:
        # An event on anything but the review write is either a mistake or an
        # attempt to smuggle one into a payload that would carry it verbatim.
        # Refusing here makes the guarantee structural instead of leaving it to
        # the body check downstream.
        raise _refuse(method, path, "only the creation of a review carries an event.")
    if creates_review:
        if event is None:
            raise _refuse(method, path, "a review must name its event, and only COMMENT and REQUEST_CHANGES exist.")
        if event not in PERMITTED_EVENTS:
            raise _refuse(
                method,
                path,
                f"the event {event!r} is not one this extension can ever emit"
                + (
                    " -- approving a pull request is a human decision, always, and no flag or configuration makes "
                    "it reachable."
                    if event == FORBIDDEN_EVENT
                    else "."
                ),
            )
        if event == EVENT_REQUEST_CHANGES:
            if conditions is None:
                raise _refuse(
                    method,
                    path,
                    "REQUEST_CHANGES carries four conditions and none were presented for checking.",
                )
            unmet = conditions.unmet()
            if unmet:
                raise _refuse(method, path, f"REQUEST_CHANGES is not authorized: {'; '.join(unmet)}.")
    if ledger is not None:
        ledger.record(operation, normalized, event=event)
    return operation


def assert_never_approves(payload: Mapping[str, Any]) -> None:
    """Belt and braces on the body of a review: no `APPROVE`, however it arrived.

    The event is validated in `authorize`, which is the check that matters. This
    one reads the payload that is actually about to be sent, so a future caller
    that builds the body from somewhere else still cannot ship an approval.
    """

    event = str(payload.get("event") or "")
    if event.upper() == FORBIDDEN_EVENT:
        raise _refuse(
            "POST",
            "repos/…/pulls/…/reviews",
            "the request body carries an APPROVE event.",
        )


def describe() -> list[dict[str, Any]]:
    """The allowlist as data, for `--json` and for the documentation tests."""

    return [operation.as_dict() for operation in ALLOWED]


def forbidden(operations: Sequence[tuple[str, str]] = FORBIDDEN_EXAMPLES) -> list[dict[str, str]]:
    """The enumerated prohibitions, for the same two audiences."""

    return [{"method": method, "path": path} for method, path in operations]
