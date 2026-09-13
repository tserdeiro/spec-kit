#!/usr/bin/env python3
"""Pure evaluation of the active GitHub rules observed for delivery branches."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

COMPATIBLE = "compatible"
INCOMPATIBLE = "incompatible"
CAPABILITY_UNAVAILABLE = "capability-unavailable"
UNVERIFIED = "unverified"

_FEATURE_RE = re.compile(r"^[0-9]{3}-(?!T[0-9]{3}(?:-|$))[A-Za-z0-9][A-Za-z0-9._-]*$")
_TASK_RE = re.compile(r"^[0-9]{3}-T[0-9]{3}-[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Result:
    state: str
    cause: str
    evidence: str
    next_action: str


@dataclass(frozen=True)
class ActiveRule:
    type: str
    source_type: str
    source: str
    ruleset_id: int
    parameters: dict[str, Any] | None = None

    @property
    def identity(self) -> tuple[str, str, int]:
        return self.source_type, self.source, self.ruleset_id

    def label(self) -> str:
        return f"{self.source_type} {self.source} ruleset {self.ruleset_id}"


@dataclass(frozen=True)
class RuleRead:
    """One branch's effective-rules read, including whether it was complete."""

    complete: bool
    rules: tuple[ActiveRule, ...] = ()
    cause: str = ""
    evidence: str = ""
    classic: "ClassicProtection | None" = None
    details: tuple["RulesetDetail", ...] = ()
    details_complete: bool = True
    details_cause: str = ""
    details_evidence: str = ""


@dataclass(frozen=True)
class ClassicProtection:
    """The fields needed to assess classic force-push protection."""

    complete: bool
    protected: bool | None
    allow_force_pushes: bool | None = None
    enforce_admins: bool | None = None
    allow_deletions: bool | None = None
    lock_branch: bool | None = None
    required_linear_history: bool | None = None
    cause: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class BypassActor:
    actor_type: str
    bypass_mode: str
    actor_id: int | None = None


@dataclass(frozen=True)
class RulesetDetail:
    """A validated ruleset detail; omitted bypass actors remain unknown."""

    ruleset_id: int
    source_type: str
    source: str
    enforcement: str
    bypass_actors: tuple[BypassActor, ...] | None = None

    @property
    def identity(self) -> tuple[str, str, int]:
        return self.source_type, self.source, self.ruleset_id

    def label(self) -> str:
        return f"{self.source_type} {self.source} ruleset {self.ruleset_id}"


def branch_role(name: str, trunk: str) -> str | None:
    if name == trunk:
        return "trunk"
    if _TASK_RE.fullmatch(name):
        return "task"
    if _FEATURE_RE.fullmatch(name):
        return "feature"
    return None


def shared_branches(names: Iterable[str], trunk: str) -> tuple[tuple[str, str], ...]:
    """Return trunk and canonical feature/task names in stable, deduplicated order."""
    seen: set[str] = set()
    selected: list[tuple[str, str]] = []
    if isinstance(trunk, str) and trunk:
        seen.add(trunk)
        selected.append((trunk, "trunk"))
    candidates = sorted({name for name in names if isinstance(name, str) and name not in seen})
    for role in ("feature", "task"):
        for name in candidates:
            if branch_role(name, trunk) == role:
                seen.add(name)
                selected.append((name, role))
    return tuple(selected)


def parse_page_collection(payload: Any) -> tuple[tuple[Any, ...], ...] | None:
    """Validate ``gh api --paginate --slurp`` output as an array of array pages."""
    if not isinstance(payload, list):
        return None
    pages: list[tuple[Any, ...]] = []
    for page in payload:
        if not isinstance(page, list):
            return None
        pages.append(tuple(page))
    return tuple(pages)


def parse_branch_page_items(pages: Iterable[Iterable[Any]]) -> tuple[str, ...] | None:
    names: list[str] = []
    for page in pages:
        for item in page:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
                return None
            names.append(item["name"])
    return tuple(dict.fromkeys(names))


