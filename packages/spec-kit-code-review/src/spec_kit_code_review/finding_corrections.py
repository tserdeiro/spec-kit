"""Byte-preserving recovery for invalid finding categories."""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping
from .errors import EXIT_ENVIRONMENT, EXIT_USAGE, AppError, Diagnostic
from .findings import CATEGORIES
from .session import FILE_MODE, ReviewSession, write_json
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MISSING = object()
_MASK = "__category_recovery_mask__"
class _DuplicateKey(ValueError):
    pass

def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result

def parse_bytes(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (_DuplicateKey, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError("the findings file cannot be used for correction", code=EXIT_USAGE,
                       diagnostics=[Diagnostic("correction_invalid_document", str(error))]) from error
    if not isinstance(value, dict):
        raise AppError("the findings file cannot be used for correction", code=EXIT_USAGE,
                       diagnostics=[Diagnostic("correction_invalid_document", "expected a JSON object")])
    return value

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _error(code: str, message: str, *, environment: bool = False) -> AppError:
    return AppError(message, code=EXIT_ENVIRONMENT if environment else EXIT_USAGE,
                    diagnostics=[Diagnostic(code, message)])

def has_invalid_categories(document: Mapping[str, Any]) -> bool:
    return bool(_invalid_indices(document))

def _invalid_indices(document: Mapping[str, Any]) -> set[int]:
    entries = document.get("findings")
    if not isinstance(entries, list):
        return set()
    return {i for i, item in enumerate(entries) if not isinstance(item, dict)
            or not isinstance(item.get("category"), str) or item["category"] not in CATEGORIES}

def _canonical(document: Mapping[str, Any], invalid: set[int]) -> str:
    # JSON serialization preserves the relevant distinctions (missing/null,
    # bool/number, arrays and object values) while allowing whitespace/key order.
    cloned = json.loads(json.dumps(document))
    entries = cloned.get("findings")
    if isinstance(entries, list):
        for i in invalid:
            if 0 <= i < len(entries):
                if isinstance(entries[i], dict):
                    entries[i]["category"] = _MASK
    return json.dumps(cloned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _bindings(session: ReviewSession, attempt: str, original: str, submitted: str) -> dict[str, Any]:
    packet = session.payload.get("packet") or {}
    return {"findings_attempt_id": attempt, "original_sha256": original, "submitted_sha256": submitted,
            "candidate_id": session.candidate_id, "packet_sha256": session.payload.get("packet_sha256"),
            "inventory_sha256": packet.get("inventory_sha256"), "config_sha256": session.payload.get("config_sha256")}

def _record(session: ReviewSession, root: Path, submitted: str, payload: dict[str, Any]) -> None:
    path = root / f"{submitted}.json"
    if path.exists():
        if submitted not in (session.payload.get("correction_record_digests") or {}):
            raise _error("correction_evidence_tampered", "an existing correction record is not indexed", environment=True)
        return
    write_json(path, payload)
    index = dict(session.payload.get("correction_record_digests") or {})
    index[submitted] = digest(path.read_bytes())
    session.payload["correction_record_digests"] = index
    session.write()

def _rewrite(session: ReviewSession, path: Path, submitted: str, payload: dict[str, Any]) -> None:
    write_json(path, payload)
    session.payload.setdefault("correction_record_digests", {})[submitted] = digest(path.read_bytes())
    session.write()

def begin(session: ReviewSession, raw: bytes) -> tuple[Path, str, str]:
    attempt = str(session.payload.get("findings_attempt_id") or "")
    if not _ID.fullmatch(attempt):
        raise _error("correction_session_format", "missing or invalid findings attempt identity")
    validate_attempt(session)
    root = session.path / "finding-corrections" / attempt
    original_path = root / "original.json"
    submitted = digest(raw)
    bound = str(session.payload.get("correction_original_sha256") or "")
    if bound:
        verify_history(session)
        try:
            if original_path.is_symlink() or digest(original_path.read_bytes()) != bound:
                raise OSError("original snapshot binding changed")
        except OSError as error:
            raise _error("correction_evidence_tampered", str(error), environment=True) from error
        return root, bound, submitted
    try:
        if root.parent.is_symlink() or root.is_symlink() or original_path.is_symlink():
            raise OSError("correction evidence path is a symlink")
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root.parent, 0o700)
        root.mkdir(mode=0o700)
        os.chmod(root, 0o700)
        descriptor = os.open(original_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        # A pre-existing directory without a session binding is partial or
        # stale evidence; never adopt it or recurse into it.
        raise _error("correction_evidence_tampered", str(error), environment=True) from error
    except OSError as error:
        raise _error("correction_evidence_unwritable", str(error), environment=True) from error
    original = digest(raw)
    session.payload["correction_original_sha256"] = original
    session.write()
    return root, original, submitted

def validate_attempt(session: ReviewSession) -> None:
    """All phase-two closes require the fresh-format attempt binding."""
    attempt = str(session.payload.get("findings_attempt_id") or "")
    if not _ID.fullmatch(attempt):
        raise _error("correction_session_format", "missing or invalid findings attempt identity")
    if session.payload.get("correction_original_sha256"):
        return
    root = session.path / "finding-corrections" / attempt
    try:
        if root.parent.is_symlink() or root.is_symlink() or root.exists():
            raise OSError(
                "correction evidence for the current attempt is present without a persisted binding; "
                "reopen the review before retrying"
            )
    except OSError as error:
        raise _error("correction_evidence_tampered", str(error), environment=True) from error

def prepare(session: ReviewSession, raw: bytes, document: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    root, original_digest, submitted = begin(session, raw)
    if session.payload.pop("correction_accepted_digest", None):
        session.write()
    original = parse_bytes((root / "original.json").read_bytes())
    invalid = _invalid_indices(original)
    if not invalid:
        raise _error("correction_original_valid", "correction requires an originally invalid category")
    before = original.get("findings") if isinstance(original.get("findings"), list) else []
    after = document.get("findings") if isinstance(document.get("findings"), list) else []
    changes = []
    for i, (old, new) in enumerate(zip(before, after), 1):
        if i - 1 not in invalid:
            continue
        old_value = old.get("category", _MISSING) if isinstance(old, dict) else _MISSING
        new_value = new.get("category", _MISSING) if isinstance(new, dict) else _MISSING
        old_key = "<missing>" if old_value is _MISSING else json.dumps(old_value, sort_keys=True, separators=(",", ":"))
        new_key = "<missing>" if new_value is _MISSING else json.dumps(new_value, sort_keys=True, separators=(",", ":"))
        if old_key != new_key:
            changes.append({"index": i, "old_present": old_value is not _MISSING,
                            "new_present": new_value is not _MISSING,
                            "old": None if old_value is _MISSING else old_value,
                            "new": None if new_value is _MISSING else new_value})
    base = {**_bindings(session, str(session.payload["findings_attempt_id"]), original_digest, submitted),
            "status": "pending", "changed_categories": changes}
    _record(session, root, submitted, base)
    try:
        if _canonical(original, invalid) != _canonical(document, invalid):
            raise _error("correction_non_category_change", "the correction changes fields other than originally invalid categories")
    except AppError as error:
        finish(session, submitted, status="rejected", reason=error.diagnostics[0].code)
        raise
    valid = isinstance(after, list) and all(isinstance(item, dict) and isinstance(item.get("category"), str)
                                             and item["category"] in CATEGORIES for item in after)
    record = {**base,
              "status": "pending" if valid else "rejected", "changed_categories": changes}
    _rewrite(session, root / f"{submitted}.json", submitted, record)
    return record, submitted

def reject_submission(session: ReviewSession, raw: bytes, reason: str) -> None:
    if not session.payload.get("correction_original_sha256"):
        return
    root, original, submitted = begin(session, raw)
    path = root / f"{submitted}.json"
    changes = []
    if path.exists():
        try:
            changes = json.loads(path.read_text(encoding="utf-8")).get("changed_categories", [])
        except (OSError, ValueError):
            pass
    record = {**_bindings(session, str(session.payload["findings_attempt_id"]), original, submitted),
              "status": "rejected", "reason": reason, "changed_categories": changes}
    if path.exists() and submitted in (session.payload.get("correction_record_digests") or {}):
        _rewrite(session, path, submitted, record)
    else:
        _record(session, root, submitted, record)

def finish(session: ReviewSession, submitted_digest: str, *, status: str, reason: str = "") -> None:
    if not _SHA.fullmatch(submitted_digest):
        raise _error("correction_record_unreadable", "invalid correction record digest", environment=True)
    verify_history(session)
    attempt = str(session.payload.get("findings_attempt_id") or "")
    path = session.path / "finding-corrections" / attempt / f"{submitted_digest}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _error("correction_record_unreadable", str(error), environment=True) from error
    record["status"] = status
    if reason:
        record["reason"] = reason
    _rewrite(session, path, submitted_digest, record)
    if status == "validated":
        session.payload["correction_accepted_digest"] = submitted_digest
    session.write()

def verify_history(session: ReviewSession) -> None:
    original = str(session.payload.get("correction_original_sha256") or "")
    if not original:
        return
    attempt = str(session.payload.get("findings_attempt_id") or "")
    if not _ID.fullmatch(attempt):
        raise _error("correction_evidence_tampered", "invalid correction attempt identity", environment=True)
    root = session.path / "finding-corrections" / attempt
    try:
        if (root.is_symlink() or root.parent.is_symlink() or (root / "original.json").is_symlink()
                or digest((root / "original.json").read_bytes()) != original):
            raise OSError("original snapshot binding changed")
    except OSError as error:
        raise _error("correction_evidence_tampered", str(error), environment=True) from error
    indexed = session.payload.get("correction_record_digests")
    if not isinstance(indexed, dict):
        raise _error("correction_evidence_tampered", "correction records are not indexed", environment=True)
    actual = {item.stem for item in root.glob("*.json") if item.name != "original.json"}
    if actual != set(indexed):
        raise _error("correction_evidence_tampered", "correction records and index differ", environment=True)
    for submitted, expected in indexed.items():
        if not isinstance(submitted, str) or not _SHA.fullmatch(submitted):
            raise _error("correction_evidence_tampered", "invalid indexed submission digest", environment=True)
        path = root / f"{submitted}.json"
        try:
            if path.is_symlink():
                raise OSError("correction record is a symlink")
            content = path.read_bytes()
            record = json.loads(content.decode("utf-8"))
        except (OSError, ValueError) as error:
            raise _error("correction_record_unreadable", str(error), environment=True) from error
        if (digest(content) != expected or record.get("submitted_sha256") != submitted
                or record.get("status") not in {"pending", "rejected", "validated"}):
            raise _error("correction_evidence_tampered", "correction record digest changed", environment=True)
        expected_binding = _bindings(session, attempt, original, submitted)
        if any(record.get(key) != value for key, value in expected_binding.items()):
            raise _error("correction_evidence_tampered", "correction record binding changed", environment=True)
    accepted = session.payload.get("correction_accepted_digest")
    if accepted:
        if accepted not in indexed:
            raise _error("correction_evidence_tampered", "accepted correction is not indexed", environment=True)
        try:
            accepted_record = json.loads((root / f"{accepted}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise _error("correction_record_unreadable", str(error), environment=True) from error
        if accepted_record.get("status") != "validated":
            raise _error("correction_evidence_tampered", "accepted correction is not validated", environment=True)
