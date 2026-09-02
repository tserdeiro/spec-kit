"""Versioned adapter for ``ocr delegate``: invocation, verbatim output, parsing.

Doc "Motor de revision: OCR en delegation mode". Delegation mode is the whole
point of this engine: ``ocr`` instantiates no LLM client, needs no API key, and
answers only the two deterministic questions -- **which files are in scope** and
**which rules apply to them**. The judgement stays with the host agent.

Two properties of this module matter more than its size:

- **The output is Markdown on stdout, not an API.** "Riesgos abiertos" says so
  explicitly: a minor upstream change can break the parser. So the raw output is
  preserved verbatim, the parser is defensive about cosmetics and strict about
  shape, and anything it does not recognize is exit code 9 with the raw output
  referenced -- never a guessed scope. Guessing which files are under review is
  the one failure mode that would silently shrink a review.
- **The output is untrusted content.** It is candidate-influenced (paths, rule
  text) and reaches logs, evidence and, in a later stage, the packet. Every path
  is validated as repository-relative before it propagates anywhere, and every
  message this module raises goes through redaction.

The shapes below are derived from the contract's description of the output.
Whether they match the pinned binary byte for byte is what
``tests/conformance/test_real_ocr.py`` exists to prove; until a person runs it
against the real ``ocr``, both this parser and the fake are **unverified**.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import EXIT_ENGINE, AppError, Diagnostic
from .evidence import harden_directories
from .git import validate_repository_relative_path
from .process import CommandResult, run_command
from .redaction import redact_text


# Bumped whenever the parsing contract changes, and recorded in the evidence so
# a stored session says which adapter read its raw output.
# Bumped when the shape this adapter reads changes. Version 2 is the first one
# verified against the real binary: open-code-review v1.8.3 (80a579466). What
# changed is recorded in tests/conformance/evidence/real-ocr.md.
ADAPTER_VERSION = "2"

OCR_CONFIG_ENV = "OCR_CONFIG_PATH"

# Doc "Aislamiento de la configuracion de OCR": in delegate mode no provider and
# no model are needed, so the operator's personal ~/.opencodereview/config.json
# only adds variance between machines. This minimal document replaces it. It
# carries no telemetry key in either direction: the extension never enables OCR
# telemetry, and never force-disables a decision the operator made.
MINIMAL_CONFIG: dict[str, Any] = {"language": "English"}

_HEADER_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*{1,2}|_{1,2})?(?P<key>mode|from|to|merge[ _-]?base|repo(?:sitory)?"
    r"|total[ _-]?insertions|total[ _-]?deletions)"
    r"(?:\*{1,2}|_{1,2})?\s*[:=]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
# The real binary prints its metadata as list items *inside* the file section,
# before the entries (verified against v1.8.3). They are recognized by their
# key, and only when the line carries no delimited path token -- so a file
# genuinely named `mode` still reports as the file it is.
_METADATA_KEYS = frozenset({"mode", "from", "to", "merge_base", "repo", "repository", "total_insertions", "total_deletions"})
# An entry the engine struck through: the wrapper spans the whole item, dash
# included (`~~- `path` [status] (excluded: reason)~~`). Recognized only in that
# whole-item shape -- `~~` is not accepted as a delimiter anywhere it pleases.
_STRIKETHROUGH_ITEM_RE = re.compile(r"^\s*~~(?P<body>(?:[-*+]|\d+[.)])\s+.+?)~~\s*$")
# A metadata line is only ever *text*; an entry names its path in a backticked
# or quoted token. Emphasis is not part of that test: both shapes of this
# engine's own metadata use it (`- **Mode**: range`, `- mode: range`), so
# treating bold as a path delimiter here would lose the metadata entirely.
_QUOTED_TOKEN_RE = re.compile(r"^\s*[`\"]")
_HEADING_RE = re.compile(r"^\s{0,3}(?P<hashes>#{1,6})\s*(?P<text>.*?)\s*#*\s*$")
_FILES_HEADING_TEXT_RE = re.compile(r"\b(files?|scope|selected|changes?|excluded|skipped)\b", re.IGNORECASE)
# The state marker is only ever read from what *follows* the path token, never
# from the whole line: a file legitimately named `excluded.py` or `filtered.go`
# must not remove itself from the review.
_EXCLUDED_RE = re.compile(r"\b(excluded?|skipp?ed|ignored|filtered)\b", re.IGNORECASE)
_REASON_RE = re.compile(
    r"\b(?:excluded?|skipp?ed|ignored|filtered)\b\s*(?:by|because|due to)?\s*[:\-—–(\[]?\s*(?P<reason>[^)\]]+)",
    re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(?P<body>.+?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")
_CODE_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
# A delimited path wins over everything else on the line.
_DELIMITED_RE = re.compile(r"^\s*(?:`(?P<token>[^`]+)`|\"(?P<q>[^\"]+)\"|~~(?P<s>[^~]+)~~|\*\*(?P<b>[^*]+)\*\*)")
# Otherwise the path ends at the first explicit separator.
_SEPARATOR_RE = re.compile(r"\s+[—–]\s+|\s+[-]\s+|\s*[:(\[]\s*|\s{2,}")
# What may legitimately follow a delimited path: an annotation, never more path.
_ANNOTATION_START_RE = re.compile(r"^\s*(?:[—–:|(\[]|-\s|$)")
# A token made only of decoration is not a path.
_DECORATION_ONLY = "`~*_ \t"
# Markdown decoration comes in matching pairs, so it is unwrapped once -- never
# stripped character by character, which would rename `__init__.py`.
_WRAPPERS: tuple[str, ...] = ("```", "``", "`", "***", "**", "*", "___", "__", "_", "~~")


@dataclass(frozen=True)
class ScopeEntry:
    """One file the engine considered, and whether it is under review."""

    path: str
    included: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "state": "included" if self.included else "excluded", "reason": self.reason}


@dataclass(frozen=True)
class PreviewResult:
    """The deterministic file selection, plus the raw output it was read from."""

    raw: str
    entries: tuple[ScopeEntry, ...]
    mode: str | None = None
    from_ref: str | None = None
    to_ref: str | None = None
    merge_base: str | None = None
    adapter_version: str = ADAPTER_VERSION
    # Set when this extension deliberately reviews a subset of what the engine
    # reported; the packet prints it so a narrowed scope is never silent.
    narrowing: str = ""

    @property
    def included_paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.entries if entry.included)

    @property
    def excluded(self) -> tuple[ScopeEntry, ...]:
        return tuple(entry for entry in self.entries if not entry.included)

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "mode": self.mode,
            "from": self.from_ref,
            "to": self.to_ref,
            "merge_base": self.merge_base,
            "files": [entry.as_dict() for entry in self.entries],
            "included_count": len(self.included_paths),
            "excluded_count": len(self.excluded),
        }


@dataclass(frozen=True)
class RuleAssignment:
    """The rules the engine resolved for one path."""

    path: str
    rules: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "rules": list(self.rules)}


@dataclass(frozen=True)
class RuleResolution:
    """The resolved rule cascade for the selected files, and its raw output."""

    raw: str
    assignments: tuple[RuleAssignment, ...]
    adapter_version: str = ADAPTER_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "assignments": [assignment.as_dict() for assignment in self.assignments],
        }


@dataclass
class Invocation:
    """One external engine call, kept for the evidence."""

    argv: tuple[str, ...]
    returncode: int
    stderr: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"argv": list(self.argv), "returncode": self.returncode}


class Ocr:
    """Every ``ocr`` invocation this extension makes, in one auditable place."""

    def __init__(
        self,
        executable: Path | str,
        *,
        timeout: int = 300,
        config_path: Path | None = None,
        environment: Mapping[str, str] | None = None,
        on_stderr: Callable[[str], None] | None = None,
    ) -> None:
        self.executable = str(executable)
        self.timeout = timeout
        self.config_path = config_path
        self._environment = dict(environment) if environment is not None else None
        self._on_stderr = on_stderr
        self.invocations: list[Invocation] = []
        self.stderr_log: list[str] = []

    # -- invocation ------------------------------------------------------

    def _environment_for_call(self) -> dict[str, str]:
        """The deliberately minimal environment the engine is run in.

        Passing only ``SPECKIT_CODE_REVIEW_*`` would leave the engine without
        ``PATH`` or ``HOME``: the real ``ocr`` is an npm wrapper whose shebang is
        ``#!/usr/bin/env node``, so it would not even start. Passing the whole
        environment through would hand candidate-adjacent state to a subprocess
        for no reason. So the set is explicit, and every entry earns its place:
        ``PATH`` and ``HOME`` for the interpreter and its own config, ``TMPDIR``
        for scratch files, the locale so output is stable, ``SystemRoot`` and
        ``USERPROFILE`` because Windows processes do not start without them.

        No model credential and no telemetry switch is ever added -- in either
        direction. ``OCR_CONFIG_PATH`` is the one engine variable this extension
        sets, and only in delegate mode.
        """

        source = dict(self._environment if self._environment is not None else os.environ)
        environment: dict[str, str] = {}
        for name in ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SystemRoot", "USERPROFILE"):
            value = source.get(name)
            if value:
                environment[name] = value
        environment.setdefault("PATH", os.defpath)
        if self.config_path is not None:
            # Doc "Aislamiento de la configuracion de OCR": delegate mode reads
            # the generated minimal config, never the operator's personal one.
            environment[OCR_CONFIG_ENV] = str(self.config_path)
        return environment

    def run(self, *arguments: str, cwd: Path | None = None) -> CommandResult:
        """Run ``ocr`` by argv, never through a shell, and never in the background."""

        for argument in arguments:
            if argument in ("-B", "--background"):
                raise AppError(
                    "the review engine is never run in the background",
                    code=EXIT_ENGINE,
                    diagnostics=[Diagnostic("engine_background", "the review needs synchronous, deterministic output")],
                )
        result = run_command(
            [self.executable, *arguments],
            cwd=cwd,
            env=self._environment_for_call(),
            timeout=self.timeout,
        )
        self.invocations.append(Invocation(argv=result.argv, returncode=result.returncode, stderr=result.stderr))
        if result.stderr.strip():
            self.stderr_log.append(f"$ {' '.join(result.argv)}\n{redact_text(result.stderr)}")
            # The stderr of a *failed* invocation is the most useful thing the
            # evidence can hold, so it is handed over as it arrives rather than
            # after a later step that may never run.
            if self._on_stderr is not None:
                self._on_stderr("\n".join(self.stderr_log))
        return result

    def version(self) -> str:
        result = self.run("--version")
        if not result.ok:
            raise _engine_failure("`ocr --version` did not succeed", result)
        return (result.stdout or result.stderr or "").strip()

    # -- delegation ------------------------------------------------------

    def delegate_preview(
        self,
        repository: Path,
        *,
        from_ref: str | None = None,
        to_ref: str | None = None,
        rule_path: Path | None = None,
        on_raw: Callable[[str], None] | None = None,
    ) -> PreviewResult:
        """Ask the engine which files are under review.

        Full, already validated SHAs only -- never branch names -- and
        ``--from <merge_base>`` so the scope is the candidate's own work rather
        than whatever the base branch has picked up since. Omitting the range
        entirely is the workspace mode the pre-pull-request review uses.
        """

        arguments = ["delegate", "preview", "--repo", str(repository)]
        if (from_ref is None) != (to_ref is None):
            raise AppError(
                "the engine range needs both ends or neither",
                code=EXIT_ENGINE,
                diagnostics=[Diagnostic("engine_range_incomplete", "pass --from and --to together, or omit both")],
            )
        if from_ref is not None and to_ref is not None:
            arguments.extend(["--from", from_ref, "--to", to_ref])
        if rule_path is not None:
            arguments.extend(["--rule", str(rule_path)])

        result = self.run(*arguments)
        # The raw output reaches the evidence *before* it is parsed, so a shape
        # this adapter does not recognize still leaves the operator the bytes to
        # look at -- which is what the exit-9 message points them to.
        if on_raw is not None:
            on_raw(result.stdout)
        if not result.ok:
            raise _engine_failure("`ocr delegate preview` failed", result)
        return parse_preview(result.stdout)

    def delegate_rule(
        self,
        repository: Path,
        paths: Sequence[str],
        *,
        rule_path: Path | None = None,
        batch_size: int = 100,
        on_raw: Callable[[str], None] | None = None,
    ) -> RuleResolution:
        """Ask the engine which rules apply to exactly the selected files.

        Long file lists are split into fixed batches (``engine.rule_batch_size``)
        and the outputs concatenated in batch order -- which is the deterministic
        order ``preview`` produced, so the result does not depend on the batch
        size.
        """

        if not paths:
            return RuleResolution(raw="", assignments=())
        size = max(int(batch_size or 100), 1)
        raw_chunks: list[str] = []
        assignments: list[RuleAssignment] = []
        for start in range(0, len(paths), size):
            batch = list(paths[start : start + size])
            arguments = ["delegate", "rule", "--repo", str(repository)]
            if rule_path is not None:
                arguments.extend(["--rule", str(rule_path)])
            # Doc "Inyeccion de opciones": paths go after every flag, and each
            # one was validated as a repository-relative path before getting
            # here, so none can look like an option.
            # `--` closes the flag list: with it, a candidate file named `--rule`
            # is a path, not a second flag that would redirect the criteria.
            arguments.append("--")
            arguments.extend(batch)
            result = self.run(*arguments)
            raw_chunks.append(result.stdout)
            if on_raw is not None:
                on_raw("\n".join(raw_chunks))
            if not result.ok:
                raise _engine_failure("`ocr delegate rule` failed", result)
            assignments.extend(parse_rules(result.stdout, expected_paths=batch).assignments)
        return RuleResolution(raw="\n".join(raw_chunks), assignments=tuple(assignments))


def _engine_failure(message: str, result: CommandResult) -> AppError:
    """Exit code 9 with the engine's stderr captured and redacted."""

    detail = redact_text((result.stderr or result.stdout or "").strip())
    return AppError(
        message,
        code=EXIT_ENGINE,
        diagnostics=[
            Diagnostic(
                "engine_failed",
                f"exit {result.returncode}" + (f": {detail}" if detail else ""),
                result.argv[0] if result.argv else None,
            )
        ],
    )



