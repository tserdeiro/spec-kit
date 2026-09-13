"""Versioned adapter for ``ocr delegate``: invocation, verbatim output, parsing.

Doc "Motor de revision: OCR en delegation mode". Delegation mode is the whole
point of this engine: ``ocr`` instantiates no LLM client, needs no API key, and
answers only the two deterministic questions -- **which files are in scope** and
**which rules apply to them**. The judgement stays with the host agent.

Two properties of this module matter more than its size:

- **The output is JSON, verified by ``schema_version``.** Since ocr v1.9.0
  ``delegate preview`` and ``delegate rule`` both accept ``--format json``,
  which is the machine-readable contract this adapter reads instead of
  scraping the Markdown rendering meant for a terminal. The raw output is
  still preserved verbatim before parsing, and a shape this adapter does not
  recognize -- wrong JSON, a ``schema_version`` it was not verified against --
  is exit code 9 with the raw output referenced, never a guessed scope.
- **The output is untrusted content.** It is candidate-influenced (paths, rule
  text) and reaches logs, evidence and, in a later stage, the packet. Every
  path is validated as repository-relative before it propagates anywhere, and
  every message this module raises goes through redaction.

Verified against the pinned binary by ``tests/conformance/test_real_ocr.py``;
the shape read here is ``delegate_cmd.go``'s ``schema_version: "1"``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .errors import EXIT_ENGINE, AppError, Diagnostic
from .evidence import harden_directories
from .git import validate_repository_relative_path
from .process import CommandResult, run_command
from .redaction import redact_text


# Bumped whenever the parsing contract changes, and recorded in the evidence so
# a stored session says which adapter read its raw output.
# Version 3 is the first one that reads ``--format json`` instead of scraping
# Markdown, verified against open-code-review v1.12.0 (494bf1c8d). What
# changed is recorded in tests/conformance/evidence/real-ocr.md.
ADAPTER_VERSION = "3"

# The ``schema_version`` this adapter has been verified against. ocr's own
# delegate JSON contract, not this adapter's ``ADAPTER_VERSION``.
SUPPORTED_SCHEMA_VERSION = "1"

OCR_CONFIG_ENV = "OCR_CONFIG_PATH"

# Doc "Aislamiento de la configuracion de OCR": in delegate mode no provider and
# no model are needed, so the operator's personal ~/.opencodereview/config.json
# only adds variance between machines. This minimal document replaces it. It
# carries no telemetry key in either direction: the extension never enables OCR
# telemetry, and never force-disables a decision the operator made.
MINIMAL_CONFIG: dict[str, Any] = {"language": "English"}


@dataclass(frozen=True)
class ScopeEntry:
    """One file the engine considered, and whether it is under review."""

    path: str
    included: bool
    reason: str | None = None
    status: str | None = None
    insertions: int | None = None
    deletions: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "state": "included" if self.included else "excluded",
            "reason": self.reason,
            "status": self.status,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


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
class RuleGroup:
    """One resolved rule group the engine reported, and the files it covers."""

    group_id: int
    source: str
    pattern: str
    files: tuple[str, ...]
    rule: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "source": self.source,
            "pattern": self.pattern,
            "files": list(self.files),
            "rule": self.rule,
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
    groups: tuple[RuleGroup, ...] = ()
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

        arguments = ["delegate", "preview", "--repo", str(repository), "--format", "json"]
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
        on_raw: Callable[[str], None] | None = None,
    ) -> RuleResolution:
        """Ask the engine which rules apply to exactly the selected files.

        Every selected path goes into one ``delegate rule`` call: the engine
        groups files by the rule content they share, and splitting the request
        into batches would only recombine what the engine had already grouped
        for us, for no benefit.
        """

        if not paths:
            return RuleResolution(raw="", assignments=())
        arguments = ["delegate", "rule", "--repo", str(repository), "--format", "json"]
        if rule_path is not None:
            arguments.extend(["--rule", str(rule_path)])
        # Doc "Inyeccion de opciones": paths go after every flag, and each one
        # was validated as a repository-relative path before getting here, so
        # none can look like an option.
        # `--` closes the flag list: with it, a candidate file named `--rule` is
        # a path, not a second flag that would redirect the criteria.
        arguments.append("--")
        arguments.extend(paths)
        result = self.run(*arguments)
        if on_raw is not None:
            on_raw(result.stdout)
        if not result.ok:
            raise _engine_failure("`ocr delegate rule` failed", result)
        return parse_rules(result.stdout, expected_paths=paths)


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
# Two invariants hold this together:
#
# 1. **Shape verification.** The JSON must decode, and its ``schema_version``
#    must be the one this adapter has been verified against. Anything else is
#    exit code 9 -- never a silent discard, which is the failure mode that
#    shrinks a review without saying so.
# 2. **Cross-verification against git** (``verify_scope_against_git``). The set
#    of paths the engine reports must be exactly the set git reports for the
#    same range. This is the only defence that does not depend on the output
#    format at all, so it keeps working when upstream changes it.


def parse_preview(raw: str) -> PreviewResult:
    """Read the file selection out of the engine's ``delegate preview`` JSON."""

    document = _load_json(raw, "delegate preview")
    _check_schema_version(document, raw)

    entries: list[ScopeEntry] = []
    for item in _files_array(document, "reviewable_files", raw):
        entries.append(_scope_entry(item, included=True, raw=raw))
    for item in _files_array(document, "excluded_files", raw):
        entries.append(_scope_entry(item, included=False, raw=raw))

    return PreviewResult(
        raw=raw,
        entries=_deduplicate(entries, raw),
        mode=_optional_str(document, "mode"),
        from_ref=_optional_str(document, "from"),
        to_ref=_optional_str(document, "to"),
        merge_base=_optional_str(document, "merge_base"),
    )


