"""The review session: open, validate, close, abandon, and inventory.

A CLI cannot wait for the host agent to review -- the agent is what invokes the
CLI -- so an anchored review runs in two internal phases. The first produces the
packet, leaves the candidate materialized **on purpose**, and opens a session
holding everything needed to withdraw it. The second validates that the
candidate and the packet are still the same ones, normalizes the findings, and
withdraws the environment.

If the second phase never arrives, nothing is lost and nothing is silently
cleaned: ``session.json`` records the temporary worktree, retention never
deletes an open session, and the next review of the same candidate withdraws the
orphan environment before opening a fresh session.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from .paths import EXTENSION_DIRECTORY, state_root
from .errors import EXIT_DRIFT, EXIT_ENVIRONMENT, EXIT_USAGE, AppError, Diagnostic
from .evidence import FILE_MODE, EvidenceRoot, harden_directories
from .redaction import redact_payload, redact_text


SESSION_FILENAME = "session.json"
RAW_DIRECTORY = "raw"
PACKET_FILENAME = "review-packet.md"
FINDINGS_FILENAME = "findings.json"
FINDINGS_MARKDOWN_FILENAME = "findings.md"
PUBLICATION_PLAN_FILENAME = "publication-plan.json"
PUBLICATION_RESULT_FILENAME = "publication-result.json"
POINTER_DIRECTORY_NAME = "open-sessions"
ENVIRONMENT_FILENAME = "environment.json"
ENVIRONMENT_DIRECTORY = "env"
SCHEMA_VERSION = "1.0"

PHASE_OPEN = "open"
PHASE_CLOSED = "closed"
PHASE_ABANDONED = "abandoned"
PHASES: tuple[str, ...] = (PHASE_OPEN, PHASE_CLOSED, PHASE_ABANDONED)


@dataclass
class ReviewSession:
    """One evidence directory and the session document inside it."""

    path: Path
    payload: dict[str, Any]

    # -- accessors ------------------------------------------------------

    @property
    def phase(self) -> str:
        return str(self.payload.get("phase") or "")

    @property
    def candidate_id(self) -> str | None:
        return self.payload.get("candidate_id")

    @property
    def head_commit(self) -> str | None:
        return self.payload.get("head_commit")

    @property
    def merge_base(self) -> str | None:
        return self.payload.get("merge_base")

    @property
    def repository_root(self) -> Path | None:
        value = self.payload.get("repository_root")
        return Path(value) if value else None

    @property
    def opened_at(self) -> str | None:
        return self.payload.get("opened_at")

    @property
    def document(self) -> Path:
        return self.path / SESSION_FILENAME

    def age_hours(self, *, now: datetime | None = None) -> float | None:
        opened = _parse_timestamp(self.opened_at)
        if opened is None:
            return None
        moment = now or datetime.now(timezone.utc)
        return max((moment - opened).total_seconds() / 3600.0, 0.0)

    def summary(self, *, now: datetime | None = None) -> dict[str, Any]:
        """The shape the JSON output reports a session with."""

        age = self.age_hours(now=now)
        return {
            "path": str(self.path),
            "phase": self.phase,
            "candidate_id": self.candidate_id,
            "head_commit": self.head_commit,
            "merge_base": self.merge_base,
            "opened_at": self.opened_at,
            "age_hours": round(age, 2) if age is not None else None,
            "worktree_path": (self.payload.get("environment") or {}).get("worktree_path"),
        }

    # -- mutation -------------------------------------------------------

    def write(self) -> None:
        write_json(self.document, self.payload)

    def mark(self, phase: str, **extra: Any) -> None:
        if phase not in PHASES:
            raise ValueError(f"unknown phase: {phase}")
        self.payload["phase"] = phase
        self.payload["closed_at"] = _timestamp()
        self.payload.update(extra)
        self.write()
        if phase != PHASE_OPEN:
            forget_open_session(self)


def session_directory(evidence_root: EvidenceRoot, repository_id: str, head_commit: str) -> Path:
    """``<evidence-root>/<repo-id>/<head_commit>/`` -- the documented layout."""

    return evidence_root.path / repository_id / head_commit


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write an evidence document: redacted, ``0600``, under ``0700`` directories.

    ``redaction.py`` is the only path through which text
    reaches the evidence, and every session document carries untrusted content
    (a base branch name, a pull-request URL, a recorded ref, a diff stat). This
    is also the writer the packet and the findings will reuse, so the guarantee
    belongs here rather than at each call site.
    """

    try:
        harden_directories(path.parent)
        path.write_text(
            json.dumps(redact_payload(dict(payload)), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, FILE_MODE)
    except OSError as error:
        raise AppError(
            f"could not write the session evidence at {path}",
            code=EXIT_ENVIRONMENT,
            diagnostics=[Diagnostic("evidence_unwritable", str(error), str(path))],
        ) from error


def write_text(path: Path, text: str) -> None:
    """Write a raw evidence artifact: redacted, ``0600``, under ``0700`` directories.

    The engine's stdout is preserved **verbatim** in the sense the contract
    means -- nothing is reformatted, reordered or summarized -- but it still
    passes through the credential catalog, because it is untrusted content on
    its way to a file the operator will read and later attach to a packet.
    """

    try:
        harden_directories(path.parent)
        path.write_text(redact_text(text), encoding="utf-8")
        os.chmod(path, FILE_MODE)
    except OSError as error:
        raise AppError(
            f"could not write the session evidence at {path}",
            code=EXIT_ENVIRONMENT,
            diagnostics=[Diagnostic("evidence_unwritable", str(error), str(path))],
        ) from error


def open_session(
    *,
    directory: Path,
    candidate: Mapping[str, Any],
    environment: Mapping[str, Any],
    config_sha256: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> ReviewSession:
    """Write ``session.json`` (phase ``open``) plus ``env/environment.json``."""

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE_OPEN,
        "opened_at": _timestamp(),
        "candidate_id": candidate.get("candidate_id"),
        "head_commit": candidate.get("head_commit"),
        "merge_base": candidate.get("merge_base"),
        "candidate": dict(candidate),
        "repository_root": environment.get("repository_root"),
        "working_root": environment.get("working_root"),
        "environment": dict(environment),
        "config_sha256": config_sha256,
        "packet_sha256": None,
        "verdict": None,
    }
    if extra:
        collisions = sorted(set(extra) & set(payload))
        if collisions:
            # The core keys are the ones every later phase validates against;
            # letting a caller overwrite them would make the session lie.
            raise AppError(
                f"a session document may not be overwritten: {', '.join(collisions)}",
                code=EXIT_ENVIRONMENT,
                diagnostics=[Diagnostic("session_key_collision", "these keys belong to the session core", str(directory))],
            )
        payload.update(extra)
    session = ReviewSession(path=directory, payload=payload)
    session.write()
    write_json(directory / ENVIRONMENT_DIRECTORY / ENVIRONMENT_FILENAME, dict(environment))
    record_open_session(session)
    return session


def write_environment(session: ReviewSession, environment: Mapping[str, Any]) -> None:
    """Rewrite ``env/environment.json`` -- the record of the environment."""

    write_json(session.path / ENVIRONMENT_DIRECTORY / ENVIRONMENT_FILENAME, dict(environment))


# -- the trusted pointer ----------------------------------------------------
#
# Doc "Precedencia y momento de lectura de la configuracion": a guard that looks
# for open sessions must not depend on the shared configuration, because the
# configuration is exactly what it is protecting. These pointers live in the
# state directory, whose location comes from the environment and the home
# directory only -- never from a file the candidate could have written.


def pointer_directory() -> Path:
    """Beside the evidence, inside the distribution's own state root.

    Derived through `paths`, never by walking XDG here: a second walk is a
    second convention, and this one used to return the pre-amendment path --
    so the pointers sat outside all three roots `doctor` reports and outside
    the `rm -rf` the uninstall documents, which is precisely the "survives the
    uninstall" problem the namespace decision exists to end.
    """

    return state_root() / EXTENSION_DIRECTORY / POINTER_DIRECTORY_NAME


def pointer_path(repository_root: Path) -> Path:
    digest = hashlib.sha256(str(Path(repository_root).resolve()).encode("utf-8")).hexdigest()[:16]
    return pointer_directory() / f"{digest}.json"


def record_open_session(session: ReviewSession) -> None:
    """Note an open session where a trusted-path lookup can always find it."""

    root = session.repository_root
    if root is None:
        return
    payload = {
        "repository_root": str(root),
        "session_path": str(session.path),
        "head_commit": session.head_commit,
        "candidate_id": session.candidate_id,
        "opened_at": session.opened_at,
    }
    try:
        write_json(pointer_path(root), payload)
    except AppError:
        # Best effort: the pointer is an optimization for the guard's message,
        # never the guarantee itself.
        return


def forget_open_session(session: ReviewSession) -> None:
    root = session.repository_root
    if root is None:
        return
    path = pointer_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if str(payload.get("session_path") or "") != str(session.path):
        return
    try:
        path.unlink()
    except OSError:
        return


@contextmanager
def repository_lock(repository_root: Path) -> Iterator[bool]:
    """A best-effort, advisory lock around opening or closing a session.

    The guards that read the evidence layout and then act on it are a
    check-then-act pair, so two concurrent ``run`` invocations could both decide
    that no session is open. This narrows that window with an exclusive create
    in the trusted state directory. It is deliberately **advisory**: a stale lock
    from a killed process must never be able to make the tool unusable, so the
    caller is told the lock was not acquired and proceeds anyway -- the real
    guarantees (an open session is never overwritten, an environment is never
    silently discarded) come from the checks themselves, not from this.
    """

    path = pointer_path(repository_root).with_suffix(".lock")
    acquired = False
    try:
        harden_directories(path.parent)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE)
    except FileExistsError:
        descriptor = None
    except OSError:
        descriptor = None
    else:
        acquired = True
        try:
            os.write(descriptor, f"{os.getpid()}\n".encode("utf-8"))
        finally:
            os.close(descriptor)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                path.unlink()
            except OSError:
                pass


