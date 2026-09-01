"""The review execution environment: one temporary worktree, always withdrawn.

There is exactly one strategy, because one is enough and it is the only one that
works from any starting state: the candidate is materialized in a temporary
worktree under the evidence root, so the operator's branch, index, and untracked
files are never touched, and the review never depends on the checkout being
clean or on any particular commit.

The worktree lives outside the repository by construction and is withdrawn when
the review ends. A worktree still holding uncommitted content is **kept** and
reported with the command that removes it: nothing is ever forced or discarded.
"""

from __future__ import annotations

import signal
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

from .errors import EXIT_ENVIRONMENT, EXIT_USAGE, AppError, Diagnostic
from .evidence import harden_directories
from .git import Git


WORKTREE_DIRECTORY_NAME = "worktree"

# Enumerated here so the contract is readable next to the code that relies on
# it, and asserted behaviourally by the tests: local refs, .git/config, hooks,
# the stash, `gc`, `prune`, `worktree prune` and `reflog expire` are never
# touched.
PERMITTED_GIT_WRITES: tuple[str, ...] = (
    "objects and packs brought in by one bounded fetch (a single SHA, or refs/pull/<n>/head)",
    "FETCH_HEAD, which git updates as an effect of that fetch",
    "worktree metadata under .git/worktrees/<name>",
    "the reflog derived from those operations",
)

FORBIDDEN_GIT_WRITES: tuple[str, ...] = (
    "creating, moving or deleting local refs (branches, tags, remotes)",
    "editing .git/config, hooks, or any configuration file",
    "git gc, git prune, git worktree prune, git reflog expire",
    "any write to the stash",
    "any change to the operator's own checkout",
)


@dataclass
class PreparedEnvironment:
    """A materialized candidate: the temporary worktree and how to withdraw it."""

    head_commit: str
    repository_root: Path
    working_root: Path
    git: Git
    worktree_path: Path | None = None
    forbidden_roots: tuple[Path, ...] = ()
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "head_commit": self.head_commit,
            "repository_root": str(self.repository_root),
            "working_root": str(self.working_root),
            "worktree_path": str(self.worktree_path) if self.worktree_path else None,
            "forbidden_roots": [str(path) for path in self.forbidden_roots],
            "permitted_git_writes": list(PERMITTED_GIT_WRITES),
        }


def prepare(
    git: Git,
    *,
    head_commit: str,
    worktree_parent: Path,
    forbidden_roots: Sequence[Path] = (),
    into: "PreparedEnvironment | None" = None,
) -> PreparedEnvironment:
    """Materialize the candidate in a temporary worktree; never destructive.

    ``into`` lets the caller own the (initially unmaterialized) description
    *before* anything is materialized, so an interruption in the middle of
    ``git worktree add`` still has something restorable to hand to ``restore``.
    """

    repository_root = git.root or git.toplevel(Path.cwd())
    prepared = into or PreparedEnvironment(
        head_commit=head_commit,
        repository_root=repository_root,
        working_root=repository_root,
        git=git,
        forbidden_roots=tuple(forbidden_roots),
    )

    path = _worktree_path(worktree_parent, repository_root)
    # The path is recorded before the worktree exists, so an interruption
    # mid-creation still leaves a withdrawable record rather than an orphan.
    prepared.worktree_path = path
    result = git.worktree_add(path, head_commit)
    if not result.ok:
        prepared.worktree_path = path if path.exists() else None
        raise AppError(
            f"could not create the temporary worktree at {path}",
            code=EXIT_ENVIRONMENT,
            diagnostics=[Diagnostic("worktree_add_failed", result.stderr.strip() or "git worktree add failed")],
        )
    prepared.working_root = path
    prepared.git = Git(git.executable, root=path, timeout=git.timeout)
    # The newly materialized tree is candidate content too, so it joins the
    # paths no executable may be resolved from for the rest of the session.
    prepared.forbidden_roots = (*prepared.forbidden_roots, path)
    prepared.diagnostics.append(
        Diagnostic("environment_worktree", f"temporary worktree created at {path}", str(path), severity="info")
    )
    return prepared


def _worktree_path(parent: Path, repository_root: Path) -> Path:
    path = (parent / WORKTREE_DIRECTORY_NAME).expanduser()
    resolved_parent = parent.expanduser().resolve() if parent.exists() else parent.expanduser().absolute()
    root = repository_root.resolve()
    if resolved_parent == root or root in resolved_parent.parents:
        raise AppError(
            f"the temporary worktree may not live inside the repository under review: {resolved_parent}",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "worktree_inside_repository",
                    "the worktree lives under the evidence root, which is outside the repository by construction",
                    str(resolved_parent),
                )
            ],
        )
    # The worktree holds candidate content under the evidence root, so every
    # directory created on the way to it is 0700 like the rest of the evidence.
    harden_directories(parent)
    return path


@dataclass
class RestoreOutcome:
    """What the withdrawal did, and what the operator must do if it could not."""

    restored: bool
    already_restored: bool = False
    retained_worktree: Path | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    code: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "restored": self.restored,
            "already_restored": self.already_restored,
            "retained_worktree": str(self.retained_worktree) if self.retained_worktree else None,
            "code": self.code,
        }