# -- parsing ---------------------------------------------------------------
#
# Two invariants hold this together, and they are deliberately independent of
# how the engine formats anything:
#
# 1. **Conservation.** Every list item and every table row inside the file
#    section produces exactly one entry. A line that cannot be turned into an
#    entry is exit code 9 -- never a silent discard, which is the failure mode
#    that shrinks a review without saying so.
# 2. **Cross-verification against git** (``verify_scope_against_git``). The set
#    of paths the engine reports must be exactly the set git reports for the
#    same range. This is the only defence that does not depend on the output
#    format at all, so it keeps working when upstream changes it.


def parse_preview(raw: str) -> PreviewResult:
    """Read the file selection out of the engine's Markdown.

    Tolerant about presentation -- bullets, numbering, emphasis, checkboxes,
    tables, heading depth -- and unforgiving about structure. The file section
    must be identifiable, every entry line must yield an entry, and a path that
    cannot be extracted cleanly is a failure rather than an omission.
    """

    if not raw or not raw.strip():
        raise _unparseable("the engine produced no output at all", raw)

    headers: dict[str, str] = {}
    entries: list[ScopeEntry] = []
    section_level: int | None = None
    in_code_fence = False
    saw_files_section = False
    pending_table_header: int | None = None

    for number, line in enumerate(raw.splitlines(), start=1):
        if _CODE_FENCE_RE.match(line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line.strip():
            continue

        heading = _HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group("hashes"))
            if _FILES_HEADING_TEXT_RE.search(heading.group("text")):
                # A files heading opens (or re-opens) the section at its level.
                section_level = level
                saw_files_section = True
                pending_table_header = None
                continue
            if section_level is not None and level > section_level:
                # A *deeper* heading is a sub-grouping inside the file section --
                # by directory, by language -- and must not truncate it.
                continue
            section_level = None
            continue

        header = _HEADER_RE.match(line)
        if header is not None and not _QUOTED_TOKEN_RE.match(_LIST_BODY(line)):
            key = re.sub(r"[ _-]+", "_", header.group("key").strip().lower())
            if key in _METADATA_KEYS:
                # Metadata, wherever the engine chose to print it: v1.8.3 puts
                # it inside the file section, as list items, before the entries.
                headers.setdefault(key, _unwrap(header.group("value").strip()))
                continue

        if section_level is None:
            continue

        if _is_table_separator(line):
            # The row above a `| --- |` separator was the table's header.
            if pending_table_header is not None and entries:
                del entries[pending_table_header]
            pending_table_header = None
            continue

        entry = _parse_scope_line(line, number=number, raw=raw)
        pending_table_header = len(entries) if _TABLE_ROW_RE.match(line) else None
        entries.append(entry)

    if not saw_files_section:
        raise _unparseable(
            "the engine's output has no recognizable file section, so the review scope is unknown",
            raw,
        )

    return PreviewResult(
        raw=raw,
        entries=_deduplicate(entries, raw),
        mode=headers.get("mode"),
        from_ref=headers.get("from"),
        to_ref=headers.get("to"),
        merge_base=headers.get("merge_base"),
    )