def recorded_open_session(repository_root: Path) -> dict[str, Any] | None:
    """The pointer for this repository, when one was left behind."""

    try:
        payload = json.loads(pointer_path(repository_root).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_session(path: Path) -> ReviewSession:
    """Load a session directory; a missing or malformed one is a usage error."""

    directory = Path(path).expanduser()
    if directory.is_file() and directory.name == SESSION_FILENAME:
        directory = directory.parent
    document = directory / SESSION_FILENAME
    if not document.is_file():
        raise AppError(
            f"no review session at {directory}",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("session_missing", f"expected {SESSION_FILENAME} in this directory", str(directory))],
        )
    try:
        payload = json.loads(document.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(
            f"the review session at {directory} is not readable",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("session_unreadable", str(error), str(document))],
        ) from error
    if not isinstance(payload, dict):
        raise AppError(
            f"the review session at {directory} has an unexpected shape",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("session_shape", "expected a JSON object", str(document))],
        )
    return ReviewSession(path=directory.resolve(), payload=payload)


def require_open(session: ReviewSession) -> ReviewSession:
    """A session that is not open cannot be closed again."""

    if session.phase == PHASE_OPEN:
        return session
    verdict = session.payload.get("verdict")
    published = bool(session.payload.get("published"))
    raise AppError(
        f"this session is already {session.phase}",
        code=EXIT_USAGE,
        diagnostics=[
            Diagnostic(
                "session_not_open",
                f"phase {session.phase}, verdict {verdict!r}, published: {published}",
                str(session.path),
            )
        ],
    )


