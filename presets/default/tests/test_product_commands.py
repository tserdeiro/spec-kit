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


def test_pr_feature_variant_resolves_before_approval_commit() -> None:
    pr = (COMMANDS / "pr.md").read_text(encoding="utf-8")
    resolution = pr.split("## 2. Guarantee the branch invariant", 1)[0]

    assert re.search(
        r"whether\s+its artifacts are local\s+drafts or already published",
        resolution,
    )
    assert "with its artifacts committed" not in resolution
    assert "feature PR" in resolution


def test_feature_publication_observes_state_and_uses_idempotent_writes() -> None:
    pr = (COMMANDS / "pr.md").read_text(encoding="utf-8")
    observation = pr.index("## 3. Observe before every feature mutation")
    first_commit = pr.index("git commit --only")

    assert observation < first_commit
    for command in (
        "check-prerequisites.sh --paths-only",
        "git remote get-url origin",
        "pr_create.py feature",
        'gh repo view "$origin_url" --json nameWithOwner --jq .nameWithOwner',
        "git rev-parse HEAD",
        "git ls-remote --heads origin <branch>",
        'gh pr view <branch> --repo "$origin_url" --json',
        'gh pr create --repo "$origin_url" --draft',
        'gh pr edit --repo "$origin_url" <number>',
    ):
        assert command in pr
    assert "publication lookup failed" in pr
    assert "confirmed absence" in pr
    assert "Only `state: OPEN` is reusable" in pr
    assert "CLOSED` or `MERGED`" in pr
    assert "headRepository.nameWithOwner" in pr
    assert "isCrossRepository" in pr
    assert "expected_base" in pr
    assert "expected_repo" in pr
    assert "expected_head" in pr
    assert "origin_url" in pr
    assert "current branch does not match selected feature" in pr
    assert 'expected_base="$base"' in pr
    assert "GitHub target repository is empty" in pr
    assert "confirmed remote OID" in pr
    assert "before reporting publication verified" in pr
    assert "gate-consistency failure" in pr
    assert "Never adopt an observed `baseRefName`" in pr
    assert observation < pr.index("pr_create.py feature") < pr.index(
        'gh pr view <branch> --repo "$origin_url" --json'
    )
    assert "--body-file \"$body_file\"" in pr
    assert "--body \"<the body>\"" not in pr
    assert pr.index("git commit --only") < pr.index("gh pr create")

    preparation = pr.split("## 4. Prepare the canonical body", 1)[1].split(
        "## 5. Publish the approved handoff", 1
    )[0]
    publication = pr.split("## 5. Publish the approved handoff", 1)[1].split(
        "## 6. Open task or work-item delivery PRs", 1
    )[0]
    assert "approved feature diff" in preparation
    assert "effective committed diff" in preparation
    assert 'git diff "$base"...HEAD --stat' in publication
    assert publication.index('git diff "$base"...HEAD --stat') < publication.index(
        "gh pr create"
    )
    assert publication.index("gh pr view <branch> --repo \"$origin_url\" --json number,state,isCrossRepository,headRepository,headRepositoryOwner,headRefName,baseRefName,headRefOid") < publication.index(
        "git push -u origin"
    )
    assert re.search(r"known\s+push\s+failure\s+stops before PR or Linear writes", publication)
    assert re.search(
        r"same\s+number, state, head branch, base branch, and remote head\s+OID",
        publication,
    )
    assert publication.index("status --current") < publication.index("gh pr create")
    assert "reuse its body verbatim" in publication
    assert re.search(r"stable\s+Linear IDs, states, assignees", preparation)
    assert "historical successful publication evidence" in preparation
    assert re.search(r"retry with zero operations", publication)
    assert "retry counters" in preparation
    assert 'gh pr create --repo "$origin_url" --draft --base "$base" --title "feat(<area>): <feature outcome>" --body-file "$body_file"' in publication
    assert 'gh pr edit --repo "$origin_url" <number> --body-file "$body_file"' in publication
    assert re.search(
        r"Preserve the Git and PR publication\s+when Linear requirements\s+fail",
        publication,
    )
    assert "expected_base" in publication
    assert "never adopt its observed `baseRefName`" in publication
    assert "Run exactly one delivery route" in pr


def test_feature_close_covers_interrupted_retries_and_handoff_prerequisites() -> None:
    pr = (COMMANDS / "pr.md").read_text(encoding="utf-8")
    phase = (COMMANDS / "phase-close-append.md").read_text(encoding="utf-8")

    for text in (pr, phase):
        assert re.search(r"explicit\s+human\s+approval", text)
        assert "material" in text
        assert "ambiguous" in text
    assert "Only `state: OPEN` is reusable" in pr
    assert "reuses only an OPEN" in phase
    assert "unassigned" in phase
    for phrase in (
        "lost push",
        "lost or ambiguous response",
        "ambiguous response",
        "known commit or push failure",
        "lost response or timeout",
        "Two unchanged retries",
        "zero duplicate",
        "push --current --apply",
        "status --current",
        "technical approval",
    ):
        assert phrase in pr
    assert re.search(r"assignment allowlist\s+remains unchanged", pr)
    assert re.search(r"completion\s+checkboxes and completion\s+evidence alone", pr, re.I)

    task_flow = pr.split("## 6. Open task or work-item delivery PRs", 1)[1]
    assert task_flow.index("1. Observe") < task_flow.index("2. Immediately before pushing") < task_flow.index("3. Observe")
    assert task_flow.index("2. Immediately before pushing") < task_flow.index("git push -u origin")
    assert "Fixes WOR-123" in task_flow
    assert "N/A" in task_flow
    assert "(chore)" in task_flow
    assert task_flow.index("1. Observe") < task_flow.index('base_line="$(GH_REPO=')
    assert "do not invoke `pr_create.py`" in task_flow
    assert 'gh pr create --repo "$origin_url" --draft --base "$base" --title "<type(scope): subject>" --body-file "$body_file"' in task_flow
    assert 'gh pr edit --repo "$origin_url" <number> --body-file "$body_file"' in task_flow


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
