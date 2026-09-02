"""Where the pinned engine is found, and the one command allowed to install it.

Resolution order, for every command:

1. ``SPECKIT_CODE_REVIEW_OCR_BIN``, from the real process environment or the
   operator's own env file -- an explicit choice, verified like anything else;
2. the canonical pinned path,
   ``${XDG_DATA_HOME:-~/.local/share}/tserdeiro/spec-kit/tools/ocr/<version>/``,
   for the tag the lock pins.

``PATH`` is deliberately absent from that list. The npm package installs a JS
shim named ``ocr``; its digest is never the pinned one, so resolving it could
only ever produce a digest mismatch an operator has to diagnose after the fact.
The canonical path names the real platform binary, which is what the lock's
``binaries`` digests are of.

The installation policy, since 2026-08-03:

- ``review`` never installs, downloads or updates anything, on any path. It
  resolves, re-verifies, and refuses.
- ``doctor --fix`` installs, and only: the engine the lock pins, at the version
  the lock pins, into this distribution's data root -- never global, never
  inside the tree under review, which the executable guard refuses anyway.
- What is installed is verified against the lock before it is left on disk. A
  digest that does not match is not a warning: the tree is removed, so an
  unverified binary never survives the command that produced it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .env_files import ENV_PREFIX
from .errors import AppError, Diagnostic
from .paths import (
    OCR_NPM_PACKAGE,
    OCR_TOOL_NAME,
    TOOLS_DIRECTORY,
    data_root,
    ocr_install_argv,
    ocr_install_command,
    ocr_uninstall_command,
    tool_executable,
    tool_root,
)
from .process import DEFAULT_TIMEOUT_SECONDS, resolve_executable, run_command, sha256_file
from .redaction import redact_text


DEFAULT_OCR_TAG = "v1.8.3"
OCR_RELEASES_URL = "https://github.com/alibaba/open-code-review/releases/tag/{tag}"


def canonical_executable(tag: str, environment: Mapping[str, str] | None = None) -> Path:
    """The pinned engine's own path under this distribution's data root."""

    return tool_executable(OCR_TOOL_NAME, tag, environment)


def resolve_engine(
    *,
    tag: str,
    override: str | None = None,
    forbidden_roots: Sequence[Path] = (),
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    """The engine for this run: the operator's override, else the pinned path.

    Both go through the same executable guard -- an absolute path with symlinks
    resolved, never inside the tree under review -- and both are verified
    against the lock by the caller. ``None`` means "not installed", which is a
    diagnosis for the caller to phrase.
    """

    if override:
        return resolve_executable(OCR_TOOL_NAME, override=override, forbidden_roots=forbidden_roots)
    canonical = canonical_executable(tag, environment)
    if not canonical.is_file():
        return None
    return resolve_executable(OCR_TOOL_NAME, override=str(canonical), forbidden_roots=forbidden_roots)


@dataclass(frozen=True)
class InstallOutcome:
    """What ``doctor --fix`` did about a missing engine, and what to report."""

    path: Path | None = None
    applied: str | None = None
    diagnostic: Diagnostic | None = None


def install_engine(
    *,
    tag: str,
    package: str | None = None,
    expected_digest: str | None = None,
    platform: str = "this platform",
    environment: Mapping[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> InstallOutcome:
    """Install the pinned engine into the data root, or leave nothing behind.

    Fail-closed by construction: every path that cannot end in a binary whose
    digest matches the lock removes the directory it created. The only outcome
    that keeps an unverified binary is a lock that pins no digest for this
    platform at all, which is reported as a warning -- the same reading the
    review path already gives an engine it cannot verify.
    """

    destination = tool_root(OCR_TOOL_NAME, tag, environment)
    binary = canonical_executable(tag, environment)

    npm = shutil.which("npm")
    if npm is None:
        return InstallOutcome(
            diagnostic=Diagnostic(
                "npm_missing",
                "npm was not found on PATH, and the pinned engine is distributed as an npm package. Install Node.js "
                f"and re-run `doctor --fix`, or install the engine yourself:\n  {ocr_install_command(tag, environment, package=package)}",
            )
        )

    argv = ocr_install_argv(npm, tag, environment, package=package)
    if argv is None:
        return InstallOutcome(
            diagnostic=Diagnostic(
                "ocr_install_unpinnable",
                f"the lock pins {tag!r}, which is not a release tag; there is no npm specifier to install",
            )
        )

    try:
        destination.mkdir(parents=True, exist_ok=True)
        # npm warns and ignores `--save-exact` when the prefix has no manifest,
        # so the install would not pin what it says it pins.
        (destination / "package.json").write_text("{}\n", encoding="utf-8")
    except OSError as error:
        return InstallOutcome(
            diagnostic=Diagnostic("ocr_install_failed", f"could not prepare {destination}: {error}", str(destination))
        )

    try:
        invocation = run_command(argv, timeout=timeout)
    except AppError as error:
        _discard(destination, environment)
        return InstallOutcome(
            diagnostic=Diagnostic(
                "ocr_install_failed",
                f"the install did not complete ({error}); {destination} was removed",
                str(destination),
            )
        )

    if not invocation.ok:
        _discard(destination, environment)
        return InstallOutcome(
            diagnostic=Diagnostic(
                "ocr_install_failed",
                f"npm exited {invocation.returncode}; {destination} was removed. "
                f"{redact_text(_tail(invocation.stderr or invocation.stdout))}",
                str(destination),
            )
        )

    if not binary.is_file():
        _discard(destination, environment)
        return InstallOutcome(
            diagnostic=Diagnostic(
                "ocr_install_incomplete",
                f"the install succeeded but {binary.name} is not at {binary}; the engine may publish no platform "
                f"package for {platform}. {destination} was removed.",
                str(destination),
            )
        )

    observed = sha256_file(binary)
    if expected_digest is None:
        return InstallOutcome(
            path=binary,
            applied=f"installed ocr {tag} into {destination}",
            diagnostic=Diagnostic(
                "ocr_install_unverified",
                f"the lock pins no binary digest for {platform}, so the engine installed at {binary} could not be "
                "verified against it",
                str(binary),
                severity="warning",
            ),
        )
    if observed != expected_digest:
        _discard(destination, environment)
        return InstallOutcome(
            diagnostic=Diagnostic(
                "ocr_install_digest_mismatch",
                f"the installed binary digest {observed} does not match the {platform} digest pinned in the lock; "
                f"{destination} was removed and no unverified engine was left on disk",
                str(destination),
            )
        )
    return InstallOutcome(
        path=binary,
        applied=f"installed ocr {tag} into {destination}, digest verified against the lock",
    )


def ocr_install_hint(tag: str, package: str | None = None) -> str:
    """The remediation printed when ``ocr`` is missing.

    ``doctor --fix`` is the answer, and the manual command stays beside it: an
    operator who prefers to install it themselves, or whose machine has no npm,
    needs the resolved command more than a suggestion to re-run a command.
    """

    return (
        f"ocr was not found. Run `doctor --fix`: it installs open-code-review {tag} into this distribution's data "
        "root and verifies its digest against the lock. A review never installs anything.\n"
        f"To install it yourself instead:\n"
        f"  {ocr_install_command(tag, package=package or OCR_NPM_PACKAGE)}\n"
        f"Either way the engine ends up at:\n"
        f"  {canonical_executable(tag)}\n"
        f"Point {ENV_PREFIX}OCR_BIN somewhere else only to use a binary of your own -- and not at "
        "`node_modules/.bin/ocr`, which is a JS shim whose digest is not the one the lock pins.\n"
        f"To remove it again: {ocr_uninstall_command(tag)}\n"
        f"Releases: {OCR_RELEASES_URL.format(tag=tag)}"
    )


def _discard(destination: Path, environment: Mapping[str, str] | None) -> None:
    """Remove a directory this module created, and never anything else."""

    tools = data_root(environment) / TOOLS_DIRECTORY / OCR_TOOL_NAME
    try:
        resolved = destination.resolve()
    except OSError:
        return
    if tools.resolve() not in resolved.parents:
        return
    shutil.rmtree(resolved, ignore_errors=True)


def _tail(text: str, lines: int = 3) -> str:
    return " ".join((text or "").strip().splitlines()[-lines:]).strip()
