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
