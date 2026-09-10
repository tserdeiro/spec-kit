"""Tests for the preset's ignore_entries script: the venv-already-covered
case (report, fix, idempotent) and the no-.gitignore-at-all case."""

from __future__ import annotations

from pathlib import Path

import pytest

import ignore_entries

_CACHE = (".specify/extensions/.cache/", ".specify/presets/.cache/", ".specify/integrations/.cache/")
_CACHE_LINES = "\n".join(_CACHE) + "\n"

def _gitignore(repo: Path, text: str) -> Path:
    path = repo / ".gitignore"
    path.write_text(text, encoding="utf-8")
    return path

def test_venv_covered_report_fix_then_idempotent(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    gitignore = _gitignore(repo, ".venv/\n")
    assert ignore_entries.add_ignore_entries(repo, False) == 0
    report = capsys.readouterr().out
    assert all(entry in report for entry in _CACHE) and ".specify/extensions/*/.venv/" not in report
    assert gitignore.read_text(encoding="utf-8") == ".venv/\n"

    assert ignore_entries.add_ignore_entries(repo, True) == 0
    assert gitignore.read_text(encoding="utf-8") == f".venv/\n\n# tserdeiro/spec-kit installer state\n{_CACHE_LINES}"
    capsys.readouterr()

    assert ignore_entries.add_ignore_entries(repo, True) == 0
    assert capsys.readouterr().out == "ignore: nothing to do\n"

def test_missing_gitignore_is_created_with_the_header(repo: Path) -> None:
    assert ignore_entries.add_ignore_entries(repo, True) == 0
    assert (repo / ".gitignore").read_text(encoding="utf-8") == (
        f"# tserdeiro/spec-kit installer state\n{_CACHE_LINES}.specify/extensions/*/.venv/\n"
    )
