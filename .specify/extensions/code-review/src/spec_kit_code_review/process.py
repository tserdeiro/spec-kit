"""Argv-only subprocess execution and safe external executable resolution."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .errors import EXIT_ENGINE, EXIT_PREREQUISITE, AppError, Diagnostic


DEFAULT_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class CommandResult:
    """The captured result of one external invocation."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    stdin: str | None = None,
) -> CommandResult:
    """Run ``argv`` without a shell and capture its output.

    Doc "Inyeccion de opciones": every external invocation uses an argv list,
    never ``shell=True`` and never string concatenation. A timeout is an engine
    failure (exit code 9) carrying the exact invocation, never a silent partial
    result.
    """

    command = [str(item) for item in argv]
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            # A request body goes in on stdin, never in argv: it carries the
            # candidate's own text, and argv is visible to every process on the
            # machine.
            input=stdin,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise AppError(
            f"executable not found: {command[0]}",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("executable_missing", "install it and re-run; a review never installs anything", command[0])],
        ) from error
    except subprocess.TimeoutExpired as error:
        raise AppError(
            f"external invocation timed out after {timeout}s: {' '.join(command)}",
            code=EXIT_ENGINE,
            diagnostics=[Diagnostic("invocation_timeout", "the invocation exceeded the configured timeout", command[0])],
            retryable=True,
        ) from error
    if completed.returncode in (-signal.SIGINT, -signal.SIGTERM):
        # The child died from the operator's own Ctrl-C/termination of the
        # process group. Classifying its exit as a tool failure would report
        # an interruption as a prerequisite or engine error; propagate the
        # interruption instead, and let the interrupt handler answer 130.
        raise KeyboardInterrupt(f"{command[0]} was interrupted")
    return CommandResult(
        argv=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def resolve_executable(
    name: str,
    *,
    override: str | None = None,
    forbidden_roots: Sequence[Path] = (),
) -> Path | None:
    """Resolve ``name`` from a trusted override or ``PATH``; never from the candidate tree.

    Doc "Resolucion de ejecutables": ``gh`` and ``git`` are resolved exclusively
    from ``SPECKIT_CODE_REVIEW_*_BIN`` set in the real process environment or in
    ``${XDG_CONFIG_HOME:-~/.config}/tserdeiro/spec-kit/env``, or from ``PATH``.
    The engine does not use ``PATH`` at all -- ``engine.resolve_engine`` falls
    back to its canonical pinned path instead -- and calls this function with
    that path as the override, so one guard covers every executable.
    The resolved path is made absolute with symlinks resolved and rejected with
    exit code 4 when it falls inside any ``forbidden_roots`` entry -- the
    consumer repository toplevel, any active worktree of it, or this session's
    temporary worktree. An executable that lives in the tree under review is,
    by definition, candidate code.

    Returns ``None`` when the executable simply is not installed; that is a
    diagnosis for the caller to phrase, not an exception.
    """

    located = override or shutil.which(name)
    if not located:
        return None
    candidate = Path(located).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise AppError(
            f"{name} override does not exist: {candidate}",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("executable_override_missing", "the configured executable path does not exist", str(candidate))],
        ) from None
    for root in forbidden_roots:
        if _is_within(resolved, root):
            raise AppError(
                f"{name} resolves inside the repository under review: {resolved}",
                code=EXIT_PREREQUISITE,
                diagnostics=[
                    Diagnostic(
                        "executable_inside_candidate",
                        f"an executable inside {root} is candidate content and is never trusted",
                        str(resolved),
                    )
                ],
            )
    if not os.access(resolved, os.X_OK):
        raise AppError(
            f"{name} is not executable: {resolved}",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("executable_not_executable", "the resolved path is not executable", str(resolved))],
        )
    return resolved


def _is_within(path: Path, root: Path) -> bool:
    try:
        resolved_root = root.resolve()
    except OSError:
        return False
    if path == resolved_root:
        return True
    return resolved_root in path.parents


def sha256_file(path: Path) -> str | None:
    """Return the hex SHA-256 of ``path``, or ``None`` when it is not a readable regular file."""

    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Return the hex SHA-256 of ``text`` encoded as UTF-8."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