def parse_active_rules(payload: Any) -> tuple[ActiveRule, ...] | None:
    pages = parse_page_collection(payload)
    if pages is None:
        return None
    parsed: list[ActiveRule] = []
    seen: set[tuple[str, str, int, str]] = set()
    for page in pages:
        for item in page:
            if not isinstance(item, dict):
                return None
            rule_type = item.get("type")
            source_type = item.get("ruleset_source_type")
            source = item.get("ruleset_source")
            ruleset_id = item.get("ruleset_id")
            if (
                not isinstance(rule_type, str)
                or not rule_type
                or not isinstance(source_type, str)
                or not source_type
                or not isinstance(source, str)
                or not source
                or type(ruleset_id) is not int
            ):
                return None
            parameters = item.get("parameters")
            if parameters is not None and not isinstance(parameters, dict):
                return None
            rule = ActiveRule(rule_type, source_type, source, ruleset_id, parameters)
            identity = (*rule.identity, rule.type)
            if identity not in seen:
                seen.add(identity)
                parsed.append(rule)
    return tuple(parsed)


def parse_classic_protection(payload: Any) -> ClassicProtection | None:
    """Validate a successful classic protection response."""
    if not isinstance(payload, dict):
        return None
    values: dict[str, bool] = {}
    for name in ("allow_force_pushes", "enforce_admins"):
        value = payload.get(name)
        if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
            return None
        values[name] = value["enabled"]
    optional: dict[str, bool | None] = {}
    for name in ("allow_deletions", "lock_branch", "required_linear_history"):
        value = payload.get(name)
        if value is None:
            optional[name] = None
        elif isinstance(value, dict) and type(value.get("enabled")) is bool:
            optional[name] = value["enabled"]
        else:
            return None
    return ClassicProtection(
        True,
        True,
        values["allow_force_pushes"],
        values["enforce_admins"],
        optional["allow_deletions"],
        optional["lock_branch"],
        optional["required_linear_history"],
    )


def parse_ruleset_detail(payload: Any) -> RulesetDetail | None:
    """Validate the detail fields used for source and bypass evidence."""
    if not isinstance(payload, dict):
        return None
    ruleset_id = payload.get("id")
    source_type = payload.get("source_type")
    source = payload.get("source")
    enforcement = payload.get("enforcement")
    if (
        type(ruleset_id) is not int
        or not isinstance(source_type, str)
        or not source_type
        or not isinstance(source, str)
        or not source
        or not isinstance(enforcement, str)
        or not enforcement
    ):
        return None
    actors = payload.get("bypass_actors")
    if actors is None and "bypass_actors" in payload:
        return None
    if actors is not None:
        if not isinstance(actors, list):
            return None
        parsed: list[BypassActor] = []
        for actor in actors:
            if not isinstance(actor, dict):
                return None
            actor_type = actor.get("actor_type")
            bypass_mode = actor.get("bypass_mode")
            if not isinstance(actor_type, str) or not actor_type or not isinstance(bypass_mode, str) or not bypass_mode:
                return None
            actor_id = actor.get("actor_id")
            if actor_id is not None and type(actor_id) is not int:
                return None
            parsed.append(BypassActor(actor_type, bypass_mode, actor_id))
        actors_value: tuple[BypassActor, ...] | None = tuple(parsed)
    else:
        actors_value = None
    return RulesetDetail(ruleset_id, source_type, source, enforcement, actors_value)