def _deduplicate(entries: list[ScopeEntry], raw: str) -> tuple[ScopeEntry, ...]:
    """Collapse repeats, and refuse to choose when they contradict each other."""

    seen: dict[str, ScopeEntry] = {}
    for entry in entries:
        previous = seen.get(entry.path)
        if previous is None:
            seen[entry.path] = entry
            continue
        if previous.included != entry.included:
            raise _unparseable(
                f"the engine reported {entry.path} as both included and excluded; the scope is ambiguous",
                raw,
            )
    return tuple(seen.values())


def _LIST_BODY(line: str) -> str:
    """The body of a list item, or the line itself when it is not one."""

    item = _LIST_ITEM_RE.match(line)
    return item.group("body") if item else line.strip()


def _parse_scope_line(line: str, *, number: int, raw: str) -> ScopeEntry:
    """Turn one entry line into exactly one entry, or fail loudly.

    The path is read as a **delimited token** -- a backticked or quoted span, a
    table cell, or the text up to an explicit separator -- and the state is read
    only from what follows that separator. Scanning the whole line for the word
    "excluded" would make a file called ``excluded.py`` or ``filtered.go``
    vanish from the scope, which a pull request chooses simply by naming a file.
    """

    table = _TABLE_ROW_RE.match(line)
    if table:
        cells = [cell.strip() for cell in table.group("cells").split("|")]
        cells = [cell for cell in cells if cell]
        if not cells:
            raise _unparseable(f"line {number} is a table row with no cells", raw)
        path = _clean_path(cells[0], line=line, number=number, raw=raw)
        rest = " ".join(cells[1:])
        excluded = bool(_EXCLUDED_RE.search(rest))
        return ScopeEntry(path=path, included=not excluded, reason=_reason(rest) if excluded else None)

    struck = _STRIKETHROUGH_ITEM_RE.match(line)
    if struck is not None:
        # Presentation, not structure: v1.8.3 strikes through the whole item for
        # an excluded file. The wrapper is removed and the item inside is parsed
        # exactly like any other, so the state still comes from what follows the
        # path token and never from the decoration around it.
        line = struck.group("body")

    item = _LIST_ITEM_RE.match(line)
    if item is None:
        raise _unparseable(
            f"line {number} of the file section is neither a list item nor a table row: {line.strip()[:80]!r}",
            raw,
        )
    body = item.group("body").strip()
    token, remainder = _split_entry(body)
    path = _clean_path(token, line=line, number=number, raw=raw)
    excluded = bool(_EXCLUDED_RE.search(remainder))
    return ScopeEntry(path=path, included=not excluded, reason=_reason(remainder) if excluded else None)


