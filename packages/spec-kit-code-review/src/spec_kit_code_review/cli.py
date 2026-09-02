"""Command-line boundary: three commands, the exit-code contract, and rendering.

The whole surface is ``review``, ``doctor`` and ``completions``. ``review`` is
the single review command: with no candidate it reviews the pending diff of the
working tree (advisory), with a pull request it reviews the anchored candidate
and can publish. The packet/findings two-phase protocol is an implementation
detail of ``review`` -- a CLI cannot wait for the agent to read a packet, because
the agent is what invokes it -- and the agent-facing command file drives both
phases so the person only ever runs one command.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .budget import compute as compute_budget
from .budget import compute_working_tree as compute_working_tree_budget
from .candidate import parse_selector, resolve_from_pull_request, resolve_from_refs
from .completions import generate_completion_script
from .config import (
    RULE_RELATIVE_PATH,
    load_config,
)
from .doctor import DoctorOptions, external_tool_pin as _external_tool_pin, run_doctor
from .engine import DEFAULT_OCR_TAG, ocr_install_hint, resolve_engine
from .env_files import ENV_PREFIX, REPO_ENV_FILENAME, EnvSnapshot, assert_repo_env_not_tracked, load_env_files
from .environment import PreparedEnvironment, SignalInterrupt, prepared_environment, restore
from .errors import (
    EXIT_CATEGORIES,
    EXIT_CONFIGURATION,
    EXIT_DRIFT,
    EXIT_ENGINE,
    EXIT_ENVIRONMENT,
    EXIT_INTERRUPTED,
    EXIT_PREREQUISITE,
    EXIT_SUCCESS,
    EXIT_USAGE,
    AppError,
    Diagnostic,
)
from .evidence import ensure_root, harden_directories, repository_id, resolve_evidence_root
from .git import MINIMUM_GIT_VERSION, Git, open_git
from .github import open_github, require_github, validate_number, validate_repository
from .session import (
    FINDINGS_FILENAME,
    FINDINGS_MARKDOWN_FILENAME,
    FINDINGS_NORMALIZED_FILENAME,
    PUBLICATION_PLAN_FILENAME,
    PUBLICATION_RESULT_FILENAME,
    write_json,
    PACKET_FILENAME,
    PHASE_ABANDONED,
    PHASE_CLOSED,
    RAW_DIRECTORY,
    ReviewSession,
    apply_retention,
    detect_drift,
    load_session,
    open_session,
    repository_lock,
    require_open,
    session_directory,
    write_environment,
    write_text,
)
from .lockfile import SELF_PIN_FILENAME, first_line, lock_path, platform_key, version_matches_pin
from .ocr import ADAPTER_VERSION, Ocr, verify_scope_against_git, write_minimal_config
from .anchors import load_hunks
from .findings import load_document, normalize as normalize_findings, render_markdown as render_findings_markdown
from .packet import assemble as assemble_packet
from .packet import digest_of as packet_digest
from .packet import new_suffix
from .allowlist import EventConditions, Ledger
from .publish import InlineComment, PublicationFailed, PublicationPlan
from .publish import build_plan as build_publication_plan
from .publish import execute as execute_publication
from .publish import resolve_event
from .reporting import render_human, review_document
from .verdict import CAUSE_ENGINE, CAUSE_SCOPE, InconclusiveCause, Verdict
from .verdict import derive as derive_verdict
from .sdd_context import CommitReader, WorkingTreeReader, load_context, resolve_feature
from .rules import RuleResolution, parse_rule_document, resolve_rules
from .process import resolve_executable, run_command, sha256_file
from .redaction import redact_payload, redact_text


DEFAULT_TIMEOUT = 300


class _ArgumentParser(argparse.ArgumentParser):
    """Emit the public JSON error shape when --json accompanies bad input.

    The flag is a *class* attribute so that a subparser -- which argparse
    instantiates itself, from this same class -- reports a bad choice in the
    same shape the top-level parser would.
    """

    json_requested = False

    def error(self, message: str) -> None:
        if getattr(self, "json_requested", False):
            _write_json(
                {
                    "code": EXIT_USAGE,
                    "category": EXIT_CATEGORIES[EXIT_USAGE],
                    "message": message,
                    "retryable": False,
                    "operations": [],
                    "diagnostics": [{"code": "arguments", "message": message, "severity": "error"}],
                }
            )
            raise SystemExit(EXIT_USAGE)
        super().error(message)


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--quiet", action="store_true", help="suppress human-readable detail")
    parser.add_argument("--verbose", action="store_true", help="add safe diagnostics")
    parser.add_argument("--config", help="path to the shared configuration")
    parser.add_argument("--root", help="explicit consumer repository root")


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="spec-kit-code-review", description="Review the pending diff, or a pull-request candidate")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("review", help="review the working tree, or a pull-request candidate")
    _common_arguments(review)
    review.add_argument("selector", nargs="?", help="pull-request number or URL; without one the working tree is reviewed")
    review.add_argument("--base", metavar="REF", help="explicit base of an anchored candidate; requires --head")
    review.add_argument("--head", metavar="REF", help="explicit head of an anchored candidate; requires --base")
    review.add_argument("--findings", metavar="PATH", help="the JSON findings produced by the reviewing agent")
    review.add_argument("--session", metavar="PATH", help="the open session those findings belong to")
    review.add_argument("--publish", action="store_true", help="publish the review to GitHub; always explicit")

    doctor = subparsers.add_parser("doctor", help="validate prerequisites; --fix applies the local repairs")
    _common_arguments(doctor)
    doctor.add_argument("--fix", action="store_true", help="apply the bounded, strictly local repairs")

    completions = subparsers.add_parser("completions", help="print a shell completion script")
    completions.add_argument("shell", choices=("bash", "zsh"), help="shell to generate the completion script for")
    return parser


# -- shared plumbing --------------------------------------------------------


@dataclass(frozen=True)
class CommandContext:
    """Everything frozen before a command reads anything at all.

    The repository toplevel, the paths no executable may be resolved from, and
    the environment snapshot are all established once, here, and every command
    works from them. There is exactly one choke point so that no command can
    forget the guard -- forgetting it once is how a candidate's own binary gets
    executed.
    """

    root: Path
    git: Git
    environment: EnvSnapshot
    forbidden_roots: tuple[Path, ...]

    def executable_override(self, key: str) -> str | None:
        return self.environment.executable_override(key)


def _start_directory(value: str | None) -> Path:
    root = Path(value).expanduser() if value else Path.cwd()
    try:
        resolved = root.resolve(strict=True)
    except FileNotFoundError as error:
        raise AppError(
            f"repository root does not exist: {root}",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("root_missing", "--root must exist", str(root))],
        ) from error
    if not resolved.is_dir():
        raise AppError(
            f"repository root is not a directory: {resolved}",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("root_not_directory", "--root must be a directory", str(resolved))],
        )
    return resolved


def _candidate_toplevel(start: Path) -> Path | None:
    """Find the enclosing repository without running ``git`` first.

    ``git`` itself is an external executable that must not be resolved from the
    tree under review, and the tree under review is only known once the toplevel
    is. This walk breaks that circularity without executing anything.
    """

    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _open_context(args: argparse.Namespace, *, timeout: int = DEFAULT_TIMEOUT) -> CommandContext:
    """Resolve the toplevel, guard every executable, and freeze the environment."""

    explicit_root = getattr(args, "root", None)
    start = _start_directory(explicit_root)
    discovered = _candidate_toplevel(start)
    if discovered is None:
        if explicit_root:
            raise AppError(
                f"--root is not a Git repository: {start}",
                code=EXIT_USAGE,
                diagnostics=[Diagnostic("root_not_repository", "--root must be the toplevel of a Git repository", str(start))],
            )
        raise AppError(
            f"not inside a Git worktree: {start}",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("git_root", "run this command inside a Git repository, or pass --root", str(start))],
        )

    git = open_git(start, forbidden_roots=(discovered,), timeout=timeout)
    toplevel = git.toplevel(start)
    if explicit_root and toplevel != start:
        raise AppError(
            f"--root is not the toplevel of its repository: {start}",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic("root_not_toplevel", f"pass the repository toplevel instead: {toplevel}", str(start))
            ],
        )

    git = Git(git.executable, root=toplevel, timeout=timeout)
    forbidden = git.forbidden_roots()
    # The toplevel discovered by the walk can be narrower than the authoritative
    # one (a worktree, a symlinked path); re-validate git against the real set.
    resolve_executable("git", forbidden_roots=forbidden)

    environment = load_env_files(toplevel)
    head = git.head_commit()
    assert_repo_env_not_tracked(
        head is not None and git.path_tracked_at("HEAD", REPO_ENV_FILENAME),
        ref="HEAD",
        root=toplevel,
    )
    # The renderer needs the frozen snapshot for SPECKIT_CODE_REVIEW_LOG_LEVEL;
    # it travels on the namespace, never inside the JSON payload.
    setattr(args, "_environment", environment)
    return CommandContext(root=toplevel, git=git, environment=environment, forbidden_roots=forbidden)


def _write_json(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    sys.stdout.write("\n")


def _success(message: str, *, diagnostics: list[Diagnostic], operations: list[dict[str, object]] | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": EXIT_SUCCESS,
        "category": EXIT_CATEGORIES[EXIT_SUCCESS],
        "message": message,
        "retryable": False,
        "operations": operations or [],
        "diagnostics": [diagnostic.as_dict() for diagnostic in diagnostics],
    }
    payload.update(extra)
    return payload


def _write_non_info_diagnostics(payload: Mapping[str, Any]) -> None:
    for diagnostic in payload["diagnostics"]:
        if diagnostic["severity"] == "info":
            continue
        location = f" ({diagnostic['path']})" if "path" in diagnostic else ""
        sys.stdout.write(f"{diagnostic['severity']}: {diagnostic['message']}{location}\n")


def _render(payload: Mapping[str, Any], as_json: bool, quiet: bool) -> None:
    """Render a result. Redaction is unconditional, not a flag.

    ``redaction.py`` is the only path through which text reaches stdout, the
    evidence, or GitHub, so the catalogued patterns are always applied --
    including to text this extension merely relayed, such as ``gh`` stderr.
    """

    rendered = redact_payload(dict(payload))
    if as_json:
        _write_json(rendered)
        return
    if quiet:
        # --quiet suppresses the human detail, never the verdict and never the
        # exit code. The code is the caller's; the verdict line is this one.
        if rendered.get("verdict"):
            sys.stdout.write(f"{rendered['message']}\n")
        return
    if rendered.get("human"):
        sys.stdout.write(rendered["human"] if rendered["human"].endswith("\n") else rendered["human"] + "\n")
        _write_non_info_diagnostics(rendered)
        return
    sys.stdout.write(f"{rendered['message']}\n")
    if rendered.get("operations"):
        sys.stdout.write(f"planned operations: {len(rendered['operations'])}\n")
    _write_non_info_diagnostics(rendered)


def _render_verbose(payload: Mapping[str, Any]) -> None:
    for diagnostic in payload["diagnostics"]:
        if diagnostic["severity"] != "info":
            continue
        sys.stdout.write(f"info: {diagnostic['message']}\n")


# -- doctor -----------------------------------------------------------------


def run_doctor_command(args: argparse.Namespace) -> dict[str, Any]:
    context = _open_context(args)
    report = run_doctor(
        DoctorOptions(
            root=context.root,
            environment=context.environment,
            git=context.git,
            config_flag=args.config,
            fix=args.fix,
        )
    )
    if report.code != EXIT_SUCCESS:
        raise AppError("doctor found blocking problems", code=report.code, diagnostics=report.diagnostics)
    return _success("doctor completed with no blocking problems", diagnostics=report.diagnostics, **report.as_dict())


# -- review -----------------------------------------------------------------


def run_review(args: argparse.Namespace) -> dict[str, Any]:
    """The single review command; the two phases are internal to it."""

    if args.findings:
        return _review_phase_two(args)
    if args.session:
        raise AppError(
            "--session belongs with --findings",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic("session_without_findings", "the session is what the findings are closed against")
            ],
        )
    if args.base or args.head or args.selector:
        if args.publish:
            # Opening a session and exiting 0 would look exactly like a
            # publication that happened. Publishing needs the review it publishes.
            raise AppError(
                "--publish needs the review it is publishing",
                code=EXIT_USAGE,
                diagnostics=[
                    Diagnostic(
                        "publish_without_review",
                        "review the candidate first; --publish belongs to the invocation that closes the review "
                        "with its findings",
                    )
                ],
            )
        return _review_phase_one(args)
    if args.publish:
        raise AppError(
            "there is nothing to publish a working-tree review to",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "publish_without_candidate",
                    "a working-tree review is advisory and has no pull request; name one to publish against it",
                )
            ],
        )
    return _review_working_tree(args)


def _timeout(config) -> int:
    return int(config.get("engine", "timeout_seconds", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)


def _preflight(context: CommandContext) -> None:
    """``git >= 2.41`` is a hard engine requirement."""

    version = context.git.version()
    if not version.supported:
        minimum = ".".join(str(part) for part in MINIMUM_GIT_VERSION)
        raise AppError(
            f"git >= {minimum} is required by the review engine; found {version.text}",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("git_version_unsupported", "upgrade git yourself; only `doctor --fix` installs anything, and only the pinned engine")],
        )


def _admit_engine(context: CommandContext, config, *, diagnostics: list[Diagnostic], timeout: int) -> tuple[Path, str]:
    """Resolve ``ocr`` and verify it **before** the engine is ever invoked.

    ``doctor`` is a diagnosis, not an admission control, and anything can happen
    between a ``doctor`` and a review. So the review re-resolves the binary --
    the operator's override, else the canonical pinned path -- re-reads
    ``ocr --version`` and recalculates the SHA-256 itself, and a mismatch is exit
    code 4 **before** the first invocation. A review installs nothing on any
    path; ``doctor --fix`` is the only command that does.
    """

    pin = _external_tool_pin(context.root)
    expected_tag = (
        (pin.release_tag if pin else None)
        or (config.get("engine", "ocr_version") if config else None)
        or DEFAULT_OCR_TAG
    )
    executable = resolve_engine(
        tag=expected_tag,
        override=context.executable_override(f"{ENV_PREFIX}OCR_BIN"),
        forbidden_roots=context.forbidden_roots,
    )
    if executable is None:
        raise AppError(
            "the review engine is not installed",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("ocr_missing", ocr_install_hint(expected_tag, pin.npm_package if pin else None))],
        )

    invocation = run_command([str(executable), "--version"], timeout=timeout)
    observed_version = (invocation.stdout or invocation.stderr or "").strip()
    if not invocation.ok:
        raise AppError(
            "`ocr --version` did not succeed, so the engine cannot be admitted",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("ocr_version_failed", redact_text(invocation.stderr.strip()), str(executable))],
        )

    if pin is None:
        diagnostics.append(
            Diagnostic(
                "ocr_pin_missing",
                f"no engine pin in {lock_path(context.root)} nor in the extension's own {SELF_PIN_FILENAME}; "
                "the engine's version and digest cannot be verified for this run",
                str(lock_path(context.root)),
                severity="warning",
            )
        )
        return executable, observed_version

    expected_version = pin.version_string
    if expected_version and not version_matches_pin(observed_version, expected_version):
        raise AppError(
            "the installed review engine is not the pinned one",
            code=EXIT_PREREQUISITE,
            diagnostics=[
                Diagnostic(
                    "ocr_version_mismatch",
                    f"`ocr --version` reported {first_line(observed_version)!r}; the lock pins {expected_version!r}. "
                    "Run `doctor --fix` to install the pinned version; a review never installs or updates anything.",
                    str(executable),
                )
            ],
        )

    key = platform_key()
    expected_digest = pin.binary_digest(key)
    observed_digest = sha256_file(executable)
    if expected_digest is None:
        diagnostics.append(
            Diagnostic(
                "ocr_digest_platform_unpinned",
                f"the lock has no binary digest for {key}; the installed engine cannot be verified on this platform",
                str(executable),
                severity="warning",
            )
        )
    elif observed_digest is None:
        diagnostics.append(
            Diagnostic(
                "ocr_digest_unreadable",
                "the resolved engine is not a readable regular file; its digest cannot be verified",
                str(executable),
                severity="warning",
            )
        )
    elif observed_digest != expected_digest:
        raise AppError(
            "the installed review engine does not match the pinned digest",
            code=EXIT_PREREQUISITE,
            diagnostics=[
                Diagnostic(
                    "ocr_digest_mismatch",
                    f"the binary digest {observed_digest} does not match the {key} digest pinned in the lock; "
                    "the engine was not invoked",
                    str(executable),
                )
            ],
        )
    else:
        diagnostics.append(Diagnostic("ocr_digest", f"{key} digest matches the lock", str(executable), severity="info"))
    return executable, observed_version


def _resolve_candidate(args: argparse.Namespace, context: CommandContext, config, *, timeout: int, fetch_missing: bool):
    selector, base, head = args.selector, args.base, args.head
    if selector and (base or head):
        raise AppError(
            "a pull-request selector and --base/--head are mutually exclusive",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("selector_conflict", "pass a selector, or --base and --head, never both")],
        )
    if selector is None:
        return resolve_from_refs(context.git, base=base, head=head), None
    client = require_github(
        override=context.executable_override(f"{ENV_PREFIX}GH_BIN"),
        forbidden_roots=context.forbidden_roots,
        timeout=timeout,
    )
    return resolve_from_pull_request(
        context.git,
        client,
        parse_selector(selector),
        repository=config.get("repository", "github"),
        remote=str(config.get("repository", "remote", "origin") or "origin"),
        fetch_missing=fetch_missing,
    )


def _review_phase_one(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve the candidate, materialize it, and write the review packet."""

    context = _open_context(args)
    diagnostics: list[Diagnostic] = list(context.environment.diagnostics)
    config = load_config(context.root, explicit=args.config, environment=context.environment)
    diagnostics.extend(config.diagnostics)
    timeout = _timeout(config)
    _preflight(context)

    candidate, pull_request = _resolve_candidate(args, context, config, timeout=timeout, fetch_missing=True)
    diagnostics.extend(candidate.diagnostics)

    # From this stage on, the repository env file is checked against the
    # candidate's own head.
    assert_repo_env_not_tracked(
        context.git.path_tracked_at(candidate.head_commit, REPO_ENV_FILENAME),
        ref=candidate.head_commit,
        root=context.root,
    )

    # The engine is admitted -- resolved, version-checked, digest-checked --
    # before anything is materialized and long before it is invoked.
    engine_executable, engine_version = _admit_engine(context, config, diagnostics=diagnostics, timeout=timeout)

    evidence_root = ensure_root(
        resolve_evidence_root(
            environment=context.environment,
            config=config,
            forbidden_roots=context.forbidden_roots,
        )
    )
    repository_slug = repository_id(candidate.repository, context.root)
    directory = session_directory(evidence_root, repository_slug, candidate.head_commit)

    # Retention runs when a session *begins*, never when one ends.
    removed = apply_retention(
        evidence_root,
        repository_slug,
        keep=int(config.get("evidence", "keep_sessions", 20) or 20),
        protect=directory,
    )
    if removed:
        diagnostics.append(
            Diagnostic("evidence_retention", f"{len(removed)} closed session(s) removed by retention", severity="info")
        )

    # Deciding "no session is open here" and then opening one is a check-then-act
    # pair; the advisory lock narrows the window between them. It is best effort
    # by design, so a stale lock is reported, never fatal.
    with repository_lock(context.root) as locked:
        if not locked:
            diagnostics.append(
                Diagnostic(
                    "session_lock_unavailable",
                    "another invocation holds the session lock for this repository, or a stale lock file remains",
                    severity="warning",
                )
            )
        _reclaim_existing_session(context, directory, diagnostics)
        _clear_previous_review_outputs(directory)
        with prepared_environment(
            context.git,
            head_commit=candidate.head_commit,
            worktree_parent=directory,
            forbidden_roots=context.forbidden_roots,
        ) as prepared:
            diagnostics.extend(prepared.diagnostics)
            engine = _run_engine(
                context,
                config,
                candidate=candidate,
                prepared=prepared,
                directory=directory,
                diagnostics=diagnostics,
                engine_executable=engine_executable,
                engine_version=engine_version,
                timeout=timeout,
            )
            assembled = _assemble_packet(
                context,
                config,
                candidate=candidate,
                pull_request=pull_request,
                prepared=prepared,
                directory=directory,
                engine=engine,
                diagnostics=diagnostics,
            )
            write_text(directory / PACKET_FILENAME, assembled["packet"].text)
            session = open_session(
                directory=directory,
                candidate=candidate.as_dict(),
                environment=prepared.as_dict(),
                config_sha256=config.sha256,
                extra={
                    # The second phase re-resolves the candidate, and it can only
                    # do that the way the first did. Recorded SHAs cannot move;
                    # the refs they came from can.
                    "selector": {
                        "kind": candidate.selector_kind,
                        "value": args.selector,
                        "base_ref": args.base,
                        "head_ref": args.head,
                        "repository": candidate.repository,
                    },
                    "engine": engine["engine"],
                    "scope": engine["scope"],
                    "rules": engine["rules"],
                    "sdd": assembled["sdd"],
                    "budget": assembled["budget"],
                    "packet": assembled["packet"].as_dict(),
                },
            )
            # The second phase validates the packet it is closing against the one
            # the first produced.
            session.payload["packet_sha256"] = assembled["packet"].packet_sha256
            session.payload["pr_metadata_sha256"] = assembled["packet"].pr_metadata_sha256
            session.payload["containment_suffix"] = assembled["packet"].containment_suffix
            session.write()

    diagnostics.append(
        Diagnostic(
            "packet_written",
            f"the review packet is at {session.path / PACKET_FILENAME} (packet_sha256 "
            f"{assembled['packet'].packet_sha256})",
            str(session.path / PACKET_FILENAME),
            severity="info",
        )
    )
    return _success(
        f"review packet ready at {session.path / PACKET_FILENAME}",
        diagnostics=diagnostics,
        candidate=candidate.as_dict(),
        environment=prepared.as_dict(),
        session=session.summary(),
        engine=engine["engine"],
        scope=engine["scope"],
        rules=engine["rules"],
        sdd=assembled["sdd"],
        budget=assembled["budget"],
        packet=assembled["packet"].as_dict(),
    )


