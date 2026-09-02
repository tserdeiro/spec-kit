"""Safe ``git`` wrapper: argv-only invocations and ref validation before use."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import EXIT_CANDIDATE, EXIT_PREREQUISITE, AppError, Diagnostic
from .process import CommandResult, resolve_executable, run_command


MINIMUM_GIT_VERSION = (2, 41)
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True)
class GitVersion:
    """The parsed ``git --version`` of the resolved executable."""

    raw: str
    parts: tuple[int, ...]

    @property
    def supported(self) -> bool:
        return self.parts >= MINIMUM_GIT_VERSION

    @property
    def text(self) -> str:
        return ".".join(str(part) for part in self.parts)


@dataclass(frozen=True)
class Remote:
    """A configured Git remote and the ``owner/name`` its URL normalizes to."""

    name: str
    url: str
    repository: str | None


class Git:
    """Every ``git`` invocation this extension makes, in one auditable place."""

    def __init__(self, executable: Path | str = "git", *, root: Path | None = None, timeout: int = 300) -> None:
        self.executable = str(executable)
        self.root = root
        self.timeout = timeout

    # -- invocation -----------------------------------------------------

    def run(self, *arguments: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
        argv = [self.executable]
        working_root = cwd or self.root
        if working_root is not None:
            argv.extend(["-C", str(working_root)])
        argv.extend(arguments)
        return run_command(argv, timeout=self.timeout, env=env)

    # -- environment ----------------------------------------------------

    def version(self) -> GitVersion:
        result = self.run("--version")
        if not result.ok:
            raise AppError(
                "git is not usable",
                code=EXIT_PREREQUISITE,
                diagnostics=[Diagnostic("git_unusable", result.stderr.strip() or "git --version failed")],
            )
        raw = result.stdout.strip()
        match = _VERSION_RE.search(raw)
        if not match:
            raise AppError(
                f"could not parse git version: {raw}",
                code=EXIT_PREREQUISITE,
                diagnostics=[Diagnostic("git_version_unparseable", "unexpected `git --version` output")],
            )
        parts = tuple(int(group) for group in match.groups() if group is not None)
        return GitVersion(raw=raw, parts=parts)

    def toplevel(self, start: Path) -> Path:
        result = self.run("rev-parse", "--show-toplevel", cwd=start)
        if not result.ok:
            raise AppError(
                f"not inside a Git worktree: {start}",
                code=EXIT_PREREQUISITE,
                diagnostics=[Diagnostic("git_root", "run this command inside a Git repository", str(start))],
            )
        return Path(result.stdout.strip()).resolve()

    def worktree_roots(self) -> list[Path]:
        """Every active worktree of this repository, resolved."""

        result = self.run("worktree", "list", "--porcelain")
        if not result.ok:
            return []
        roots: list[Path] = []
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                candidate = Path(line[len("worktree ") :].strip())
                try:
                    roots.append(candidate.resolve())
                except OSError:
                    roots.append(candidate)
        return roots

    def forbidden_roots(self) -> tuple[Path, ...]:
        """Every path an external executable may never be resolved from.

        Doc "Resolucion de ejecutables": the consumer repository toplevel and
        every active worktree of it. One implementation, shared by every caller,
        so no command can accidentally resolve an executable that lives in the
        tree under review.
        """

        roots: list[Path] = []
        if self.root is not None:
            try:
                roots.append(self.toplevel(self.root))
            except AppError:
                roots.append(self.root.resolve())
        for worktree in self.worktree_roots():
            if worktree not in roots:
                roots.append(worktree)
        return tuple(roots)

    # -- refs -----------------------------------------------------------

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """Whether ``ancestor`` is reachable from ``descendant``."""

        validate_ref_syntax(ancestor)
        validate_ref_syntax(descendant)
        return self.run("merge-base", "--is-ancestor", "--end-of-options", ancestor, descendant).ok

    def rev_parse_commit(self, ref: str) -> str:
        """Validate ``ref`` and return the full SHA-1 it names.

        Doc "Inyeccion de opciones": every ref received from the operator or
        from ``gh`` is validated with ``git rev-parse --verify --end-of-options
        "<ref>^{commit}"`` and only the resulting SHA-1 is propagated forward.
        """

        validate_ref_syntax(ref)
        result = self.run("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        if not result.ok:
            raise AppError(
                f"ref does not resolve to a commit in this repository: {ref}",
                code=EXIT_CANDIDATE,
                diagnostics=[
                    Diagnostic(
                        "ref_unresolvable",
                        result.stderr.strip() or "git rev-parse could not resolve this ref",
                        ref,
                    )
                ],
            )
        sha = result.stdout.strip()
        if not SHA1_RE.match(sha):
            raise AppError(
                f"git returned an unexpected object id for {ref}: {sha}",
                code=EXIT_CANDIDATE,
                diagnostics=[Diagnostic("ref_unexpected_oid", "expected a full 40-character SHA-1", ref)],
            )
        return sha

    def try_rev_parse_commit(self, ref: str) -> str | None:
        """``rev_parse_commit`` that answers ``None`` instead of raising."""

        try:
            return self.rev_parse_commit(ref)
        except AppError:
            return None

    def has_commit(self, sha: str) -> bool:
        validate_ref_syntax(sha)
        return self.run("cat-file", "-e", "--end-of-options", f"{sha}^{{commit}}").ok

    def merge_base(self, first: str, second: str) -> str | None:
        result = self.run("merge-base", "--end-of-options", first, second)
        if not result.ok:
            return None
        sha = result.stdout.strip()
        return sha if SHA1_RE.match(sha) else None

    # -- working tree ---------------------------------------------------

    def status_porcelain(self) -> str:
        result = self.run(
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
            "--ignore-submodules=none",
            "--end-of-options",
        )
        if not result.ok:
            raise AppError(
                "git status failed",
                code=EXIT_PREREQUISITE,
                diagnostics=[Diagnostic("git_status_failed", result.stderr.strip() or "git status failed")],
            )
        return result.stdout

    def is_clean(self) -> bool:
        return self.status_porcelain().strip() == ""

    def head_commit(self) -> str | None:
        result = self.run("rev-parse", "--verify", "--end-of-options", "HEAD")
        if not result.ok:
            return None
        sha = result.stdout.strip()
        return sha if SHA1_RE.match(sha) else None

    def changed_paths(self, from_ref: str, to_ref: str) -> tuple[str, ...]:
        """Every path the diff touches, exactly, with nothing lost in quoting.

        This is the ground truth the engine's reported scope is checked against,
        so it is asked for in the least ambiguous form git offers:

        - ``-z`` so paths are NUL separated and never quoted or escaped;
        - ``core.quotePath=false`` for the same reason, belt and braces;
        - ``--no-renames`` so a rename yields **both** the old and the new path;
          with rename detection a file that moved out of a watched directory
          would only ever be reported under its new name.
        """

        validate_ref_syntax(from_ref)
        validate_ref_syntax(to_ref)
        result = self.run(
            "-c",
            "core.quotePath=false",
            "diff",
            "-z",
            "--no-renames",
            "--name-only",
            "--end-of-options",
            f"{from_ref}..{to_ref}",
        )
        if not result.ok:
            raise AppError(
                f"could not read the changed paths between {from_ref} and {to_ref}",
                code=EXIT_CANDIDATE,
                diagnostics=[
                    Diagnostic("diff_unreadable", result.stderr.strip() or "git diff --name-only failed")
                ],
            )
        return tuple(path for path in result.stdout.split("\0") if path)

    def uncommitted_paths(self, *, staged_only: bool = False) -> tuple[str, ...]:
        """Every path with uncommitted content, tracked or not.

        ``local`` without ``--base`` reviews exactly this set -- staged, unstaged
        and untracked -- so it is also the ground truth the engine's workspace
        scope is cross-checked against. Same NUL-separated, quote-free form as
        ``changed_paths``, and ``--exclude-standard`` so a file the consumer
        already told Git to ignore is not resurrected into the review.
        """

        # `git diff` against the working tree *writes*: it refreshes the stat
        # cache in `.git/index` unless told not to. `local` promises to write
        # nothing inside the repository, so every working-tree read disables it.
        arguments = [
            "-c",
            "core.quotePath=false",
            "-c",
            "diff.autoRefreshIndex=false",
            "diff",
            "-z",
            "--no-renames",
            "--name-only",
        ]
        if staged_only:
            arguments.append("--cached")
        arguments.extend(["--end-of-options", "HEAD"])
        result = self.run(*arguments)
        if not result.ok:
            raise AppError(
                "could not read the working tree's changed paths against HEAD",
                code=EXIT_CANDIDATE,
                diagnostics=[Diagnostic("diff_unreadable", result.stderr.strip() or "git diff --name-only failed")],
            )
        paths = {path for path in result.stdout.split("\0") if path}
        if not staged_only:
            untracked = self.run("-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard", "-z")
            if untracked.ok:
                paths.update(path for path in untracked.stdout.split("\0") if path)
        return tuple(sorted(paths))

    def diff_stat(self) -> str:
        """``git diff --stat HEAD``: the third component of the read-only fingerprint."""

        result = self.run("-c", "diff.autoRefreshIndex=false", "diff", "--stat", "HEAD", "--end-of-options")
        return result.stdout if result.ok else ""

    def current_branch(self) -> str | None:
        """The checked-out branch, or ``None`` when HEAD is detached."""

        result = self.run("symbolic-ref", "--quiet", "--short", "HEAD")
        if not result.ok:
            return None
        return result.stdout.strip() or None

    def local_refs(self) -> dict[str, str]:
        """Every local ref and the object it points at.

        Used to prove the ``.git`` write contract behaviourally: no local ref is
        ever created, moved, or deleted by preparing and restoring an
        environment.
        """

        result = self.run("show-ref")
        if not result.ok:
            return {}
        refs: dict[str, str] = {}
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                refs[parts[1]] = parts[0]
        return refs

    # -- bounded materialization ----------------------------------------

    def fetch(self, remote: str, refspec: str) -> CommandResult:
        """Exactly one bounded fetch of one object or one pull refspec.

        Doc "Reglas de resolucion" rule 4 and "Que significa exactamente solo
        lectura": git may write objects, packs, ``FETCH_HEAD`` (explicitly
        permitted) and the derived reflog, and must create or move no local ref.
        Four things enforce that, and each of them is load-bearing:

        - the refspec is validated to carry **no destination** (``<src>:<dst>``
          creates a local ref, the first entry of the forbidden list, and a
          leading ``+`` makes it a forced update);
        - ``--no-tags`` suppresses the tag refs a default fetch would create;
        - ``--no-auto-maintenance`` suppresses the implicit ``git maintenance
          --auto`` (a ``gc`` by another name, also on the forbidden list);
        - ``GIT_TERMINAL_PROMPT=0`` makes an unauthenticated remote fail instead
          of blocking the process on a credential prompt it inherited stdin for.
        """

        validate_remote_name(remote)
        validate_fetch_refspec(refspec)
        return self.run(
            "fetch",
            "--no-tags",
            "--no-auto-maintenance",
            "--end-of-options",
            remote,
            refspec,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""},
        )

    def worktree_add(self, path: Path, commit: str) -> CommandResult:
        """``git worktree add --detach`` at ``commit``; the only worktree we create."""

        validate_ref_syntax(commit)
        return self.run("worktree", "add", "--detach", "--end-of-options", str(path), commit)

    def worktree_remove(self, path: Path) -> CommandResult:
        """``git worktree remove`` -- never ``--force``, which discards work."""

        return self.run("worktree", "remove", "--end-of-options", str(path))

    def checkout_detached(self, commit: str) -> CommandResult:
        validate_ref_syntax(commit)
        return self.run("checkout", "--detach", "--end-of-options", commit)

    def switch_branch(self, branch: str) -> CommandResult:
        """Restore a recorded **branch**; ``switch`` can only ever mean a branch.

        ``git checkout <name>`` is ambiguous: when the branch no longer exists
        and a tracked file or directory shares its name, git silently falls back
        to a *pathspec* checkout, overwrites that path from the index --
        destroying uncommitted work -- and exits 0 while HEAD stays detached.
        ``git switch`` has no pathspec form, so a missing branch fails cleanly
        and touches no file.
        """

        validate_ref_syntax(branch)
        return self.run("switch", "--end-of-options", branch)

    # -- objects --------------------------------------------------------

    def path_tracked_at(self, ref: str, relative_path: str) -> bool:
        """Whether ``relative_path`` is tracked in the tree of ``ref``."""

        validate_ref_syntax(ref)
        validate_repository_relative_path(relative_path)
        result = self.run("ls-tree", "--name-only", "--end-of-options", ref, "--", relative_path)
        return result.ok and result.stdout.strip() != ""

    def path_exists_at(self, ref: str, relative_path: str) -> bool:
        """Whether ``ref`` contains a blob at ``relative_path``.

        Distinct from reading it: `git show` failing tells you nothing about
        *why* it failed, and treating every failure as "the file is not there"
        turns a transient error into a silent deletion of real findings.
        ``cat-file -e`` answers exactly this question and nothing else.
        """

        validate_ref_syntax(ref)
        validate_repository_relative_path(relative_path)
        result = self.run("cat-file", "-e", f"{ref}:{relative_path}")
        return result.ok

    def show(self, ref: str, relative_path: str) -> str | None:
        """Read a repository file from Git objects, never from the working tree."""

        validate_ref_syntax(ref)
        validate_repository_relative_path(relative_path)
        result = self.run("show", "--end-of-options", f"{ref}:{relative_path}")
        if not result.ok:
            return None
        return result.stdout

    # -- remotes --------------------------------------------------------

    def remotes(self) -> list[Remote]:
        """Every configured remote URL, fetch and push alike.

        A remote whose push URL differs from its fetch URL (``pushurl``, or an
        ``insteadOf`` rewrite) is two identities, and the checkout/pull-request
        correspondence check must see both: keeping only the fetch URL would
        reject a checkout that legitimately pushes to the pull request's
        repository.
        """

        result = self.run("remote", "-v")
        if not result.ok:
            return []
        seen: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            entry = (parts[0], parts[1])
            if entry not in seen:
                seen.append(entry)
        return [Remote(name=name, url=url, repository=normalize_remote_url(url)) for name, url in seen]


def validate_ref_syntax(ref: str) -> None:
    """Reject refs that could smuggle option syntax, NUL bytes, or newlines."""

    if not ref or not ref.strip():
        raise AppError(
            "empty ref",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("ref_empty", "a ref is required")],
        )
    if "\x00" in ref or "\n" in ref or "\r" in ref:
        raise AppError(
            "ref contains a control character",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("ref_control_character", "refs may not contain NUL or newline characters")],
        )


_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_remote_name(name: str) -> None:
    """Reject a remote name that could smuggle option syntax into a fetch."""

    if not _REMOTE_NAME_RE.fullmatch(name or ""):
        raise AppError(
            f"invalid remote name: {name}",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("remote_name_invalid", "expected a plain remote name", name)],
        )


def validate_fetch_refspec(refspec: str) -> None:
    """Reject any refspec that could create or force-update a local ref.

    ``<src>:<dst>`` writes ``<dst>`` into the local ref namespace and a leading
    ``+`` makes the update forced -- both are on the forbidden list, and both are
    reachable from a hostile ``gh`` payload if the value travels unchecked.
    """

    validate_ref_syntax(refspec)
    if ":" in refspec or refspec.startswith("+"):
        raise AppError(
            f"refusing a fetch refspec with a destination: {refspec}",
            code=EXIT_CANDIDATE,
            diagnostics=[
                Diagnostic(
                    "fetch_refspec_destination",
                    "a bounded fetch names one source only; a destination would create or move a local ref",
                    refspec,
                )
            ],
        )


def validate_repository_relative_path(path: str) -> None:
    """Reject anything that is not a plain path inside the repository.

    A path from the engine or from a pull request is candidate-controlled and
    ends up in an argv, so a leading ``-`` is refused as firmly as traversal is:
    a file named ``--rule`` in the candidate would otherwise become a *flag* of
    the very invocation that decides which rules are applied.
    """

    if not path:
        raise AppError(
            "empty repository path",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("path_empty", "a repository-relative path is required")],
        )
    if "\x00" in path or "\n" in path or "\r" in path:
        raise AppError(
            "repository path contains a control character",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("path_nul", "repository paths may not contain NUL or newline characters", path)],
        )
    if path.startswith("-"):
        raise AppError(
            f"repository path looks like a command-line option: {path}",
            code=EXIT_CANDIDATE,
            diagnostics=[
                Diagnostic(
                    "path_option_shaped",
                    "a path starting with - would be read as a flag by the tool it is passed to",
                    path,
                )
            ],
        )
    pure = Path(path)
    if pure.is_absolute() or path.startswith("/") or ".." in pure.parts:
        raise AppError(
            f"repository path escapes the repository: {path}",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("path_escapes_repository", "paths must be relative and free of ..", path)],
        )


_SCP_LIKE_RE = re.compile(r"^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>.+)$")
_URL_RE = re.compile(r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+)$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def normalize_remote_url(url: str) -> str | None:
    """Normalize a GitHub remote URL to ``owner/name``.

    Doc "Reglas de resolucion" rule 8: the checkout/pull-request correspondence
    check normalizes SSH and HTTPS forms, with or without a ``.git`` suffix and
    with embedded credentials stripped, before comparing against the resolved
    repository. Non-GitHub remotes normalize to ``None`` and simply do not
    participate in the comparison.
    """

    value = (url or "").strip()
    if not value:
        return None
    host: str | None = None
    path: str | None = None
    url_match = _URL_RE.match(value)
    if url_match:
        host = url_match.group("host")
        path = url_match.group("path")
    else:
        scp_match = _SCP_LIKE_RE.match(value)
        if scp_match:
            host = scp_match.group("host")
            path = scp_match.group("path")
    if host is None or path is None:
        return None
    if host.lower() != "github.com" and not host.lower().endswith(".github.com"):
        return None
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if not _REPOSITORY_RE.match(path):
        return None
    return path


def open_git(root: Path | None, *, override: str | None = None, forbidden_roots: tuple[Path, ...] = (), timeout: int = 300) -> Git:
    """Resolve the ``git`` executable safely and bind it to ``root``."""

    executable = resolve_executable("git", override=override, forbidden_roots=forbidden_roots)
    if executable is None:
        raise AppError(
            "git is required and was not found on PATH",
            code=EXIT_PREREQUISITE,
            diagnostics=[Diagnostic("git_missing", "install git >= 2.41; this extension never installs anything")],
        )
    return Git(executable, root=root, timeout=timeout)