def evaluate_force_push(branch: str, read: RuleRead) -> Result:
    """Combine effective rules, classic protection, and bypass visibility."""
    active = tuple(rule for rule in read.rules if rule.type == "non_fast_forward")
    details = {detail.identity: detail for detail in read.details}
    protected: list[str] = []
    unknown: list[str] = []
    unavailable: list[tuple[str, str, str]] = []
    exceptions: list[str] = []
    uncertain_cause = ""
    if not read.complete:
        evidence = read.evidence or "effective branch rules were not completely observed"
        if read.cause == "plan-limitation":
            unavailable.append((read.cause, evidence, cause_action(read.cause, "effective branch rules")))
        else:
            unknown.append(evidence)
            uncertain_cause = read.cause or "partial-read"
    for rule in active:
        detail = details.get(rule.identity)
        if detail is None:
            cause = read.details_cause or "bypass-coverage-unobserved"
            evidence = f"{rule.label()} bypass detail missing"
            if cause == "plan-limitation":
                unavailable.append((cause, evidence, cause_action(cause, "ruleset detail")))
            else:
                unknown.append(evidence)
                uncertain_cause = uncertain_cause or cause
            continue
        if detail.enforcement == "active":
            protected.append(rule.label())
            if detail.bypass_actors is None:
                unknown.append(f"{detail.label()} bypass_actors omitted")
                uncertain_cause = uncertain_cause or "bypass-coverage-unobserved"
            else:
                for actor in detail.bypass_actors:
                    actor_name = actor.actor_type + (f" #{actor.actor_id}" if actor.actor_id is not None else "")
                    mode = actor.bypass_mode
                    if mode == "pull_request":
                        exceptions.append(f"{detail.label()} {actor_name} pull_request bypass (no direct force-push)")
                    elif mode in {"always", "exempt"}:
                        exceptions.append(f"{detail.label()} {actor_name} {mode} bypass")
                    else:
                        unknown.append(f"{detail.label()} unsupported bypass mode {mode}")
                        uncertain_cause = uncertain_cause or "unsupported-bypass-mode"
        else:
            unknown.append(f"{detail.label()} enforcement changed to {detail.enforcement}")
            uncertain_cause = uncertain_cause or "ruleset-detail-mismatch"

    classic = read.classic
    classic_unknown = classic is None or not classic.complete
    if classic is not None and classic.cause == "plan-limitation":
        unavailable.append((classic.cause, classic.evidence or "classic protection was unavailable on the current plan", cause_action(classic.cause, "classic protection")))
    elif classic_unknown:
        evidence = (classic.evidence if classic else "classic protection was not read") or "classic protection was not read"
        cause = classic.cause if classic else "classic-protection-unobserved"
        unknown.append(evidence)
        uncertain_cause = uncertain_cause or cause
    elif classic.protected and classic.allow_force_pushes is False:
        protected.append("classic protection allow_force_pushes.enabled=false")
        if classic.enforce_admins is False:
            exceptions.append("classic protection does not enforce administrators")
    elif classic.protected and classic.allow_force_pushes is True:
        exceptions.append("classic protection allow_force_pushes.enabled=true")

    evidence = []
    if protected:
        evidence.append("force-push blocked by " + ", ".join(protected))
    if classic is not None and classic.complete and not classic.protected:
        evidence.append("classic protection absent (GitHub reported Branch not protected)")
    if exceptions:
        evidence.append("exceptions: " + "; ".join(exceptions))
    if unavailable:
        cause, detail, action = unavailable[0]
        return Result(CAPABILITY_UNAVAILABLE, cause, "; ".join([*evidence, detail, *unknown]), action)
    if unknown:
        evidence.extend(unknown)
        cause = uncertain_cause or ("classic-protection-unobserved" if classic_unknown else "read-failure")
        return Result(UNVERIFIED, cause, "; ".join(evidence) or "force-push protection evidence is incomplete", cause_action(cause, "GitHub protection and ruleset detail"))
    if protected:
        return Result(COMPATIBLE, "", "; ".join(evidence), "")
    return Result(
        INCOMPATIBLE,
        "missing-configuration",
        "; ".join(evidence) or "no enforced force-push protection was observed",
        f"Protect shared branch {branch} from force pushes with an active non_fast_forward ruleset or classic branch protection",
    )


def unknown_branch_result(reason: str = "branch-rules-unobserved") -> Result:
    return Result(
        UNVERIFIED,
        reason,
        "active rules and classic protection are not completely observed",
        cause_action(reason, "GitHub rules"),
    )


