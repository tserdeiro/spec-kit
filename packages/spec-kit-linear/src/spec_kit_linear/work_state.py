"""Derive each `Txxx` task's workflow state from observable repository reality.

Stage 3 (vision steps 4-7) never listens for events and never remembers what
it did last time. Every `push` and every `status` re-derives the state of
every task from three things that can be observed right now:

- the `tasks.md` checkbox (the repository is the authority);
- the branches Git already knows about, matched against the `NNN-Txxx`
  convention;
- when `gh` is available, the pull requests whose head branch follows that
  same convention.

The map, highest priority first -- the first rule that applies wins:

| observation                        | state       |
| ---------------------------------- | ----------- |
| `[x]` checkbox, or a merged PR     | `completed` |
| an open, ready-for-review PR       | `review`    |
| an open draft PR, or a branch      | `started`   |
| nothing at all                     | `unstarted` |

Which Linear workflow state each of those four names writes to is
configuration (`lifecycle` in `speckit-linear.yml`), resolved by `onboard`;
this module names the state, never the id.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .domain import DesiredState
from .github import PullRequest


STATE_COMPLETED = "completed"
STATE_REVIEW = "review"
STATE_STARTED = "started"
STATE_UNSTARTED = "unstarted"

SOURCE_CHECKBOX = "checkbox"
SOURCE_PULL_REQUEST = "pr"
SOURCE_BRANCH = "branch"
SOURCE_NONE = "none"


def branch_pattern(feature: str, task: str) -> re.Pattern[str]:
    """The one branch-naming convention: `NNN-Txxx`, optionally `-<suffix>`.

    Deliberately strict, because a false positive silently moves someone
    else's Issue: `001-T004` and `001-T004-add-parser` match, while `T004`
    (no feature), `001-T004x` (no separator) and `1-T004` do not.
    """

    return re.compile(rf"^{re.escape(feature)}-{re.escape(task)}(?:-.*)?$")


@dataclass(frozen=True)
class TaskWorkState:
    """One task's derived state, with the observation that produced it."""

    state: str
    source: str
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {"state": self.state, "source": self.source, "detail": self.detail}


def derive_task_state(
    feature: str,
    task: str,
    *,
    completed: bool,
    branches: Sequence[str] = (),
    pull_requests: Sequence[PullRequest] = (),
) -> TaskWorkState:
    """Apply the priority map above to one task."""

    if completed:
        return TaskWorkState(STATE_COMPLETED, SOURCE_CHECKBOX)
    pattern = branch_pattern(feature, task)
    pull_request = _strongest_pull_request(pattern, pull_requests)
    if pull_request is not None:
        return TaskWorkState(pull_request_state(pull_request), SOURCE_PULL_REQUEST, pull_request.head_branch)
    branch = next((name for name in branches if pattern.fullmatch(name)), None)
    if branch is not None:
        return TaskWorkState(STATE_STARTED, SOURCE_BRANCH, branch)
    return TaskWorkState(STATE_UNSTARTED, SOURCE_NONE)


def derive_task_states(
    desired_states: Sequence[DesiredState],
    *,
    branches: Sequence[str] = (),
    pull_requests: Sequence[PullRequest] = (),
) -> dict[str, TaskWorkState]:
    """Derive every selected feature's tasks, keyed by `DesiredTask.identity`."""

    derived: dict[str, TaskWorkState] = {}
    for desired in desired_states:
        feature = desired.feature.identifier
        for task in desired.feature.tasks:
            derived[task.identity] = derive_task_state(
                feature,
                task.identity.rsplit(":", 1)[-1],
                completed=task.completed,
                branches=branches,
                pull_requests=pull_requests,
            )
    return derived


# A closed-but-unmerged pull request is not an observation about the task's
# state at all -- the work was abandoned or superseded -- so it is ignored and
# the branch (or the checkbox) decides. Among the rest the strongest signal
# wins, which is also what makes stacked PRs behave: several PRs on one task
# report the furthest that task has actually got.
_PULL_REQUEST_RANK = {"merged": 3, "ready": 2, "draft": 1}


def strongest_pull_request(matches: Sequence[PullRequest]) -> PullRequest | None:
    """The furthest-advanced pull request among ``matches``, ignoring the rest.

    Shared with ``work_items.py`` so a bug/chore branch and a feature task
    branch rank their pull requests by exactly the same rule.
    """

    relevant = [item for item in matches if item.is_merged or item.is_open]
    if not relevant:
        return None
    return max(relevant, key=lambda item: _PULL_REQUEST_RANK[_rank_key(item)])


def pull_request_state(pull_request: PullRequest) -> str:
    """The derived state a single pull request observation stands for."""

    if pull_request.is_merged:
        return STATE_COMPLETED
    return STATE_STARTED if pull_request.is_draft else STATE_REVIEW


def _strongest_pull_request(pattern: re.Pattern[str], pull_requests: Sequence[PullRequest]) -> PullRequest | None:
    return strongest_pull_request([item for item in pull_requests if pattern.fullmatch(item.head_branch)])


def _rank_key(pull_request: PullRequest) -> str:
    if pull_request.is_merged:
        return "merged"
    return "draft" if pull_request.is_draft else "ready"