def _reclaim_existing_session(context: CommandContext, directory: Path, diagnostics: list[Diagnostic]) -> None:
    """Close and clean an orphan session for this candidate, then carry on.

    A previous review whose second phase never arrived left a session open and a
    worktree materialized. That is not an error and not a surface: the worktree
    is this extension's own, outside the repository, so it is withdrawn and the
    session marked ``abandoned`` before a fresh one opens. A worktree the
    operator has put work into is the one case that stops here, because it holds
    state nobody has seen.
    """

    if not (directory / "session.json").is_file():
        return
    existing = load_session(directory)
    if existing.phase != "open":
        return
    prepared = _prepared_from_session(context, existing)
    outcome = restore(prepared)
    diagnostics.extend(outcome.diagnostics)
    if not outcome.restored:
        raise AppError(
            "an earlier review of this candidate left an environment that could not be withdrawn",
            code=outcome.code or EXIT_ENVIRONMENT,
            diagnostics=diagnostics,
        )
    existing.mark(PHASE_ABANDONED, environment_restored=True, restore=outcome.as_dict())
    diagnostics.append(
        Diagnostic(
            "session_reclaimed",
            f"an earlier session for this candidate was still open at {directory}; it was closed and its "
            "environment withdrawn before this review started",
            str(directory),
            severity="info",
        )
    )