def inventory(evidence_root: EvidenceRoot, *, phase: str | None = PHASE_OPEN) -> list[ReviewSession]:
    """Every session under this evidence root, optionally filtered by phase.

    Defensive by construction: an unreadable or malformed ``session.json`` is
    skipped, never a crash, because this feeds ``status`` and ``doctor``.
    """

    if not evidence_root.exists:
        return []
    sessions: list[ReviewSession] = []
    for document in sorted(evidence_root.path.glob(f"*/*/{SESSION_FILENAME}")):
        try:
            session = load_session(document.parent)
        except AppError:
            continue
        if phase is None or session.phase == phase:
            sessions.append(session)
    return sessions


def apply_retention(
    evidence_root: EvidenceRoot,
    repository_id: str,
    *,
    keep: int,
    protect: Path | None = None,
) -> list[Path]:
    """Delete the oldest *closed* sessions of one repository, at session start.

    Retention runs when a new session **begins**, never when one ends, so a
    failure never deletes the evidence of the run that failed. A session in an
    open phase is never deleted whatever its age: removing it would leave an
    unrestored environment with no record of how to restore it.
    """

    if keep <= 0 or not evidence_root.exists:
        return []
    directory = evidence_root.path / repository_id
    if not directory.is_dir():
        return []
    candidates: list[tuple[float, Path]] = []
    for child in directory.iterdir():
        if not child.is_dir() or (protect is not None and child.resolve() == protect.resolve()):
            continue
        document = child / SESSION_FILENAME
        if not document.is_file():
            continue
        try:
            session = load_session(child)
        except AppError:
            continue
        if session.phase == PHASE_OPEN:
            continue
        try:
            candidates.append((document.stat().st_mtime, child))
        except OSError:
            continue
    if len(candidates) <= keep:
        return []
    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    removed: list[Path] = []
    for _, path in candidates[keep:]:
        if _remove_tree(path):
            removed.append(path)
    return removed


