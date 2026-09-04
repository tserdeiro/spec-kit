"""Branch names Git already knows about, read locally and never over the network.

Stage 3 derives "this task is in progress" from the existence of a branch
named after the task. That question is answered from the refs already in the
repository -- `refs/heads/*` and the remote-tracking `refs/remotes/origin/*`
-- so a push or a status never fetches, never authenticates, and never waits
on a remote. A repository whose remote-tracking refs are stale simply
contributes fewer branches to the derivation, which is a weaker signal, never
a wrong one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


_ORIGIN_PREFIX = "origin/"
_GIT_TIMEOUT_SECONDS = 20


def known_branches(root: Path) -> tuple[str, ...]:
    """Return every local and already-known `origin` branch name, deduplicated.

    Remote-tracking names are reported without their ``origin/`` prefix so a
    local and a remote branch for the same task are one name to the caller.
    Anything that prevents the read -- no repository, no `git` -- yields an
    empty tuple: branch detection is one signal among several, so its absence
    degrades the derivation instead of failing the command.
    """

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"],
            check=False,
            text=True,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    names: list[str] = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if name.startswith(_ORIGIN_PREFIX):
            name = name[len(_ORIGIN_PREFIX) :]
        if not name or name == "HEAD":
            continue
        names.append(name)
    return tuple(dict.fromkeys(names))


def main_worktree_root(root: Path) -> Path | None:
    """Return the main checkout's root when ``root`` is a linked worktree.

    ``git -C <root> rev-parse --git-common-dir`` names the one Git directory
    every worktree of a repository shares; its parent is the main checkout on
    every platform -- an absolute path when ``root`` is a worktree, the
    relative ``.git`` when ``root`` already is the main checkout (probed
    2026-09-03). Anything that prevents the read -- no repository, no `git`
    -- or a candidate that resolves back to ``root`` itself (the main
    checkout, or a bare-repository layout with no main checkout) yields
    ``None``: the caller then falls back to ``root``'s own files, exactly as
    it does today.
    """

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
            check=False,
            text=True,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    common_dir = result.stdout.strip()
    if not common_dir:
        return None
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = root / common_path
    main_root = common_path.resolve().parent
    if main_root == root.resolve():
        return None
    return main_root
