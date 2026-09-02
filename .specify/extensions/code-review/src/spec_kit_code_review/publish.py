"""The publication plan: exactly what would be published, and nothing sent.

Doc "Publicación en GitHub" rule 2: ``run --publish`` first renders exactly what
it is about to publish and persists that as ``publication-plan.json`` **even if
the confirmation ends up negative**. This module is that renderer, and in this
stage it is the *whole* of publication: no request is made, no allowlist is
exercised, nothing reaches GitHub. Executing the plan arrives in the next stage,
against this same structure -- which is why the plan is a data object rather
than a side effect.

Three rules shape the plan and all three exist because of GitHub's failure
modes, not because of taste:

- **Only ``RIGHT`` findings inside a hunk are anchored inline.** Everything else
  is degraded into the summary body with its path and lines in text; a whole
  batch rejected because of one out-of-hunk comment is an avoidable failure.
- **The event is a ceiling, not a default.** ``COMMENT`` unless the repository's
  configuration authorizes ``request-changes`` *and* the invocation asks for it
  *and* the verdict is ``changes-requested`` *and* the authenticated user is not
  the author. ``APPROVE`` is not reachable from any combination of inputs.
- **Everything published is redacted**, through the same module that protects
  logs and JSON.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .allowlist import EventConditions, Ledger
from .errors import EXIT_PUBLICATION, EXIT_USAGE, AppError, Diagnostic
from .findings import Finding
from .packet import code_span, contain, visible
from .redaction import redact_text
from .verdict import CHANGES_REQUESTED, Verdict


EVENT_COMMENT = "COMMENT"
EVENT_REQUEST_CHANGES = "REQUEST_CHANGES"
# Never produced, never accepted, and named here only so the test that proves it
# unreachable has something to assert against.
EVENT_APPROVE = "APPROVE"

SUMMARY_MARKER = "speckit-code-review:summary"
DEFAULT_BATCH_SIZE = 25
DEFAULT_MAX_INLINE_COMMENTS = 100
# A degraded finding carries its explanation into the summary. The bound keeps
# one verbose finding from crowding out the rest of the comment; what is cut is
# said so, with the evidence path that holds the whole text.
MAX_DEGRADED_CONTENT_CHARS = 2000


@dataclass(frozen=True)
class InlineComment:
    """One comment that would be posted against a line of the head."""

    finding_id: str
    path: str
    line: int
    start_line: int | None
    side: str
    body: str

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "finding_id": self.finding_id,
            "path": self.path,
            "line": self.line,
            "side": self.side,
            "body": self.body,
        }
        if self.start_line is not None and self.start_line != self.line:
            payload["start_line"] = self.start_line
            payload["start_side"] = self.side
        return payload


@dataclass
class PublicationPlan:
    """What would be published, in the order it would be published."""

    candidate_id: str
    # The two halves of the candidate's identity, so the re-verification the
    # publication stage performs can report *what* moved rather than only that
    # something did.
    head_commit: str
    merge_base: str
    repository: str | None
    pr_number: int | None
    event: str
    verdict: str
    # Recorded as data rather than left to be inferred from the published prose:
    # the publication stage re-decides the event, and it needs the verdict, not
    # a count of how often a word appears in a finding's text.
    summary_marker: str
    summary_body: str
    findings_sha256: str
    verdict_value: str = ""
    verdict_blocking: int = 0
    inline: tuple[InlineComment, ...] = ()
    degraded: tuple[dict[str, Any], ...] = ()
    batches: tuple[tuple[str, ...], ...] = ()
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def summary_sha256(self) -> str:
        return hashlib.sha256(self.summary_body.encode("utf-8")).hexdigest()

    @property
    def plan_sha256(self) -> str:
        payload = {
            "candidate_id": self.candidate_id,
            "head_commit": self.head_commit,
            "merge_base": self.merge_base,
            "repository": self.repository,
            "pr_number": self.pr_number,
            "event": self.event,
            "verdict": self.verdict,
            "verdict_value": self.verdict_value,
            "verdict_blocking": self.verdict_blocking,
            "summary_marker": self.summary_marker,
            "findings_sha256": self.findings_sha256,
            "inline_comments": [
                {
                    "finding_id": comment.finding_id,
                    "path": comment.path,
                    "line": comment.line,
                    "start_line": comment.start_line,
                    "side": comment.side,
                }
                for comment in self.inline
            ],
            "degraded": list(self.degraded),
            "batches": [list(batch) for batch in self.batches],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "head_commit": self.head_commit,
            "merge_base": self.merge_base,
            "repository": self.repository,
            "pr_number": self.pr_number,
            "event": self.event,
            "verdict": self.verdict,
            "verdict_value": self.verdict_value,
            "verdict_blocking": self.verdict_blocking,
            "summary_marker": self.summary_marker,
            "summary_sha256": self.summary_sha256,
            "plan_sha256": self.plan_sha256,
            "findings_sha256": self.findings_sha256,
            "summary_body": self.summary_body,
            "inline_comments": [comment.as_dict() for comment in self.inline],
            "inline_count": len(self.inline),
            "degraded": list(self.degraded),
            "batches": [list(batch) for batch in self.batches],
            "executed": False,
        }


def resolve_event(
    *,
    verdict: Verdict,
    ceiling: str,
    requested: bool,
    authenticated_user: str | None,
    author: str | None,
    diagnostics: list[Diagnostic],
) -> str:
    """The event, decided by the four conditions the allowlist enumerates.

    Every one of them is necessary and none of them is sufficient: the
    configuration can only *permit*, the invocation can only *use* what is
    permitted, the verdict has to warrant it, and GitHub itself refuses
    ``REQUEST_CHANGES`` from the author of the pull request.
    """

    if not requested:
        return EVENT_COMMENT
    if ceiling != "request-changes":
        # A usage error belongs to the caller, which knows about flags; here the
        # plan simply cannot carry an event the repository does not authorize.
        diagnostics.append(
            Diagnostic(
                "publish_event_ceiling",
                f"this repository's publish.event ceiling is {ceiling!r}, so the event stays COMMENT",
                severity="warning",
            )
        )
        return EVENT_COMMENT
    if verdict.value != CHANGES_REQUESTED:
        diagnostics.append(
            Diagnostic(
                "publish_event_verdict",
                f"the verdict is {verdict.value}, so REQUEST_CHANGES would not be warranted; the event stays COMMENT",
                severity="info",
            )
        )
        return EVENT_COMMENT
    if not authenticated_user:
        # The contract's condition is "the authenticated user is **not** the
        # author", and an identity that did not resolve -- unauthenticated, rate
        # limited, network -- does not satisfy it. Failing open here would emit
        # REQUEST_CHANGES precisely when nothing is known about who is emitting
        # it.
        diagnostics.append(
            Diagnostic(
                "publish_identity_unknown",
                "the authenticated GitHub identity could not be determined, so it cannot be established that the "
                "publisher is not the author of the pull request; the event degrades to COMMENT",
                severity="warning",
            )
        )
        return EVENT_COMMENT
    if author and authenticated_user.casefold() == author.casefold():
        # Doc rule 8: GitHub forbids REQUEST_CHANGES on your own pull request.
        # Degrading beats letting the whole publication fail with an API error
        # the operator would have to decode.
        diagnostics.append(
            Diagnostic(
                "publish_event_self_review",
                "the authenticated user is the author of this pull request, and GitHub does not accept "
                "REQUEST_CHANGES from the author; the event degrades to COMMENT",
                severity="warning",
            )
        )
        return EVENT_COMMENT
    return EVENT_REQUEST_CHANGES


def comment_body(finding: Finding, *, suffix: str) -> str:
    """One inline comment, with the finding's own text contained.

    The body reaches GitHub, where it is rendered as Markdown next to the
    candidate's code -- so it gets the same containment as the packet, and the
    same redaction as every other output.
    """

    lines = [
        f"**{finding.severity} / {finding.category}** — {code_span(finding.title)}",
        "",
        contain(
            finding.content,
            suffix=suffix,
            origin=f"finding {finding.identifier}",
            escape_on_collision=True,
        ).text,
    ]
    if finding.suggestion_code:
        lines.extend(
            [
                "",
                contain(
                    finding.suggestion_code,
                    suffix=suffix,
                    origin=f"the suggested code of finding {finding.identifier}",
                    escape_on_collision=True,
                ).text,
            ]
        )
    footer = [f"_{finding.identifier}_"]
    if finding.rule_source:
        footer.append(f"rule_source: `{visible(finding.rule_source)}`")
    if finding.sdd_reference:
        footer.append(f"sdd_reference: {code_span(finding.sdd_reference)}")
    lines.extend(["", " · ".join(footer)])
    return redact_text("\n".join(lines))


def _degraded_body(finding: Finding, *, suffix: str, evidence: str | None) -> str:
    """The explanation of a degraded finding, contained and bounded."""

    text = finding.content
    cut = len(text) > MAX_DEGRADED_CONTENT_CHARS
    if cut:
        text = text[:MAX_DEGRADED_CONTENT_CHARS]
    block = contain(
        text,
        suffix=suffix,
        origin=f"finding {finding.identifier}",
        escape_on_collision=True,
    ).text
    parts = [block]
    if finding.suggestion_code:
        parts.append(
            contain(
                finding.suggestion_code[:MAX_DEGRADED_CONTENT_CHARS],
                suffix=suffix,
                origin=f"the suggested code of finding {finding.identifier}",
                escape_on_collision=True,
            ).text
        )
    if cut:
        parts.append(
            f"_This explanation was cut at {MAX_DEGRADED_CONTENT_CHARS} characters"
            + (f"; the whole text is in the session evidence at `{evidence}`._" if evidence else "._")
        )
    return "\n\n".join(parts)


def summary_body(
    *,
    candidate_id: str,
    verdict: Verdict,
    findings: Sequence[Finding],
    degraded: Sequence[Finding],
    truncated: Sequence[Finding],
    budget: Any | None,
    packet_sha256: str,
    suffix: str,
    evidence_path: str | None = None,
) -> str:
    """The summary comment: the verdict, the degraded findings, and the caveats."""

    marker = f"<!-- {SUMMARY_MARKER}:{candidate_id} -->"
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    lines = [
        marker,
        "",
        "## Spec Kit code review",
        "",
        f"**Verdict: {verdict.value}**",
        "",
        # The plan's own words, every time, because the value's name is not
        # self-explanatory to a reader who has not read this contract.
        "This is a non-binding recommendation produced by an automated reviewer. It is **not an approval**: "
        "approving and merging this pull request are human decisions, always.",
        "",
        f"- candidate_id: `{candidate_id}`",
        f"- packet_sha256: `{packet_sha256}`",
        f"- findings: {len(findings)}"
        + (f" ({', '.join(f'{count} {name}' for name, count in sorted(counts.items()))})" if counts else ""),
    ]
    if budget is not None:
        lines.append(
            f"- budget: {budget.counted} counted line(s) against {budget.limit}"
            + (" — **over budget**" if budget.over_budget else "")
        )
    for cause in verdict.causes:
        lines.append(f"- not covered ({cause.kind}): {visible(cause.detail)}")
    for note in verdict.notes:
        lines.extend(["", note])

    if degraded:
        lines.extend(
            [
                "",
                "### Findings reported here rather than inline",
                "",
                "These could not be anchored to a line of the diff — a deleted line, or a range outside a hunk — "
                "so they are listed with their location instead.",
                "",
            ]
        )
        for finding in degraded:
            lines.append(
                f"- **{finding.identifier}** {code_span(finding.path, table=False)} "
                f"{finding.start_line}-{finding.end_line} ({finding.side}, {finding.severity}/{finding.category}) — "
                f"{code_span(finding.title)}"
            )
            if finding.degraded_reason:
                lines.append(f"  - {finding.degraded_reason}")
            # The whole point of degrading rather than discarding is that the
            # finding survives. A title with no explanation is a finding nobody
            # can act on, which is losing it by another route.
            lines.extend(["", _degraded_body(finding, suffix=suffix, evidence=evidence_path), ""])
    if truncated:
        lines.extend(
            [
                "",
                "### Findings beyond the inline comment limit",
                "",
                f"{len(truncated)} finding(s) exceeded the configured maximum of inline comments and are listed here:",
                "",
            ]
        )
        for finding in truncated:
            lines.append(
                f"- **{finding.identifier}** {code_span(finding.path)} {finding.start_line}-{finding.end_line} "
                f"({finding.severity}/{finding.category}) — {code_span(finding.title)}"
            )
            lines.extend(["", _degraded_body(finding, suffix=suffix, evidence=evidence_path), ""])
    return redact_text("\n".join(lines) + "\n")


def build_plan(
    *,
    candidate,
    verdict: Verdict,
    findings: Sequence[Finding],
    packet_sha256: str,
    suffix: str,
    budget: Any | None = None,
    event_ceiling: str = "request-changes",
    request_changes: bool = False,
    authenticated_user: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_inline_comments: int = DEFAULT_MAX_INLINE_COMMENTS,
    evidence_path: str | None = None,
) -> PublicationPlan:
    """Render the plan. Nothing here contacts GitHub, by construction."""

    diagnostics: list[Diagnostic] = []
    event = resolve_event(
        verdict=verdict,
        ceiling=event_ceiling,
        requested=request_changes,
        authenticated_user=authenticated_user,
        author=getattr(candidate, "author", None),
        diagnostics=diagnostics,
    )

    anchorable = [finding for finding in findings if finding.anchorable]
    degraded = [finding for finding in findings if not finding.anchorable]
    limit = max(int(max_inline_comments), 0)
    inline_findings = anchorable[:limit]
    truncated = anchorable[limit:]
    if truncated:
        diagnostics.append(
            Diagnostic(
                "publish_inline_truncated",
                f"{len(truncated)} anchorable finding(s) exceed publish.max_inline_comments ({limit}) and move to "
                "the summary comment, listed with their exact locations",
                severity="warning",
            )
        )

    inline = tuple(
        InlineComment(
            finding_id=finding.identifier,
            path=finding.path,
            line=finding.end_line,
            start_line=finding.start_line,
            side=finding.side,
            body=comment_body(finding, suffix=suffix),
        )
        for finding in inline_findings
    )
    size = max(int(batch_size), 1)
    batches = tuple(
        tuple(comment.finding_id for comment in inline[index : index + size]) for index in range(0, len(inline), size)
    )
    body = summary_body(
        candidate_id=candidate.candidate_id,
        verdict=verdict,
        findings=findings,
        degraded=degraded,
        truncated=truncated,
        budget=budget,
        packet_sha256=packet_sha256,
        suffix=suffix,
        evidence_path=evidence_path,
    )
    return PublicationPlan(
        candidate_id=candidate.candidate_id,
        head_commit=getattr(candidate, "head_commit", "") or "",
        merge_base=getattr(candidate, "merge_base", "") or "",
        verdict_value=verdict.value,
        verdict_blocking=verdict.blocking,
        repository=getattr(candidate, "repository", None),
        pr_number=getattr(candidate, "pr_number", None),
        event=event,
        verdict=verdict.value,
        summary_marker=f"<!-- {SUMMARY_MARKER}:{candidate.candidate_id} -->",
        summary_body=body,
        findings_sha256=hashlib.sha256(
            json.dumps(
                [finding.identity_sha256 for finding in findings],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        inline=inline,
        degraded=tuple(
            {
                "finding_id": finding.identifier,
                "path": finding.path,
                "start_line": finding.start_line,
                "end_line": finding.end_line,
                "side": finding.side,
                "reason": finding.degraded_reason or "",
            }
            for finding in degraded
        )
        + tuple(
            {
                "finding_id": finding.identifier,
                "path": finding.path,
                "start_line": finding.start_line,
                "end_line": finding.end_line,
                "side": finding.side,
                "reason": "beyond publish.max_inline_comments",
            }
            for finding in truncated
        ),
        batches=batches,
        diagnostics=diagnostics,
    )


# -- execution ---------------------------------------------------------------
#
# Doc "Publicación en GitHub". Everything below performs remote writes, and it is
# the only code in this package that does. Three properties hold over all of it:
# every call goes through `allowlist.authorize`; the candidate is re-verified
# immediately before the first write and a discrepancy means zero writes; and a
# failure part-way through reports exactly what was created and what was not.


@dataclass
class PublicationResult:
    """What was actually created, and what was not."""

    candidate_id: str = ""
    plan_sha256: str = ""
    executed: bool = False
    event: str = EVENT_COMMENT
    review_ids: tuple[int, ...] = ()
    review_urls: tuple[str, ...] = ()
    summary_comment_id: int | None = None
    summary_comment_url: str | None = None
    posted_inline: int = 0
    planned_inline: int = 0
    batches_completed: int = 0
    batches_planned: int = 0
    resumed_from: int = 0
    failure_code: int = 0
    failure: str | None = None
    operations: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        """Whether something was created and something else was not."""

        return bool(self.failure) and (bool(self.review_ids) or self.summary_comment_id is not None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "executed": self.executed,
            "event": self.event,
            "review_ids": list(self.review_ids),
            "review_urls": list(self.review_urls),
            "summary_comment_id": self.summary_comment_id,
            "summary_comment_url": self.summary_comment_url,
            "posted_inline": self.posted_inline,
            "planned_inline": self.planned_inline,
            "batches_completed": self.batches_completed,
            "batches_planned": self.batches_planned,
            "resumed_from": self.resumed_from,
            "candidate_id": self.candidate_id,
            "plan_sha256": self.plan_sha256,
            "partial": self.partial,
            "failure": self.failure,
            "failure_code": self.failure_code,
            "operations": list(self.operations),
        }


def find_summary_comment(
    github: Any,
    *,
    repository: str,
    pr_number: int,
    marker: str,
    max_scanned: int,
    ledger: Ledger,
    diagnostics: list[Diagnostic],
) -> dict[str, Any] | None:
    """This extension's own summary comment for this candidate, if it exists.

    Doc rule 7: the marker carries the ``candidate_id``, which is derived from
    the merge base and the head, so a comment is found only for the *same*
    candidate. The scan is bounded and the bound is reported: assuming absence
    after a bounded scan is a guess, and a guess that leads to a duplicate
    comment should be visible.
    """

    owner, _, name = repository.partition("/")
    # The bound is expressed to the API rather than applied after the fact:
    # fetching every page and then discarding most of them is not a bound, it is
    # the same unbounded read with a filter. `direction=desc` puts the most
    # recent first, which is the half the marker would be in.
    per_page = max(1, min(100, max_scanned or 100))
    pages = max(1, -(-max_scanned // per_page)) if max_scanned else 1
    page = github.api(
        "GET",
        f"repos/{owner}/{name}/issues/{pr_number}/comments?per_page={per_page}&sort=created&direction=desc",
        ledger=ledger,
        paginate=pages > 1,
    )
    comments = page if isinstance(page, list) else []
    if max_scanned and len(comments) >= max_scanned:
        comments = comments[:max_scanned]
        diagnostics.append(
            Diagnostic(
                "publish_scan_bounded",
                f"the {max_scanned} most recent comments were scanned for this extension's marker; an older summary "
                "of this candidate, if one exists, would not be seen",
                severity="warning",
            )
        )
    scanned = comments
    for comment in scanned:
        if isinstance(comment, dict) and marker in str(comment.get("body") or ""):
            return comment
    return None


# The marker is what a resumed publication looks for, so it travels on the
# review body as well as on the summary comment: a review created before a
# failure has to be findable afterwards.
REVIEW_MARKER = "speckit-code-review:review"


def review_marker(candidate_id: str, index: int) -> str:
    return f"<!-- {REVIEW_MARKER}:{candidate_id}:{index} -->"


def review_body(plan: PublicationPlan, index: int, total: int) -> str:
    """The body of one review request.

    **Never empty.** GitHub requires a body on a review carrying an event, so an
    empty one is a 422 on the very first POST -- the happy path, every time.
    The body is a short header rather than the whole summary: the summary is a
    comment of its own, and repeating it inside the review would publish the same
    text twice.
    """

    lines = [review_marker(plan.candidate_id, index)]
    if index == 0:
        lines.extend(
            [
                "",
                f"**Spec Kit code review — verdict: {plan.verdict}**",
                "",
                "A non-binding recommendation from an automated reviewer. It is **not an approval**: "
                "approving and merging this pull request are human decisions, always.",
                "",
                f"`candidate_id: {plan.candidate_id}`",
            ]
        )
        if total > 1:
            lines.extend(["", f"The inline comments arrive in {total} parts; this is part 1."])
        lines.extend(["", "The full summary is in a separate comment on this pull request."])
    else:
        lines.extend(
            [
                "",
                f"**Spec Kit code review — inline comments, part {index + 1} of {total}**",
                "",
                f"Continuation of the review of `{plan.candidate_id}`. The verdict and the summary are in part 1.",
            ]
        )
    return "\n".join(lines)


def completed_batches(
    github: Any,
    plan: PublicationPlan,
    *,
    previous: Mapping[str, Any] | None,
    ledger: Ledger,
    diagnostics: list[Diagnostic],
) -> int:
    """How many review batches of this candidate are already on GitHub.

    A retry after a partial failure must not post the same inline comments
    twice, and deleting a duplicate is an operation this extension does not
    perform -- so the count is established before anything is sent, from two
    sources that have to agree: what the previous run recorded locally, and what
    ``GET /pulls/{n}/reviews`` reports remotely. The remote reading is the
    authority; the local one is what makes the question worth asking.
    """

    resumable = bool(
        previous
        and str(previous.get("candidate_id") or "") == plan.candidate_id
        # Only a run that *failed* leaves work to resume; a completed one leaves
        # nothing.
        and previous.get("failure")
    )
    recorded = 0
    if resumable:
        recorded = int(previous.get("batches_completed") or 0)
    if not recorded:
        return 0
    if str(previous.get("plan_sha256") or "") != plan.plan_sha256:
        raise AppError(
            "the partial publication belongs to a different review plan",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "publish_resume_plan_mismatch",
                    "published review batches already exist for this candidate, but the current findings produce "
                    "a different publication plan. The existing batches cannot be reused or overwritten; publish "
                    "a new candidate instead.",
                )
            ],
        )

    owner, _, name = (plan.repository or "").partition("/")
    reviews = github.api(
        "GET",
        f"repos/{owner}/{name}/pulls/{plan.pr_number}/reviews?per_page=100",
        ledger=ledger,
        paginate=True,
    )
    found = 0
    for index in range(len(plan.batches)):
        marker = review_marker(plan.candidate_id, index)
        if any(marker in str(item.get("body") or "") for item in reviews if isinstance(item, dict)):
            found += 1
        else:
            break
    if found:
        diagnostics.append(
            Diagnostic(
                "publish_resuming",
                f"{found} review batch(es) of this candidate are already on the pull request and are not sent again; "
                f"publication resumes at part {found + 1}",
                severity="warning",
            )
        )
    if recorded and not found:
        diagnostics.append(
            Diagnostic(
                "publish_previous_not_found",
                f"a previous run recorded {recorded} published batch(es), and none of them carries this candidate's "
                "marker on the pull request; publication starts from the beginning",
                severity="warning",
            )
        )
    return found


def listed_files(
    github: Any,
    plan: PublicationPlan,
    *,
    max_listed: int,
    ledger: Ledger,
    diagnostics: list[Diagnostic],
) -> tuple[str, ...]:
    """The pull request's own file list, as **metadata** and nothing else.

    Doc "Allowlist de operaciones remotas": ``GET /pulls/{n}/files`` is never a
    source of anchor positions -- those come from the local diff, and two sources
    that can disagree would produce an anchor that validates against one and is
    rejected by the other. What it is good for is the one thing the local diff
    cannot know: whether GitHub itself truncated the pull request's file list at
    its own 3000-file ceiling, in which case a comment on a file beyond the cut
    will be rejected however correct the anchor is.
    """

    owner, _, name = (plan.repository or "").partition("/")
    per_page = 100
    pages = max(1, -(-max_listed // per_page))
    payload = github.api(
        "GET",
        f"repos/{owner}/{name}/pulls/{plan.pr_number}/files?per_page={per_page}",
        ledger=ledger,
        paginate=pages > 1,
    )
    files = tuple(
        str(item.get("filename") or "") for item in (payload or ()) if isinstance(item, dict) and item.get("filename")
    )
    if len(files) >= max_listed:
        diagnostics.append(
            Diagnostic(
                "publish_files_truncated",
                f"GitHub listed {len(files)} file(s), at or above the configured publish.max_listed_files "
                f"({max_listed}); a pull request this large can have files the API does not list, and an inline "
                "comment on one of them is rejected by GitHub whatever this review computed",
                severity="warning",
            )
        )
    return files


def _batch_payload(plan: PublicationPlan, comments: Sequence[InlineComment]) -> dict[str, Any]:
    return {
        # Doc "Anclaje": the review is anchored to the head the review actually
        # read. Without it GitHub anchors to whatever the pull request's head is
        # at the moment of the POST, so a head that moved in the seconds after
        # the re-verification would put these comments on code this review never
        # saw. With it, that race becomes a 422 from the server -- fail closed,
        # at no cost.
        "commit_id": plan.head_commit,
        "comments": [
            {key: value for key, value in comment.as_dict().items() if key != "finding_id"} for comment in comments
        ],
    }


def execute(
    plan: PublicationPlan,
    github: Any,
    *,
    ledger: Ledger,
    conditions: EventConditions | None = None,
    max_scanned_comments: int = 300,
    max_listed_files: int = 3000,
    previous_result: Mapping[str, Any] | None = None,
) -> PublicationResult:
    """Execute a plan that has already been verified against its candidate.

    Re-verification, confirmation and the drift check happen *before* this is
    called: by the time execution begins the only remaining question is whether
    GitHub accepts the writes. What this guarantees is the honest report of a
    partial failure -- the review batches are created in order, and whatever was
    created stays recorded even when a later one fails.
    """

    result = PublicationResult(
        candidate_id=plan.candidate_id,
        plan_sha256=plan.plan_sha256,
        event=plan.event,
        planned_inline=len(plan.inline),
        batches_planned=max(len(plan.batches), 0),
    )
    if not plan.repository or not plan.pr_number:
        raise AppError(
            "this session has no pull request to publish to",
            code=EXIT_PUBLICATION,
            diagnostics=[
                Diagnostic(
                    "publish_no_pull_request",
                    "a review resolved with --base/--head has no pull request; publish a candidate resolved from a "
                    "pull-request selector",
                )
            ],
        )
    owner, _, name = plan.repository.partition("/")

    existing = find_summary_comment(
        github,
        repository=plan.repository,
        pr_number=plan.pr_number,
        marker=plan.summary_marker,
        max_scanned=max_scanned_comments,
        ledger=ledger,
        diagnostics=result.diagnostics,
    )
    if existing is not None:
        # Doc rule 7: a second publication over the same candidate is refused
        # rather than duplicated. It is not an update either -- each review
        # belongs to an immutable candidate, and overwriting one would destroy
        # the record of what was reviewed and when.
        raise AppError(
            "this candidate already has a published review",
            code=EXIT_USAGE,
            diagnostics=[
                Diagnostic(
                    "publish_already_published",
                    f"the summary comment {existing.get('html_url') or existing.get('id')} already carries this "
                    "candidate's marker. The existing review is never edited or deleted; review the new candidate "
                    "instead.",
                )
            ],
        )

    # Metadata, before the first write: a comment on a file GitHub did not list
    # is rejected however correct its anchor is, and knowing that in advance is
    # the difference between a diagnostic and a 422 mid-batch.
    if plan.inline:
        remote_files = listed_files(
            github,
            plan,
            max_listed=max_listed_files,
            ledger=ledger,
            diagnostics=result.diagnostics,
        )
        unlisted = sorted({comment.path for comment in plan.inline} - set(remote_files)) if remote_files else []
        if unlisted:
            result.diagnostics.append(
                Diagnostic(
                    "publish_path_not_listed",
                    f"{len(unlisted)} path(s) with inline comments are not in the pull request's file list: "
                    f"{', '.join(unlisted[:5])}. GitHub rejects comments on files it does not consider part of the "
                    "pull request.",
                    severity="warning",
                )
            )

    batches = plan.batches or ((),)
    comments_by_id = {comment.finding_id: comment for comment in plan.inline}
    already = completed_batches(
        github, plan, previous=previous_result, ledger=ledger, diagnostics=result.diagnostics
    )
    result.batches_completed = already
    result.resumed_from = already
    try:
        for index, batch in enumerate(batches):
            if index < already:
                continue
            comments = [comments_by_id[identifier] for identifier in batch if identifier in comments_by_id]
            if not comments and index > 0:
                continue
            payload = _batch_payload(plan, comments)
            # The event travels on the first review only: it is the verdict of
            # the review as a whole, and repeating it would emit several
            # verdicts for one candidate.
            event = plan.event if index == 0 else EVENT_COMMENT
            payload["body"] = review_body(plan, index, len(batches))
            created = github.api(
                "POST",
                f"repos/{owner}/{name}/pulls/{plan.pr_number}/reviews",
                fields=payload,
                event=event,
                conditions=conditions,
                ledger=ledger,
            )
            if isinstance(created, dict):
                if created.get("id") is not None:
                    result.review_ids = (*result.review_ids, int(created["id"]))
                if created.get("html_url"):
                    result.review_urls = (*result.review_urls, str(created["html_url"]))
            result.posted_inline += len(comments)
            result.batches_completed += 1

        summary = github.api(
            "POST",
            f"repos/{owner}/{name}/issues/{plan.pr_number}/comments",
            fields={"body": plan.summary_body},
            ledger=ledger,
        )
        if isinstance(summary, dict):
            result.summary_comment_id = summary.get("id")
            result.summary_comment_url = summary.get("html_url")
        result.executed = True
    except AppError as error:
        # Doc rule 10 and the partial-failure semantics: what was created stays
        # created, and the operator is told exactly which parts of the plan
        # landed. Nothing is rolled back, because deleting a comment is itself a
        # forbidden operation.
        result.failure = str(error)
        result.failure_code = error.code
        result.operations = ledger.as_list()
        result.diagnostics.extend(error.diagnostics)
        if result.batches_completed == 0:
            # Nothing landed: the review carrying the event was never created,
            # so the pull request has no partial verdict on it and a plain
            # re-run publishes from the beginning.
            detail = (
                "nothing was created: the first review request failed, so the pull request carries no part of this "
                "review. Fix the cause and run the same command again."
            )
        elif result.review_ids and result.batches_completed < result.batches_planned:
            # The review carrying the *event* did land: the pull request already
            # shows this review's verdict while some of its comments are
            # missing. That is the state a retry must resume, not repeat.
            detail = (
                f"{result.batches_completed} of {result.batches_planned} review batch(es) were created "
                f"({result.posted_inline} of {result.planned_inline} inline comment(s)). The pull request already "
                "carries the verdict from part 1. Run the same command again: the batches that landed are detected "
                "by their marker and are not sent twice."
            )
        else:
            detail = (
                f"every review batch was created ({result.posted_inline} inline comment(s)) and the summary comment "
                "was not. Run the same command again; the reviews that landed are not sent twice."
            )
        result.diagnostics.append(
            Diagnostic("publish_partial", detail, severity="warning" if result.partial else "error")
        )
        raise PublicationFailed(result) from error
    result.operations = ledger.as_list()
    return result


class PublicationFailed(Exception):
    """A publication that failed after writing something, or before writing anything.

    Carries the result so the caller can persist and report it: the difference
    between "nothing happened" and "half of it happened" is the whole point of
    exit code 10, and it cannot be reconstructed from an error message.
    """

    def __init__(self, result: PublicationResult) -> None:
        super().__init__(result.failure or "publication failed")
        self.result = result
        # An expired token and a rejected write need different remedies, so the
        # more specific code survives the flattening into "publication failed".
        self.code = result.failure_code or EXIT_PUBLICATION