def _clear_previous_review_outputs(directory: Path) -> None:
    """Make reopening the same candidate require fresh findings."""

    for filename in (
        FINDINGS_FILENAME,
        FINDINGS_NORMALIZED_FILENAME,
        FINDINGS_MARKDOWN_FILENAME,
        PUBLICATION_PLAN_FILENAME,
    ):
        (directory / filename).unlink(missing_ok=True)


def _sdd_diagnostics(resolution, sdd) -> list[Diagnostic]:
    """Report an unresolved Spec Kit context; never fail on it.

    A diff without SDD context still deserves reviewing, and an ambiguous
    feature is information the packet carries rather than a refusal.
    """

    if resolution.ambiguous:
        return [
            Diagnostic(
                "sdd_context_ambiguous",
                f"the candidate's Spec Kit feature is ambiguous: {', '.join(resolution.candidates)}",
                severity="warning",
            )
        ]
    if not sdd.present:
        return [
            Diagnostic(
                "sdd_context_absent",
                "no Spec Kit context was resolved; the review continues without it",
                severity="warning",
            )
        ]
    return []


def _assemble_packet(
    context: CommandContext,
    config,
    *,
    candidate,
    pull_request,
    prepared: PreparedEnvironment,
    directory: Path,
    engine: dict[str, Any],
    diagnostics: list[Diagnostic],
) -> dict[str, Any]:
    """The SDD context, the budget, and the packet."""

    changed = context.git.changed_paths(candidate.merge_base, candidate.head_commit)
    reader = CommitReader(context.git, candidate.head_commit)
    resolution = resolve_feature(
        reader,
        changed_paths=changed,
        pr_body=getattr(pull_request, "body", None),
    )
    sdd = load_context(
        reader,
        resolution=resolution,
        include_checklists=bool(config.get("packet", "include_checklists", True)),
        changed_paths=changed,
    )
    diagnostics.extend(sdd.diagnostics)
    diagnostics.extend(_sdd_diagnostics(resolution, sdd))

    budget_report = compute_budget(
        context.git,
        merge_base=candidate.merge_base,
        head_commit=candidate.head_commit,
        limit=int(config.get("budget", "limit", 400) or 400),
    )
    diagnostics.extend(budget_report.diagnostics)

    assembled = assemble_packet(
        candidate=candidate,
        pull_request=pull_request,
        working_root=str(prepared.working_root),
        evidence_path=str(directory),
        engine_version=engine["engine"].get("version"),
        adapter_version=engine["engine"].get("adapter_version", ""),
        preview=engine["preview_result"],
        rules=engine["rules_resolution"],
        rule_assignments=engine["rule_assignments"],
        sdd=sdd,
        budget=budget_report,
        max_bytes_per_artifact=int(config.get("packet", "max_bytes_per_artifact", 60000) or 60000),
        max_total_bytes=int(config.get("packet", "max_total_bytes", 400000) or 400000),
        include_pr_body=bool(config.get("packet", "include_pr_body", True)),
        include_checklists=bool(config.get("packet", "include_checklists", True)),
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    diagnostics.extend(assembled.warnings)
    for truncation in assembled.truncations:
        diagnostics.append(
            Diagnostic(
                "packet_truncated",
                f"{truncation.path}: {truncation.omitted_bytes} byte(s) omitted; read the rest with "
                f"{truncation.command}",
                truncation.path,
                severity="warning",
            )
        )
    return {"packet": assembled, "sdd": sdd.as_dict(), "budget": budget_report.as_dict()}


def _run_engine(
    context: CommandContext,
    config,
    *,
    candidate,
    prepared: PreparedEnvironment,
    directory: Path,
    diagnostics: list[Diagnostic],
    engine_executable: Path,
    engine_version: str,
    timeout: int,
) -> dict[str, Any]:
    """The scope, then the rules -- the only questions the engine answers.

    Everything it returns is untrusted content: the raw output is preserved
    verbatim (through redaction) in the evidence, every path it reports has
    already been validated as repository-relative, and an output shape the
    adapter does not recognize is exit code 9 rather than a guessed scope.
    """

    raw_directory = directory / RAW_DIRECTORY
    config_path = write_minimal_config(raw_directory / "ocr-config.json")

    resolution = resolve_rules(
        context.git,
        head_commit=candidate.head_commit,
        merge_base=candidate.merge_base,
        cross_repository=candidate.cross_repository,
        destination=raw_directory,
    )
    diagnostics.extend(resolution.warnings)

    engine = Ocr(
        engine_executable,
        timeout=timeout,
        config_path=config_path,
        on_stderr=lambda text: write_text(raw_directory / "ocr.stderr", text),
    )
    preview = engine.delegate_preview(
        prepared.working_root,
        from_ref=candidate.merge_base,
        to_ref=candidate.head_commit,
        rule_path=resolution.path,
        on_raw=lambda raw: write_text(raw_directory / "ocr-delegate-preview.stdout", raw),
    )
    # The invariant that does not depend on the engine's output format: the set
    # of files it reports must be exactly the set the candidate's diff contains.
    verify_scope_against_git(preview, context.git.changed_paths(candidate.merge_base, candidate.head_commit))

    resolved_rules = engine.delegate_rule(
        prepared.working_root,
        preview.included_paths,
        rule_path=resolution.path,
        batch_size=int(config.get("engine", "rule_batch_size", 100) or 100),
        on_raw=lambda raw: write_text(raw_directory / "ocr-delegate-rule.stdout", raw),
    )

    if not preview.included_paths:
        diagnostics.append(
            Diagnostic(
                "scope_empty",
                "the engine selected no files for review; an empty scope is a legitimate answer, not a failure",
                severity="warning",
            )
        )
    diagnostics.append(
        Diagnostic(
            "scope_resolved",
            f"{len(preview.included_paths)} file(s) in scope, {len(preview.excluded)} excluded",
            severity="info",
        )
    )
    diagnostics.append(
        Diagnostic(
            "rules_resolved",
            f"{len(resolution.document.rules)} rule(s) from {resolution.document.ref} ({resolution.ref_kind}), "
            f"rule_source {resolution.rule_source}",
            str(resolution.path),
            severity="info",
        )
    )
    return {
        "preview_result": preview,
        "rules_resolution": resolution,
        "rule_assignments": resolved_rules,
        "engine": {
            # Delegation mode has no status field of its own: the engine either
            # produced a scope this adapter could read -- in which case the
            # deterministic part of the review is complete -- or the invocation
            # already failed with exit code 9 and never reached this line.
            "status": "success",
            "adapter_version": ADAPTER_VERSION,
            "executable": str(engine_executable),
            "version": engine_version,
            "config_path": str(config_path),
            "invocations": [invocation.as_dict() for invocation in engine.invocations],
        },
        "scope": preview.as_dict(),
        "rules": {**resolution.as_dict(), "assignments": resolved_rules.as_dict()["assignments"]},
    }


# -- review: the working tree ------------------------------------------------


@dataclass(frozen=True)
class WorkspaceOrigin:
    """What an advisory review covers, in the shape the packet expects.

    It is deliberately *not* a candidate: there is no ``candidate_id`` because
    there is nothing immutable to identify. The tree can change while the review
    is being read, which is exactly why the packet this produces is advisory and
    says so in its own first section.
    """

    root: str
    head_commit: str | None
    branch: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"root": self.root, "head": self.head_commit, "branch": self.branch}


