"""Evidence-root resolution: always outside the consumer repository."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import EVIDENCE_DIR_ENV_VAR, ResolvedConfig
from .env_files import EnvSnapshot
from .paths import evidence_root as default_evidence_root
from .errors import EXIT_USAGE, AppError, Diagnostic


DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class EvidenceRoot:
    """The resolved evidence root and which source chose it."""

    path: Path
    source: str

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    @property
    def mode(self) -> int | None:
        try:
            return stat.S_IMODE(self.path.stat().st_mode)
        except OSError:
            return None

    @property
    def writable(self) -> bool:
        target = self.path
        while not target.exists() and target.parent != target:
            target = target.parent
        return os.access(target, os.W_OK)


def resolve_evidence_root(
    *,
    environment: EnvSnapshot | None = None,
    config: ResolvedConfig | None = None,
    forbidden_roots: Sequence[Path] = (),
) -> EvidenceRoot:
    """Resolve the evidence root, highest priority first, and refuse inside-repo paths.

    Order: ``SPECKIT_CODE_REVIEW_EVIDENCE_DIR``,
    ``evidence.root`` of the local configuration,
    ``${XDG_STATE_HOME}/tserdeiro/spec-kit/code-review``,
    ``~/.local/state/tserdeiro/spec-kit/code-review``.

    Any root that resolves inside the consumer repository toplevel, inside any
    active worktree of it, or inside this session's temporary worktree is
    rejected with exit code 2, whichever source proposed it. Allowing it "when
    the operator insists" would mean the guarantee is not a guarantee.
    """

    candidate: Path
    source: str
    if environment is not None and environment.get(EVIDENCE_DIR_ENV_VAR):
        candidate, source = Path(str(environment.get(EVIDENCE_DIR_ENV_VAR))).expanduser(), "environment"
    elif config is not None and config.get("evidence", "root"):
        candidate, source = Path(str(config.get("evidence", "root"))).expanduser(), "configuration"
    else:
        # Both remaining layers are the same path with a different origin, so
        # they are computed once and only their *source* differs -- which is
        # what the report shows the operator.
        # xdg-allowed: reads the variable only to label *which* source chose
        # the root; the root itself comes from `paths`.
        source = "xdg" if (os.environ.get("XDG_STATE_HOME") or "").strip() else "home"
        # The XDG variables are process-level, not part of the extension's own
        # `SPECKIT_CODE_REVIEW_` snapshot, so they are read from the process.
        candidate = default_evidence_root(None)

    resolved = _resolve_without_requiring_existence(candidate)
    for forbidden in forbidden_roots:
        forbidden_resolved = _resolve_without_requiring_existence(forbidden)
        if resolved == forbidden_resolved or forbidden_resolved in resolved.parents:
            raise AppError(
                f"the evidence root may not live inside the repository under review: {resolved}",
                code=EXIT_USAGE,
                diagnostics=[
                    Diagnostic(
                        "evidence_root_inside_repository",
                        f"rejected from the {source} source; it resolves inside {forbidden_resolved}",
                        str(resolved),
                    )
                ],
            )
    return EvidenceRoot(path=resolved, source=source)


def repository_id(repository: str | None, root: Path) -> str:
    """A stable slug for the evidence layout: from ``owner/name``, else from the path."""

    if repository:
        slug = _SLUG_RE.sub("-", repository.lower()).strip("-")
        if slug:
            return slug
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
    return f"path-{digest[:16]}"


def permission_diagnostics(evidence_root: EvidenceRoot) -> list[Diagnostic]:
    """Report the evidence root's resolvability, writability, and permissions."""

    diagnostics: list[Diagnostic] = [
        Diagnostic("evidence_root", f"{evidence_root.path} (from {evidence_root.source})", severity="info")
    ]
    if not evidence_root.exists:
        diagnostics.append(
            Diagnostic(
                "evidence_root_absent",
                "the evidence root does not exist yet; it is created on the first review",
                str(evidence_root.path),
                severity="info",
            )
        )
        if not evidence_root.writable:
            diagnostics.append(
                Diagnostic(
                    "evidence_root_unwritable",
                    "no writable ancestor for the evidence root",
                    str(evidence_root.path),
                    severity="warning",
                )
            )
        return diagnostics
    mode = evidence_root.mode
    if mode is not None and mode != DIRECTORY_MODE:
        diagnostics.append(
            Diagnostic(
                "evidence_root_permissions",
                f"expected mode {DIRECTORY_MODE:04o}, found {mode:04o}; evidence can contain the consumer's own secrets",
                str(evidence_root.path),
                severity="warning",
            )
        )
    if not evidence_root.writable:
        diagnostics.append(
            Diagnostic("evidence_root_unwritable", "the evidence root is not writable", str(evidence_root.path), severity="warning")
        )
    return diagnostics


def harden_directories(directory: Path) -> None:
    """Create every missing component of ``directory`` with ``0700``.

    The umask would otherwise leave an intermediate directory group- and
    world-readable, and the evidence tree holds diffs and repository content that
    can include the consumer's own legitimate secrets. Every writer under the
    evidence root goes through this.
    """

    missing: list[Path] = []
    probe = directory
    while not probe.exists() and probe.parent != probe:
        missing.append(probe)
        probe = probe.parent
    directory.mkdir(parents=True, exist_ok=True)
    for path in (*missing, directory):
        try:
            os.chmod(path, DIRECTORY_MODE)
        except OSError:
            continue


def ensure_root(evidence_root: EvidenceRoot) -> EvidenceRoot:
    """Create the evidence root with the documented ``0700`` permissions.

    It holds diffs and repository content that can include the consumer's own
    legitimate secrets, so it is never world- or group-readable.
    """

    try:
        evidence_root.path.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
        evidence_root.path.chmod(DIRECTORY_MODE)
    except OSError as error:
        raise AppError(
            f"the evidence root is not writable: {evidence_root.path}",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("evidence_root_unwritable", str(error), str(evidence_root.path))],
        ) from error
    return evidence_root


def enforce_permissions(evidence_root: EvidenceRoot) -> bool:
    """Tighten an existing evidence root to ``0700``; the only write ``--fix`` makes here."""

    if not evidence_root.exists:
        return False
    mode = evidence_root.mode
    if mode is None or mode == DIRECTORY_MODE:
        return False
    evidence_root.path.chmod(DIRECTORY_MODE)
    return True


def _resolve_without_requiring_existence(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()