def _split_entry(body: str) -> tuple[str, str]:
    """Separate the path token from whatever annotates it.

    A delimited path wins outright: ``` `src/excluded.py` ``` is a path, whatever
    the rest of the line says. Otherwise the first explicit separator ends the
    path -- and if there is none, the whole body is the path, because file names
    may contain spaces.
    """

    delimited = _DELIMITED_RE.match(body)
    if delimited:
        token = next(group for group in delimited.groups() if group)
        remainder = body[delimited.end() :]
        if remainder.strip() and not _ANNOTATION_START_RE.match(remainder):
            # `a`b.py` closes its span early: the line could mean two different
            # paths and there is no honest way to choose between them.
            raise _ambiguous(body)
        return token, remainder
    separator = _SEPARATOR_RE.search(body)
    if separator:
        return body[: separator.start()], body[separator.end() :]
    return body, ""


def _reason(text: str) -> str | None:
    match = _REASON_RE.search(text)
    if not match:
        return None
    reason = match.group("reason").strip().strip("`*_ \t:-—–()[]")
    return reason or None


def _clean_path(token: str, *, line: str, number: int, raw: str) -> str:
    """Normalize and validate one reported path, or fail.

    Doc "Contenido no confiable": scope paths are validated as repository
    relative -- no ``..``, no absolute path, no NUL, and no leading ``-`` -- and
    a path that fails validation is a parse failure, never a dropped file.
    """

    text = _unwrap(token).strip().strip("\"'").strip()
    if not text.strip(_DECORATION_ONLY):
        raise _unparseable(
            f"line {number} of the file section has no path in it: {line.strip()[:80]!r}",
            raw,
        )
    try:
        validate_repository_relative_path(text)
    except AppError as error:
        raise AppError(
            f"the engine reported a path this extension refuses to use: {text}",
            code=EXIT_ENGINE,
            diagnostics=[Diagnostic("engine_path_invalid", redact_text(str(error)), text)],
        ) from error
    return text


