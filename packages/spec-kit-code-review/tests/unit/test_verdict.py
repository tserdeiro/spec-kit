"""The verdict, and the exit code the contract's table assigns to each path."""

from __future__ import annotations

import unittest

from spec_kit_code_review.findings import Finding
from spec_kit_code_review.verdict import (
    CAUSE_CONTEXT,
    CAUSE_ENGINE,
    CAUSE_SCOPE,
    CHANGES_REQUESTED,
    INCONCLUSIVE,
    NO_BLOCKING_FINDINGS,
    InconclusiveCause,
    derive,
    describe,
)


def finding(severity: str = "minor") -> Finding:
    return Finding(
        path="src/module.py",
        start_line=1,
        end_line=1,
        severity=severity,
        category="correctness",
        title="t",
        content="c",
    )


class DerivationTests(unittest.TestCase):
    def test_no_findings_is_not_an_approval(self) -> None:
        verdict = derive([])

        self.assertEqual(verdict.value, NO_BLOCKING_FINDINGS)
        self.assertFalse(verdict.as_dict()["is_approval"])
        self.assertIn("not an approval", " ".join(verdict.notes))

    def test_non_blocking_findings_still_mean_no_blocking_findings(self) -> None:
        verdict = derive([finding("major"), finding("nit"), finding("info")])

        self.assertEqual(verdict.value, NO_BLOCKING_FINDINGS)

    def test_one_blocking_finding_requests_changes(self) -> None:
        verdict = derive([finding("minor"), finding("blocking")])

        self.assertEqual(verdict.value, CHANGES_REQUESTED)
        self.assertEqual(verdict.blocking, 1)

    def test_a_cause_makes_the_review_inconclusive_whatever_was_found(self) -> None:
        # The absence of a blocking finding says nothing about the part of the
        # candidate that was never covered.
        verdict = derive([], causes=[InconclusiveCause(CAUSE_SCOPE, "half the plan did not fit in the packet")])

        self.assertEqual(verdict.value, INCONCLUSIVE)
        self.assertIn("says nothing", " ".join(verdict.notes))

    def test_an_inconclusive_review_still_reports_its_blocking_findings(self) -> None:
        verdict = derive([finding("blocking")], causes=[InconclusiveCause(CAUSE_ENGINE, "engine timed out")])

        self.assertEqual(verdict.value, INCONCLUSIVE)
        self.assertEqual(verdict.blocking, 1)
        self.assertIn("1 blocking finding(s) were still recorded", " ".join(verdict.notes))


class ExitCodeTests(unittest.TestCase):
    def test_no_blocking_findings_is_zero(self) -> None:
        self.assertEqual(derive([]).exit_code(), 0)

    def test_changes_requested_is_one(self) -> None:
        self.assertEqual(derive([finding("blocking")]).exit_code(), 1)

    def test_an_engine_cause_is_nine(self) -> None:
        verdict = derive([], causes=[InconclusiveCause(CAUSE_ENGINE, "status budget_exceeded")])

        self.assertEqual(verdict.exit_code(), 9)

    def test_a_context_cause_is_six(self) -> None:
        verdict = derive([], causes=[InconclusiveCause(CAUSE_CONTEXT, "no SDD context")])

        self.assertEqual(verdict.exit_code(), 6)

    def test_any_other_cause_without_a_blocking_finding_is_zero(self) -> None:
        verdict = derive([], causes=[InconclusiveCause(CAUSE_SCOPE, "an artifact was truncated")])

        self.assertEqual(verdict.exit_code(), 0)

    def test_the_engine_cause_wins_over_the_others(self) -> None:
        verdict = derive(
            [],
            causes=[
                InconclusiveCause(CAUSE_SCOPE, "truncated"),
                InconclusiveCause(CAUSE_ENGINE, "engine failed"),
                InconclusiveCause(CAUSE_CONTEXT, "no context"),
            ],
        )

        self.assertEqual(verdict.exit_code(), 9)

    def test_an_inconclusive_review_with_a_blocking_finding_is_never_green(self) -> None:
        # A degraded review that still found something blocking is never a green
        # result: being inconclusive is an aggravating circumstance.
        verdict = derive([finding("blocking")], causes=[InconclusiveCause(CAUSE_SCOPE, "truncated")])

        self.assertEqual(verdict.exit_code(), 1)

    def test_an_inconclusive_review_without_a_blocking_finding_is_zero(self) -> None:
        verdict = derive([finding("minor")], causes=[InconclusiveCause(CAUSE_SCOPE, "truncated")])

        self.assertEqual(verdict.exit_code(), 0)

    def test_an_engine_cause_still_wins_over_the_blocking_rule(self) -> None:
        verdict = derive([finding("blocking")], causes=[InconclusiveCause(CAUSE_ENGINE, "engine failed")])

        self.assertEqual(verdict.exit_code(), 9)

    def test_a_context_cause_still_wins_over_the_blocking_rule(self) -> None:
        verdict = derive([finding("blocking")], causes=[InconclusiveCause(CAUSE_CONTEXT, "no context")])

        self.assertEqual(verdict.exit_code(), 6)


class DescriptionTests(unittest.TestCase):
    def test_every_verdict_describes_itself_honestly(self) -> None:
        self.assertIn("not an approval", describe(derive([])))
        self.assertIn("1 blocking", describe(derive([finding("blocking")])))
        self.assertIn(
            "not covered", describe(derive([], causes=[InconclusiveCause(CAUSE_SCOPE, "x")]))
        )


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
