from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def copy_consumer_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    source = Path(__file__).parents[1] / "fixtures" / "consumer"
    destination = Path(temporary.name) / "consumer"
    shutil.copytree(source, destination)
    return temporary, destination


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def worktree_repository() -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    """A real repository (`git init`, one commit) with one linked worktree.

    Returns ``(temporary, main_root, worktree_root)``; clean up with
    ``temporary.cleanup()``, as :func:`copy_consumer_fixture` callers do.
    """

    temporary = tempfile.TemporaryDirectory()
    main_root = Path(temporary.name).resolve() / "main"
    worktree_root = main_root.parent / "wt"
    main_root.mkdir()
    (main_root / "README.md").write_text("# sample\n", encoding="utf-8")
    run_git(main_root, "init", "-q")
    run_git(main_root, "config", "user.email", "test@example.com")
    run_git(main_root, "config", "user.name", "Test")
    run_git(main_root, "add", "README.md")
    run_git(main_root, "commit", "-q", "-m", "init")
    run_git(main_root, "worktree", "add", "-q", "-b", "wt-branch", str(worktree_root), "HEAD")
    return temporary, main_root, worktree_root


def isolate_operator_global_env(case) -> None:
    """Point the operator-global env file at a nonexistent path for this test.

    Without this, a developer's real ~/.config/speckit-linear/env leaks into
    any test that invokes the CLI, silently turning offline-fallback tests
    into live-credential runs.
    """

    from spec_kit_linear import env_files

    original = env_files.OPERATOR_GLOBAL_ENV_PATH
    env_files.OPERATOR_GLOBAL_ENV_PATH = Path(tempfile.gettempdir()) / "speckit-linear-test-no-global-env"
    case.addCleanup(setattr, env_files, "OPERATOR_GLOBAL_ENV_PATH", original)