def _unwrap(token: str) -> str:
    """Remove **one** matching Markdown wrapper, never inner characters.

    A single pass, on purpose: iterating would turn ``__init__`` into ``init``
    and ``_private_`` into ``private``, silently renaming real files.
    """

    text = token.strip()
    for wrapper in _WRAPPERS:
        if len(text) > 2 * len(wrapper) and text.startswith(wrapper) and text.endswith(wrapper):
            return text[len(wrapper) : -len(wrapper)].strip()
    return text


def _is_table_separator(line: str) -> bool:
    table = _TABLE_ROW_RE.match(line)
    if not table:
        return False
    cells = [cell.strip() for cell in table.group("cells").split("|")]
    filled = [cell for cell in cells if cell]
    return bool(filled) and all(set(cell) <= set("-: ") for cell in filled)


def verify_scope_against_git(preview: PreviewResult, changed_paths: Sequence[str]) -> None:
    """Cross-check the reported scope against what git says actually changed.

    This is the invariant that does not care how the engine formats its output,
    and therefore the one that still holds when upstream changes it. The contract
    says the preview lists every file of the range -- the selected ones and the
    discarded ones with their reason -- so the union of both must be *exactly*
    what ``git diff --name-only`` reports for the same range.

    A path git has and the engine did not mention is the silent-shrink failure:
    a file that would go unreviewed with nobody told. A path the engine reports
    and git does not have means the two are talking about different trees, or
    that a line was misread as a file. Both are exit code 9, and the message
    names the paths, because a mismatch here is either a real bug or an upstream
    format change and the operator needs to see which.
    """

    reported = {entry.path for entry in preview.entries}
    expected = {path for path in changed_paths}
    missing = sorted(expected - reported)
    extra = sorted(reported - expected)
    if not missing and not extra:
        return
    details: list[str] = []
    if missing:
        details.append(f"git reports {len(missing)} path(s) the engine did not mention: {', '.join(missing[:10])}")
    if extra:
        details.append(f"the engine reported {len(extra)} path(s) git does not have: {', '.join(extra[:10])}")
    raise AppError(
        "the engine's file scope does not match the candidate's diff",
        code=EXIT_ENGINE,
        diagnostics=[
            Diagnostic("engine_scope_mismatch", redact_text(detail)) for detail in details
        ]
        + [
            Diagnostic(
                "engine_scope_mismatch_remedy",
                "the raw output is preserved in the session evidence under raw/. A review whose scope disagrees with "
                "its own diff is never run on a guess: if the engine legitimately reports a different set, that is an "
                "upstream format change and this adapter has to be re-verified against the pinned binary.",
                severity="warning",
            )
        ],
    )


