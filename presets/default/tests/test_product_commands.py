"""Contract tests for the product-phase approval boundary."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "commands"
TEMPLATES = ROOT / "templates"
PRESET = ROOT / "preset.yml"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    )
    return result.stdout


def test_all_product_phases_share_the_local_draft_registration() -> None:
    preset = PRESET.read_text(encoding="utf-8")
    phase_append = 'file: "commands/phase-close-append.md"'

    for command in ("specify", "clarify", "plan", "analyze"):
        entry = re.search(
            rf'name: "speckit\.{command}"(?P<body>.*?)(?=\n\s*- type:|\Z)',
            preset,
            re.DOTALL,
        )
        assert entry, command
        assert phase_append in entry.group("body")
        assert 'strategy: "append"' in entry.group("body")

    tasks = re.search(
        r'name: "speckit\.tasks"(?P<body>.*?)(?=\n\s*- type:|\Z)',
        preset,
        re.DOTALL,
    )
    assert tasks
    assert 'file: "commands/tasks.md"' in tasks.group("body")
    assert 'strategy: "replace"' in tasks.group("body")

    phase = (COMMANDS / "phase-close-append.md").read_text(encoding="utf-8")
    assert phase.startswith("\n## Phase close (tserdeiro/spec-kit)\n")


def test_phase_close_suppresses_git_commit_but_keeps_linear_hooks() -> None:
    phase = (COMMANDS / "phase-close-append.md").read_text(encoding="utf-8")

    assert "product-phase `git.commit` hook is suppressed silently" in phase
    assert "including mandatory and default-enabled configurations" in phase
    assert "Mandatory hooks for other extensions, including Linear" in phase
    assert "The phase remains local" in phase
    assert "analysis itself is read-only" in phase
    assert "explicit human approval" in phase
    assert "feature variant of `/speckit.pr`" in phase
    assert "specs/<feature-directory>/" in phase
    assert "unrelated staged\n  content remains outside the commit" in phase
    assert "The phase ends committed" not in phase


def test_tasks_phase_does_not_publish_or_freeze_ids() -> None:
    tasks = (COMMANDS / "tasks.md").read_text(encoding="utf-8")

    assert "suppress every product-phase `git.commit` hook" in tasks
    assert "Mandatory Linear hooks remain active" in tasks
    assert "IDs are provisional during local refinement" in tasks
    assert "Freeze the task IDs" in tasks
    assert "Leave the generated `tasks.md` local" in tasks
    assert "Do not commit, push, or create a feature PR" in tasks
    assert "phase-close commit's subject" not in tasks


def test_templates_describe_the_same_approval_boundary() -> None:
    plan = (TEMPLATES / "plan-template.md").read_text(encoding="utf-8")
    tasks = (TEMPLATES / "tasks-template.md").read_text(encoding="utf-8")
    pr = (COMMANDS / "pr.md").read_text(encoding="utf-8")

    for text in (plan, tasks, pr):
        assert re.search(r"explicit\s+human", text)
        assert re.search(r"spec,\s+plan,\s+tasks", text)

    assert "Product approval of the exact analyzed artifacts" in plan
    assert "Product phases remain local drafts" in tasks
    assert "first approved publication" in tasks
    assert "Stage only" in pr
    assert "git diff --cached --name-only" in pr
    assert "git commit --only" in pr
    assert "stop if any unrelated staged path is present" not in pr
    assert "technical approval of the" in pr


def test_approved_close_commit_only_preserves_pre_staged_unrelated_files(
    repo: Path,
) -> None:
    """A native scoped commit leaves an unrelated staged path untouched."""
    feature = repo / "specs/003-feature"
    feature.mkdir(parents=True)
    (feature / "spec.md").write_text("draft\n", encoding="utf-8")
    unrelated = repo / "notes.txt"
    unrelated.write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore: base")

    (feature / "spec.md").write_text("approved\n", encoding="utf-8")
    unrelated.write_text("keep local\n", encoding="utf-8")
    # Both paths are already staged, as can happen when a developer has
    # unrelated work in progress before the approved close.
    _git(repo, "add", "--", "notes.txt", "specs/003-feature/")
    staged_before = set(_git(repo, "diff", "--cached", "--name-only").splitlines())
    assert staged_before == {"notes.txt", "specs/003-feature/spec.md"}

    # This is the exact scoped commit operation documented by pr.md.
    _git(
        repo,
        "commit",
        "--only",
        "-m",
        "docs(specs): approved feature",
        "--",
        "specs/003-feature/",
    )
    committed = set(_git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
    assert committed == {"specs/003-feature/spec.md"}
    assert set(_git(repo, "diff", "--cached", "--name-only").splitlines()) == {"notes.txt"}
