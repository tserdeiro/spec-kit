"""Bugs and chores: Issues a human filed in Linear, followed by branch and PR.

Stage 5 (vision "Workflow de bugs y chores") is the short path: an Issue is
created in Linear by a person, a branch named after it appears, a PR follows,
and it is reviewed and merged. This extension never creates such an Issue and
never edits its title, description, labels, or assignee -- the only thing it
projects is the Issue's *workflow state*, derived from exactly the same
observable reality Stage 3 already derives task states from.

The convention is the Issue key itself: a local or ``origin/`` branch named
``<team key>-<number>``, optionally followed by ``-<suffix>``, references that
Issue. ``wor-123-fix-crash``, ``WOR-45`` and ``Wor-45-x`` all reference the
same team's Issues; the team key comes from the repository binding, never from
a constant. The comparison is case-insensitive because Git branch names are
conventionally lowercase while Linear Issue keys are uppercase.

The map is Stage 3's, minus the checkbox -- a bug has no `tasks.md` row:

| observation                   | state       |
| ----------------------------- | ----------- |
| a merged PR                   | `completed` |
| an open, ready-for-review PR  | `review`    |
| an open draft PR, or a branch | `started`   |
| nothing at all                | *not touched* |

The last row is the one difference that matters: an Issue with neither a
branch nor a PR produces no observation at all, so a backlog of bugs nobody
started is never rewritten to "Todo" by a push.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .github import PullRequest
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
    state: str
    source: str
    detail: str

    @property
    def identity(self) -> str:
        return work_item_identity(self.identifier)

    def as_dict(self) -> dict[str, object]:
        return {"identifier": self.identifier, "state": self.state, "source": self.source, "detail": self.detail}


def derive_work_items(
    team_key: str,
    *,
    branches: Sequence[str] = (),
    pull_requests: Sequence[PullRequest] = (),
) -> tuple[WorkItemState, ...]:
    """Derive every Issue key observed in ``branches`` or ``pull_requests``.

    Both sources are matched with the same pattern and grouped by the
    canonical ``<TEAM>-<number>`` identifier, so the branch and the PR that
    share a name are one work item. The result is sorted by Issue number,
    which is also the order `status` renders and `push` reconciles in.
    """

    pattern = issue_key_pattern(team_key)
    canonical = team_key.upper()
    branches_by_key: dict[str, str] = {}
    for name in branches:
        match = pattern.fullmatch(name)
        if match is not None:
            branches_by_key.setdefault(f"{canonical}-{int(match.group(1))}", name)
    pull_requests_by_key: dict[str, list[PullRequest]] = {}
    for pull_request in pull_requests:
        match = pattern.fullmatch(pull_request.head_branch)
        if match is not None:
            pull_requests_by_key.setdefault(f"{canonical}-{int(match.group(1))}", []).append(pull_request)

    derived: list[WorkItemState] = []
    for identifier in set(branches_by_key) | set(pull_requests_by_key):
        # A closed-but-unmerged PR is not an observation about the work at all
        # (`strongest_pull_request` drops it), so the branch decides -- exactly
        # as it does for a task.
        pull_request = strongest_pull_request(pull_requests_by_key.get(identifier, ()))
        if pull_request is not None:
            derived.append(WorkItemState(identifier, pull_request_state(pull_request), SOURCE_PULL_REQUEST, pull_request.head_branch))
            continue
        branch = branches_by_key.get(identifier)
        if branch is not None:
            derived.append(WorkItemState(identifier, STATE_STARTED, SOURCE_BRANCH, branch))
    return tuple(sorted(derived, key=lambda item: int(item.identifier.rsplit("-", 1)[-1])))


def issue_numbers(work_items: Sequence[WorkItemState]) -> tuple[int, ...]:
    """The Issue numbers to resolve, for the single batched remote lookup."""

    return tuple(sorted({int(item.identifier.rsplit("-", 1)[-1]) for item in work_items}))