def parse_rules(raw: str, *, expected_paths: Iterable[str]) -> RuleResolution:
    """Read the resolved rule cascade, anchored on the paths we asked about.

    Anchoring on our own request rather than on the engine's headings means a
    cosmetic change to how a group is titled cannot make the parser miss a
    group, and a group for a path nobody asked about is never invented. The
    anchors are matched on **path boundaries**: without them ``a.py`` would
    swallow the rules of ``vendor/a.py``, and ``vendor/a.py`` would lose its own.

    Every requested path must appear. A partial answer is exit code 9, because
    "this file has no rules" and "the engine did not tell us about this file"
    have to stay distinguishable.
    """

    wanted = list(expected_paths)
    if not wanted:
        return RuleResolution(raw=raw, assignments=())
    if not raw or not raw.strip():
        raise _unparseable("the engine produced no rule output for the selected files", raw)

    positions: list[tuple[int, str]] = []
    found: set[str] = set()
    for path in wanted:
        pattern = re.compile(rf"(?<![\w./\\-]){re.escape(path)}(?![\w./\\-])")
        for match in pattern.finditer(raw):
            positions.append((match.start(), path))
            found.add(path)

    absent = [path for path in wanted if path not in found]
    if absent:
        raise _unparseable(
            "the engine's rule output does not mention "
            f"{len(absent)} of the {len(wanted)} file(s) it was asked about: {', '.join(absent[:10])}",
            raw,
        )

    grouped = _parse_rule_groups(raw, wanted)
    if grouped is not None:
        return RuleResolution(raw=raw, assignments=grouped)

    positions.sort()
    assignments: list[RuleAssignment] = []
    claimed: set[str] = set()
    for index, (start, path) in enumerate(positions):
        if path in claimed:
            continue
        claimed.add(path)
        end = len(raw)
        for later_start, later_path in positions[index + 1 :]:
            if later_path not in claimed:
                end = later_start
                break
        # A group also ends at the engine's *next* group heading, even when that
        # heading names a file this batch did not ask about: without that bound
        # `a.py` would absorb every rule printed after it.
        end = min(end, _next_group_boundary(raw, start))
        assignments.append(RuleAssignment(path=path, rules=_rule_texts(raw[start:end], path)))
    order = {path: position for position, path in enumerate(wanted)}
    assignments.sort(key=lambda assignment: order.get(assignment.path, len(order)))
    return RuleResolution(raw=raw, assignments=tuple(assignments))


