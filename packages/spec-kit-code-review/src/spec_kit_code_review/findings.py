"""Findings: strict validation, normalization, and the canonical order.

Doc "Findings y veredicto". Everything in this module treats its input as
**untrusted**. The findings arrive as a JSON file produced by a reviewing agent
that has just read a packet full of the candidate's own text, so a finding is a
plausible carrier for whatever that text was trying to say: a path that escapes
the repository, a line range pointing anywhere, a `content` that closes a fence
and opens a section of its own, a severity nobody defined.

Three separate defences, in order:

1. **Schema**: field names, types, ranges and enumerations, with unknown keys
   refused rather than ignored -- an unknown key is either a different schema
   (so the rest cannot be trusted either) or an attempt to reach a field this
   version does not validate.
2. **Reality**: the path must exist at the head commit and the range must fall
   inside the file. A finding that fails this is discarded with a diagnostic; it
   is a hallucination and must never reach GitHub.
3. **Containment**: every string that will be rendered goes through the packet's
   own machinery before it is written to evidence or to a comment body.

The order of `id` is the contract's full canonical key --
``(path, start_line, end_line, severity, category, title, sha256(content))`` --
compared as UTF-8 bytes, because two findings can legitimately share a path, a
line and a severity, and an ambiguous order would make the golden unstable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .anchors import HunkMap, file_line_counts
from .errors import EXIT_USAGE, AppError, Diagnostic
from .git import Git, validate_repository_relative_path
from .packet import code_span, visible


SEVERITIES: tuple[str, ...] = ("blocking", "major", "minor", "nit", "info")
CATEGORIES: tuple[str, ...] = (
    "correctness",
    "security",
    "contract",
    "delivery",
    "tests",
    "maintainability",
    "style",
)
RULE_SOURCES: tuple[str, ...] = ("repo", "repo-candidate", "system", "packet", "sdd")
SIDES: tuple[str, ...] = ("RIGHT", "LEFT")

REQUIRED_FIELDS: tuple[str, ...] = ("path", "start_line", "end_line", "severity", "category", "title", "content")
OPTIONAL_FIELDS: tuple[str, ...] = (
    "id",
    "side",
    "existing_code",
    "suggestion_code",
    "rule_source",
    "sdd_reference",
    "anchorable",
)
KNOWN_FIELDS: frozenset[str] = frozenset(REQUIRED_FIELDS + OPTIONAL_FIELDS)

# Bounds, not rejections: an over-long field is far more likely to be a verbose
# reviewer than an attack, and losing a real finding costs more than trimming
# it. What is *cut* is always reported.
MAX_TITLE_CHARS = 200
MAX_CONTENT_CHARS = 20000
MAX_CODE_CHARS = 20000
MAX_REFERENCE_CHARS = 300
MAX_FINDINGS = 500


@dataclass
class Finding:
    """One normalized finding, with everything the later stages need decided."""

    path: str
    start_line: int
    end_line: int
    severity: str
    category: str
    title: str
    content: str
    side: str = "RIGHT"
    existing_code: str | None = None
    suggestion_code: str | None = None
    rule_source: str | None = None
    sdd_reference: str | None = None
    anchorable: bool = False
    identifier: str = ""
    degraded_reason: str | None = None

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def order_key(self) -> tuple[bytes, int, int, bytes, bytes, bytes, bytes, bytes]:
        """The contract's canonical order, compared as UTF-8 bytes.

        Severity and category are compared **as strings**, not by rank: the
        contract says byte comparison, and a rank would silently reorder the
        golden the day a severity is added.

        The eighth component is this module's own: the contract's seven can
        still tie -- two findings identical in all of them but differing in
        `side`, `rule_source` or `suggestion_code` are possible -- and a tie
        there would leave the order to the input's, which is not an order at
        all. The digest of the whole finding breaks it deterministically.
        """

        return (
            self.path.encode("utf-8"),
            self.start_line,
            self.end_line,
            self.severity.encode("utf-8"),
            self.category.encode("utf-8"),
            self.title.encode("utf-8"),
            self.content_sha256.encode("utf-8"),
            self.identity_sha256.encode("utf-8"),
        )

    @property
    def identity_sha256(self) -> str:
        """A digest of everything the finding declares, minus its assigned id."""

        payload = {key: value for key, value in self.as_dict().items() if key != "id"}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.identifier,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "side": self.side,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "anchorable": self.anchorable,
        }
        for name in ("existing_code", "suggestion_code", "rule_source", "sdd_reference"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        if self.degraded_reason:
            payload["degraded_reason"] = self.degraded_reason
        return payload


@dataclass
class FindingSet:
    """The normalized findings, what was discarded, and why."""

    findings: tuple[Finding, ...] = ()
    discarded: tuple[dict[str, Any], ...] = ()
    diagnostics: list[Diagnostic] = field(default_factory=list)
    source_sha256: str = ""

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity == "blocking")

    @property
    def anchorable(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.anchorable)

    @property
    def degraded(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if not item.anchorable)

    def by_severity(self) -> dict[str, int]:
        counts = {severity: 0 for severity in SEVERITIES}
        for item in self.findings:
            counts[item.severity] += 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256,
            "count": len(self.findings),
            "by_severity": self.by_severity(),
            "anchorable": len(self.anchorable),
            "degraded": len(self.degraded),
            "findings": [item.as_dict() for item in self.findings],
            "discarded": list(self.discarded),
        }


def _usage(message: str, code: str, detail: str) -> AppError:
    """Doc "run": an invalid findings document is exit code 2, and the session
    stays open so the operator can fix the file and retry."""

    return AppError(message, code=EXIT_USAGE, diagnostics=[Diagnostic(code, detail)])


def load_document(path: Path) -> tuple[list[Any], str]:
    """Read the findings file, refusing anything that is not the agreed shape."""

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise _usage(
            f"the findings file could not be read: {path}",
            "findings_unreadable",
            str(error),
        ) from error
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _usage(
            "the findings file is not valid UTF-8",
            "findings_not_utf8",
            f"decoding failed at byte {error.start}; the packet asks for UTF-8 JSON",
        ) from error
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        # Truncated output is the common case -- an agent that ran out of budget
        # mid-write -- so the message says where it broke rather than "invalid".
        raise _usage(
            "the findings file is not valid JSON",
            "findings_invalid_json",
            f"{error.msg} at line {error.lineno} column {error.colno}",
        ) from error

    if isinstance(document, list):
        raise _usage(
            "the findings file must be an object with a `findings` array",
            "findings_shape",
            'the packet asks for {"findings": [...]}; a bare array is ambiguous about what else the document claims',
        )
    if not isinstance(document, dict):
        raise _usage(
            "the findings file must be a JSON object",
            "findings_shape",
            f"found {type(document).__name__}",
        )
    if "findings" not in document:
        raise _usage(
            "the findings file has no `findings` array",
            "findings_shape",
            'the packet asks for {"findings": [...]}',
        )
    entries = document["findings"]
    if not isinstance(entries, list):
        raise _usage(
            "`findings` must be an array",
            "findings_shape",
            f"found {type(entries).__name__}",
        )
    if len(entries) > MAX_FINDINGS:
        raise _usage(
            f"the findings file declares {len(entries)} findings, over the {MAX_FINDINGS} this command accepts",
            "findings_too_many",
            "a review with more findings than this is not a review a human can act on; split the candidate instead",
        )
    return entries, digest


def _require_string(
    entry: Mapping[str, Any],
    name: str,
    *,
    index: int,
    limit: int,
    allow_empty: bool = False,
    truncated: list[str] | None = None,
) -> str:
    value = entry.get(name)
    if not isinstance(value, str):
        raise _usage(
            f"finding #{index}: `{name}` must be a string",
            "findings_field_type",
            f"found {type(value).__name__}",
        )
    if not allow_empty and not value.strip():
        raise _usage(f"finding #{index}: `{name}` is empty", "findings_field_empty", "an empty field says nothing")
    if len(value) > limit:
        # Recorded here rather than inferred later from `len(value) == limit`,
        # which reports a field that merely happens to be exactly at the limit
        # and misses one truncated to a shorter length by a future rule.
        if truncated is not None:
            truncated.append(name)
        return value[:limit]
    return value


def _require_enum(entry: Mapping[str, Any], name: str, allowed: Sequence[str], *, index: int) -> str:
    value = entry.get(name)
    if value not in allowed:
        raise _usage(
            f"finding #{index}: `{name}` is not one of {', '.join(allowed)}",
            "findings_field_enum",
            f"found {value!r}",
        )
    return str(value)


def _require_line(entry: Mapping[str, Any], name: str, *, index: int) -> int:
    value = entry.get(name)
    # `bool` is an `int` in Python, and `True` as a line number is a bug, not a
    # line 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _usage(
            f"finding #{index}: `{name}` must be an integer",
            "findings_field_type",
            f"found {type(value).__name__}",
        )
    if value < 1:
        raise _usage(
            f"finding #{index}: `{name}` must be 1 or greater",
            "findings_field_range",
            f"found {value}",
        )
    return value


def validate_entry(entry: Any, *, index: int, truncated: list[str] | None = None) -> Finding:
    """One entry, validated field by field. Anything unexpected is exit code 2.

    ``truncated`` collects the names of fields that were cut to their limit, so
    the caller can report exactly what was trimmed instead of guessing from a
    length.
    """

    if not isinstance(entry, dict):
        raise _usage(
            f"finding #{index} is not an object",
            "findings_field_type",
            f"found {type(entry).__name__}",
        )
    unknown = sorted(set(entry) - KNOWN_FIELDS)
    if unknown:
        raise _usage(
            f"finding #{index} carries unknown field(s): {', '.join(unknown)}",
            "findings_unknown_field",
            "unknown keys are refused rather than ignored: either the document follows a different schema, in which "
            "case the rest of it cannot be trusted either, or something is trying to reach a field this version does "
            "not validate",
        )
    missing = [name for name in REQUIRED_FIELDS if name not in entry]
    if missing:
        raise _usage(
            f"finding #{index} is missing: {', '.join(missing)}",
            "findings_field_missing",
            "every required field of the packet's schema must be present",
        )

    path = _require_string(entry, "path", index=index, limit=4096)
    try:
        validate_repository_relative_path(path)
    except AppError as error:
        # The same validation the engine's paths go through: traversal, absolute
        # paths and a leading dash are refused identically wherever a path comes
        # from, because the danger is in the value, not in its provenance.
        raise _usage(
            f"finding #{index}: `path` is not a repository-relative path",
            "findings_path_invalid",
            f"{visible(path)}: {error}",
        ) from error

    start_line = _require_line(entry, "start_line", index=index)
    end_line = _require_line(entry, "end_line", index=index)
    if end_line < start_line:
        raise _usage(
            f"finding #{index}: `end_line` is before `start_line`",
            "findings_field_range",
            f"{start_line}..{end_line}",
        )

    side = str(entry.get("side", "RIGHT"))
    if side not in SIDES:
        raise _usage(
            f"finding #{index}: `side` must be RIGHT or LEFT",
            "findings_field_enum",
            f"found {side!r}",
        )
    rule_source = entry.get("rule_source")
    if rule_source is not None and rule_source not in RULE_SOURCES:
        raise _usage(
            f"finding #{index}: `rule_source` is not one of {', '.join(RULE_SOURCES)}",
            "findings_field_enum",
            f"found {rule_source!r}",
        )
    anchorable = entry.get("anchorable")
    if anchorable is not None and not isinstance(anchorable, bool):
        raise _usage(
            f"finding #{index}: `anchorable` must be a boolean",
            "findings_field_type",
            f"found {type(anchorable).__name__}",
        )

    return Finding(
        path=path,
        start_line=start_line,
        end_line=end_line,
        severity=_require_enum(entry, "severity", SEVERITIES, index=index),
        category=_require_enum(entry, "category", CATEGORIES, index=index),
        # The title is a single line by construction: it is rendered into list
        # items and table rows, and a newline in it would be structure.
        title=" ".join(visible(_require_string(entry, "title", index=index, limit=MAX_TITLE_CHARS, truncated=truncated)).split()),
        content=_require_string(entry, "content", index=index, limit=MAX_CONTENT_CHARS, truncated=truncated),
        side=side,
        existing_code=(
            _require_string(entry, "existing_code", index=index, limit=MAX_CODE_CHARS, allow_empty=True)
            if entry.get("existing_code") is not None
            else None
        ),
        suggestion_code=(
            _require_string(entry, "suggestion_code", index=index, limit=MAX_CODE_CHARS, allow_empty=True)
            if entry.get("suggestion_code") is not None
            else None
        ),
        rule_source=str(rule_source) if rule_source is not None else None,
        sdd_reference=(
            " ".join(
                visible(
                    _require_string(entry, "sdd_reference", index=index, limit=MAX_REFERENCE_CHARS, allow_empty=True)
                ).split()
            )
            or None
            if entry.get("sdd_reference") is not None
            else None
        ),
    )


def normalize(
    entries: Sequence[Any],
    *,
    git: Git,
    head_commit: str,
    hunks: HunkMap,
    merge_base: str | None = None,
    source_sha256: str = "",
) -> FindingSet:
    """Validate, discard the unlocatable, anchor the rest, and assign ids.

    **Each finding is checked against the frame it declares.** A `side: RIGHT`
    finding is numbered against the head; a `side: LEFT` finding is numbered
    against the merge base, because the lines it is about are the ones the
    candidate *deleted*. Checking a LEFT finding against the head discards
    exactly the findings the contract calls legitimate -- a file the candidate
    removed entirely, or a deleted region past the new end of the file -- and it
    discards them silently, as `no-blocking-findings`, exit code 0.
    """

    diagnostics: list[Diagnostic] = []
    validated: list[Finding] = []
    for index, raw in enumerate(entries, start=1):
        cut: list[str] = []
        finding = validate_entry(raw, index=index, truncated=cut)
        validated.append(finding)
        if cut:
            diagnostics.append(
                Diagnostic(
                    "findings_truncated_field",
                    f"{finding.path}:{finding.start_line}: {', '.join(sorted(set(cut)))} exceeded the limit and was "
                    f"cut ({MAX_TITLE_CHARS} characters for a title, {MAX_CONTENT_CHARS} for content)",
                    finding.path,
                    severity="warning",
                )
            )

    frames: dict[str, str] = {"RIGHT": head_commit}
    if merge_base:
        frames["LEFT"] = merge_base
    else:
        # Without a merge base there is no frame a LEFT finding can be checked
        # against. It is kept and degraded -- never discarded on the strength of
        # a check that could not be performed.
        diagnostics.append(
            Diagnostic(
                "findings_left_unverified",
                "no merge base was supplied, so findings about deleted lines could not be checked against the base "
                "they are numbered in; they are kept and reported in the summary",
                severity="warning",
            )
        )

    counts: dict[tuple[str, str], int | None] = {}
    for side, ref in frames.items():
        paths = [finding.path for finding in validated if finding.side == side]
        if paths:
            counts.update({(side, path): value for path, value in file_line_counts(git, ref, paths).items()})

    kept: list[Finding] = []
    discarded: list[dict[str, Any]] = []
    for finding in validated:
        ref = frames.get(finding.side)
        if ref is None:
            kept.append(finding)
            continue
        frame = "head commit" if finding.side == "RIGHT" else "merge base"
        lines = counts.get((finding.side, finding.path))
        if lines is None:
            discarded.append(_discard(finding, f"the path does not exist at the {frame}"))
            continue
        # A file with no trailing newline still has its last line; a finding one
        # past the end is out of the file either way.
        if finding.end_line > max(lines, 1):
            discarded.append(
                _discard(
                    finding,
                    f"lines {finding.start_line}-{finding.end_line} are outside the file at the {frame} "
                    f"({lines} lines)",
                )
            )
            continue
        kept.append(finding)

    for entry in discarded:
        diagnostics.append(
            Diagnostic(
                "finding_discarded",
                f"{entry['path']}:{entry['start_line']}-{entry['end_line']}: {entry['reason']}. "
                "A finding that does not exist in the candidate is a hallucination and never reaches GitHub.",
                entry["path"],
                severity="warning",
            )
        )

    for finding in kept:
        if finding.side == "LEFT":
            # Doc "Modelo de finding": a finding about a deleted line is
            # legitimate -- removing a validation is a real finding -- but
            # anchoring on LEFT needs an exact diff position and is the most
            # common source of GitHub 422s. It degrades to the summary instead.
            finding.anchorable = False
            finding.degraded_reason = "side: LEFT is never anchored inline; it is reported in the summary"
            continue
        hunk = hunks.anchor(finding.path, finding.start_line, finding.end_line)
        finding.anchorable = hunk is not None
        if hunk is None:
            finding.degraded_reason = "the range is not inside a hunk of the candidate's diff"

    ordered = sorted(kept, key=lambda item: item.order_key())
    for position, finding in enumerate(ordered, start=1):
        finding.identifier = f"F{position:03d}"

    degraded = [finding for finding in ordered if not finding.anchorable]
    if degraded:
        diagnostics.append(
            Diagnostic(
                "findings_degraded",
                f"{len(degraded)} finding(s) cannot be anchored inline and will be reported in the summary",
                severity="info",
            )
        )
    return FindingSet(
        findings=tuple(ordered),
        discarded=tuple(discarded),
        diagnostics=diagnostics,
        source_sha256=source_sha256,
    )


def _discard(finding: Finding, reason: str) -> dict[str, Any]:
    return {
        "path": finding.path,
        "start_line": finding.start_line,
        "end_line": finding.end_line,
        "severity": finding.severity,
        "title": finding.title,
        "reason": reason,
    }


def render_markdown(findings: Sequence[Finding], *, suffix: str) -> str:
    """The human render of the findings, with every field contained.

    The text comes from an agent that has just read the candidate's own content,
    so it is quoted with the packet's machinery rather than interpolated: the
    same rule that governs the packet governs everything derived from it.
    """

    from .packet import contain

    lines = ["# Review findings", ""]
    if not findings:
        return "\n".join(lines + ["_No findings._", ""])
    lines.extend(["| id | severity | category | file | lines | anchored |", "| --- | --- | --- | --- | --- | --- |"])
    for finding in findings:
        lines.append(
            f"| {finding.identifier} | {finding.severity} | {finding.category} | "
            f"{code_span(finding.path, table=True)} | {finding.start_line}-{finding.end_line} | "
            f"{'inline' if finding.anchorable else 'summary'} |"
        )
    for finding in findings:
        lines.extend(
            [
                "",
                f"## {finding.identifier} — {code_span(finding.title)}",
                "",
                f"- file: {code_span(finding.path)} lines {finding.start_line}-{finding.end_line} ({finding.side})",
                f"- severity: {finding.severity}; category: {finding.category}",
            ]
        )
        if finding.rule_source:
            lines.append(f"- rule_source: {finding.rule_source}")
        if finding.sdd_reference:
            lines.append(f"- sdd_reference: {code_span(finding.sdd_reference)}")
        if finding.degraded_reason:
            lines.append(f"- not anchored inline: {finding.degraded_reason}")
        block = contain(finding.content, suffix=suffix, origin=f"finding {finding.identifier}", escape_on_collision=True)
        lines.extend(["", block.text])
        if finding.suggestion_code:
            suggestion = contain(
                finding.suggestion_code,
                suffix=suffix,
                origin=f"the suggested code of finding {finding.identifier}",
                escape_on_collision=True,
            )
            lines.extend(["", "Suggested code:", "", suggestion.text])
    return "\n".join(lines) + "\n"
