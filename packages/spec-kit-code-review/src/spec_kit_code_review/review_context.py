from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from .sdd_context import SOURCE_BRANCH, SddContext, TaskEntry, _fence_mask

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


@dataclass(frozen=True)
class SourceRange:
    path: str
    start: int
    end: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "start": self.start, "end": self.end, "reason": self.reason}


@dataclass(frozen=True)
class ContextSelection:
    required: tuple[SourceRange, ...] = ()
    selected: tuple[SourceRange, ...] = ()
    excluded: tuple[SourceRange, ...] = ()
    gaps: tuple[ScopeGap, ...] = ()

    @property
    def unresolved(self) -> bool:
        return bool(self.gaps)

    def as_dict(self) -> dict[str, Any]:
        return {
            "required": [item.as_dict() for item in self.required],
            "selected": [item.as_dict() for item in self.selected],
            "excluded": [item.as_dict() for item in self.excluded],
            "gaps": [{"code": item.code, "detail": item.detail, "affected": list(item.affected)} for item in self.gaps],
        }


def select_context(sdd: SddContext, scope: ReviewScope) -> ContextSelection:
    """Select complete, source-addressable context for one resolved scope.

    Selection is deliberately structural: task blocks and containing markdown
    sections are retained verbatim, while omitted task blocks remain visible as
    deliberate exclusions. Dependency traversal stops at direct dependencies.
    """
    required: list[SourceRange] = []
    gaps: list[ScopeGap] = []
    selected_ids = set(scope.task_ids)
    entries = {entry.identifier: entry for entry in sdd.task_entries}
    if scope.kind == "feature":
        selected_ids.update(entries)
    traces = {trace for entry in entries.values() if entry.identifier in selected_ids for trace in entry.traces}
    # Direct dependencies are evidence, not a recursive history walk.
    dependency_evidence: set[str] = set()
    for identifier in tuple(selected_ids):
        entry = entries.get(identifier)
        if entry is None:
            gaps.append(ScopeGap("task_reference_missing", f"required task {identifier} is absent", (identifier,)))
            continue
        for dependency in entry.dependencies:
            if dependency not in entries:
                gaps.append(ScopeGap("dependency_missing", f"{identifier} depends on missing {dependency}", (identifier, dependency)))
            else:
                selected_ids.add(dependency)
                dependency_evidence.add(dependency)
    for entry in sdd.task_entries:
        if entry.identifier in selected_ids and entry.source_range and sdd.tasks:
            start, end = entry.source_range
            reason = f"direct dependency evidence {entry.identifier}" if entry.identifier in dependency_evidence else f"complete task block {entry.identifier}"
            required.append(SourceRange(sdd.tasks.path, start, end, reason))
            gaps.extend(ScopeGap("task_gap", gap, (entry.identifier,)) for gap in entry.gaps)

    if sdd.tasks and sdd.tasks.present and sdd.task_entries:
        ordered = sorted(sdd.task_entries, key=lambda item: item.source_start or 1)
        all_blocks = [
            SourceRange(sdd.tasks.path, entry.source_start, entry.source_end, "task block")
            for entry in ordered if entry.source_range
        ]
        required.extend(_complement_ranges(sdd.tasks.path, len((sdd.tasks.text or "").splitlines()), all_blocks, "task ledger shared prose"))
    elif sdd.tasks and sdd.tasks.present:
        required.append(SourceRange(sdd.tasks.path, 1, len((sdd.tasks.text or "").splitlines()) or 1, "unstructured task ledger"))

    for artifact in sdd.artifacts():
        if artifact.present and artifact not in (sdd.spec, sdd.plan, sdd.tasks):
            required.append(SourceRange(artifact.path, 1, len((artifact.text or "").splitlines()) or 1, "complete rendered artifact"))
    if scope.kind == "feature":
        for artifact in (sdd.spec, sdd.plan):
            if artifact and artifact.present:
                required.append(SourceRange(artifact.path, 1, len((artifact.text or "").splitlines()) or 1, "complete feature contract"))

    # A cycle is useful evidence but must not recursively inject the cycle's
    # ancestors into the packet.
    visited: set[str] = set()
    for root in sorted(selected_ids):
        if root in visited or root not in entries:
            continue
        active: dict[str, int] = {}
        stack: list[tuple[str, int]] = [(root, 0)]
        trail: list[str] = []
        while stack:
            identifier, index = stack[-1]
            if identifier not in active:
                active[identifier] = len(trail)
                trail.append(identifier)
            dependencies = entries[identifier].dependencies
            if index < len(dependencies):
                dependency = dependencies[index]
                stack[-1] = (identifier, index + 1)
                if dependency in active:
                    cycle = tuple(trail[active[dependency]:] + [dependency])
                    gaps.append(ScopeGap("dependency_cycle", "dependency cycle: " + " -> ".join(cycle), cycle))
                elif dependency in entries and dependency not in visited:
                    stack.append((dependency, 0))
                continue
            stack.pop()
            active.pop(identifier, None)
            if trail and trail[-1] == identifier:
                trail.pop()
            visited.add(identifier)

    # Requirement/scenario and plan sections are selected by containing heading.
    wanted = set(traces)
    if scope.kind == "feature":
        wanted.update(sdd.requirement_ids)
    for artifact, identifiers in ((sdd.spec, wanted), (sdd.plan, wanted)):
        if artifact and artifact.present:
            if scope.kind == "feature":
                continue
            matching: list[SourceRange] = []
            sections = _markdown_sections(artifact.text or "")
            for start, end, level, body in sections:
                references = set(re.findall(r"\b(?:FR|NFR|SC)-\d+\b", body))
                if not references or identifiers.intersection(references):
                    matching.append(SourceRange(artifact.path, start, end, "related requirement or shared contract section"))
            if matching:
                required.extend(matching)
            else:
                required.append(SourceRange(artifact.path, 1, len((artifact.text or "").splitlines()) or 1, "unstructured required context"))
            if artifact is sdd.spec:
                available = set(re.findall(r"\b(?:FR|NFR|SC)-\d+\b", artifact.text or ""))
                for identifier in sorted(identifiers):
                    if identifier not in available:
                        gaps.append(ScopeGap("requirement_missing", f"required reference {identifier} is absent from {artifact.path}", (identifier, artifact.path)))
    if sdd.spec and sdd.spec.present and scope.kind == "feature":
        available = set(re.findall(r"\b(?:FR|NFR|SC)-\d+\b", sdd.spec.text or ""))
        for identifier in sorted(wanted):
            if identifier not in available:
                gaps.append(ScopeGap("requirement_missing", f"required reference {identifier} is absent from {sdd.spec.path}", (identifier, sdd.spec.path)))

    required = _merge_ranges(required)
    selected = tuple(required)
    excluded: list[SourceRange] = []
    for artifact in sdd.artifacts():
        artifact_ranges = [item for item in required if item.path == artifact.path]
        excluded.extend(_complement_ranges(artifact.path, len((artifact.text or "").splitlines()), artifact_ranges, "outside selected scope"))
    return ContextSelection(tuple(required), selected, tuple(excluded), tuple(_unique_gaps(gaps)))