# The shape v1.8.3 actually prints: a numbered group heading, the paths it
# applies to, and the rule text under its own sub-heading.
#
#     ### Rule Group 1: custom / src/**
#
#     Applies to:
#     - src/m.py
#
#     #### Content
#
#     <the rule text, which itself contains headings and list items>
#
# Reading it group-first matters for a reason the positional fallback made
# invisible: slicing from the first mention of a path to the next heading stops
# at `#### Content`, so every file came back with **zero rules** and nothing
# failed. An empty answer that looks like a valid one is worse than an error.
_RULE_GROUP_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s*Rule\s+Group\b(?P<title>[^\n]*)$", re.IGNORECASE)
_APPLIES_TO_RE = re.compile(r"(?m)^\s*(?:\*{1,2})?Applies\s+to(?:\*{1,2})?\s*:?\s*$", re.IGNORECASE)
_CONTENT_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s*Content\s*$", re.IGNORECASE)
_GROUP_BOUNDARY_RE = re.compile(r"(?m)^(?:\s{0,3}#{1,6}\s|\s*\*\*[^*\n]+\*\*\s*:?\s*$)")


def _parse_rule_groups(raw: str, wanted: Sequence[str]) -> tuple[RuleAssignment, ...] | None:
    """Read the engine's own grouping, when it prints one.

    Returns ``None`` when the output carries no recognizable groups, so the
    positional reading stays as the fallback for a shape this version has not
    seen. Every requested path must still be accounted for: a path in no group
    at all sends the whole parse back to the fallback rather than silently
    receiving no rules.
    """

    starts = [match.start() for match in _RULE_GROUP_RE.finditer(raw)]
    if not starts:
        return None

    remaining = set(wanted)
    texts: dict[str, tuple[str, ...]] = {}
    bounds = [*starts, len(raw)]
    for index, start in enumerate(starts):
        block = raw[start : bounds[index + 1]]
        applies = _APPLIES_TO_RE.search(block)
        content = _CONTENT_HEADING_RE.search(block)
        if applies is None or content is None:
            return None
        listed = {
            line.strip().lstrip("-*+ ").strip("`\"' ")
            for line in block[applies.end() : content.start()].splitlines()
            if line.strip()
        }
        body = block[content.end() :]
        rules = _rule_texts(body, "")
        for path in wanted:
            if path in listed:
                texts.setdefault(path, ())
                texts[path] = texts[path] + rules
                remaining.discard(path)

    if remaining:
        return None
    if not any(texts.values()):
        # The groups parsed and every one of them was empty. That is not a
        # review with no criteria; it is a shape this adapter misread.
        raise _unparseable(
            "the engine's rule groups were recognized but none of them carried any rule text",
            raw,
        )
    return tuple(RuleAssignment(path=path, rules=texts.get(path, ())) for path in wanted)