def cause_action(cause: str, target: str) -> str:
    if cause == "github-cli-unavailable":
        return "Install GitHub CLI and authenticate it, then rerun the doctor"
    if cause == "plan-limitation":
        return f"Ask the GitHub owner to enable {target} on a plan that supports it, then rerun the doctor"
    if cause == "authentication-failure":
        return f"Run gh auth login and retry the {target} read"
    if cause == "insufficient-permissions":
        if target == "ruleset detail":
            return "Ask the GitHub ruleset owner or organization administrator to inspect bypass exceptions with ruleset access, then retry"
        return f"Ask the repository or organization owner for read access needed for the {target} read, then retry"
    if cause == "rate-limited":
        return f"Retry the {target} read after GitHub's rate limit resets"
    if cause == "ambiguous-read":
        return f"Retry the {target} read after confirming repository visibility and access"
    if cause == "hidden-fields":
        return f"Ask the GitHub owner for visibility of the fields needed by the {target} read, then retry"
    if cause in {"bypass-coverage-unobserved", "unsupported-bypass-mode", "ruleset-detail-mismatch"}:
        return "Ask the GitHub ruleset owner or organization administrator to inspect its bypass fields and enforcement, then retry"
    if cause in {"malformed-response", "unsupported-rule-semantics"}:
        return f"Retry the {target} read and inspect the response fields before relying on it"
    if cause in {"branch-disappeared", "branch-missing"}:
        return "Retry after confirming the branch still exists on GitHub"
    return f"Retry the {target} read after confirming access to repository metadata"


_NEUTRAL_RULES = {
    "creation", "deletion", "required_deployments", "required_signatures",
    "required_status_checks", "non_fast_forward", "commit_message_pattern",
    "commit_author_email_pattern", "committer_email_pattern", "branch_name_pattern",
    "tag_name_pattern", "workflows", "file_path_restriction", "file_extension_restriction",
    "file_size", "code_scanning", "code_quality", "code_coverage", "secret_scanning",
}


def _bypass_notes(rule: ActiveRule, details: dict[tuple[str, str, int], RulesetDetail], operation: str) -> tuple[str, ...]:
    detail = details.get(rule.identity)
    if detail is None:
        return (f"{rule.label()} bypass detail missing",)
    if detail.bypass_actors is None:
        return (f"{detail.label()} bypass_actors omitted",)
    notes: list[str] = []
    for actor in detail.bypass_actors:
        name = actor.actor_type + (f" #{actor.actor_id}" if actor.actor_id is not None else "")
        if actor.bypass_mode == "pull_request":
            suffix = f" (does not bypass {operation})" if "deletion" in operation else ""
            notes.append(f"{detail.label()} {name} pull_request bypass{suffix}")
        elif actor.bypass_mode in {"always", "exempt"}:
            notes.append(f"{detail.label()} {name} {actor.bypass_mode} bypass")
        else:
            notes.append(f"{detail.label()} unsupported bypass mode {actor.bypass_mode}")
    return tuple(notes)


def _detail_gap(rule: ActiveRule, read: RuleRead, details: dict[tuple[str, str, int], RulesetDetail], operation: str) -> tuple[str, str]:
    detail = details.get(rule.identity)
    if detail is None:
        return f"{rule.label()} {operation} detail unavailable: {read.details_evidence or 'ruleset detail was not observed'}", read.details_cause or "bypass-coverage-unobserved"
    if detail.enforcement != "active":
        return f"{detail.label()} enforcement changed to {detail.enforcement}", "ruleset-detail-mismatch"
    if detail.bypass_actors is None:
        return f"{detail.label()} bypass_actors omitted", "bypass-coverage-unobserved"
    if any(actor.bypass_mode not in {"always", "pull_request", "exempt"} for actor in detail.bypass_actors):
        return f"{detail.label()} has an unsupported bypass mode", "unsupported-bypass-mode"
    return "", ""


