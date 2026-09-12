from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from .sdd_context import SOURCE_BRANCH, SddContext, TaskEntry

_TASK_BRANCH_RE = re.compile(
    r"^(?P<number>\d{3})(?:-[A-Za-z0-9._-]+)?-T(?P<task>\d{3,})(?:-[A-Za-z0-9._-]+)?$"
)
_FEATURE_BRANCH_RE = re.compile(r"^\d{3}(?:-[A-Za-z0-9._-]+)?$")
_ISSUE_BRANCH_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9]+-\d+(?:[-/].*)?|(?:bug|chore|fix)(?:[-/].*)?)$", re.IGNORECASE)

@dataclass(frozen=True)
class ScopeGap:
    code: str
    detail: str
    affected: tuple[str, ...] = ()

@dataclass(frozen=True)
class ReviewScope:
    kind: str
    feature: str | None
    task_ids: tuple[str, ...]
    changed_paths: tuple[str, ...]
    candidate_id: str
    merge_base: str
    head_commit: str
    head_ref_name: str | None = None
    evidence: tuple[tuple[str, Any], ...] = ()
    gaps: tuple[ScopeGap, ...] = ()

    @property
    def unresolved(self) -> bool:
        return bool(self.gaps)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "feature": self.feature,
            "task_ids": list(self.task_ids),
            "changed_paths": list(self.changed_paths),
            "candidate_id": self.candidate_id,
            "merge_base": self.merge_base,
            "head_commit": self.head_commit,
            "head_ref_name": self.head_ref_name,
            "evidence": dict(self.evidence),
            "gaps": [{"code": gap.code, "detail": gap.detail, "affected": list(gap.affected)} for gap in self.gaps],
            "unresolved": self.unresolved,
        }


def resolve_scope(
    candidate: Any,
    *,
    pull_request: Any | None,
    sdd: SddContext,
    changed_paths: Sequence[str],
    base_task_entries: Sequence[TaskEntry] = (),
) -> ReviewScope:
    paths = tuple(dict.fromkeys(changed_paths))
    head_ref = getattr(pull_request, "head_ref_name", None) or None
    feature = sdd.resolution.feature
    gaps: list[ScopeGap] = []
    branch_task: str | None = None
    branch_feature: str | None = None
    branch_kind = "short-path"
    if head_ref:
        branch_task_match = _TASK_BRANCH_RE.match(head_ref.strip().strip("/"))
        if branch_task_match:
            branch_task = f"T{branch_task_match.group('task')}"
            branch_feature = feature if feature and feature.startswith(branch_task_match.group("number")) else None
            branch_kind = "task"
        elif feature and _feature_branch_matches(head_ref, feature):
            branch_feature = feature
            branch_kind = "feature"
        elif feature and not _ISSUE_BRANCH_RE.match(head_ref.strip().strip("/")):
            gaps.append(ScopeGap("branch_unrecognized", f"head branch {head_ref!r} is not attributable to a feature or issue-key work item"))
    elif pull_request is not None:
        gaps.append(ScopeGap("head_branch_missing", "the pull-request snapshot did not include headRefName"))

    if sdd.resolution.ambiguous:
        gaps.append(ScopeGap("feature_ambiguous", "candidate evidence names multiple feature directories", sdd.resolution.candidates))
    if branch_task and not branch_feature:
        gaps.append(ScopeGap("branch_feature_mismatch", f"head branch {head_ref!r} does not match resolved feature {feature or '(none)'!r}"))
    if branch_task and not any(entry.identifier == branch_task for entry in sdd.task_entries):
        gaps.append(ScopeGap("task_unknown", f"head branch names {branch_task}, but that task is absent from the candidate ledger", (branch_task,)))

    path_matches = {
        entry.identifier: tuple(path for path in entry.referenced_paths if path in paths)
        for entry in sdd.task_entries
    }
    affected = {identifier for identifier, matches in path_matches.items() if matches}
    block_changes = _changed_task_blocks(sdd.task_entries, base_task_entries)
    affected.update(block_changes)
    missing_tasks = sorted(block_changes - {entry.identifier for entry in sdd.task_entries})
    if missing_tasks:
        gaps.append(ScopeGap("task_block_missing", "changed task blocks are absent from the candidate ledger", tuple(missing_tasks)))
    if branch_task:
        affected.add(branch_task)
    all_task_ids = tuple(entry.identifier for entry in sdd.task_entries) + tuple(missing_tasks)

    tasks_path = next((path for path in paths if path.endswith("/tasks.md") or path == "tasks.md"), None)
    if tasks_path and not block_changes:
        gaps.append(ScopeGap("tasks_changed_unmatched", f"{tasks_path} changed but no task block could be associated with the candidate", (tasks_path,)))

    if missing_tasks or branch_kind == "feature" or (pull_request is None and feature):
        kind = "feature"
        task_ids = tuple(dict.fromkeys(all_task_ids))
    elif branch_kind == "task" and feature:
        unmatched = [
            path for path in paths
            if path != tasks_path and not any(path in matches for matches in path_matches.values())
        ]
        if unmatched and feature:
            kind = "feature"
            task_ids = tuple(entry.identifier for entry in sdd.task_entries)
        else:
            task_ids = tuple(entry.identifier for entry in sdd.task_entries if entry.identifier in affected)
            kind = "multi-task" if len(task_ids) > 1 else "task"
    elif feature and sdd.resolution.source == SOURCE_BRANCH:
        kind = "feature"
        task_ids = tuple(entry.identifier for entry in sdd.task_entries)
    else:
        kind = "short-path"
        task_ids = ()

    evidence = (
        ("branch", head_ref),
        ("branch_kind", branch_kind),
        ("path_matches", {key: list(value) for key, value in path_matches.items() if value}),
        ("changed_task_blocks", sorted(block_changes)),
        ("resolution", sdd.resolution.as_dict()),
    )
    return ReviewScope(
        kind=kind,
        feature=feature,
        task_ids=task_ids,
        changed_paths=paths,
        candidate_id=str(candidate.candidate_id),
        merge_base=str(candidate.merge_base),
        head_commit=str(candidate.head_commit),
        head_ref_name=head_ref,
        evidence=evidence,
        gaps=tuple(gaps),
    )

def _feature_branch_matches(branch: str, feature: str) -> bool:
    value = branch.strip().strip("/")
    if value == feature:
        return True
    match = _FEATURE_BRANCH_RE.match(value)
    return bool(match and feature.startswith(value.split("-", 1)[0] + "-"))

def _changed_task_blocks(head: Sequence[TaskEntry], base: Sequence[TaskEntry]) -> set[str]:
    before = {entry.identifier: entry.block_text for entry in base}
    after = {entry.identifier: entry.block_text for entry in head}
    return {
        identifier for identifier in set(before) | set(after)
        if before.get(identifier) != after.get(identifier)
    }