def _next_group_boundary(raw: str, start: int) -> int:
    """Where the group that begins at ``start`` stops, structurally."""

    line_end = raw.find("\n", start)
    if line_end == -1:
        return len(raw)
    match = _GROUP_BOUNDARY_RE.search(raw, line_end + 1)
    return match.start() if match else len(raw)


def _rule_texts(block: str, path: str) -> tuple[str, ...]:
    texts: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or _CODE_FENCE_RE.match(line):
            continue
        stripped = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", stripped)
        stripped = stripped.strip("`*_ ")
        if not stripped or (path and stripped == path) or stripped.startswith("#"):
            continue
        if stripped.startswith(">"):
            # A block quote in the engine's own preamble is guidance about how
            # to review, not a rule about this file.
            stripped = stripped.lstrip("> ").strip()
            if not stripped:
                continue
        # A line that only repeats the path is a title in disguise, not a rule.
        if stripped.replace(path, "").strip(" :-—–") == "":
            continue
        texts.append(stripped)
    return tuple(texts)


def _ambiguous(body: str) -> AppError:
    """Exit code 9 for a line that could mean two different paths."""

    return AppError(
        "the review engine reported a file entry this adapter cannot read unambiguously",
        code=EXIT_ENGINE,
        diagnostics=[
            Diagnostic(
                "engine_entry_ambiguous",
                "the path token does not span the whole entry, so the line could name more than one file; "
                f"the raw output is preserved in the session evidence. Entry: {redact_text(body[:120])}",
            )
        ],
    )


def _unparseable(message: str, raw: str) -> AppError:
    """Exit code 9, with the raw output preserved and pointed at."""

    preview = redact_text(raw.strip()[:400]) if raw and raw.strip() else "(empty)"
    return AppError(
        f"the review engine's output could not be parsed: {message}",
        code=EXIT_ENGINE,
        diagnostics=[
            Diagnostic(
                "engine_output_unparseable",
                "the raw output is preserved verbatim in the session evidence under raw/; the review scope is never "
                f"guessed. First bytes: {preview}",
            )
        ],
    )



def write_minimal_config(path: Path) -> Path:
    """Generate the delegate-mode configuration and point ``OCR_CONFIG_PATH`` at it."""

    import json

    harden_directories(path.parent)
    path.write_text(json.dumps(MINIMAL_CONFIG, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