def _finish(
    conflicts: list[str],
    unknown: list[str],
    unavailable: list[tuple[str, str, str]],
    actions: list[str],
    unknown_cause: str,
    unknown_action: str,
    notes: list[str] | None = None,
) -> Result:
    unavailable_evidence = [detail for _, detail, _ in unavailable]
    evidence = "; ".join(conflicts + (notes or []) + unknown + unavailable_evidence) or "all required delivery constraints were observed"
    action = "; ".join(dict.fromkeys(actions))
    if conflicts:
        return Result(INCOMPATIBLE, "conflicting-configuration", evidence, action or unknown_action)
    if unavailable:
        cause, detail, suggested = unavailable[0]
        return Result(CAPABILITY_UNAVAILABLE, cause, "; ".join([*conflicts, *(notes or []), *unknown, detail]), suggested or cause_action(cause, "GitHub delivery rules"))
    if unknown:
        retry_causes = {"authentication-failure", "insufficient-permissions", "rate-limited", "ambiguous-read", "hidden-fields", "plan-limitation"}
        return Result(UNVERIFIED, unknown_cause, evidence, action or (cause_action(unknown_cause, "GitHub delivery rules") if unknown_cause in retry_causes else unknown_action))
    return Result(COMPATIBLE, "", evidence, "")