def _remove_tree(path: Path) -> bool:
    import shutil

    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return True


# -- candidate drift --------------------------------------------------------


@dataclass(frozen=True)
class Drift:
    """A difference between the candidate a session reviewed and the current one."""

    kind: str  # "head" | "merge_base"
    previous: str
    current: str

    @property
    def diagnostic(self) -> Diagnostic:
        if self.kind == "head":
            return Diagnostic(
                "candidate_head_advanced",
                f"the head advanced from {self.previous} to {self.current}: there are new commits to review, "
                "so this is a new candidate and needs a new pass",
            )
        return Diagnostic(
            "candidate_merge_base_changed",
            f"the merge base changed from {self.previous} to {self.current}: the head did not move, but the base branch "
            "advanced and the comparison range is another one, so the file scope and the budget no longer correspond; "
            "redo the pass against the new range",
        )

    def as_error(self) -> AppError:
        return AppError(
            "the candidate changed: " + ("the head advanced" if self.kind == "head" else "the merge base changed"),
            code=EXIT_DRIFT,
            diagnostics=[self.diagnostic],
        )


def detect_drift(
    *,
    previous_head: str | None,
    previous_merge_base: str | None,
    current_head: str | None,
    current_merge_base: str | None,
) -> Drift | None:
    """Distinguish a moved head from a moved merge base; both are a new candidate.

    A ``base_commit`` that advanced without moving the merge base is not drift --
    the base branch simply moved along a path that does not affect the candidate
    -- and is reported as information elsewhere, never as an error.
    """

    if previous_head and current_head and previous_head != current_head:
        return Drift("head", previous_head, current_head)
    if previous_merge_base and current_merge_base and previous_merge_base != current_merge_base:
        return Drift("merge_base", previous_merge_base, current_merge_base)
    return None


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