def _markdown_sections(text: str) -> tuple[tuple[int, int, int, str], ...]:
    lines = text.splitlines(keepends=True)
    fenced = _fence_mask(lines)
    headings = [(i + 1, len(m.group("level")), m.group("title")) for i, line in enumerate(lines)
                if not fenced[i] and (m := re.match(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*#*\s*$", line.rstrip("\r\n")))]
    sections: list[tuple[int, int, str]] = []
    if headings and headings[0][0] > 1:
        sections.append((1, headings[0][0] - 1, 0, "".join(lines[:headings[0][0] - 1])))
    for index, (start, level, _title) in enumerate(headings):
        end = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
        sections.append((start, end, level, "".join(lines[start - 1:end])))
    return tuple(sections)


def _complement_ranges(path: str, total: int, selected: Sequence[SourceRange], reason: str) -> list[SourceRange]:
    if total <= 0:
        return []
    excluded: list[SourceRange] = []
    cursor = 1
    for item in sorted(selected, key=lambda value: (value.start, value.end)):
        if cursor < item.start:
            excluded.append(SourceRange(path, cursor, item.start - 1, reason))
        cursor = max(cursor, item.end + 1)
    if cursor <= total:
        excluded.append(SourceRange(path, cursor, total, reason))
    return excluded


def _merge_ranges(items: Sequence[SourceRange]) -> list[SourceRange]:
    result: list[SourceRange] = []
    for item in sorted(items, key=lambda value: (value.path, value.start, value.end, value.reason)):
        if result and result[-1].path == item.path and item.start <= result[-1].end + 1:
            previous = result.pop()
            result.append(SourceRange(item.path, previous.start, max(previous.end, item.end), f"{previous.reason}; {item.reason}"))
        else:
            result.append(item)
    return result


def _unique_gaps(gaps: Sequence[ScopeGap]) -> list[ScopeGap]:
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    result: list[ScopeGap] = []
    for gap in gaps:
        key = (gap.code, gap.detail, gap.affected)
        if key not in seen:
            seen.add(key)
            result.append(gap)
    return result


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
