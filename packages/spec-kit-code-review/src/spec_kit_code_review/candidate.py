"""Resolution of the immutable review candidate (``merge_base``, ``head_commit``)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .errors import EXIT_CANDIDATE, EXIT_USAGE, AppError, Diagnostic
from .git import Git
from .github import PR_URL_RE, GitHub, PullRequest, validate_number, validate_repository
from .redaction import redact_text


@dataclass(frozen=True)
class Selector:
    """A pull-request selector: a number, or a URL that also names a repository."""

    number: int
    repository: str | None = None
    raw: str = ""


@dataclass(frozen=True)
class Candidate:
    """The resolved candidate; its identity is ``(merge_base, head_commit)`` only."""

    head_commit: str
    merge_base: str
    candidate_id: str
    resolved_at: str
    repository: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    base_branch: str | None = None
    base_commit: str | None = None
    base_observed_at: str | None = None
    cross_repository: bool = False
    state: str | None = None
    selector_kind: str = "refs"
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        """The candidate block shared by the packet, ``session.json``, and ``--json``."""

        return {
            "repository": self.repository,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "base_branch": self.base_branch,
            "base_commit": self.base_commit,
            "base_observed_at": self.base_observed_at,
            "head_commit": self.head_commit,
            "merge_base": self.merge_base,
            "cross_repository": self.cross_repository,
            "candidate_id": self.candidate_id,
            "state": self.state,
            "selector_kind": self.selector_kind,
            "resolved_at": self.resolved_at,
        }


def compute_candidate_id(merge_base: str, head_commit: str) -> str:
    """``sha256("<merge_base>\\n<head_commit>\\n")`` -- the canonical candidate identity."""

    return hashlib.sha256(f"{merge_base}\n{head_commit}\n".encode("utf-8")).hexdigest()


def parse_selector(value: str) -> Selector:
    """Parse a pull-request number or URL into a selector."""

    raw = (value or "").strip()
    if not raw:
        raise AppError(
            "empty pull-request selector",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("selector_empty", "pass a pull-request number, a URL, or --base/--head")],
        )
    match = PR_URL_RE.match(raw)
    if match:
        return Selector(
            number=int(match.group("number")),
            repository=f"{match.group('owner')}/{match.group('name')}",
            raw=raw,
        )
    if raw.startswith("#"):
        raw = raw[1:]
    if raw.isdigit():
        return Selector(number=validate_number(raw), raw=value)
    raise AppError(
        f"unrecognized pull-request selector: {value}",
        code=EXIT_USAGE,
        diagnostics=[Diagnostic("selector_invalid", "expected a pull-request number or a github.com pull URL", value)],
    )


def resolve_repository(
    git: Git,
    *,
    explicit: str | None = None,
    selector: Selector | None = None,
    remote: str = "origin",
) -> str:
    """Resolve ``owner/name`` from the flag, the selector URL, or the configured remotes.

    Doc "Reglas de resolucion" rule 7: a selector that resolves to more than
    one repository (several candidate remotes and no ``--repository``) aborts
    with exit code 6 listing the options. A repository is never chosen
    arbitrarily.
    """

    if explicit:
        return validate_repository(explicit)
    if selector is not None and selector.repository:
        return validate_repository(selector.repository)
    remotes = [item for item in git.remotes() if item.repository]
    if not remotes:
        raise AppError(
            "no GitHub remote is configured in this checkout",
            code=EXIT_CANDIDATE,
            diagnostics=[Diagnostic("remote_missing", "pass --repository OWNER/NAME, or configure a GitHub remote")],
        )
    preferred = [item for item in remotes if item.name == remote]
    if preferred:
        return validate_repository(preferred[0].repository or "")
    distinct = sorted({item.repository or "" for item in remotes})
    if len(distinct) == 1:
        return validate_repository(distinct[0])
    observed = ", ".join(f"{item.name} -> {item.repository}" for item in sorted(remotes, key=lambda entry: entry.name))
    raise AppError(
        "the repository of this pull request is ambiguous",
        code=EXIT_CANDIDATE,
        diagnostics=[
            Diagnostic(
                "repository_ambiguous",
                f"pass --repository OWNER/NAME or --remote NAME; observed remotes: {observed}",
            )
        ],
    )


def verify_checkout_matches_pull_request(git: Git, pull_request: PullRequest) -> tuple[Diagnostic, str | None]:
    """Verify the local checkout really is the repository of the pull request.

    Doc "Reglas de resolucion" rule 8. Satisfied when a configured remote
    normalizes to the pull request's ``owner/name``, or when the local
    ``refs/pull/<n>/head`` of that repository already resolves to the head
    commit. Otherwise exit code 6, naming the expected identity and the remotes
    actually observed -- without it, ``run 128`` on the wrong checkout would
    review same-numbered commits of another project.

    Returns the diagnostic **and the remote that satisfied the check**, because
    that -- not whatever ``--remote`` happens to say -- is the only remote whose
    objects belong to this pull request. ``None`` means the local pull ref
    satisfied it and nothing needs fetching from anywhere.
    """

    remotes = git.remotes()
    expected = pull_request.repository.lower()
    for item in remotes:
        if item.repository and item.repository.lower() == expected:
            return (
                Diagnostic(
                    "checkout_matches_pull_request",
                    f"remote {item.name} resolves to {item.repository}",
                    severity="info",
                ),
                item.name,
            )
    pull_ref = f"refs/pull/{pull_request.number}/head"
    local_pull_head = git.try_rev_parse_commit(pull_ref)
    # "reachable from refs/pull/<n>/head", not "equal to it": the ref can already
    # carry a newer head than the one this pull request currently reports, and an
    # equality test would reject a checkout that plainly holds the candidate.
    if local_pull_head and git.is_ancestor(pull_request.head_commit, local_pull_head):
        return (
            Diagnostic(
                "checkout_matches_pull_request",
                f"the head commit is reachable from {pull_ref} in this checkout",
                severity="info",
            ),
            None,
        )
    observed = ", ".join(f"{item.name} -> {item.url}" for item in sorted(remotes, key=lambda entry: entry.name))
    raise AppError(
        f"this checkout does not correspond to {pull_request.repository}",
        code=EXIT_CANDIDATE,
        diagnostics=[
            Diagnostic(
                "checkout_repository_mismatch",
                f"expected a remote resolving to {pull_request.repository}; observed: {observed or 'no remotes'}",
            )
        ],
    )


def resolve_from_refs(git: Git, *, base: str | None, head: str | None, now: datetime | None = None) -> Candidate:
    """The offline path: explicit ``--base``/``--head``, never contacting GitHub."""

    if not base or not head:
        raise AppError(
            "--base and --head must be used together",
            code=EXIT_USAGE,
            diagnostics=[Diagnostic("base_head_pair", "pass both --base and --head, or a pull-request selector")],
        )
    base_commit = git.rev_parse_commit(base)
    head_commit = git.rev_parse_commit(head)
    merge_base = _require_merge_base(git, base_commit, head_commit)
    resolved_at = _timestamp(now)
    return Candidate(
        head_commit=head_commit,
        merge_base=merge_base,
        candidate_id=compute_candidate_id(merge_base, head_commit),
        resolved_at=resolved_at,
        base_commit=base_commit,
        base_observed_at=resolved_at,
        selector_kind="refs",
    )


def resolve_from_pull_request(
    git: Git,
    github: GitHub,
    selector: Selector,
    *,
    repository: str | None = None,
    remote: str = "origin",
    now: datetime | None = None,
    fetch_missing: bool = False,
) -> tuple[Candidate, PullRequest]:
    """Resolve the immutable candidate from a pull-request selector.

    The real base branch always wins: ``baseRefOid``/``headRefOid`` are the
    source of the commits and the operator's current ``HEAD`` is never read to
    decide the base. ``base_commit`` is recorded as a dated observation, never
    as part of the candidate identity.
    """

    target_repository = resolve_repository(git, explicit=repository, selector=selector, remote=remote)
    pull_request = github.pull_request(selector.number, repository=target_repository)
    correspondence, matched_remote = verify_checkout_matches_pull_request(git, pull_request)

    # Doc "Reglas de resolucion" rule 8 exists to stop objects being taken from a
    # repository that is not the pull request's, so the fetch goes to the remote
    # that *satisfied* the correspondence -- never to whatever --remote names.
    head_commit = _require_local_commit(
        git,
        pull_request.head_commit,
        label="head",
        pull_request=pull_request,
        remote=matched_remote,
        fetch_missing=fetch_missing,
    )
    base_commit = _require_local_commit(
        git,
        pull_request.base_commit,
        label="base",
        pull_request=pull_request,
        remote=matched_remote,
        fetch_missing=fetch_missing,
    )
    merge_base = _require_merge_base(git, base_commit, head_commit)
    resolved_at = _timestamp(now)
    candidate = Candidate(
        head_commit=head_commit,
        merge_base=merge_base,
        candidate_id=compute_candidate_id(merge_base, head_commit),
        resolved_at=resolved_at,
        repository=pull_request.repository,
        pr_number=pull_request.number,
        pr_url=pull_request.url or None,
        base_branch=pull_request.base_branch,
        base_commit=base_commit,
        base_observed_at=resolved_at,
        cross_repository=pull_request.cross_repository,
        state=pull_request.state,
        selector_kind="pull-request",
        diagnostics=(correspondence,),
    )
    return candidate, pull_request


def _require_local_commit(
    git: Git,
    sha: str,
    *,
    label: str,
    pull_request: PullRequest,
    remote: str | None,
    fetch_missing: bool = False,
) -> str:
    """Resolve a commit, fetching it once if the caller is allowed to write.

    Doc "Reglas de resolucion" rule 4: when the object is absent, exactly **one**
    bounded fetch of the remote is attempted -- and only when the caller
    materializes an environment (``fetch_missing``). Read-only commands never
    reach for the network or write inside ``.git``; they report exit code 6 with
    the exact command instead.

    The refspec differs by label, and using the wrong one wastes the operator's
    time: the pull refspec fetches the *head* and says nothing about the base
    branch tip, so an absent base commit is fetched by its SHA.
    """

    if git.has_commit(sha):
        return git.rev_parse_commit(sha)
    refspec = f"refs/pull/{pull_request.number}/head" if label == "head" else sha
    if remote is None:
        raise AppError(
            f"{label} commit {sha} is not present in this checkout",
            code=EXIT_CANDIDATE,
            diagnostics=[
                Diagnostic(
                    "commit_absent",
                    "no configured remote corresponds to this pull request, so there is nowhere safe to fetch it from; "
                    f"fetch it yourself from the right remote and re-run: git fetch <remote> {refspec}",
                    sha,
                )
            ],
        )
    fetch_command = f"git fetch {remote} {refspec}"
    failure = ""
    if fetch_missing:
        result = git.fetch(remote, refspec)
        if git.has_commit(sha):
            return git.rev_parse_commit(sha)
        if not result.ok:
            # A fetch that fails on authentication, on the network, or on a
            # timeout is still "the candidate could not be resolved" (exit 6),
            # not an engine failure -- and its stderr is relayed redacted.
            failure = redact_text(result.stderr.strip())
    detail = (
        f"one bounded fetch was attempted and the object is still absent; run it yourself and re-run: {fetch_command}"
        if fetch_missing
        else f"fetch it yourself and re-run: {fetch_command}"
    )
    if failure:
        detail = f"{detail} (git said: {failure})"
    raise AppError(
        f"{label} commit {sha} is not present in this checkout",
        code=EXIT_CANDIDATE,
        diagnostics=[Diagnostic("commit_absent", detail, sha)],
    )


def _require_merge_base(git: Git, base_commit: str, head_commit: str) -> str:
    merge_base = git.merge_base(base_commit, head_commit)
    if merge_base is None:
        raise AppError(
            "merge base could not be computed for this candidate",
            code=EXIT_CANDIDATE,
            diagnostics=[
                Diagnostic(
                    "merge_base_missing",
                    "the base and head commits have unrelated histories; the comparison range would be a lie about the candidate scope",
                )
            ],
        )
    return merge_base


def _timestamp(now: datetime | None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
