"""Missing contracts must survive receipt validation as inconclusive causes."""

import json
from pathlib import Path

from tests.support.coverage import coverage_for_session
from tests.unit.test_cli import RunCommandCase


class RequiredContractClosureTests(RunCommandCase):
    def _assert_missing_contract(self, filename: str) -> None:
        self.repository.checkout("main")
        path = f"specs/001-review-skeleton/{filename}"
        self.repository.git("rm", path)
        self.repository.git("commit", "-m", "seed incomplete contract")
        self.repository.branch("missing-contract")
        self.repository.commit("src/feature.py", "value = 2\n", "change implementation")
        self.repository.checkout("main")
        code, opened = self.invoke_json("review", "--base", "main", "--head", "missing-contract")
        self.assertEqual(code, 0, opened)
        self.assertEqual(opened["review_scope"]["kind"], "feature")
        session = Path(opened["session"]["path"])
        findings = session / "findings.json"
        findings.write_text(json.dumps({
            "findings": [],
            "coverage": coverage_for_session(self.repository, session),
        }), encoding="utf-8")
        code, closed = self.invoke_json("review", "--findings", str(findings), "--session", str(session))
        # Scope gaps retain the existing exit-code contract; the verdict is
        # explicitly inconclusive even when available range receipts validate.
        self.assertEqual(code, 0, closed)
        self.assertEqual(closed["verdict"]["value"], "inconclusive")
        self.assertTrue(any(
            "required_artifact_missing" in cause["detail"] and path in cause["detail"]
            for cause in closed["verdict"]["causes"]
        ), closed["verdict"])

    def test_missing_spec_cannot_close_with_only_available_receipts(self) -> None:
        self._assert_missing_contract("spec.md")

    def test_missing_plan_cannot_close_with_only_available_receipts(self) -> None:
        self._assert_missing_contract("plan.md")