def _review_working_tree(args: argparse.Namespace) -> dict[str, Any]:
    """The advisory review of the operator's own pending diff.

    It never contacts GitHub, materializes nothing (the point is to review the
    checkout dirty and all), opens no session because there is no environment to
    restore, and produces no publishable verdict because there is no immutable
    candidate behind it. It writes nothing inside the repository.
    """

    with ExitStack() as exit_stack:
        return _run_working_tree(args, exit_stack)


def _run_working_tree(args: argparse.Namespace, exit_stack: ExitStack) -> dict[str, Any]:
    context = _open_context(args)
    diagnostics: list[Diagnostic] = list(context.environment.diagnostics)
    config = load_config(context.root, explicit=args.config, environment=context.environment)
    diagnostics.extend(config.diagnostics)
    timeout = _timeout(config)
    _preflight(context)
    engine_executable, engine_version = _admit_engine(context, config, diagnostics=diagnostics, timeout=timeout)

    head = context.git.rev_parse_commit("HEAD")
    origin = WorkspaceOrigin(root=str(context.root), head_commit=head, branch=context.git.current_branch())
    diagnostics.append(
        Diagnostic(
            "working_tree_review",
            "reviewing uncommitted content: staged, unstaged and untracked",
            severity="info",
        )
    )

    evidence_root = ensure_root(
        resolve_evidence_root(
            environment=context.environment,
            config=config,
            forbidden_roots=context.forbidden_roots,
        )
    )
    # One directory per run, so two reviews cannot overwrite each other's packet
    # or mix their raw evidence. `latest` points at the newest.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parent = evidence_root.path / repository_id(None, context.root) / "working-tree"
    directory = parent / f"{stamp}-{secrets.token_hex(3)}"
    harden_directories(directory)

    with tempfile.TemporaryDirectory(prefix="spec-kit-code-review-") as scratch:
        destination = Path(scratch)
        config_path = write_minimal_config(destination / "ocr-config.json")
        resolution = _working_tree_rules(context, destination)
        diagnostics.extend(resolution.warnings)

        # The engine's raw output reaches the evidence *before* it is parsed: an
        # output shape the adapter does not recognize is exit code 9, and the
        # operator is pointed at the bytes rather than at a guess.
        raw_directory = directory / RAW_DIRECTORY
        engine = Ocr(
            engine_executable,
            timeout=timeout,
            config_path=config_path,
            on_stderr=lambda text: write_text(raw_directory / "ocr.stderr", text),
        )
        preview = engine.delegate_preview(
            context.root,
            from_ref=None,
            to_ref=None,
            rule_path=resolution.path,
            on_raw=lambda raw: write_text(raw_directory / "ocr-delegate-preview.stdout", raw),
        )
        # The same format-independent invariant as an anchored review: the
        # engine's scope must be exactly what git reports for what is reviewed.
        verify_scope_against_git(preview, context.git.uncommitted_paths())
        assignments = engine.delegate_rule(
            context.root,
            preview.included_paths,
            rule_path=resolution.path,
            batch_size=int(config.get("engine", "rule_batch_size", 100) or 100),
            on_raw=lambda raw: write_text(raw_directory / "ocr-delegate-rule.stdout", raw),
        )

    # The SDD context and the rules come from the working tree here: the content
    # is the operator's own, so the candidate/base distinction does not apply.
    reader = WorkingTreeReader(context.root)
    reviewed_paths = [entry.path for entry in preview.entries]
    feature = resolve_feature(reader, changed_paths=reviewed_paths)
    sdd = load_context(
        reader,
        resolution=feature,
        include_checklists=bool(config.get("packet", "include_checklists", True)),
        changed_paths=reviewed_paths,
    )
    diagnostics.extend(sdd.diagnostics)
    diagnostics.extend(_sdd_diagnostics(feature, sdd))

    budget_report = compute_working_tree_budget(
        context.git, context.root, limit=int(config.get("budget", "limit", 400) or 400)
    )
    diagnostics.extend(budget_report.diagnostics)

    packet = assemble_packet(
        candidate=origin,
        pull_request=None,
        working_root=str(context.root),
        evidence_path=str(directory),
        engine_version=engine_version,
        adapter_version=ADAPTER_VERSION,
        preview=preview,
        rules=resolution,
        rule_assignments=assignments,
        sdd=sdd,
        budget=budget_report,
        max_bytes_per_artifact=int(config.get("packet", "max_bytes_per_artifact", 60000) or 60000),
        max_total_bytes=int(config.get("packet", "max_total_bytes", 400000) or 400000),
        include_pr_body=False,
        include_checklists=bool(config.get("packet", "include_checklists", True)),
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        advisory=True,
    )
    diagnostics.extend(packet.warnings)
    for truncation in packet.truncations:
        diagnostics.append(
            Diagnostic(
                "packet_truncated",
                f"{truncation.path}: {truncation.omitted_bytes} byte(s) omitted; read the rest with {truncation.command}",
                truncation.path,
                severity="warning",
            )
        )
    packet_path = directory / PACKET_FILENAME
    write_text(packet_path, packet.text)
    _point_at_latest(directory)
    diagnostics.append(
        Diagnostic(
            "packet_written",
            f"the advisory packet is at {packet_path} (packet_sha256 {packet.packet_sha256})",
            str(packet_path),
            severity="info",
        )
    )
    diagnostics.append(
        Diagnostic(
            "advisory",
            "this is an advisory review of your own working tree: it does not replace, anticipate or credit the "
            "review the pull request will receive",
            severity="info",
        )
    )
    return _success(
        f"advisory review packet at {packet_path}",
        diagnostics=diagnostics,
        workspace=origin.as_dict(),
        scope=preview.as_dict(),
        rules={**resolution.as_dict(), "assignments": assignments.as_dict()["assignments"]},
        sdd=sdd.as_dict(),
        budget=budget_report.as_dict(),
        packet={**packet.as_dict(), "path": str(packet_path)},
    )


