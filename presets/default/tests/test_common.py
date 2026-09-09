"""Tests for the default preset's shared script helper, ``_common``."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from spec_kit_linear import parser as linear_parser

import _common

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "tasks-template.md"

REAL_TASK = """\
- [x] T025 [US1] Shared helper and test harness
  - **Delivery**: single PR (~120 authored lines)
  - **Completion evidence**: PR #90, `uv run pytest presets/default/tests` -> green
- [ ] T001 [US1] Next task
  - **Delivery**: single PR (~150 authored lines)
  - **Completion evidence**: Pending
"""

def test_fence_rule_equals_the_linear_parsers() -> None:
    for name in ("_fence_start", "_fence_end"):
        assert inspect.getsource(getattr(_common, name)) == inspect.getsource(getattr(linear_parser, name))

def test_parse_ledger_skips_the_template_fenced_sample() -> None:
    tasks = _common.parse_ledger(TEMPLATE.read_text(encoding="utf-8"))
    assert [task.id for task in tasks] == ["T001", "T002", "T003", "T004"]
    assert tasks[0].completion_evidence == "Pending"
    assert tasks[0].forecast == _common.DEFAULT_FORECAST

def test_parse_ledger_reads_a_real_task_block() -> None:
    tasks = _common.parse_ledger(REAL_TASK)
    assert tasks[0] == _common.Task("T025", True, 120, "PR #90, `uv run pytest presets/default/tests` -> green")
    assert _common.first_unchecked(tasks) == tasks[1]
    assert tasks[1].forecast == 150

def _set_trunk(repo: Path, value: str) -> None:
    (repo / ".specify/extensions/git").mkdir(parents=True)
    (repo / ".specify/extensions/git/git-config.yml").write_text(value, encoding="utf-8")

def test_delivery_base_explicit_trunk_wins(repo: Path) -> None:
    _set_trunk(repo, 'trunk: "custom-trunk"\n')
    assert _common.delivery_base(repo) == "custom-trunk"

def test_delivery_base_falls_back_to_the_default_branch(repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_DEFAULT_BRANCH", "trunk-main")
    assert _common.delivery_base(repo) == "trunk-main"
    calls = [json.loads(line) for line in fake_gh.read_text(encoding="utf-8").splitlines()]
    assert calls == [["repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]]
    _set_trunk(repo, 'trunk: ""\n')
    assert _common.delivery_base(repo) == "trunk-main"

def test_run_gh_json_dies_on_a_failing_call(repo: Path, fake_gh: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _common.run_gh_json("nonsense", cwd=repo)  # the fake gh exits 1 on argv it does not know
    assert excinfo.value.code == 2

def test_run_gh_json_dies_on_invalid_json(repo: Path, fake_gh: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_PR_LIST_JSON", "not json")
    with pytest.raises(SystemExit) as excinfo:
        _common.run_gh_json("pr", "list", "--state", "open", "--limit", "100", "--json", "headRefName,baseRefName,isDraft", cwd=repo)
    assert excinfo.value.code == 2

def test_die_writes_to_stderr_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _common.die("something went wrong")
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "error: something went wrong\n")
