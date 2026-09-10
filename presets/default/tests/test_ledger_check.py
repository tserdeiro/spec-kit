"""Tests for the preset's ledger_check script: checked with evidence,
unchecked, checked but "Pending", checked but empty evidence, both
missing at once, and the template's bracketed sample text, against
feature_repo from conftest.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import ledger_check

def _write_task(repo: Path, checkbox: str, evidence_line: str = "") -> None:
    path = repo / "specs/003-feature/tasks.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"- [{checkbox}] T001 Sample\n  - **Delivery**: single PR (~50 authored lines)\n"
    if evidence_line:
        text += f"  - **Completion evidence**: {evidence_line}\n"
    path.write_text(text, encoding="utf-8")

def test_checked_with_evidence_exits_0(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_task(feature_repo, "x", "PR #90; tests green")
    assert ledger_check.check_ledger(feature_repo, "T001") == 0
    assert capsys.readouterr().out == "ledger: T001 checked, completion evidence filled\n"

def test_unchecked_exits_2(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_task(feature_repo, " ", "PR #90; tests green")
    with pytest.raises(SystemExit) as excinfo:
        ledger_check.check_ledger(feature_repo, "T001")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: task T001 is not checked\n"

def test_checked_but_pending_exits_2(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_task(feature_repo, "x", "Pending")
    with pytest.raises(SystemExit) as excinfo:
        ledger_check.check_ledger(feature_repo, "T001")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: task T001 has no completion evidence\n"

def test_checked_but_empty_evidence_exits_2(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_task(feature_repo, "x")
    with pytest.raises(SystemExit) as excinfo:
        ledger_check.check_ledger(feature_repo, "T001")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: task T001 has no completion evidence\n"

def test_both_missing_are_joined_with_and(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_task(feature_repo, " ", "pending")
    with pytest.raises(SystemExit) as excinfo:
        ledger_check.check_ledger(feature_repo, "T001")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: task T001 is not checked and has no completion evidence\n"

def test_template_sample_text_is_not_filled(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sample = "[filled in the task PR's final commit, before ready for review; the merge lands it on the feature branch]"
    _write_task(feature_repo, "x", sample)
    with pytest.raises(SystemExit) as excinfo:
        ledger_check.check_ledger(feature_repo, "T001")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: task T001 has no completion evidence\n"
