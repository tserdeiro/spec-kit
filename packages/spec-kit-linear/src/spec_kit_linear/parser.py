"""Pure parsers for the Spec Kit artifacts that remain authoritative."""

from __future__ import annotations

import re
from pathlib import Path

from .discovery import FEATURE_RE
from .domain import Feature, Phase, SourceRef, Task
from .errors import AppError, Diagnostic


TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
PHASE_RE = re.compile(r"^#{1,6}\s+Phase\s+([0-9]+)(?:\s*:\s*(.+?))?\s*$", re.IGNORECASE)
TASK_RE = re.compile(r"^\s*-\s+\[([ xX])\]\s+(T[0-9]{3})\b(?:\s*[-:]\s*)?(.*?)\s*$")
LEADING_MARKERS_RE = re.compile(r"^(?:\[[^\]]+\]\s*)+")
# doc "Parsing de artefactos" (annotation syntax): a task's leading `[...]`
# markers may include at most one `[@alias]` assignee annotation. This is
# extracted from the leading-markers span *before* LEADING_MARKERS_RE strips
# it from the title below, so the alias is never silently swallowed with the
# rest of the markers.
MARKER_TOKEN_RE = re.compile(r"\[([^\]]+)\]")
ALIAS_TOKEN_RE = re.compile(r"^@(.+)$")


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise AppError(
            f"required artifact is missing: {path.name}",
            code=4,
            category="prerequisite",
            diagnostics=[Diagnostic("artifact_missing", "required artifact is missing", str(path))],
        ) from error
    except UnicodeDecodeError as error:
        raise AppError(
            f"artifact is not UTF-8: {path.name}",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("artifact_encoding", "artifact must be UTF-8", str(path))],
        ) from error


def _document_title(path: Path, root: Path) -> tuple[str, SourceRef]:
    for number, line in enumerate(_read_lines(path), start=1):
        match = TITLE_RE.fullmatch(line)
        if match:
            title = " ".join(match.group(1).split())
            if title:
                return title, SourceRef(_relative(root, path), number)
    raise AppError(
        f"{path.name} requires a level-one Markdown title",
        code=2,
        category="usage",
        diagnostics=[Diagnostic("artifact_title", "expected '# Title'", str(path))],
    )


def _extract_assignee_alias(raw_rest: str, identifier: str, path: Path, line: int) -> str | None:
    """Extract at most one ``[@alias]`` marker from a task's leading markers.

    Doc "Parsing de artefactos": the annotation lives among the leading
    ``[...]`` markers after the checkbox (e.g. ``[US1] [@facu]``). Must run
    before ``LEADING_MARKERS_RE.sub`` strips those markers from the title, or
    the alias would be silently discarded along with them. Two or more
    ``[@alias]`` markers on one line is a parse error, not a "last one wins".
    """

    markers_match = LEADING_MARKERS_RE.match(raw_rest)
    if not markers_match:
        return None
    aliases = [
        alias_match.group(1)
        for token in MARKER_TOKEN_RE.findall(markers_match.group(0))
        for alias_match in (ALIAS_TOKEN_RE.match(token),)
        if alias_match
    ]
    if len(aliases) > 1:
        raise AppError(
            f"task {identifier} declares more than one [@alias] assignee marker",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("task_assignee_duplicate", "a task may declare at most one [@alias] marker", str(path), line)],
        )
    return aliases[0] if aliases else None


def _parse_tasks(path: Path, root: Path) -> tuple[Phase, ...]:
    phases: list[Phase] = []
    phase_numbers: set[int] = set()
    task_ids: set[str] = set()
    current_number: int | None = None
    current_title: str | None = None
    current_source: SourceRef | None = None
    current_tasks: list[Task] = []

    def finish_phase() -> None:
        nonlocal current_number, current_title, current_source, current_tasks
        if current_number is not None and current_title is not None and current_source is not None:
            phases.append(Phase(current_number, current_title, current_source, tuple(current_tasks)))
        current_number = None
        current_title = None
        current_source = None
        current_tasks = []

    for number, line in enumerate(_read_lines(path), start=1):
        phase_match = PHASE_RE.fullmatch(line)
        if phase_match:
            finish_phase()
            phase_number = int(phase_match.group(1))
            phase_title = " ".join((phase_match.group(2) or "").split())
            if not phase_title:
                raise AppError(
                    f"phase {phase_number} needs a title",
                    code=2,
                    category="usage",
                    diagnostics=[Diagnostic("phase_title", "phase title is required", str(path), number)],
                )
            if phase_number in phase_numbers:
                raise AppError(
                    f"duplicate phase {phase_number}",
                    code=2,
                    category="usage",
                    diagnostics=[Diagnostic("phase_duplicate", "phase number must be unique", str(path), number)],
                )
            phase_numbers.add(phase_number)
            current_number = phase_number
            current_title = phase_title
            current_source = SourceRef(_relative(root, path), number)
            continue
        task_match = TASK_RE.fullmatch(line)
        if not task_match:
            continue
        if current_number is None:
            raise AppError(
                "task is not inside a Phase heading",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("task_phase", "each Txxx task needs one Phase", str(path), number)],
            )
        identifier = task_match.group(2)
        if identifier in task_ids:
            raise AppError(
                f"duplicate task identifier {identifier}",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("task_duplicate", "task identifier must be unique", str(path), number)],
            )
        task_ids.add(identifier)
        # TASK_RE's optional dash/colon group only ever consumes a literal
        # "-"/":" separator, never a bare leading space, so group(3) can
        # start with one extra space before a marker run (e.g. "T004 [@x]
        # Title"). Strip it before matching LEADING_MARKERS_RE, which is
        # anchored at the start of the string, or a marker run preceded by
        # that space would neither be recognized as an alias nor stripped
        # from the title.
        raw_rest = task_match.group(3).lstrip()
        assignee_alias = _extract_assignee_alias(raw_rest, identifier, path, number)
        title = LEADING_MARKERS_RE.sub("", raw_rest).strip()
        title = " ".join(title.split())
        if not title:
            raise AppError(
                f"task {identifier} needs a title",
                code=2,
                category="usage",
                diagnostics=[Diagnostic("task_title", "task title is required", str(path), number)],
            )
        current_tasks.append(
            Task(
                identifier=identifier,
                title=title,
                completed=task_match.group(1).lower() == "x",
                source=SourceRef(_relative(root, path), number),
                assignee_alias=assignee_alias,
            )
        )
    finish_phase()
    if not phases:
        raise AppError(
            "tasks.md contains no Phase headings",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("phase_missing", "expected '## Phase N: Title'", str(path))],
        )
    if not task_ids:
        raise AppError(
            "tasks.md contains no Txxx tasks",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("task_missing", "expected task checkboxes with Txxx identifiers", str(path))],
        )
    return tuple(phases)


def parse_feature(root: Path, feature_dir: Path) -> Feature:
    """Parse one feature without changing any artifact."""

    match = FEATURE_RE.fullmatch(feature_dir.name)
    if not match:
        raise AppError(
            f"feature directory must match NNN-name: {feature_dir.name}",
            code=2,
            category="usage",
            diagnostics=[Diagnostic("feature_directory", "invalid feature directory name", str(feature_dir))],
        )
    identifier = match.group(1)
    title, spec_source = _document_title(feature_dir / "spec.md", root)
    plan_title, plan_source = _document_title(feature_dir / "plan.md", root)
    phases = _parse_tasks(feature_dir / "tasks.md", root)
    return Feature(
        identifier=identifier,
        title=title,
        spec_source=spec_source,
        plan_title=plan_title,
        plan_source=plan_source,
        phases=phases,
    )

