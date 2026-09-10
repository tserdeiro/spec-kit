"""Tests for the preset's skill_mirror script: the two-integration mirror
with and without an existing append, a replaced core reset or missing on
the lagging side, the single-integration skip, and the two fail-closed
cases (a bad append, an unsupported strategy). The script reads only
files, so a hand-built fixture stands in for a real install -- no repo or
gh fixture needed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import skill_mirror

_APPENDS = {
    "tasks-append.md": "## Order (tserdeiro/spec-kit)\nline one\nline two\n",
}
_PRESET_YML = """provides:
  commands:
    - type: "command"
      name: "speckit.tasks"
      file: "commands/tasks-append.md"
      strategy: "append"
    - type: "command"
      name: "speckit.implement"
      file: "commands/implement.md"
      strategy: "replace"
"""

def _fixture(root: Path) -> None:
    """codex (default) and claude (lagging), each with three core skills
    (implement, tasks, checklist) and codex's own extension skill, pr, not
    yet mirrored into claude; claude's tasks render carries no append yet,
    its implement render predates the preset's replace, and its own
    speckit-pr is stale."""
    (root / ".specify").mkdir(parents=True)
    (root / ".specify/init-options.json").write_text('{"ai": "codex"}', encoding="utf-8")
    (root / ".specify/integration.json").write_text(
        json.dumps({"installed_integrations": ["codex", "claude"]}), encoding="utf-8")
    (root / ".specify/integrations").mkdir()
    for key, prefix in (("codex", ".agents"), ("claude", ".claude")):
        files = {f"{prefix}/skills/speckit-{n}/SKILL.md": "x" for n in ("implement", "tasks", "checklist")}
        (root / f".specify/integrations/{key}.manifest.json").write_text(
            json.dumps({"files": files}), encoding="utf-8")
    commands = root / ".specify/presets/default/commands"
    commands.mkdir(parents=True)
    (commands.parent / "preset.yml").write_text(_PRESET_YML, encoding="utf-8")
    for name, body in _APPENDS.items():
        (commands / name).write_text(body, encoding="utf-8")
    for name in ("implement", "tasks", "checklist"):
        path = root / f".agents/skills/speckit-{name}/SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text("codex core render, content unused by this name\n", encoding="utf-8")
    (root / ".agents/skills/speckit-pr").mkdir(parents=True)
    (root / ".agents/skills/speckit-pr/SKILL.md").write_text("codex pr body, extension skill\n", encoding="utf-8")
    for name, body in (("implement", "claude implement body"), ("tasks", "claude tasks body")):
        path = root / f".claude/skills/speckit-{name}/SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f'---\nname: "speckit-{name}"\nframework: "claude"\n---\n{body}\n', encoding="utf-8")
    checklist = root / ".claude/skills/speckit-checklist/SKILL.md"
    checklist.parent.mkdir(parents=True)
    checklist.write_text("claude checklist body, core, no append\n", encoding="utf-8")
    (root / ".claude/skills/speckit-pr").mkdir(parents=True)
    (root / ".claude/skills/speckit-pr/SKILL.md").write_text("stale content\n", encoding="utf-8")

def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}

def test_report_then_fix_then_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fixture(tmp_path)
    before = _snapshot(tmp_path)
    assert skill_mirror.mirror_skills(tmp_path, False) == 0
    report = capsys.readouterr().out
    for name in ("speckit-pr", "speckit-implement", "speckit-tasks"):
        assert name in report
    assert "speckit-checklist" not in report
    assert _snapshot(tmp_path) == before  # fix=false never writes

    assert skill_mirror.mirror_skills(tmp_path, True) == 0
    fixed = capsys.readouterr().out
    assert "copied speckit-pr" in fixed
    assert "copied speckit-implement" in fixed
    assert "appended the preset layer to speckit-tasks" in fixed
    mirrored_pr = tmp_path / ".claude/skills/speckit-pr/SKILL.md"
    assert mirrored_pr.read_bytes() == (tmp_path / ".agents/skills/speckit-pr/SKILL.md").read_bytes()
    mirrored_implement = tmp_path / ".claude/skills/speckit-implement/SKILL.md"
    assert mirrored_implement.read_bytes() == (tmp_path / ".agents/skills/speckit-implement/SKILL.md").read_bytes()
    tasks = (tmp_path / ".claude/skills/speckit-tasks/SKILL.md").read_text(encoding="utf-8")
    assert tasks == (
        '---\nname: "speckit-tasks"\nframework: "claude"\n---\nclaude tasks body'
        "\n\n\n## Order (tserdeiro/spec-kit)\nline one\nline two\n"
    )
    checklist = tmp_path / ".claude/skills/speckit-checklist/SKILL.md"
    assert checklist.read_text(encoding="utf-8") == "claude checklist body, core, no append\n"

    mid = _snapshot(tmp_path)
    assert skill_mirror.mirror_skills(tmp_path, True) == 0
    assert capsys.readouterr().out == "mirror: nothing to do\n"
    assert _snapshot(tmp_path) == mid  # idempotent: nothing left to change

def test_single_integration_is_skipped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".specify").mkdir(parents=True)
    (tmp_path / ".specify/init-options.json").write_text('{"ai": "codex"}', encoding="utf-8")
    (tmp_path / ".specify/integration.json").write_text(
        json.dumps({"installed_integrations": ["codex"]}), encoding="utf-8")
    assert skill_mirror.mirror_skills(tmp_path, False) == 0
    assert capsys.readouterr().out == "mirror: only one integration installed, skipped\n"

def test_bad_append_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A registered append pointing at a missing file must fail before any
    write, even for the core skills that would otherwise need one (review
    finding kept as a regression test, dogfooding entry 41's block)."""
    _fixture(tmp_path)
    skill_mirror.mirror_skills(tmp_path, True)  # bring every other name to its fixed point first
    capsys.readouterr()
    preset_yml = tmp_path / ".specify/presets/default/preset.yml"
    with preset_yml.open("a", encoding="utf-8") as handle:
        handle.write(
            '    - type: "command"\n      name: "speckit.checklist"\n'
            '      file: "commands/missing-append.md"\n      strategy: "append"\n'
        )
    before = _snapshot(tmp_path)
    assert skill_mirror.mirror_skills(tmp_path, True) == 2
    assert capsys.readouterr().err == (
        "mirror: append .specify/presets/default/commands/missing-append.md "
        "for speckit-checklist is missing or has no heading\n"
    )
    assert _snapshot(tmp_path) == before