def restore(prepared: PreparedEnvironment) -> RestoreOutcome:
    """Withdraw exactly what ``prepare`` created -- and never anything else."""

    path = prepared.worktree_path
    git = Git(prepared.git.executable, root=prepared.repository_root, timeout=prepared.git.timeout)
    if path is None:
        return RestoreOutcome(
            restored=True,
            already_restored=True,
            diagnostics=[Diagnostic("environment_restored", "nothing had been materialized", severity="info")],
        )
    if not path.exists():
        return RestoreOutcome(
            restored=True,
            already_restored=True,
            diagnostics=[
                Diagnostic(
                    "environment_already_restored",
                    f"the temporary worktree {path} is already gone; if git still lists it, run `git worktree prune` yourself",
                    str(path),
                    severity="info",
                )
            ],
        )

    worktree_git = Git(prepared.git.executable, root=path, timeout=prepared.git.timeout)
    try:
        dirty = worktree_git.status_porcelain().strip()
    except AppError:
        # An interrupted `git worktree add` withdraws its own half-created
        # worktree; when that lands between the existence check above and
        # this status, the worktree is gone -- which is restored, not broken.
        if not path.exists():
            return RestoreOutcome(
                restored=True,
                already_restored=True,
                diagnostics=[
                    Diagnostic(
                        "environment_already_restored",
                        f"the temporary worktree {path} withdrew itself mid-restore; "
                        "if git still lists it, run `git worktree prune` yourself",
                        str(path),
                        severity="info",
                    )
                ],
            )
        raise
    if dirty:
        return RestoreOutcome(
            restored=False,
            retained_worktree=path,
            code=EXIT_ENVIRONMENT,
            diagnostics=[
                Diagnostic(
                    "worktree_retained",
                    f"the temporary worktree holds uncommitted content and was kept at {path}. "
                    f"Rescue what you need, then run: git worktree remove {path} "
                    f"(and `git worktree prune` if the directory is already gone but git still lists it)",
                    str(path),
                )
            ],
        )

    result = git.worktree_remove(path)
    if not result.ok:
        return RestoreOutcome(
            restored=False,
            retained_worktree=path,
            code=EXIT_ENVIRONMENT,
            diagnostics=[
                Diagnostic(
                    "worktree_remove_failed",
                    f"could not withdraw {path}: {result.stderr.strip() or 'git worktree remove failed'}. "
                    f"Run it yourself once you have looked: git worktree remove {path}",
                    str(path),
                )
            ],
        )
    return RestoreOutcome(
        restored=True,
        diagnostics=[Diagnostic("environment_restored", f"the temporary worktree {path} was withdrawn", severity="info")],
    )


class SignalInterrupt(BaseException):
    """A ``SIGTERM`` delivered while an environment was prepared."""

    def __init__(self, signal_number: int) -> None:
        super().__init__(f"interrupted by signal {signal_number}")
        self.signal_number = signal_number


@contextmanager
def prepared_environment(
    git: Git,
    *,
    head_commit: str,
    worktree_parent: Path,
    forbidden_roots: Sequence[Path] = (),
) -> Iterator[PreparedEnvironment]:
    """Prepare an environment whose withdrawal is guaranteed on failure.

    The cleanup block runs on exception, on ``SIGINT`` and on ``SIGTERM`` too --
    and, critically, the **materialization itself happens inside that guard**. A
    signal delivered in the middle of ``git worktree add`` would otherwise leave
    a materialized environment with nothing recorded and nobody withdrawing it.

    On a *successful* exit the environment is deliberately left prepared: the
    first phase ends with the candidate materialized on purpose, so the agent can
    read it and run the packet's diff commands against it.
    """

    repository_root = git.root or git.toplevel(Path.cwd())
    prepared = PreparedEnvironment(
        head_commit=head_commit,
        repository_root=repository_root,
        working_root=repository_root,
        git=git,
        forbidden_roots=tuple(forbidden_roots),
    )
    with _signal_guard():
        try:
            prepare(
                git,
                head_commit=head_commit,
                worktree_parent=worktree_parent,
                forbidden_roots=forbidden_roots,
                into=prepared,
            )
            yield prepared
        except BaseException as error:
            with _signals_ignored():
                outcome = restore(prepared)
            if not outcome.restored:
                raise AppError(
                    "the review environment could not be restored",
                    code=outcome.code or EXIT_ENVIRONMENT,
                    diagnostics=outcome.diagnostics,
                ) from error
            raise


@contextmanager
def _signal_guard() -> Iterator[None]:
    """Turn ``SIGINT``/``SIGTERM`` into an exception the cleanup block can see."""

    def _raise(signal_number: int, _frame: Any) -> None:
        raise SignalInterrupt(signal_number)

    with _handlers(_raise):
        yield


@contextmanager
def _signals_ignored() -> Iterator[None]:
    """Ignore ``SIGINT``/``SIGTERM`` while the cleanup block runs.

    A second Ctrl-C during the withdrawal would otherwise escape it and leave the
    environment half restored -- with the process reporting the interruption as
    if everything had been put back.
    """

    with _handlers(signal.SIG_IGN):
        yield


@contextmanager
def _handlers(handler: Any) -> Iterator[None]:
    installed: dict[int, Any] = {}
    for number in (signal.SIGINT, signal.SIGTERM):
        try:
            installed[number] = signal.signal(number, handler)
        except (ValueError, OSError):  # not the main thread, or unsupported
            continue
    try:
        yield
    finally:
        for number, previous in installed.items():
            try:
                signal.signal(number, previous)
            except (ValueError, OSError):
                continue