def _point_at_latest(directory: Path) -> None:
    """A stable path to the newest run, beside the per-run directories.

    A symlink where the platform allows one, a one-line pointer file otherwise:
    Windows refuses symlinks without a privilege this extension will not ask for.
    """

    latest = directory.parent / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(directory.name, target_is_directory=True)
    except (OSError, NotImplementedError):
        try:
            (directory.parent / "latest.txt").write_text(f"{directory.name}\n", encoding="utf-8")
        except OSError:
            pass


def _working_tree_rules(context: CommandContext, destination: Path) -> RuleResolution:
    """The rules that govern an advisory review: the working tree's own file.

    No commit is involved and none should be: the file on disk is the operator's
    own, and materializing it explicitly is still what keeps a personal
    ``~/.opencodereview/rule.json`` out of the review.
    """

    repository_rule_path = context.root / RULE_RELATIVE_PATH
    text = repository_rule_path.read_text(encoding="utf-8") if repository_rule_path.is_file() else None
    document = parse_rule_document(text, ref=None, origin=str(repository_rule_path))
    path = destination / "rule.effective.json"
    path.write_text(document.text if document.text is not None else '{"rules": []}\n', encoding="utf-8")
    return RuleResolution(document=document, path=path, ref_kind="working-tree", rule_source="repo")


# -- review: closing the session --------------------------------------------


def _reresolve_candidate(context: CommandContext, session: ReviewSession, *, timeout: int):
    """Resolve the candidate again, the way the first phase did.

    The point is to catch a candidate that moved *while the agent was reviewing*,
    so the resolution repeats the original path rather than trusting what the
    first phase wrote down: a pull-request session asks GitHub again, and a
    ``--base``/``--head`` session recomputes the merge base from the refs it
    recorded. Only then is ``candidate_id`` compared.
    """

    recorded = dict(session.payload.get("candidate") or {})
    selector = dict(session.payload.get("selector") or {})
    number = recorded.get("pr_number")
    if number:
        client = require_github(
            override=context.executable_override(f"{ENV_PREFIX}GH_BIN"),
            forbidden_roots=context.forbidden_roots,
            timeout=timeout,
        )
        return resolve_from_pull_request(
            context.git,
            client,
            parse_selector(str(number)),
            repository=recorded.get("repository") or selector.get("repository"),
            remote="origin",
            fetch_missing=False,
        )
    # The refs the operator named, not the SHAs they resolved to: a branch that
    # moved while the agent was reviewing is exactly the drift this catches, and
    # a recorded SHA can never move.
    base = selector.get("base_ref") or recorded.get("base_commit") or recorded.get("merge_base")
    head = selector.get("head_ref") or recorded.get("head_commit")
    if not base or not head:
        raise AppError(
            "this session does not record enough to re-resolve its candidate",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    "session_candidate_incomplete",
                    "the second phase re-resolves the candidate before normalizing anything; a session without its "
                    "refs cannot be verified",
                    str(session.path),
                )
            ],
        )
    return resolve_from_refs(context.git, base=str(base), head=str(head)), None


def _verify_session_correspondence(session: ReviewSession, candidate, diagnostics: list[Diagnostic]) -> None:
    """Fail closed on anything that says "this is not the review that was opened".

    Any discrepancy is exit code 8 and **nothing is normalized**. The two causes
    are reported differently on purpose -- a moved head and a moved merge base
    need different explanations -- and the packet digest is checked as well,
    because a session whose packet was replaced between the phases describes a
    review that never happened.
    """

    recorded = dict(session.payload.get("candidate") or {})
    drift = detect_drift(
        previous_head=recorded.get("head_commit"),
        previous_merge_base=recorded.get("merge_base"),
        current_head=candidate.head_commit,
        current_merge_base=candidate.merge_base,
    )
    if drift is not None:
        raise AppError(
            f"the candidate changed while it was being reviewed: its {drift.kind} moved",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    f"drift_{drift.kind}",
                    f"{drift.previous} -> {drift.current}. The findings describe the previous candidate, so nothing "
                    "is normalized. Review the new candidate instead.",
                    str(session.path),
                )
            ],
        )
    if recorded.get("candidate_id") and recorded["candidate_id"] != candidate.candidate_id:
        raise AppError(
            "this session belongs to a different candidate",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    "session_candidate_mismatch",
                    f"session {recorded['candidate_id']}, resolved {candidate.candidate_id}",
                    str(session.path),
                )
            ],
        )

    recorded_digest = str(session.payload.get("packet_sha256") or "")
    packet_path = session.path / PACKET_FILENAME
    if not recorded_digest or not packet_path.is_file():
        raise AppError(
            "this session has no packet to verify the findings against",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    "session_packet_missing",
                    "the findings are validated against the packet the first phase produced; without it there is "
                    "nothing to correspond to",
                    str(session.path),
                )
            ],
        )
    current = packet_digest(packet_path.read_text(encoding="utf-8"), session.payload.get("containment_suffix") or "")
    if current != recorded_digest:
        raise AppError(
            "the review packet changed after it was written",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    "packet_sha256_mismatch",
                    f"session {recorded_digest}, packet on disk {current}. The findings were produced from a document "
                    "this session no longer describes.",
                    str(packet_path),
                )
            ],
        )
    diagnostics.append(
        Diagnostic(
            "session_verified",
            f"candidate {candidate.candidate_id} and packet {recorded_digest[:12]} match the open session",
            severity="info",
        )
    )


