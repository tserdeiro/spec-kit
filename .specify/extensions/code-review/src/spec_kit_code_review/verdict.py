"""The verdict, and the exit code it maps to.

Doc "Veredicto". Three values and nothing else:

``no-blocking-findings``
    No blocking finding. **Not an approval**: it unblocks nothing, and the
    published text says so. Approve and merge are human decisions
    (`spec-kit.plan.md`, "Human role boundaries").
``changes-requested``
    At least one blocking finding.
``inconclusive``
    The review could not be completed over its intended scope.

An ``inconclusive`` verdict is never presented as a quiet success: even with
exit code 0 the human render and the JSON label it and enumerate what was not
covered. That is the whole point of the value existing -- a review that silently
covered half the candidate is worse than one that says it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .errors import EXIT_CANDIDATE, EXIT_ENGINE, EXIT_FINDINGS, EXIT_SUCCESS


NO_BLOCKING_FINDINGS = "no-blocking-findings"
CHANGES_REQUESTED = "changes-requested"
INCONCLUSIVE = "inconclusive"
VERDICTS: tuple[str, ...] = (NO_BLOCKING_FINDINGS, CHANGES_REQUESTED, INCONCLUSIVE)

# The two families of cause the exit-code table distinguishes. `engine` means the
# review engine itself could not deliver its part; `context` means the candidate's
# own context was missing under a flag that demanded it.
CAUSE_ENGINE = "engine"
CAUSE_CONTEXT = "context"
CAUSE_SCOPE = "scope"


@dataclass(frozen=True)
class InconclusiveCause:
    """One reason the review did not cover what it set out to cover."""

    kind: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail}


@dataclass
class Verdict:
    """The verdict, its causes, and the exit code the contract assigns it."""

    value: str
    blocking: int = 0
    causes: tuple[InconclusiveCause, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def inconclusive(self) -> bool:
        return self.value == INCONCLUSIVE

    def exit_code(self) -> int:
        """The exit code the contract assigns this verdict.

        ``changes-requested`` is 1: the review completed, and the code says the
        candidate needs work. An ``inconclusive`` verdict keeps its own codes --
        9 for an engine cause, 6 for a context cause -- and 1 when it still
        retained a blocking finding, because a degraded review that found
        something blocking is never a green result.
        """

        if self.value == CHANGES_REQUESTED:
            return EXIT_FINDINGS
        if self.value != INCONCLUSIVE:
            return EXIT_SUCCESS
        kinds = {cause.kind for cause in self.causes}
        if CAUSE_ENGINE in kinds:
            return EXIT_ENGINE
        if CAUSE_CONTEXT in kinds:
            return EXIT_CANDIDATE
        if self.blocking:
            return EXIT_FINDINGS
        # Any other inconclusive is 0 with an explicit warning in both renders.
        return EXIT_SUCCESS

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "blocking": self.blocking,
            "causes": [cause.as_dict() for cause in self.causes],
            "notes": list(self.notes),
            "is_approval": False,
        }


def derive(
    findings: Sequence[Any],
    *,
    causes: Sequence[InconclusiveCause] = (),
) -> Verdict:
    """Derive the verdict from the normalized findings and the recorded causes.

    ``inconclusive`` wins over the other two: if the scope was not covered, the
    absence of a blocking finding says nothing about the candidate, and reporting
    ``no-blocking-findings`` would be a claim the review cannot support.
    """

    blocking = sum(1 for finding in findings if getattr(finding, "severity", None) == "blocking")
    if causes:
        verdict = Verdict(value=INCONCLUSIVE, blocking=blocking, causes=tuple(causes))
        verdict.notes.append(
            "The review did not cover its intended scope; the causes are listed above. "
            + (
                f"{blocking} blocking finding(s) were still recorded."
                if blocking
                else "No blocking finding was recorded, which says nothing about the part that was not covered."
            )
        )
        return verdict
    if blocking:
        return Verdict(value=CHANGES_REQUESTED, blocking=blocking)
    verdict = Verdict(value=NO_BLOCKING_FINDINGS, blocking=0)
    verdict.notes.append(
        "No blocking finding. This is a non-binding recommendation, not an approval: it unblocks nothing, "
        "and approving or merging this pull request remains a human decision."
    )
    return verdict


def describe(verdict: Verdict) -> str:
    """One line for the human render, honest about what the verdict is not."""

    if verdict.value == CHANGES_REQUESTED:
        return f"changes-requested — {verdict.blocking} blocking finding(s)"
    if verdict.value == INCONCLUSIVE:
        return f"inconclusive — {len(verdict.causes)} part(s) of the scope were not covered"
    return "no-blocking-findings — a recommendation, not an approval"
