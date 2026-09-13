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


def evaluate_force_push(branch: str, read: RuleRead) -> Result:
    """Evaluate only active non-fast-forward evidence; classic protection is T003."""
    if not read.complete:
        return Result(
            UNVERIFIED,
            read.cause or "partial-read",
            read.evidence or "effective branch rules were not completely observed",
            "Retry the GitHub rules read after confirming access to repository metadata",
        )
    sources = tuple(rule.label() for rule in read.rules if rule.type == "non_fast_forward")
    if sources:
        evidence = "active non_fast_forward from " + ", ".join(sources)
        return Result(
            UNVERIFIED,
            "bypass-coverage-unobserved",
            evidence + "; classic protection and bypass exceptions remain unverified until the next diagnosis stage",
            "Inspect classic branch protection and bypass exceptions, then rerun the doctor",
        )
    return Result(
        UNVERIFIED,
        "classic-protection-unobserved",
        "no active non_fast_forward rule was returned; classic protection is not observed yet",
        "Inspect classic branch protection and rerun the doctor",
    )


def unknown_branch_result(reason: str = "branch-rules-unobserved") -> Result:
    return Result(
        UNVERIFIED,
        reason,
        "active rules and classic protection are not completely observed",
        "Retry the GitHub rules read after confirming access to repository metadata",
    )