def _verify_frozen_configuration(session: ReviewSession, config, diagnostics: list[Diagnostic]) -> None:
    """The configuration closing the session must be the one that opened it."""

    recorded = str(session.payload.get("config_sha256") or "")
    if not recorded:
        # Fail closed: a session that does not say which configuration governed
        # it cannot be continued under one this invocation merely happens to have.
        raise AppError(
            "this session does not record the configuration it was opened with",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    "session_config_unverifiable",
                    "the review continues only under the configuration it started with, and this session cannot "
                    "prove which that was",
                    str(session.path),
                )
            ],
        )
    if recorded == config.sha256:
        return
    raise AppError(
        "the configuration changed while the review was being read",
        code=EXIT_CONFIGURATION,
        diagnostics=[
            Diagnostic(
                "config_sha256_mismatch",
                f"the session was opened with configuration {recorded[:12]}, and {config.sha256[:12]} is in effect "
                "now. The configuration governs the whole review -- the budget, the publication ceiling, the packet "
                "limits -- so it does not continue under a different one.",
                str(session.path),
            )
        ],
    )


def _findings_path_for_session(value: str, session: ReviewSession) -> Path:
    """Resolve findings only from the exact file the session it closes expects.

    Equality, not containment: a sibling file living inside the session
    directory (a stale ``findings.json`` from a prior attempt, the packet
    itself) must be refused exactly like a path outside it, or it would
    survive a reopen and let the next review close on reused findings.
    """

    expected = session.path / FINDINGS_FILENAME
    mismatch = AppError(
        f"--findings must resolve inside the session it closes; expected {expected}",
        code=EXIT_USAGE,
        diagnostics=[
            Diagnostic(
                "findings_session_mismatch",
                f"write this review's findings to {expected} and pass that path with --findings",
                value,
            )
        ],
    )
    try:
        # `expanduser` raises `RuntimeError` for a named user it cannot look up
        # (``~nosuchuser``); inside the try, that is this usage error too,
        # rather than an unhandled exit 9.
        resolved = Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise mismatch from error
    if resolved != expected:
        raise mismatch
    return resolved


def _review_phase_two(args: argparse.Namespace) -> dict[str, Any]:
    """``--findings PATH --session PATH``: normalize, verdict, withdraw, close."""

    if not args.session:
        raise AppError(
            "--findings requires --session PATH",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "session_path_missing",
                    "no session is ever guessed, not even when only one is open: the findings belong to exactly one "
                    "candidate",
                )
            ],
        )
    session = require_open(load_session(Path(args.session)))
    findings_path = _findings_path_for_session(args.findings, session)

    context = _open_context(args)
    diagnostics: list[Diagnostic] = list(context.environment.diagnostics)
    config = load_config(context.root, explicit=args.config, environment=context.environment)
    diagnostics.extend(config.diagnostics)
    timeout = _timeout(config)

    _verify_frozen_configuration(session, config, diagnostics)
    recorded_root = session.repository_root
    if recorded_root is not None and recorded_root.resolve() != context.root:
        raise AppError(
            "this session belongs to another repository",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "session_repository_mismatch",
                    f"the session was opened against {recorded_root}; this invocation is in {context.root}",
                    str(session.path),
                )
            ],
        )

    # Order matters: the correspondence is verified *before* the findings are
    # even read, so a drifted candidate never gets as far as normalization.
    candidate, pull_request = _reresolve_candidate(context, session, timeout=timeout)
    _verify_session_correspondence(session, candidate, diagnostics)

    entries, source_digest = load_document(findings_path)
    hunks = load_hunks(context.git, merge_base=candidate.merge_base, head_commit=candidate.head_commit)
    diagnostics.extend(hunks.diagnostics)
    normalized = normalize_findings(
        entries,
        git=context.git,
        head_commit=candidate.head_commit,
        merge_base=candidate.merge_base,
        hunks=hunks,
        source_sha256=source_digest,
    )
    diagnostics.extend(normalized.diagnostics)

    causes = _inconclusive_causes(session)
    review_verdict = derive_verdict(normalized.findings, causes=causes)

    prepared = _prepared_from_session(context, session)
    outcome = restore(prepared)
    diagnostics.extend(outcome.diagnostics)
    environment_record = dict(session.payload.get("environment") or {})
    environment_record["restore"] = outcome.as_dict()
    session.payload["environment"] = environment_record
    write_environment(session, environment_record)
    if not outcome.restored:
        # The session stays open: the environment still exists, and the operator
        # needs the same command to work again after rescuing what it holds.
        session.payload["last_restore_attempt"] = outcome.as_dict()
        session.write()
        raise AppError(
            "the review environment could not be withdrawn",
            code=outcome.code or EXIT_ENVIRONMENT,
            diagnostics=diagnostics,
        )

    suffix = str(session.payload.get("containment_suffix") or new_suffix())
    budget = session.payload.get("budget") or {}
    plan = build_publication_plan(
        candidate=_PublicationCandidate(
            candidate_id=candidate.candidate_id,
            head_commit=candidate.head_commit,
            merge_base=candidate.merge_base,
            repository=candidate.repository,
            pr_number=candidate.pr_number,
            author=getattr(pull_request, "author", "") or "",
        ),
        verdict=review_verdict,
        findings=normalized.findings,
        packet_sha256=str(session.payload.get("packet_sha256") or ""),
        suffix=suffix,
        budget=_BudgetView(budget) if budget else None,
        event_ceiling=str(config.get("publish", "event", "request-changes")),
        request_changes=review_verdict.value == "changes-requested",
        # Read-only, and it decides whether REQUEST_CHANGES is even possible:
        # GitHub refuses it from the author of the pull request, so a plan built
        # without it would promise an event the publication stage cannot send.
        authenticated_user=_authenticated_user(context, diagnostics) if candidate.pr_number else None,
        batch_size=int(config.get("publish", "batch_size", 25) or 25),
        max_inline_comments=int(config.get("publish", "max_inline_comments", 100) or 100),
        evidence_path=str(session.path),
    )
    diagnostics.extend(plan.diagnostics)

    # `findings_path` (the agent's input, verified above to be exactly
    # `FINDINGS_FILENAME`) is never rewritten: the normalized document is a
    # derived artifact and gets its own name, or this write would destroy the
    # very input `findings_sha256` below is the digest of.
    write_json(
        session.path / FINDINGS_NORMALIZED_FILENAME, {**normalized.as_dict(), "verdict": review_verdict.as_dict()}
    )
    write_text(session.path / FINDINGS_MARKDOWN_FILENAME, render_findings_markdown(normalized.findings, suffix=suffix))
    write_json(session.path / PUBLICATION_PLAN_FILENAME, plan.as_dict())

    code = review_verdict.exit_code()
    session.mark(
        PHASE_CLOSED,
        environment_restored=True,
        restore=outcome.as_dict(),
        verdict=review_verdict.as_dict(),
        findings_sha256=source_digest,
        findings_count=len(normalized.findings),
        publication_plan_sha256=plan.summary_sha256,
        exit_code=code,
    )
    diagnostics.append(
        Diagnostic(
            "findings_written",
            f"findings and the publication plan are in {session.path}",
            str(session.path),
            severity="info",
        )
    )

    payload = review_document(
        retryable=any(cause.kind == CAUSE_ENGINE for cause in review_verdict.causes),
        candidate=candidate,
        engine=session.payload.get("engine"),
        packet_sha256=str(session.payload.get("packet_sha256") or ""),
        rules_sha256=(session.payload.get("rules") or {}).get("sha256"),
        scope=session.payload.get("scope"),
        budget=budget,
        findings=normalized,
        verdict=review_verdict,
        code=code,
        diagnostics=diagnostics,
        session=session.summary(),
        publication_plan=plan.as_dict(),
    )
    payload["human"] = render_human(
        findings=normalized,
        verdict=review_verdict,
        budget=budget,
        evidence_path=str(session.path),
        packet_sha256=str(session.payload.get("packet_sha256") or ""),
    )
    if args.publish:
        # Publication is always explicit, and always after the review is closed
        # and its plan persisted -- so a publication that fails leaves a
        # complete, inspectable review behind rather than an ambiguous state.
        published = _publish_session(context, config, session, diagnostics, timeout=timeout)
        payload["publication"] = published["publication"]
        payload["publication_plan"] = published["publication_plan"]
        payload["operations"] = published.get("operations", [])
        payload["diagnostics"] = [item.as_dict() for item in diagnostics]
        payload["message"] = published["message"]
    return payload


