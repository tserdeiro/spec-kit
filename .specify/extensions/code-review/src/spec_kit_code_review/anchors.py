"""Diff hunks, computed locally, and the anchoring decision they support.

Doc "Publicación en GitHub" rule 5 and the allowlist: **the single source of
hunks is ``git diff --unified=0 <merge_base>..<head_commit>``, computed
locally.** ``GET /pulls/{n}/files`` is metadata only and never a source of
anchor positions -- two sources that can disagree would produce an anchor that
validates against one and is rejected by the other, and the local computation
also works on the ``--base/--head`` path with no network at all.

``--unified=0`` matters: with context lines the hunk ranges would span lines the
candidate never touched, and a comment anchored there is either rejected by
GitHub or attached to something the pull request did not change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .errors import EXIT_CANDIDATE, EXIT_ENGINE, AppError, Diagnostic
from .git import Git, validate_ref_syntax


# ``@@ -old,count +new,count @@`` -- the counts are optional and default to 1,
# which is exactly the shape `--unified=0` produces for a single-line change.
_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)
# `--no-renames` keeps a rename as a delete plus an add, so a finding about
# either name still anchors; with rename detection the old name would vanish
# from the hunk map while findings about it stayed legitimate.
_DIFF_ARGUMENTS = ("-c", "core.quotePath=false", "diff", "--unified=0", "--no-renames", "--no-color")


@dataclass(frozen=True)
class Hunk:
    """One contiguous range of the head file that this candidate touched."""

    path: str
    start: int
    end: int
    side: str = "RIGHT"

    def contains(self, start_line: int, end_line: int) -> bool:
        return self.start <= start_line and end_line <= self.end

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "start": self.start, "end": self.end, "side": self.side}


@dataclass(frozen=True)
class HunkMap:
    """Every anchorable range of the candidate, keyed by path."""

    hunks: tuple[Hunk, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    def for_path(self, path: str) -> tuple[Hunk, ...]:
        return tuple(hunk for hunk in self.hunks if hunk.path == path)

    def paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(hunk.path for hunk in self.hunks))

    def anchor(self, path: str, start_line: int, end_line: int) -> Hunk | None:
        """The hunk that fully contains this range, if any.

        Fully, not partially: a range that starts inside a hunk and ends outside
        it is not anchorable. GitHub rejects a comment whose end line is outside
        the diff, and a partially-true anchor points the reader at the wrong
        lines -- both worse than degrading the finding to the summary.
        """

        for hunk in self.for_path(path):
            if hunk.contains(start_line, end_line):
                return hunk
        return None

    def as_dict(self) -> dict[str, Any]:
        return {"hunks": [hunk.as_dict() for hunk in self.hunks]}


def parse_unified_zero(diff_text: str) -> tuple[Hunk, ...]:
    """Read ``git diff --unified=0`` into the RIGHT-side ranges it describes.

    Only the new-file side is kept: this map exists to answer "can a comment be
    anchored inline here?", and inline anchoring is `RIGHT`-only by contract. A
    hunk whose new count is zero is a pure deletion: it has no line on the head
    side to anchor to, so it contributes nothing here and every finding about it
    degrades to the summary, which is precisely the documented behaviour.
    """

    hunks: list[Hunk] = []
    path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            # `/dev/null` is a deletion; `b/` is git's prefix for the new side.
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            continue
        if line.startswith("--- ") or not line.startswith("@@"):
            continue
        match = _HUNK_RE.match(line)
        if match is None or path is None:
            continue
        start = int(match.group("new_start"))
        count = int(match.group("new_count") or 1)
        if count <= 0:
            continue
        hunks.append(Hunk(path=path, start=start, end=start + count - 1))
    return tuple(hunks)


def load_hunks(git: Git, *, merge_base: str, head_commit: str) -> HunkMap:
    """Compute the candidate's hunks from Git, and from nowhere else."""

    validate_ref_syntax(merge_base)
    validate_ref_syntax(head_commit)
    result = git.run(*_DIFF_ARGUMENTS, "--end-of-options", f"{merge_base}..{head_commit}")
    if not result.ok:
        raise AppError(
            f"could not compute the candidate's diff hunks between {merge_base} and {head_commit}",
            code=EXIT_CANDIDATE,
            diagnostics=[
                Diagnostic(
                    "hunks_unreadable",
                    result.stderr.strip() or "git diff --unified=0 failed",
                )
            ],
        )
    hunks = parse_unified_zero(result.stdout)
    diagnostics: list[Diagnostic] = []
    if not hunks:
        diagnostics.append(
            Diagnostic(
                "hunks_empty",
                "the candidate's diff has no line on the head side, so no finding can be anchored inline; "
                "every finding will be reported in the summary",
                severity="info",
            )
        )
    return HunkMap(hunks=hunks, diagnostics=tuple(diagnostics))


def file_line_counts(git: Git, ref: str, paths: Iterable[str]) -> dict[str, int | None]:
    """How many lines each path has at ``ref``, or ``None`` when it is absent.

    Doc "Modelo de finding": a finding whose path does not exist, or whose range
    falls outside the file, is a hallucination and is discarded with a
    diagnostic. Answering that needs the file's length, read from Git objects --
    never from the working tree, which may sit on another branch.

    **Absent and unreadable are not the same answer.** Existence is asked with
    ``cat-file -e``, and only a path that genuinely is not in the tree yields
    ``None``. A path that exists but cannot be read is a failure of this process,
    not a statement about the candidate, and it raises rather than quietly
    turning real findings into discarded ones.
    """

    counts: dict[str, int | None] = {}
    for path in dict.fromkeys(paths):
        if not git.path_exists_at(ref, path):
            counts[path] = None
            continue
        text = git.show(ref, path)
        if text is None:
            raise AppError(
                f"the candidate's {path} exists at {ref} but could not be read",
                code=EXIT_ENGINE,
                diagnostics=[
                    Diagnostic(
                        "finding_path_unreadable",
                        "a finding cites this path and git reports the blob exists, so this is a failure of this "
                        "invocation rather than a statement about the candidate. Nothing is discarded on a guess.",
                        path,
                    )
                ],
            )
        counts[path] = len(text.splitlines())
    return counts


def summarize(hunks: Sequence[Hunk]) -> dict[str, int]:
    """Per-path hunk counts, for the evidence and the human render."""

    summary: dict[str, int] = {}
    for hunk in hunks:
        summary[hunk.path] = summary.get(hunk.path, 0) + 1
    return summary