def test_replaced_core_reset_or_missing_is_copied_whole(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A replaced core render that `integration upgrade --force` reset to
    upstream's, or that is missing outright, comes back whole on the next
    fix run -- the lagging integration's regression once `implement`
    became a replace (dogfooding entry 71)."""
    _fixture(tmp_path)
    skill_mirror.mirror_skills(tmp_path, True)
    capsys.readouterr()
    source = tmp_path / ".agents/skills/speckit-implement/SKILL.md"
    mirrored = tmp_path / ".claude/skills/speckit-implement/SKILL.md"
    mirrored.write_text(
        '---\nname: "speckit-implement"\nmetadata:\n  source: "templates/commands/implement.md"\n---\n'
        "upstream core body, the replace lost\n", encoding="utf-8")
    assert skill_mirror.mirror_skills(tmp_path, False) == 0
    assert "speckit-implement missing or differs in .claude/skills (claude)" in capsys.readouterr().out
    assert skill_mirror.mirror_skills(tmp_path, True) == 0
    assert "copied speckit-implement" in capsys.readouterr().out
    assert mirrored.read_bytes() == source.read_bytes()
    shutil.rmtree(mirrored.parent)
    assert skill_mirror.mirror_skills(tmp_path, True) == 0
    assert "copied speckit-implement" in capsys.readouterr().out
    assert mirrored.read_bytes() == source.read_bytes()
    assert skill_mirror.mirror_skills(tmp_path, True) == 0
    assert capsys.readouterr().out == "mirror: nothing to do\n"

def test_unsupported_strategy_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A registered command strategy the mirror cannot compose (wrap,
    prepend) stops the run before any write -- with the fixture's copies
    and appends still pending -- instead of skipping that command silently,
    the shape of the gap a replace once fell into."""
    _fixture(tmp_path)
    preset_yml = tmp_path / ".specify/presets/default/preset.yml"
    with preset_yml.open("a", encoding="utf-8") as handle:
        handle.write(
            '    - type: "command"\n      name: "speckit.checklist"\n'
            '      file: "commands/checklist.md"\n      strategy: "wrap"\n'
        )
    before = _snapshot(tmp_path)
    assert skill_mirror.mirror_skills(tmp_path, True) == 2
    assert capsys.readouterr().err == (
        'mirror: speckit-checklist registers command strategy "wrap" -- '
        "the mirror composes only append and replace\n"
    )
    assert _snapshot(tmp_path) == before
