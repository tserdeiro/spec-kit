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
            rule = ActiveRule(rule_type, source_type, source, ruleset_id)
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
    for name in ("allow_deletions", "lock_branch"):
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
    if not read.complete:
        return Result(
            UNVERIFIED,
            read.cause or "partial-read",
            read.evidence or "effective branch rules were not completely observed",
            "Retry the GitHub rules read after confirming access to repository metadata",
        )
    active = tuple(rule for rule in read.rules if rule.type == "non_fast_forward")
    details = {detail.identity: detail for detail in read.details}
    protected: list[str] = []
    unknown: list[str] = []
    exceptions: list[str] = []
    uncertain_cause = ""
    for rule in active:
        detail = details.get(rule.identity)
        if detail is None:
            unknown.append(f"{rule.label()} bypass detail missing")
            uncertain_cause = uncertain_cause or read.details_cause or "bypass-coverage-unobserved"
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
    if classic_unknown:
        unknown.append((classic.evidence if classic else "classic protection was not read") or "classic protection was not read")
        uncertain_cause = uncertain_cause or (classic.cause if classic else "classic-protection-unobserved")
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
    if unknown:
        evidence.extend(unknown)
        cause = uncertain_cause or ("classic-protection-unobserved" if classic_unknown else "read-failure")
        return Result(
            UNVERIFIED,
            cause,
            "; ".join(evidence) or "force-push protection evidence is incomplete",
            "Retry the GitHub protection and ruleset detail reads after confirming access",
        )
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
        "Retry the GitHub rules read after confirming access to repository metadata",
    )