@dataclass(frozen=True)
class _PublicationCandidate:
    """The handful of candidate facts the publication plan needs."""

    candidate_id: str
    head_commit: str
    merge_base: str
    repository: str | None
    pr_number: int | None
    author: str


class _BudgetView:
    """A read-only view of the budget as ``session.json`` recorded it."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.counted = payload.get("counted", 0)
        self.limit = payload.get("limit", 0)
        self.over_budget = bool(payload.get("over_budget"))


ENGINE_STATUS_COMPLETE: tuple[str, ...] = ("success", "completed_with_warnings")


def _inconclusive_causes(session: ReviewSession) -> list[InconclusiveCause]:
    """Everything the first phase recorded that means "the scope was not covered".

    An engine that failed, or a truncation that kept part of the candidate out of
    the packet. They are read from the session rather than recomputed, because
    the first phase is where they happened.
    """

    causes: list[InconclusiveCause] = []
    packet = session.payload.get("packet") or {}
    for truncation in packet.get("truncations") or ():
        causes.append(
            InconclusiveCause(
                CAUSE_SCOPE,
                f"{truncation.get('path')}: {truncation.get('omitted_bytes')} byte(s) did not fit in the packet, so "
                f"that content was not reviewed ({truncation.get('command')})",
            )
        )
    # An allowlist, deliberately: a status this version does not know is a status
    # whose meaning it cannot vouch for, and calling an unknown status "fine" is
    # exactly the silent half-coverage `inconclusive` exists to prevent.
    engine_status = (session.payload.get("engine") or {}).get("status")
    if engine_status is not None and engine_status not in ENGINE_STATUS_COMPLETE:
        causes.append(
            InconclusiveCause(
                CAUSE_ENGINE,
                f"the engine reported status {engine_status!r}, which is not one of the statuses that mean the "
                f"scope was covered ({', '.join(ENGINE_STATUS_COMPLETE)})",
            )
        )
    # Discarded findings are deliberately *not* a cause: a hallucinated finding
    # says something about the reviewer, not about the coverage of the candidate.
    return causes


# -- publication -------------------------------------------------------------


def _reverify_before_publishing(
    context: CommandContext,
    session: ReviewSession,
    plan_payload: Mapping[str, Any],
    diagnostics: list[Diagnostic],
    *,
    timeout: int,
):
    """Resolve the candidate again, immediately before the first POST.

    A pull request whose head moved while the review was being read describes a
    different candidate, and publishing the old findings against the new code is
    the one mistake that cannot be withdrawn -- deleting a comment is a forbidden
    operation. So the check runs here, against both halves of the range, and any
    difference is exit code 8 with zero writes.
    """

    candidate, pull_request = _reresolve_candidate(context, session, timeout=timeout)
    drift = detect_drift(
        previous_head=str(plan_payload.get("head_commit") or "") or None,
        previous_merge_base=str(plan_payload.get("merge_base") or "") or None,
        current_head=candidate.head_commit,
        current_merge_base=candidate.merge_base,
    )
    if drift is not None:
        raise AppError(
            f"the candidate changed since this review was produced: its {drift.kind} moved",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    f"drift_{drift.kind}",
                    f"{drift.previous} -> {drift.current}. Nothing was published: findings anchored to the previous "
                    "candidate would point at lines this one does not have.",
                    str(session.path),
                )
            ],
        )
    if plan_payload.get("candidate_id") and plan_payload["candidate_id"] != candidate.candidate_id:
        raise AppError(
            "this publication plan belongs to a different candidate",
            code=EXIT_DRIFT,
            diagnostics=[
                Diagnostic(
                    "session_candidate_mismatch",
                    f"plan {plan_payload['candidate_id']}, resolved {candidate.candidate_id}",
                    str(session.path),
                )
            ],
        )
    state = str(getattr(candidate, "state", "") or "").upper()
    if state and state != "OPEN":
        raise AppError(
            f"this pull request is {state.lower()}, not open",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "publish_pull_request_not_open",
                    "publishing a review on a merged or closed pull request is not something this extension does",
                )
            ],
        )
    diagnostics.append(
        Diagnostic(
            "publish_reverified",
            f"the candidate still resolves to {candidate.candidate_id} ({candidate.merge_base}..{candidate.head_commit})",
            severity="info",
        )
    )
    return candidate, pull_request


def _publish_session(
    context: CommandContext,
    config,
    session: ReviewSession,
    diagnostics: list[Diagnostic],
    *,
    timeout: int,
) -> dict[str, Any]:
    """Publish the plan a closed session holds. The only remote-write path."""

    plan_path = session.path / PUBLICATION_PLAN_FILENAME
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    # Before anything remote, and before `gh` is even required: a session with no
    # pull request has nothing to publish to.
    _require_publishable(plan_payload, session)

    client = require_github(
        override=context.executable_override(f"{ENV_PREFIX}GH_BIN"),
        forbidden_roots=context.forbidden_roots,
        timeout=timeout,
    )
    ledger = Ledger()
    # The event is re-decided against the *current* facts rather than replayed
    # from the plan: the ceiling may have been lowered, and the authenticated
    # identity may be the author this time.
    authenticated = client.authenticated_user(ledger=ledger)
    ceiling = str(config.get("publish", "event", "request-changes"))
    verdict = _verdict_from_payload(plan_payload)
    requested = verdict.value == "changes-requested"
    current = client.pull_request(
        int(plan_payload["pr_number"]), repository=str(plan_payload["repository"]), ledger=ledger
    )
    event = resolve_event(
        verdict=verdict,
        ceiling=ceiling,
        requested=requested,
        authenticated_user=authenticated,
        author=current.author,
        diagnostics=diagnostics,
    )
    plan = _plan_from_payload(plan_payload, event=event)

    candidate, _pull_request = _reverify_before_publishing(context, session, plan_payload, diagnostics, timeout=timeout)
    # The evidence must not disagree with itself: the plan on disk recorded the
    # event this run *would* have used, and this run re-decided it.
    if plan_payload.get("event") != plan.event:
        plan_payload["event"] = plan.event
        plan_payload["event_redecided_at_publication"] = True
        write_json(plan_path, plan_payload)

    previous_result = None
    result_path = session.path / PUBLICATION_RESULT_FILENAME
    if result_path.is_file():
        try:
            previous_result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous_result = None

    try:
        result = execute_publication(
            plan,
            client,
            ledger=ledger,
            conditions=EventConditions(
                ceiling=ceiling,
                requested=requested,
                verdict=plan.verdict_value or plan.verdict,
                author_is_authenticated_user=bool(
                    authenticated and current.author and authenticated.casefold() == current.author.casefold()
                ),
            ),
            max_scanned_comments=int(config.get("publish", "max_scanned_comments", 300) or 300),
            max_listed_files=int(config.get("publish", "max_listed_files", 3000) or 3000),
            previous_result=previous_result,
        )
    except PublicationFailed as failure:
        # The failure is reported with exactly what landed, and the partial state
        # is persisted before the command exits.
        write_json(session.path / PUBLICATION_RESULT_FILENAME, failure.result.as_dict())
        diagnostics.extend(failure.result.diagnostics)
        raise AppError("the review could not be published in full", code=failure.code, diagnostics=diagnostics) from failure

    diagnostics.extend(result.diagnostics)
    write_json(session.path / PUBLICATION_RESULT_FILENAME, result.as_dict())
    session.payload["published"] = True
    session.payload["publication"] = result.as_dict()
    session.write()
    diagnostics.append(
        Diagnostic(
            "published",
            f"review published as {result.event}: {result.posted_inline} inline comment(s) and the summary at "
            f"{result.summary_comment_url or '(url unknown)'}",
            severity="info",
        )
    )
    return _success(
        f"review published to {plan.repository}#{plan.pr_number} as {result.event}",
        diagnostics=diagnostics,
        candidate=candidate.as_dict(),
        publication_plan=plan.as_dict(),
        publication=result.as_dict(),
        operations=ledger.as_list(),
    )


def _require_publishable(plan_payload: Mapping[str, Any], session: ReviewSession) -> None:
    """A plan without a pull request cannot be published, and says so early."""

    repository = plan_payload.get("repository")
    pr_number = plan_payload.get("pr_number")
    if not repository or not pr_number:
        raise AppError(
            "this review has no pull request to publish to",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "publish_no_pull_request",
                    "a review resolved with --base/--head has no pull request. The review itself is complete and in "
                    "the evidence; publish a candidate resolved from a pull-request selector.",
                    str(session.path),
                )
            ],
        )
    # Defence in depth: these two came off disk and are interpolated into an API
    # path, so they are validated exactly as if they had come from the operator.
    validate_repository(str(repository))
    validate_number(str(pr_number))


def _verdict_from_payload(plan_payload: Mapping[str, Any]) -> Verdict:
    """The verdict as the closed session recorded it, for the event decision."""

    recorded = plan_payload.get("verdict")
    if isinstance(recorded, Mapping):
        return Verdict(value=str(recorded.get("value") or ""), blocking=int(recorded.get("blocking") or 0))
    return Verdict(
        value=str(plan_payload.get("verdict_value") or recorded or ""),
        blocking=int(plan_payload.get("verdict_blocking") or 0),
    )


def _plan_from_payload(plan_payload: Mapping[str, Any], *, event: str) -> PublicationPlan:
    """Rebuild the plan object from the evidence, with the event re-decided."""

    return PublicationPlan(
        candidate_id=str(plan_payload.get("candidate_id") or ""),
        head_commit=str(plan_payload.get("head_commit") or ""),
        merge_base=str(plan_payload.get("merge_base") or ""),
        repository=plan_payload.get("repository"),
        pr_number=plan_payload.get("pr_number"),
        event=event,
        verdict=str(plan_payload.get("verdict") or ""),
        verdict_value=str(plan_payload.get("verdict_value") or plan_payload.get("verdict") or ""),
        verdict_blocking=int(plan_payload.get("verdict_blocking") or 0),
        summary_marker=str(plan_payload.get("summary_marker") or ""),
        summary_body=str(plan_payload.get("summary_body") or ""),
        findings_sha256=str(plan_payload.get("findings_sha256") or ""),
        inline=tuple(
            InlineComment(
                finding_id=str(comment.get("finding_id") or ""),
                path=str(comment.get("path") or ""),
                line=int(comment.get("line") or 1),
                start_line=comment.get("start_line"),
                side=str(comment.get("side") or "RIGHT"),
                body=str(comment.get("body") or ""),
            )
            for comment in plan_payload.get("inline_comments") or ()
        ),
        degraded=tuple(plan_payload.get("degraded") or ()),
        batches=tuple(tuple(batch) for batch in plan_payload.get("batches") or ()),
    )


def _prepared_from_session(context: CommandContext, session: ReviewSession) -> PreparedEnvironment:
    """Rebuild the prepared environment a previous first phase recorded."""

    payload = session.payload.get("environment") or {}
    # Session documents persist redacted paths (the home directory becomes
    # `~`); expand on the way back in, or restore() tests a literal-tilde
    # relative path, concludes "already gone", and leaks the worktree.
    worktree_value = payload.get("worktree_path")
    worktree_path = Path(worktree_value).expanduser() if worktree_value else None
    working_root = Path(str(payload.get("working_root") or context.root)).expanduser()
    working_git = (
        Git(context.git.executable, root=working_root, timeout=context.git.timeout)
        if working_root != context.root
        else context.git
    )
    return PreparedEnvironment(
        head_commit=str(session.head_commit or ""),
        repository_root=context.root,
        working_root=working_root,
        git=working_git,
        worktree_path=worktree_path,
        forbidden_roots=tuple(Path(item).expanduser() for item in payload.get("forbidden_roots") or ()),
    )


def _authenticated_user(context: CommandContext, diagnostics: list[Diagnostic]) -> str | None:
    """Best-effort ``gh`` identity; never fails the command."""

    client = open_github(
        override=context.executable_override(f"{ENV_PREFIX}GH_BIN"),
        forbidden_roots=context.forbidden_roots,
    )
    if client is None:
        diagnostics.append(
            Diagnostic("gh_missing", "gh was not found on PATH; the authenticated GitHub identity is unknown", severity="warning")
        )
        return None
    if not client.auth_status().authenticated:
        diagnostics.append(
            Diagnostic("gh_unauthenticated", "gh is not authenticated; run `gh auth login` yourself", severity="warning")
        )
        return None
    return client.authenticated_user()


# -- entry point ------------------------------------------------------------


def _verbose_requested(args: argparse.Namespace) -> bool:
    """``--verbose``, or ``SPECKIT_CODE_REVIEW_LOG_LEVEL=debug`` in the snapshot."""

    from .config import env_verbose

    if getattr(args, "verbose", False):
        return True
    return env_verbose(getattr(args, "_environment", None))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    _ArgumentParser.json_requested = "--json" in (argv if argv is not None else sys.argv[1:])
    args = parser.parse_args(argv)
    try:
        if args.command == "completions":
            sys.stdout.write(generate_completion_script(args.shell, parser))
            return EXIT_SUCCESS
        if args.command == "doctor":
            payload = run_doctor_command(args)
        elif args.command == "review":
            payload = run_review(args)
        else:  # argparse makes this unreachable, but keeps the boundary explicit.
            raise AppError(
                f"unsupported command: {args.command}",
                code=EXIT_USAGE,
                diagnostics=[Diagnostic("command", "supported commands are review, doctor, and completions")],
            )
        _render(payload, args.json, args.quiet)
        if _verbose_requested(args) and not args.json and not args.quiet:
            _render_verbose(payload)
        # A completed review can still exit non-zero -- changes-requested, an
        # inconclusive verdict with an engine cause -- and that code travels in
        # the payload rather than as an exception, because the review *did*
        # complete and its whole document must still be rendered.
        return int(payload.get("code", EXIT_SUCCESS) or EXIT_SUCCESS)
    except AppError as error:
        payload = {
            "code": error.code,
            "category": error.category,
            "message": str(error),
            "retryable": error.retryable,
            "operations": [],
            "diagnostics": [diagnostic.as_dict() for diagnostic in error.diagnostics],
        }
        # Failure text is the likeliest place for a relayed credential (a `gh`
        # stderr line, an environment value), so the catalog applies here too.
        payload = redact_payload(payload)
        if getattr(args, "json", False):
            _write_json(payload)
        elif not getattr(args, "quiet", False):
            sys.stderr.write(f"error: {payload['message']}\n")
            for diagnostic in payload["diagnostics"]:
                if diagnostic["severity"] == "info":
                    continue
                location = f" ({diagnostic['path']})" if "path" in diagnostic else ""
                line = f":{diagnostic['line']}" if "line" in diagnostic else ""
                sys.stderr.write(f"  {diagnostic['code']}{location}{line}: {diagnostic['message']}\n")
        return error.code
    except (KeyboardInterrupt, SignalInterrupt) as interruption:
        # 130 means the environment was restored correctly -- and it is only
        # reachable when that is true. A restoration that failed raises
        # AppError(7) from the cleanup block and is handled above.
        payload = {
            "code": EXIT_INTERRUPTED,
            "category": EXIT_CATEGORIES[EXIT_INTERRUPTED],
            "message": "interrupted; no review environment was left prepared",
            "retryable": True,
            "operations": [],
            "diagnostics": [Diagnostic("interrupted", str(interruption)).as_dict()],
        }
        if getattr(args, "json", False):
            _write_json(payload)
        elif not getattr(args, "quiet", False):
            sys.stderr.write(f"error: {payload['message']}\n")
        return EXIT_INTERRUPTED
    except Exception as unexpected:  # noqa: BLE001 - last resort, never a traceback
        # An unexpected failure must still speak the public contract: exit 1
        # means "changes-requested" and a traceback means nothing to a caller
        # parsing JSON. 9 is the internal-failure code of the table.
        payload = {
            "code": EXIT_ENGINE,
            "category": EXIT_CATEGORIES[EXIT_ENGINE],
            "message": f"unexpected internal failure: {type(unexpected).__name__}",
            "retryable": False,
            "operations": [],
            "diagnostics": [Diagnostic("internal_error", redact_text(str(unexpected))).as_dict()],
        }
        payload = redact_payload(payload)
        if getattr(args, "json", False):
            _write_json(payload)
        elif not getattr(args, "quiet", False):
            sys.stderr.write(f"error: {payload['message']}\n")
            sys.stderr.write(f"  internal_error: {payload['diagnostics'][0]['message']}\n")
        return EXIT_ENGINE


if __name__ == "__main__":
    raise SystemExit(main())
