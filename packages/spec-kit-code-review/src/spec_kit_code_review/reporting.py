"""The two renders of a completed review: human, and the JSON contract.

Doc "Salida". The JSON is a single document with a fixed set of top-level keys,
and it is the interface other tools consume, so it is built in one place instead
of being assembled ad hoc at each call site. Both renders pass through
`redaction`, and both state an ``inconclusive`` verdict explicitly: with exit
code 0 a quiet success would be indistinguishable from a review that covered
everything, which is the failure this verdict exists to prevent.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .errors import EXIT_CATEGORIES, Diagnostic
from .findings import FindingSet
from .verdict import Verdict, describe


SCHEMA_VERSION = "1.0"


def review_document(
    *,
    candidate: Any,
    engine: Mapping[str, Any] | None,
    packet_sha256: str,
    rules_sha256: str | None,
    scope: Mapping[str, Any] | None,
    budget: Mapping[str, Any] | None,
    findings: FindingSet,
    verdict: Verdict,
    code: int,
    diagnostics: Sequence[Diagnostic],
    session: Mapping[str, Any] | None = None,
    publication_plan: Mapping[str, Any] | None = None,
    message: str = "",
    retryable: bool = False,
) -> dict[str, Any]:
    """The `--json` document of a completed review, with every documented key."""

    warnings = [item.as_dict() for item in diagnostics if item.severity == "warning"]
    return {
        "schema_version": SCHEMA_VERSION,
        "code": code,
        "category": EXIT_CATEGORIES.get(code, "unknown"),
        "message": message or describe(verdict),
        # True only when the cause is the engine: that is the one failure here
        # that a second run can plausibly resolve. A hallucinated finding or a
        # drifted candidate will fail identically however many times it is run.
        "retryable": retryable,
        "candidate": candidate.as_dict() if hasattr(candidate, "as_dict") else dict(candidate or {}),
        "engine": dict(engine or {}),
        "packet_sha256": packet_sha256,
        "rules_sha256": rules_sha256,
        "scope": dict(scope or {}),
        "budget": dict(budget or {}),
        "findings": [finding.as_dict() for finding in findings.findings],
        "discarded_findings": list(findings.discarded),
        "verdict": verdict.as_dict(),
        "warnings": warnings,
        "diagnostics": [item.as_dict() for item in diagnostics],
        "operations": [],
        **({"session": dict(session)} if session is not None else {}),
        **({"publication_plan": dict(publication_plan)} if publication_plan is not None else {}),
    }


def render_human(
    *,
    findings: FindingSet,
    verdict: Verdict,
    budget: Mapping[str, Any] | None,
    evidence_path: str | None,
    packet_sha256: str = "",
) -> str:
    """Summary, findings by severity, budget, verdict, evidence path -- in that order."""

    counts = findings.by_severity()
    lines = [
        "Review summary",
        "==============",
        "",
        f"findings: {len(findings.findings)}"
        + (f" (discarded {len(findings.discarded)})" if findings.discarded else ""),
        "  " + "  ".join(f"{name}: {counts[name]}" for name in counts),
        f"anchorable inline: {len(findings.anchorable)}; reported in the summary: {len(findings.degraded)}",
    ]
    if budget:
        lines.append(
            f"budget: {budget.get('counted')} counted against {budget.get('limit')}"
            + (" (OVER BUDGET)" if budget.get("over_budget") else "")
        )
    if packet_sha256:
        lines.append(f"packet_sha256: {packet_sha256}")

    lines.extend(["", f"VERDICT: {describe(verdict)}"])
    if verdict.inconclusive:
        # Never a quiet success: the parts that were not covered are named.
        lines.append("The review did NOT cover its intended scope:")
        for cause in verdict.causes:
            lines.append(f"  - [{cause.kind}] {cause.detail}")
    for note in verdict.notes:
        lines.extend(["", note])

    if findings.findings:
        lines.extend(["", "id     severity  category        location"])
        for finding in findings.findings:
            location = f"{finding.path}:{finding.start_line}-{finding.end_line}"
            lines.append(
                f"{finding.identifier:<6} {finding.severity:<9} {finding.category:<15} {location}"
                + ("" if finding.anchorable else "  (summary)")
            )
    if evidence_path:
        lines.extend(["", f"evidence: {evidence_path}"])
    return "\n".join(lines) + "\n"
