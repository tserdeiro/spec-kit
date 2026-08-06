#!/usr/bin/env python3
"""A fake ``gh`` executable, driven by a JSON state file.

Installed through ``SPECKIT_CODE_REVIEW_GH_BIN`` in the *real* process
environment of the test -- never through the repository env file, which by
contract ignores executable overrides (and that fact has its own test). No test
in the default suite ever invokes the real ``gh``.

State file (``SPECKIT_CODE_REVIEW_FAKE_GH_STATE``)::

    {
      "auth": {"authenticated": true, "scopes": ["repo", "read:org"]},
      "user": "octocat",
      "pull_requests": {
        "128": {"number": 128, "baseRefName": "main", "baseRefOid": "...", ...}
      }
    }
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


STATE_ENV = "SPECKIT_CODE_REVIEW_FAKE_GH_STATE"


def _state() -> dict:
    path = os.environ.get(STATE_ENV)
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _auth_status(state: dict) -> int:
    auth = state.get("auth") or {}
    if not auth.get("authenticated", True):
        sys.stderr.write("You are not logged into any GitHub hosts. To log in, run: gh auth login\n")
        return 1
    scopes = ", ".join(f"'{scope}'" for scope in auth.get("scopes", ["repo"]))
    sys.stderr.write("github.com\n  " + "✓ Logged in to github.com account tester (keyring)\n")
    sys.stderr.write(f"  - Token scopes: {scopes}\n")
    return 0


def _pull_request(state: dict, arguments: list[str]) -> int:
    number = arguments[0] if arguments else ""
    # `pr view` is a read of /pulls/{n}; it is recorded like every other remote
    # call so a test can assert the *order* of operations, including that the
    # re-verification happens before the first write.
    _record_api(state, "GET", f"pr-view/{number}", None)
    pull_requests = state.get("pull_requests") or {}
    payload = pull_requests.get(str(number))
    if payload is None:
        sys.stderr.write(f"no pull requests found for number {number}\n")
        return 1
    if payload.get("__error") == "auth":
        sys.stderr.write("HTTP 401: Bad credentials\n")
        return 1
    sys.stdout.write(json.dumps(payload))
    return 0


# The API surface this fake serves, mirroring the contract's allowlist. Anything
# else is refused *by the fake as well*, so a test can assert both that the
# extension never attempted a forbidden call and that it would have been
# rejected if it had.
_ALLOWED = (
    ("GET", re.compile(r"^user$")),
    ("GET", re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+$")),
    ("GET", re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/files$")),
    ("GET", re.compile(r"^repos/[^/]+/[^/]+/issues/\d+/comments$")),
    ("GET", re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews$")),
    ("POST", re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews$")),
    ("POST", re.compile(r"^repos/[^/]+/[^/]+/issues/\d+/comments$")),
)


def _flag_value(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def _record_api(state: dict, method: str, endpoint: str, body: dict | None) -> None:
    """Append one API call to the behavioural log the tests read."""

    destination = state.get("record_api")
    if not destination:
        return
    entry = {"method": method, "endpoint": endpoint}
    if body is not None:
        entry["body"] = body
    try:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _api(state: dict, arguments: list[str]) -> int:
    if not arguments:
        sys.stderr.write("missing endpoint\n")
        return 1
    method = (_flag_value(arguments, "--method") or "GET").upper()
    endpoint = next(
        (
            item
            for index, item in enumerate(arguments)
            if not item.startswith("-") and (index == 0 or arguments[index - 1] not in ("--method", "--input", "--jq"))
        ),
        "",
    ).split("?", 1)[0]
    body = None
    if "--input" in arguments:
        raw = sys.stdin.read()
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            sys.stderr.write("fake gh: the request body is not JSON\n")
            return 1

    if not any(method == allowed_method and pattern.match(endpoint) for allowed_method, pattern in _ALLOWED):
        # The fake refuses what the contract forbids, so a test can prove the
        # refusal is real and not merely never exercised.
        _record_api(state, method, endpoint, body)
        sys.stderr.write(f"fake gh: {method} {endpoint} is not in the allowlist\n")
        return 1
    if body is not None and str(body.get("event") or "").upper() == "APPROVE":
        _record_api(state, method, endpoint, body)
        sys.stderr.write("fake gh: APPROVE is refused\n")
        return 1

    _record_api(state, method, endpoint, body)

    # -- the API's own validations, as far as they matter here ---------------
    #
    # A fake that accepts anything hides exactly the bugs it exists to catch.
    # These three are the ones the real endpoint enforces and that this
    # extension can get wrong.
    if method == "POST" and endpoint.endswith("/reviews"):
        payload = body or {}
        if payload.get("event") and not str(payload.get("body") or "").strip():
            sys.stderr.write(
                "HTTP 422: Validation Failed (body is required when event is COMMENT or REQUEST_CHANGES)\n"
            )
            return 1
        commit_id = str(payload.get("commit_id") or "")
        expected = str(state.get("head_commit") or "")
        if expected and commit_id and commit_id != expected:
            sys.stderr.write("HTTP 422: Validation Failed (commit_id is not the head of this pull request)\n")
            return 1
        for comment in payload.get("comments") or []:
            if not str(comment.get("body") or "").strip():
                sys.stderr.write("HTTP 422: Validation Failed (comment body is required)\n")
                return 1
            if not comment.get("path"):
                sys.stderr.write("HTTP 422: Validation Failed (comment path is required)\n")
                return 1
    if method == "POST" and endpoint.endswith("/issues/" + endpoint.split("/issues/")[-1].split("/")[0] + "/comments"):
        if not str((body or {}).get("body") or "").strip():
            sys.stderr.write("HTTP 422: Validation Failed (body is required)\n")
            return 1
    failures = state.get("api_failures") or {}
    key = f"{method} {endpoint}"
    # Persisted, not in-process: every `gh` call is its own process, so a counter
    # that lived only in memory would always read 1 and "fail after the second
    # call" would never happen.
    counter = state.setdefault("counts", {})
    counter[key] = counter.get(key, 0) + 1
    _persist(state)
    failure = failures.get(key)
    if isinstance(failure, dict) and failure.get("after", 0) < counter[key]:
        sys.stderr.write(failure.get("message", "HTTP 422: Unprocessable Entity") + "\n")
        return 1
    if isinstance(failure, str):
        sys.stderr.write(failure + "\n")
        return 1

    if endpoint == "user":
        login = state.get("user") or "tester"
        if "--jq" in arguments:
            sys.stdout.write(f"{login}\n")
        else:
            sys.stdout.write(json.dumps({"login": login}))
        return 0
    if endpoint.endswith("/comments") and method == "GET":
        comments = state.get("issue_comments") or []
        if "--paginate" in arguments and len(comments) > 2:
            # The real `--paginate` concatenates one JSON document per page;
            # emitting a single array would never exercise the adapter's
            # multi-document join.
            for start in range(0, len(comments), 2):
                sys.stdout.write(json.dumps(comments[start : start + 2]))
            return 0
        sys.stdout.write(json.dumps(comments))
        return 0
    if endpoint.endswith("/reviews") and method == "GET":
        sys.stdout.write(json.dumps(state.get("reviews") or []))
        return 0
    if endpoint.endswith("/reviews") and method == "POST":
        identifier = 9000 + counter[key]
        created = {
            "id": identifier,
            "html_url": f"https://github.com/x/y/pull/1#pullrequestreview-{identifier}",
            "body": (body or {}).get("body", ""),
            "commit_id": (body or {}).get("commit_id", ""),
            "state": "COMMENTED",
        }
        # Visible to the next invocation, which is what makes the idempotent
        # retry testable end to end.
        state.setdefault("reviews", []).append(created)
        _persist(state)
        sys.stdout.write(json.dumps(created))
        return 0
    if endpoint.endswith("/comments") and method == "POST":
        identifier = 8000 + counter[key]
        created = {"id": identifier, "html_url": f"https://github.com/x/y/pull/1#issuecomment-{identifier}"}
        # A published summary becomes visible to the next invocation, which is
        # what makes the republish refusal testable end to end.
        state.setdefault("issue_comments", []).append({"id": identifier, "body": (body or {}).get("body", "")})
        _persist(state)
        sys.stdout.write(json.dumps(created))
        return 0
    if endpoint.endswith("/files"):
        sys.stdout.write(json.dumps(state.get("files") or []))
        return 0
    sys.stdout.write(json.dumps(state.get("pull_requests", {}).get("128") or {}))
    return 0


def _persist(state: dict) -> None:
    """Write the mutated state back, so a second invocation sees the first."""

    path = os.environ.get(STATE_ENV)
    if not path:
        return
    try:
        stored = dict(state)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(stored, handle)
    except OSError:
        pass


def main(argv: list[str]) -> int:
    state = _state()
    if not argv:
        sys.stderr.write("fake gh: no arguments\n")
        return 1
    if argv[0] == "auth" and len(argv) > 1 and argv[1] == "status":
        return _auth_status(state)
    if argv[0] == "pr" and len(argv) > 1 and argv[1] == "view":
        return _pull_request(state, argv[2:])
    if argv[0] == "api":
        return _api(state, argv[1:])
    sys.stderr.write(f"fake gh: unsupported invocation: {' '.join(argv)}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
