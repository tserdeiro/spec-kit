"""Tests for the preset's budget_stop script: under/over the stop, the
no-forecast and forecast-capped defaults, and the fenced-sample skip,
against feature_repo from conftest.py. A real git diff (not a fake) drives
the counted-line exclusions."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import budget_stop

LEDGER = "- [ ] T001 Sample\n  - **Delivery**: single PR (~50 authored lines)\n"

def _write_ledger(repo: Path, text: str) -> None:
    path = repo / "specs/003-feature/tasks.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def _branch_from_feature(repo: Path, branch: str) -> None:
    subprocess.run(["git", "switch", "-q", "-c", branch, "003-feature"], cwd=repo, check=True, capture_output=True)

def _commit(repo: Path, path: str, content: str = "", binary: bool = False) -> None:
    full = repo / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(b"\x00binary") if binary else full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "test: add file"], cwd=repo, check=True, capture_output=True)

def _lines(count: int) -> str:
    return "\n".join(f"line {i}" for i in range(count)) + "\n"

def test_under_the_stop_excludes_binaries_lockfiles_and_docs(feature_repo: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    _write_ledger(feature_repo, LEDGER)
    _branch_from_feature(feature_repo, "003-T001-slug")
    _commit(feature_repo, "src/a.py", _lines(10))
    _commit(feature_repo, "docs/guide.md", _lines(500))
    _commit(feature_repo, "uv.lock", _lines(9))
    _commit(feature_repo, "assets/logo.png", binary=True)
    assert budget_stop.check_budget(feature_repo, "T001", "003-feature") == 0
    assert capsys.readouterr().out == "budget: 10/100 (forecast ~50)\n"

def test_over_the_stop_diagnoses_and_lists_the_largest_files(feature_repo: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    _write_ledger(feature_repo, LEDGER)
    _branch_from_feature(feature_repo, "003-T001-slug")
    _commit(feature_repo, "src/a.py", _lines(101))
    assert budget_stop.check_budget(feature_repo, "T001", "003-feature") == 2
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "error: T001 added 101 lines against a stop of 100 (forecast ~50)"
    assert lines[1] == "101 src/a.py"

def test_no_forecast_marker_defaults_to_400(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_ledger(feature_repo, "- [ ] T001 Sample\n  - **Delivery**: single PR\n")
    _branch_from_feature(feature_repo, "003-T001-slug")
    _commit(feature_repo, "src/a.py", _lines(350))
    assert budget_stop.check_budget(feature_repo, "T001", "003-feature") == 0
    assert capsys.readouterr().out == "budget: 350/400 (forecast ~400)\n"

def test_forecast_double_over_400_is_capped_at_400(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_ledger(feature_repo, "- [ ] T001 Sample\n  - **Delivery**: single PR (~300 authored lines)\n")
    _branch_from_feature(feature_repo, "003-T001-slug")
    _commit(feature_repo, "src/a.py", _lines(401))
    assert budget_stop.check_budget(feature_repo, "T001", "003-feature") == 2
    assert "stop of 400" in capsys.readouterr().err

def test_fenced_sample_delivery_line_is_never_read_as_the_forecast(feature_repo: Path,
                                                                      capsys: pytest.CaptureFixture[str]) -> None:
    ledger = ("```markdown\n- [ ] T001 Fenced sample\n  - **Delivery**: single PR\n```\n"
              "- [ ] T001 Real task\n  - **Delivery**: single PR (~20 authored lines)\n")
    _write_ledger(feature_repo, ledger)
    _branch_from_feature(feature_repo, "003-T001-slug")
    _commit(feature_repo, "src/a.py", _lines(40))
    assert budget_stop.check_budget(feature_repo, "T001", "003-feature") == 0
    assert capsys.readouterr().out == "budget: 40/40 (forecast ~20)\n"

def test_main_reads_argv_and_cwd(feature_repo: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    _write_ledger(feature_repo, LEDGER)
    _branch_from_feature(feature_repo, "003-T001-slug")
    _commit(feature_repo, "src/a.py", _lines(10))
    monkeypatch.chdir(feature_repo)
    assert budget_stop.main(["T001", "003-feature"]) == 0
    assert capsys.readouterr().out == "budget: 10/100 (forecast ~50)\n"

def test_missing_ledger_exits_2(feature_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _branch_from_feature(feature_repo, "003-T001-slug")
    with pytest.raises(SystemExit) as excinfo:
        budget_stop.check_budget(feature_repo, "T001", "003-feature")
    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: task ledger not found: specs/003-feature/tasks.md\n"
