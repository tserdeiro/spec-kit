"""Bugs and chores: Issues a human filed in Linear, followed by branch and PR.

Stage 5 (vision "Workflow de bugs y chores") is the short path: an Issue is
created in Linear by a person, a branch named after it appears, a PR follows,
and it is reviewed and merged. This extension never creates such an Issue and
never edits its title, description, labels, or assignee -- the only thing it
projects is the Issue's *workflow state*, derived from exactly the same
observable reality Stage 3 already derives task states from.

Identity comes from the native Linear resolver. A branch may use any valid
native name, a user prefix, or an old title; textual branch conventions are
only a resolver input and never a projection identity.

The map is Stage 3's, minus the checkbox -- a bug has no `tasks.md` row:

| observation                   | state       |
| ----------------------------- | ----------- |
| an open draft PR              | `started`   |
| an open, ready-for-review PR  | `review`    |
| a merged PR                   | `completed` |
| a branch (without live PR)    | `started`   |
| nothing at all                | *not touched* |

The last row is the one difference that matters: an Issue with neither a
branch nor a PR produces no observation at all, so a backlog of bugs nobody
started is never rewritten to "Todo" by a push.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .github import PullRequest, PullRequestScan
from .work_state import (
    SOURCE_BRANCH,
    SOURCE_PULL_REQUEST,
    STATE_STARTED,
    pull_request_state,
    strongest_pull_request,
)


WORK_ITEM_IDENTITY_PREFIX = "workitem:"


def issue_key_pattern(team_key: str) -> re.Pattern[str]:
    """The one branch-naming convention for a bug or chore: ``<TEAM>-<number>``.

    As strict as the task convention, and for the same reason -- a false
    positive silently moves someone else's Issue. ``WOR-123`` and
    ``wor-123-fix-crash`` match; ``WORX-1`` (different team), ``wor123`` (no
    separator), ``wor-`` (no number), and ``wor-12x`` (trailing junk) do not.
    """

    # The optional single-level prefix is Linear's own "Copy git branch name"
    # format (`<username>/wor-123-slug`): the native button must produce a
    # branch this extension derives, or the native path would be second-class.
    return re.compile(rf"^(?:[^/]+/)?{re.escape(team_key)}-(\d+)(?:-.*)?$", re.IGNORECASE)


def work_item_identity(identifier: str) -> str:
    """The plan/snapshot identity for one work item, e.g. ``workitem:WOR-123``."""

    return f"{WORK_ITEM_IDENTITY_PREFIX}{identifier}"


@dataclass(frozen=True)
class WorkItemState:
    """One bug or chore's derived state, with the observation that produced it."""

    identifier: str
    state: str | None
    source: str
    detail: str
    # The observed pull request's own number; see TaskWorkState.pr_number
    # (work_state.py) for why -- the same field, threaded the same way.
    pr_number: int | None = None

    @property
    def identity(self) -> str:
        return work_item_identity(self.identifier)

    def as_dict(self) -> dict[str, object]:
        return {"identifier": self.identifier, "state": self.state, "source": self.source, "detail": self.detail, "pr_number": self.pr_number}


def derive_work_items(
    *,
    branches: Sequence[str] = (),
    scan: PullRequestScan,
    resolution: Mapping[str, object],
) -> tuple[WorkItemState, ...]:
    """Derive work items from the native resolver's ordered observations.

    The resolver owns identity. This function only joins each result back to
    the corresponding branch or pull request and applies the existing
    lifecycle precedence. Any unresolved or conflicting result protects every
    Issue named by ``affected_issue_keys`` from a speculative update.
    """

    observations = resolution.get("observations")
    if not isinstance(observations, list) or len(observations) != len(branches) + len(scan.pull_requests):
        return ()

    candidates: dict[str, list[tuple[str, object]]] = {}
    blocked: dict[str, str] = {}
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            continue
        kind = "branch" if index < len(branches) else "pull_request"
        observed = branches[index] if kind == "branch" else scan.pull_requests[index - len(branches)]
        status = observation.get("status")
        affected = observation.get("affected_issue_keys")
        keys = tuple(key for key in affected if isinstance(key, str)) if isinstance(affected, list) else ()
        if status == "excluded":
            continue
        if status != "resolved":
            detail = observed if kind == "branch" else observed.head_branch
            for key in keys:
                blocked.setdefault(key, detail)
            continue
        resolution_context = observation.get("resolution")
        identifier = resolution_context.get("identifier") if isinstance(resolution_context, Mapping) else None
        if not isinstance(identifier, str) or not identifier:
            detail = observed if kind == "branch" else observed.head_branch
            for key in keys:
                blocked.setdefault(key, detail)
            continue
        # A resolved observation may carry additional affected keys from an
        # equivalent head. Those keys are evidence, not identities; only the
        # canonical resolution is eligible for lifecycle derivation.
        candidates.setdefault(identifier, []).append((kind, observed))

    derived: list[WorkItemState] = []
    identifiers = set(candidates) | set(blocked)
    for identifier in identifiers:
        if identifier in blocked or scan.outcome != "complete":
            derived.append(WorkItemState(identifier, None, "unknown", blocked.get(identifier, "pull-request observation")))
            continue
        entries = candidates.get(identifier, ())
        pull_requests = [observed for kind, observed in entries if kind == "pull_request"]
        strongest = strongest_pull_request(pull_requests)
        if strongest is not None:
            derived.append(WorkItemState(identifier, pull_request_state(strongest), SOURCE_PULL_REQUEST, strongest.head_branch, strongest.number))
            continue
        branch = next((observed for kind, observed in entries if kind == "branch"), None)
        if isinstance(branch, str):
            derived.append(WorkItemState(identifier, STATE_STARTED, SOURCE_BRANCH, branch))
    return tuple(sorted(derived, key=lambda item: int(item.identifier.rsplit("-", 1)[-1])))


def issue_numbers(work_items: Sequence[WorkItemState]) -> tuple[int, ...]:
    """The Issue numbers to resolve, for the single batched remote lookup."""

    return tuple(sorted({int(item.identifier.rsplit("-", 1)[-1]) for item in work_items}))