def _files_array(document: dict[str, Any], key: str, raw: str) -> list[Any]:
    value = document.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise _unparseable(f"the engine's {key!r} is not a list", raw)
    return value


def _scope_entry(item: Any, *, included: bool, raw: str) -> ScopeEntry:
    if not isinstance(item, dict):
        raise _unparseable("a reported file entry is not an object", raw)
    path = item.get("path")
    if not isinstance(path, str) or not path.strip():
        raise _unparseable("a reported file entry has no path", raw)
    path = _clean_path(path, raw=raw)
    reason = item.get("exclude_reason")
    reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
    status = item.get("status")
    status = status if isinstance(status, str) and status.strip() else None
    insertions = item.get("insertions")
    insertions = insertions if isinstance(insertions, int) and not isinstance(insertions, bool) else None
    deletions = item.get("deletions")
    deletions = deletions if isinstance(deletions, int) and not isinstance(deletions, bool) else None
    return ScopeEntry(
        path=path,
        included=included,
        reason=reason if not included else None,
        status=status,
        insertions=insertions,
        deletions=deletions,
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


def _clean_path(text: str, *, raw: str) -> str:
    """Validate one reported path, or fail.

    Doc "Contenido no confiable": scope paths are validated as repository
    relative -- no ``..``, no absolute path, no NUL, and no leading ``-`` -- and
    a path that fails validation is a parse failure, never a dropped file.
    """

    text = text.strip()
    try:
        validate_repository_relative_path(text)
    except AppError as error:
        raise AppError(
            f"the engine reported a path this extension refuses to use: {text}",
            code=EXIT_ENGINE,
            diagnostics=[Diagnostic("engine_path_invalid", redact_text(str(error)), text)],
        ) from error
    return text


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


def parse_rules(raw: str, *, expected_paths: Sequence[str]) -> RuleResolution:
    """Read the resolved rule cascade out of the engine's ``delegate rule`` JSON.

    Every requested path must appear in some group. A partial answer is exit
    code 9, because "this file has no rules" and "the engine did not tell us
    about this file" have to stay distinguishable.
    """

    wanted = list(expected_paths)
    if not wanted:
        return RuleResolution(raw=raw, assignments=())

    document = _load_json(raw, "delegate rule")
    _check_schema_version(document, raw)

    raw_groups = document.get("groups")
    if not isinstance(raw_groups, list):
        raise _unparseable("the engine's 'groups' is not a list", raw)

    groups: list[RuleGroup] = []
    rules_by_path: dict[str, list[str]] = {path: [] for path in wanted}
    for item in raw_groups:
        if not isinstance(item, dict):
            raise _unparseable("a rule group is not an object", raw)
        group_id = item.get("group_id")
        source = item.get("source")
        pattern = item.get("pattern")
        rule_text = item.get("rule")
        files = item.get("files")
        if (
            not isinstance(group_id, int)
            or not isinstance(source, str)
            or not isinstance(pattern, str)
            or not isinstance(rule_text, str)
            or not isinstance(files, list)
            or not all(isinstance(entry, str) for entry in files)
        ):
            raise _unparseable("a rule group has an unexpected shape", raw)
        groups.append(RuleGroup(group_id=group_id, source=source, pattern=pattern, files=tuple(files), rule=rule_text))
        for path in files:
            if path in rules_by_path:
                rules_by_path[path].append(rule_text)

    absent = [path for path in wanted if not rules_by_path[path]]
    if absent:
        raise _unparseable(
            "the engine's rule output does not mention "
            f"{len(absent)} of the {len(wanted)} file(s) it was asked about: {', '.join(absent[:10])}",
            raw,
        )

    assignments = tuple(RuleAssignment(path=path, rules=tuple(rules_by_path[path])) for path in wanted)
    return RuleResolution(raw=raw, assignments=assignments, groups=tuple(groups))


def _load_json(raw: str, label: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise _unparseable(f"the engine produced no output for {label}", raw)
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _unparseable(f"the engine's {label} output is not valid JSON: {error}", raw) from error
    if not isinstance(document, dict):
        raise _unparseable(f"the engine's {label} output is not a JSON object", raw)
    return document


def _check_schema_version(document: dict[str, Any], raw: str) -> None:
    version = document.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise _unparseable(
            f"the engine's schema_version is {version!r}, not the verified {SUPPORTED_SCHEMA_VERSION!r}",
            raw,
        )


def _optional_str(document: dict[str, Any], key: str) -> str | None:
    value = document.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


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

    harden_directories(path.parent)
    path.write_text(json.dumps(MINIMAL_CONFIG, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path
