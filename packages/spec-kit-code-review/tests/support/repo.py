"""Real temporary Git repositories: the only credible way to test Git behaviour."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


GIT_ENVIRONMENT = {
    "GIT_AUTHOR_NAME": "Spec Kit Code Review Tests",
    "GIT_AUTHOR_EMAIL": "tests@example.invalid",
    "GIT_COMMITTER_NAME": "Spec Kit Code Review Tests",
    "GIT_COMMITTER_EMAIL": "tests@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


class TemporaryRepository:
    """A throwaway Git repository with a deterministic identity and branch name."""

    def __init__(self, path: Path | None = None) -> None:
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        if path is None:
            self._temporary = tempfile.TemporaryDirectory()
            path = Path(self._temporary.name) / "repository"
        path.mkdir(parents=True, exist_ok=True)
        self.path = path.resolve()
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", GIT_ENVIRONMENT["GIT_AUTHOR_NAME"])
        self.git("config", "user.email", GIT_ENVIRONMENT["GIT_AUTHOR_EMAIL"])
        self.git("config", "commit.gpgsign", "false")

    @classmethod
    def clone(cls, source: Path, destination: Path, *, branch: str = "main", single_branch: bool = True) -> "TemporaryRepository":
        """Clone ``source`` so a test can start from a repository that is genuinely
        missing objects the remote has -- the only honest way to exercise a fetch."""

        # --no-local forces the real transport: a local clone otherwise hardlinks
        # the whole object store and the "missing" objects would be present.
        arguments = ["git", "clone", "--no-local", "--branch", branch]
        if single_branch:
            arguments.append("--single-branch")
        arguments.extend([str(source), str(destination)])
        subprocess.run(
            arguments,
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": _path(), **GIT_ENVIRONMENT},
        )
        return cls(destination)

    # -- lifecycle ------------------------------------------------------

    def cleanup(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    # -- plumbing -------------------------------------------------------

    def git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.path), *arguments],
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": _path(), **GIT_ENVIRONMENT},
        )
        return completed.stdout.strip()

    def write(self, relative_path: str, content: str) -> Path:
        target = self.path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def commit(self, relative_path: str, content: str, message: str = "commit") -> str:
        self.write(relative_path, content)
        self.git("add", "--", relative_path)
        self.git("commit", "-m", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def sha(self, ref: str) -> str:
        return self.git("rev-parse", "--verify", f"{ref}^{{commit}}")

    def branch(self, name: str, *, start_point: str | None = None) -> None:
        arguments = ["switch", "--create", name]
        if start_point:
            arguments.append(start_point)
        self.git(*arguments)

    def checkout(self, ref: str) -> None:
        self.git("checkout", ref)

    def add_remote(self, name: str, url: str) -> None:
        self.git("remote", "add", name, url)

    def dirty(self, relative_path: str = "dirty.txt", content: str = "work in progress\n") -> Path:
        return self.write(relative_path, content)


def _path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")
