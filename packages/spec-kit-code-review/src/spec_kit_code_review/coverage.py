"""Candidate-bound reading receipts for the findings submission."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .errors import AppError
from .git import validate_repository_relative_path


@dataclass(frozen=True)
class CoverageResult:
    """Validated receipts and the required ranges they actually cover."""

    reads: tuple[dict[str, Any], ...] = ()
    covered: tuple[dict[str, Any], ...] = ()
    gaps: tuple[dict[str, Any], ...] = ()

    @property
    def complete(self) -> bool:
        return not self.gaps

    def as_dict(self) -> dict[str, Any]:
        return {
            "reads": [dict(item) for item in self.reads],
            "covered": [dict(item) for item in self.covered],
            "gaps": [dict(item) for item in self.gaps],
            "complete": self.complete,
        }


def _source_bytes(read: Callable[[str], str | bytes | None], path: str) -> bytes | None:
    value = read(path)
    if value is None:
        return None
    return value if isinstance(value, bytes) else value.encode("utf-8")


def _range_bytes(raw: bytes, start: int, end: int) -> bytes | None:
    lines = raw.decode("utf-8").splitlines(keepends=True)
    if start < 1 or end < start or end > len(lines):
        return None
    return "".join(lines[start - 1 : end]).encode("utf-8")


def _intervals(reads: Sequence[Mapping[str, Any]], path: str, version: str) -> list[tuple[int, int]]:
    return sorted(
        (int(item["start_line"]), int(item["end_line"]))
        for item in reads
        if item["path"] == path and item["version"] == version
    )


def _uncovered(start: int, end: int, intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = start
    for left, right in intervals:
        if right < cursor:
            continue
        if left > cursor:
            result.append((cursor, min(end, left - 1)))
        cursor = max(cursor, right + 1)
        if cursor > end:
            break
    if cursor <= end:
        result.append((cursor, end))
    return result


def validate(
    envelope: Any,
    *,
    candidate_id: str,
    packet_sha256: str,
    inventory_sha256: str,
    inventory: Mapping[str, Any],
    read: Callable[[str], str | bytes | None],
) -> CoverageResult:
    """Validate the envelope and receipts against frozen inventory/source bytes.

    Invalid receipts become actionable gaps; valid findings remain independent of
    them. Missing or invalid coverage never discards findings.
    """

    if not isinstance(envelope, Mapping):
        return CoverageResult(gaps=({"code": "coverage_missing", "detail": "the findings submission has no coverage envelope"},))
    required_keys = ("candidate_id", "packet_sha256", "inventory_sha256", "reads")
    missing = [key for key in required_keys if key not in envelope]
    if missing:
        return CoverageResult(gaps=({"code": "coverage_field_missing", "detail": ", ".join(missing)},))
    if envelope.get("candidate_id") != candidate_id:
        return CoverageResult(gaps=({"code": "coverage_candidate_mismatch", "detail": str(envelope.get("candidate_id"))},))
    if envelope.get("packet_sha256") != packet_sha256:
        return CoverageResult(gaps=({"code": "coverage_packet_mismatch", "detail": str(envelope.get("packet_sha256"))},))
    if envelope.get("inventory_sha256") != inventory_sha256:
        return CoverageResult(gaps=({"code": "coverage_inventory_mismatch", "detail": str(envelope.get("inventory_sha256"))},))
    raw_reads = envelope.get("reads")
    if not isinstance(raw_reads, list):
        return CoverageResult(gaps=({"code": "coverage_reads_shape", "detail": type(raw_reads).__name__},))

    sources = {str(item.get("path")): item for item in inventory.get("sources", ()) if isinstance(item, Mapping)}
    valid: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(raw_reads, 1):
        if not isinstance(item, Mapping):
            gaps.append({"code": "coverage_read_shape", "detail": f"read #{index} is not an object"})
            continue
        fields = ("path", "version", "start_line", "end_line", "sha256", "assessment", "scope")
        if any(key not in item for key in fields):
            gaps.append({"code": "coverage_read_incomplete", "detail": f"read #{index} is missing a required field"})
            continue
        path, version = item["path"], item["version"]
        start, end = item["start_line"], item["end_line"]
        assessment, scope = item["assessment"], item["scope"]
        if not isinstance(path, str) or not isinstance(version, str) or not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool) or start < 1 or end < start:
            gaps.append({"code": "coverage_read_range", "detail": f"read #{index} has an invalid path, version, or range"})
            continue
        if not isinstance(assessment, str) or not assessment.strip() or not isinstance(scope, str) or not scope.strip():
            gaps.append({"code": "coverage_read_assessment", "path": path, "detail": f"read #{index} needs a non-empty assessment and scope"})
            continue
        if path != "<pull-request-intent>":
            try:
                validate_repository_relative_path(path)
            except AppError:
                gaps.append({"code": "coverage_path_invalid", "path": path, "detail": f"read #{index} is not repository-relative"})
                continue
        source = sources.get(path)
        if source is None or version != source.get("version"):
            gaps.append({"code": "coverage_source_mismatch", "path": path, "detail": f"read #{index} does not name an inventoried source version"})
            continue
        raw = _source_bytes(read, path)
        if raw is None or hashlib.sha256(raw).hexdigest() != source.get("sha256"):
            gaps.append({"code": "coverage_source_drift", "path": path, "detail": "the inventoried source bytes are unavailable or changed"})
            continue
        exact = _range_bytes(raw, start, end)
        if exact is None:
            gaps.append({"code": "coverage_read_range", "path": path, "start_line": start, "end_line": end, "detail": f"read #{index} falls outside the source"})
            continue
        digest = hashlib.sha256(exact).hexdigest()
        if digest != item.get("sha256"):
            gaps.append({"code": "coverage_hash_mismatch", "path": path, "start_line": start, "end_line": end, "detail": f"read #{index} does not hash the exact source range"})
            continue
        normalized = {"path": path, "version": version, "start_line": start, "end_line": end, "sha256": digest, "assessment": assessment.strip(), "scope": scope.strip()}
        identity = tuple(normalized.items())
        if identity not in seen:
            seen.add(identity)
            valid.append(normalized)

    covered: list[dict[str, Any]] = []
    for required in inventory.get("required", ()):
        path = str(required.get("path")); start = int(required.get("start", 1)); end = int(required.get("end", start))
        required_version = str(sources.get(path, {}).get("version") or "")
        intervals = _intervals(valid, path, required_version)
        missing_ranges = _uncovered(start, end, intervals)
        if missing_ranges:
            for left, right in missing_ranges:
                gaps.append({"code": "coverage_required_unread", "path": path, "start_line": left, "end_line": right, "detail": "required source content has no validated reading receipt"})
        else:
            covered.append({"path": path, "version": required_version, "start_line": start, "end_line": end})
    return CoverageResult(tuple(valid), tuple(covered), tuple(gaps))