def evaluate_merge(branch: str, read: RuleRead, repository_setting: Result | None = None) -> Result:
    """Assess whether the ordinary delivery path can create merge commits."""
    conflicts: list[str] = []
    unknown: list[str] = []
    unavailable: list[tuple[str, str, str]] = []
    actions: list[str] = []
    notes: list[str] = []
    unknown_cause = ""

    if repository_setting is None:
        unknown.append("mergeCommitAllowed was not observed")
    elif repository_setting.state == INCOMPATIBLE:
        conflicts.append(f"mergeCommitAllowed {repository_setting.evidence}")
        actions.append(repository_setting.next_action)
    elif repository_setting.state == CAPABILITY_UNAVAILABLE:
        unavailable.append((repository_setting.cause, repository_setting.evidence, repository_setting.next_action))
    elif repository_setting.state != COMPATIBLE:
        unknown.append(f"mergeCommitAllowed {repository_setting.evidence}")
        unknown_cause = unknown_cause or repository_setting.cause or "read-failure"

    if not read.complete:
        evidence = read.evidence or "effective branch rules were not completely observed"
        if read.cause == "plan-limitation":
            unavailable.append((read.cause, evidence, cause_action(read.cause, "effective branch rules")))
        else:
            unknown.append(evidence)
            unknown_cause = read.cause or unknown_cause or "partial-read"
    details = {detail.identity: detail for detail in read.details}
    rules = read.rules
    for rule in rules:
        label = rule.label()
        if rule.type in {"required_linear_history", "pull_request", "merge_queue", "update"}:
            gap, cause = _detail_gap(rule, read, details, "merge")
            if gap:
                if cause == "plan-limitation":
                    unavailable.append((cause, gap, cause_action(cause, "ruleset detail")))
                else:
                    unknown.append(gap)
                    unknown_cause = unknown_cause or cause
            else:
                notes.extend(_bypass_notes(rule, details, "ordinary merge updates"))
        if rule.type == "required_linear_history":
            conflicts.append(f"{label} required_linear_history prevents merge commits on {branch}")
            actions.append(f"Adjust {label} scope to allow merge commits on {branch}, preserving checks, reviews, and bypass policy")
        elif rule.type == "pull_request":
            parameters = rule.parameters
            methods = parameters.get("allowed_merge_methods") if isinstance(parameters, dict) else None
            if not isinstance(methods, list):
                unknown.append(f"{label} pull_request.allowed_merge_methods was not observed")
                unknown_cause = unknown_cause or "hidden-fields"
                actions.append(f"Inspect {label} pull_request.allowed_merge_methods before relying on merge-commit delivery for {branch}")
            elif not methods or not all(isinstance(method, str) for method in methods):
                unknown.append(f"{label} pull_request.allowed_merge_methods had unsupported values")
                unknown_cause = unknown_cause or "unsupported-rule-semantics"
            elif any(method not in {"merge", "squash", "rebase"} for method in methods):
                unknown.append(f"{label} pull_request.allowed_merge_methods had an unknown method")
                unknown_cause = unknown_cause or "unsupported-rule-semantics"
            elif "merge" not in methods:
                conflicts.append(f"{label} pull_request.allowed_merge_methods excludes merge")
                actions.append(f"Adjust {label} pull_request.allowed_merge_methods to include merge for {branch}, preserving checks, reviews, and bypass policy")
        elif rule.type == "merge_queue":
            parameters = rule.parameters
            method = parameters.get("merge_method") if isinstance(parameters, dict) else None
            if not isinstance(method, str):
                unknown.append(f"{label} merge_queue.parameters.merge_method was not observed")
                unknown_cause = unknown_cause or "hidden-fields"
                actions.append(f"Inspect {label} merge_queue.parameters.merge_method before relying on merge-commit delivery for {branch}")
            elif method not in {"MERGE", "SQUASH", "REBASE"}:
                unknown.append(f"{label} merge_queue has unsupported merge_method {method}")
                actions.append(f"Inspect {label} merge_queue.parameters.merge_method before relying on merge-commit delivery for {branch}")
            elif method != "MERGE":
                conflicts.append(f"{label} merge_queue.parameters.merge_method={method} does not create merge commits")
                actions.append(f"Adjust {label} merge_queue.parameters.merge_method to MERGE for {branch}, preserving checks, reviews, and bypass policy")
            else:
                unknown.append(f"{label} merge_queue requires queue interaction; ordinary stack merge acceptance is unverified")
                unknown_cause = unknown_cause or "unsupported-rule-semantics"
                actions.append(f"Verify {label} queue interaction for ordinary stack delivery on {branch}")
        elif rule.type == "update":
            unknown.append(f"{label} update restricts ordinary branch updates to bypass actors; merge interaction is unverified")
            unknown_cause = unknown_cause or "unsupported-rule-semantics"
            actions.append(f"Review {label} update scope and bypass policy for ordinary merge delivery on {branch}")
        elif rule.type not in _NEUTRAL_RULES:
            unknown.append(f"{label} has unsupported rule semantics for merge evaluation")
            actions.append(f"Review {label} before relying on merge-commit delivery for {branch}")
            unknown_cause = unknown_cause or "unsupported-rule-semantics"

    classic = read.classic
    if classic is not None and classic.cause == "plan-limitation":
        unavailable.append((classic.cause, classic.evidence or "classic protection was unavailable on the current plan", cause_action(classic.cause, "classic protection")))
    elif classic is None or not classic.complete:
        evidence = (classic.evidence if classic else "classic protection was not read") or "classic protection was not read"
        cause = classic.cause if classic else "classic-protection-unobserved"
        unknown.append(evidence)
        unknown_cause = unknown_cause or cause
    elif classic.protected is None:
        unknown.append("classic protection state was not observed")
        unknown_cause = unknown_cause or "missing-field"
    elif classic.protected:
        if classic.required_linear_history is True:
            conflicts.append(f"classic protection required_linear_history.enabled=true prevents merge commits on {branch}")
            actions.append(f"Set required_linear_history.enabled=false in classic protection for {branch}, preserving checks, reviews, and bypass policy")
        elif classic.required_linear_history is None:
            unknown.append("classic protection required_linear_history was not observed")
            unknown_cause = unknown_cause or classic.cause or "missing-field"
        if classic.lock_branch is True:
            conflicts.append(f"classic protection lock_branch.enabled=true makes {branch} read-only")
            actions.append(f"Set lock_branch.enabled=false in classic protection for {branch}, preserving checks, reviews, and bypass policy")
        elif classic.lock_branch is None:
            unknown.append("classic protection lock_branch was not observed")
            unknown_cause = unknown_cause or classic.cause or "missing-field"

    return _finish(
        conflicts,
        unknown,
        unavailable,
        actions,
        unknown_cause or "missing-field",
        "Retry the GitHub merge rules and classic protection reads after confirming access",
        notes,
    )


def evaluate_cleanup(
    branch: str,
    read: RuleRead,
    repository_setting: Result | None = None,
    role: str = "feature",
) -> Result:
    """Assess automatic cleanup while keeping the delivery trunk retained."""
    if role == "trunk":
        return Result(COMPATIBLE, "", "trunk is retained; cleanup applies to integrated feature/task branches", "")

    conflicts: list[str] = []
    unknown: list[str] = []
    unavailable: list[tuple[str, str, str]] = []
    actions: list[str] = []
    unknown_cause = ""
    if repository_setting is None:
        unknown.append("deleteBranchOnMerge was not observed")
    elif repository_setting.state == INCOMPATIBLE:
        conflicts.append(f"deleteBranchOnMerge {repository_setting.evidence}")
        actions.append(repository_setting.next_action)
    elif repository_setting.state == CAPABILITY_UNAVAILABLE:
        unavailable.append((repository_setting.cause, repository_setting.evidence, repository_setting.next_action))
    elif repository_setting.state != COMPATIBLE:
        unknown.append(f"deleteBranchOnMerge {repository_setting.evidence}")
        unknown_cause = unknown_cause or repository_setting.cause or "read-failure"

    if not read.complete:
        evidence = read.evidence or "effective branch rules were not completely observed"
        if read.cause == "plan-limitation":
            unavailable.append((read.cause, evidence, cause_action(read.cause, "effective branch rules")))
        else:
            unknown.append(evidence)
            unknown_cause = read.cause or unknown_cause or "partial-read"
    details = {detail.identity: detail for detail in read.details}
    for rule in read.rules:
        label = rule.label()
        if rule.type == "deletion":
            conflicts.append(f"{label} deletion restricts {branch} to bypass actors")
            actions.append(f"Adjust {label} deletion scope to permit cleanup of integrated feature/task branches while retaining trunk and preserving checks, reviews, and bypass policy")
            gap, cause = _detail_gap(rule, read, details, "cleanup")
            if gap:
                if cause == "plan-limitation":
                    unavailable.append((cause, gap, cause_action(cause, "ruleset detail")))
                else:
                    unknown.append(gap)
                    unknown_cause = unknown_cause or cause
            else:
                unknown.extend(_bypass_notes(rule, details, "ordinary branch deletion"))
        elif rule.type not in _NEUTRAL_RULES | {"required_linear_history", "pull_request", "merge_queue", "update"}:
            unknown.append(f"{label} has unsupported rule semantics for cleanup evaluation")
            actions.append(f"Review {label} before relying on automatic cleanup for {branch}")
            unknown_cause = unknown_cause or "unsupported-rule-semantics"

    classic = read.classic
    if classic is not None and classic.cause == "plan-limitation":
        unavailable.append((classic.cause, classic.evidence or "classic protection was unavailable on the current plan", cause_action(classic.cause, "classic protection")))
    elif classic is None or not classic.complete:
        evidence = (classic.evidence if classic else "classic protection was not read") or "classic protection was not read"
        cause = classic.cause if classic else "classic-protection-unobserved"
        unknown.append(evidence)
        unknown_cause = unknown_cause or cause
    elif classic.protected is None:
        unknown.append("classic protection state was not observed")
        unknown_cause = unknown_cause or "missing-field"
    elif classic.protected:
        if classic.allow_deletions is False:
            conflicts.append(f"classic protection allow_deletions.enabled=false blocks cleanup of {branch}")
            actions.append(f"Set allow_deletions.enabled=true in classic protection for integrated {branch} cleanup, preserving checks, reviews, and bypass policy")
        elif classic.allow_deletions is None:
            unknown.append("classic protection allow_deletions was not observed")
            unknown_cause = unknown_cause or classic.cause or "missing-field"
        if classic.lock_branch is True:
            conflicts.append(f"classic protection lock_branch.enabled=true blocks cleanup of {branch}")
            actions.append(f"Set lock_branch.enabled=false in classic protection for integrated {branch} cleanup, preserving checks, reviews, and bypass policy")
        elif classic.lock_branch is None:
            unknown.append("classic protection lock_branch was not observed")
            unknown_cause = unknown_cause or classic.cause or "missing-field"

    return _finish(
        conflicts,
        unknown,
        unavailable,
        actions,
        unknown_cause or "missing-field",
        "Retry the GitHub cleanup rules and classic protection reads after confirming access",
    )
