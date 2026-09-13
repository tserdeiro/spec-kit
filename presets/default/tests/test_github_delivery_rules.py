"""Pure tests for shared-branch selection and active-rule evaluation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import github_delivery
import github_delivery_rules as rules
import _common

IDENTITY = github_delivery.RepositoryIdentity("github.com", "acme", "demo")


def _repository_payload(**settings: object) -> str:
    return json.dumps({"nameWithOwner": "acme/demo", "url": "https://github.com/acme/demo", "defaultBranchRef": {"name": "main"}, **settings})


def _active(kind: str = "non_fast_forward", ident: int = 7, parameters: dict[str, object] | None = None) -> dict[str, object]:
    value = {
        "type": kind,
        "ruleset_source_type": "Organization",
        "ruleset_source": "acme",
        "ruleset_id": ident,
    }
    if parameters is not None:
        value["parameters"] = parameters
    return value


def _classic(allow: bool = False, admins: bool = True) -> dict[str, object]:
    return {"allow_force_pushes": {"enabled": allow}, "enforce_admins": {"enabled": admins}}


def _complete_classic(**values: bool) -> rules.ClassicProtection:
    return rules.ClassicProtection(True, True, allow_force_pushes=False, enforce_admins=True, **values)


def _setting(name: str, state: str = rules.COMPATIBLE) -> rules.Result:
    return rules.Result(state, "", f"{name} observed true", "")


def _detail(actors: object = None, include: bool = True) -> dict[str, object]:
    payload = {"id": 7, "source_type": "Organization", "source": "acme", "enforcement": "active"}
    if include:
        payload["bypass_actors"] = actors if actors is not None else []
    return payload


def test_active_rules_parse_pages_and_dedupe_rule_identity() -> None:
    payload = [[_active(), _active(), _active("required_signatures")]]
    parsed = rules.parse_active_rules(payload)
    assert parsed is not None
    assert [(item.type, item.identity) for item in parsed] == [
        ("non_fast_forward", ("Organization", "acme", 7)),
        ("required_signatures", ("Organization", "acme", 7)),
    ]


def test_ruleset_detail_preserves_bypass_actor_identity() -> None:
    detail = rules.parse_ruleset_detail(_detail([{"actor_type": "Team", "actor_id": 42, "bypass_mode": "always"}]))
    assert detail is not None and detail.bypass_actors is not None
    assert detail.bypass_actors[0] == rules.BypassActor("Team", "always", 42)
    assert rules.parse_ruleset_detail(_detail([{"actor_type": "Team", "bypass_mode": "always"}])) is None


def test_non_fast_forward_keeps_source_while_classic_layer_is_pending() -> None:
    parsed = rules.parse_active_rules([[_active()]])
    assert parsed is not None
    result = rules.evaluate_force_push("main", rules.RuleRead(True, parsed))
    assert result.state == rules.UNVERIFIED
    assert "Organization acme ruleset 7" in result.evidence
    assert "classic protection" in result.evidence


@pytest.mark.parametrize(
    ("classic", "detail", "state", "evidence"),
    [
        (_classic(), None, rules.COMPATIBLE, "classic protection allow_force_pushes.enabled=false"),
        (rules.ClassicProtection(True, True, allow_force_pushes=False, enforce_admins=False), None, rules.COMPATIBLE, "does not enforce administrators"),
        (rules.ClassicProtection(True, False), None, rules.INCOMPATIBLE, "Branch not protected"),
        (rules.ClassicProtection(False, None, evidence="HTTP 404: Not Found"), None, rules.UNVERIFIED, "HTTP 404"),
        (rules.ClassicProtection(True, True, allow_force_pushes=True), _detail(), rules.COMPATIBLE, "force-push blocked"),
    ],
)
def test_force_push_combines_classic_and_ruleset_layers(classic, detail, state, evidence) -> None:
    parsed = rules.parse_active_rules([[_active()]])
    assert parsed is not None
    protection = rules.parse_classic_protection(classic) if isinstance(classic, dict) else classic
    details = (rules.parse_ruleset_detail(detail),) if detail else ()
    result = rules.evaluate_force_push("main", rules.RuleRead(True, parsed if detail else (), classic=protection, details=details))
    assert result.state == state
    assert evidence in result.evidence


@pytest.mark.parametrize(
    ("actors", "needle"),
    [
        ([], "force-push blocked"),
        ([{"actor_type": "RepositoryRole", "actor_id": 1, "bypass_mode": "pull_request"}], "no direct force-push"),
        ([{"actor_type": "OrganizationAdmin", "actor_id": 42, "bypass_mode": "always"}], "#42 always bypass"),
        ([{"actor_type": "RepositoryRole", "actor_id": 1, "bypass_mode": "exempt"}], "exempt bypass"),
    ],
)
def test_bypass_modes_are_visible_without_becoming_authorization(actors, needle) -> None:
    parsed = rules.parse_active_rules([[_active()]])
    detail = rules.parse_ruleset_detail(_detail(actors))
    assert parsed is not None and detail is not None
    result = rules.evaluate_force_push("main", rules.RuleRead(True, parsed, details=(detail,), classic=rules.ClassicProtection(True, False)))
    assert result.state == rules.COMPATIBLE
    assert needle in result.evidence


def test_omitted_bypass_actors_remains_unknown() -> None:
    parsed = rules.parse_active_rules([[_active()]])
    detail = rules.parse_ruleset_detail(_detail(include=False))
    assert parsed is not None and detail is not None
    result = rules.evaluate_force_push("main", rules.RuleRead(True, parsed, details=(detail,), classic=rules.ClassicProtection(True, False)))
    assert result.state == rules.UNVERIFIED
    assert result.cause == "bypass-coverage-unobserved"
    assert "ruleset owner" in result.next_action


def test_rule_parameters_are_preserved_for_merge_evaluation() -> None:
    parsed = rules.parse_active_rules([[_active("pull_request", parameters={"allowed_merge_methods": ["squash"]})]])
    assert parsed is not None
    assert parsed[0].parameters == {"allowed_merge_methods": ["squash"]}


@pytest.mark.parametrize(
    ("rule", "needle"),
    [
        (_active("required_linear_history"), "required_linear_history"),
        (_active("pull_request", parameters={"allowed_merge_methods": ["squash", "rebase"]}), "allowed_merge_methods excludes merge"),
        (_active("merge_queue", parameters={"merge_method": "SQUASH"}), "merge_method=SQUASH"),
    ],
)
def test_merge_conflicts_keep_rule_owner_and_remediation(rule, needle) -> None:
    parsed = rules.parse_active_rules([[rule]])
    assert parsed is not None
    result = rules.evaluate_merge("001-feature", rules.RuleRead(True, parsed, classic=_complete_classic(required_linear_history=False, lock_branch=False)), _setting("mergeCommitAllowed"))
    assert result.state == rules.INCOMPATIBLE
    assert needle in result.evidence
    assert "Organization acme ruleset 7" in result.next_action


def test_merge_queue_missing_method_and_update_rule_are_unverified() -> None:
    parsed = rules.parse_active_rules([[_active("merge_queue"), _active("update", 8)]])
    assert parsed is not None
    result = rules.evaluate_merge("main", rules.RuleRead(True, parsed, classic=_complete_classic(required_linear_history=False, lock_branch=False)), _setting("mergeCommitAllowed"))
    assert result.state == rules.UNVERIFIED
    assert "merge_method" in result.evidence
    assert "ordinary branch updates" in result.evidence


def test_merge_conflict_is_retained_when_effective_rules_read_is_incomplete() -> None:
    read = rules.RuleRead(False, cause="partial-rules", evidence="page 2 failed", classic=_complete_classic(required_linear_history=True, lock_branch=False))
    result = rules.evaluate_merge("main", read, _setting("mergeCommitAllowed"))
    assert result.state == rules.INCOMPATIBLE
    assert "required_linear_history" in result.evidence
    assert "page 2 failed" in result.evidence


def test_force_push_keeps_classic_evidence_when_rules_read_is_incomplete() -> None:
    read = rules.RuleRead(False, cause="partial-rules", evidence="page 2 failed", classic=rules.ClassicProtection(True, True, allow_force_pushes=True))
    result = rules.evaluate_force_push("main", read)
    assert result.state == rules.UNVERIFIED
    assert "allow_force_pushes.enabled=true" in result.evidence
    assert "page 2 failed" in result.evidence


def test_detail_errors_keep_identity_and_plan_priority() -> None:
    parsed = rules.parse_active_rules([[_active()], [_active(ident=8)]])
    assert parsed is not None
    errors = ((parsed[0].identity, ("rate-limited", "rate page")), (parsed[1].identity, ("plan-limitation", "plan page")))
    result = rules.evaluate_force_push("main", rules.RuleRead(True, parsed, detail_errors=errors))
    assert result.state == rules.CAPABILITY_UNAVAILABLE
    assert result.cause == "plan-limitation"
    assert "Organization acme ruleset 7" in result.evidence and "rate page" in result.evidence


@pytest.mark.parametrize(("malformed", "evidence"), [(False, "HTTP 429"), (True, "malformed page")])
def test_partial_rule_pages_keep_prior_merge_and_cleanup_conflicts(tmp_path, monkeypatch, malformed: bool, evidence: str) -> None:
    responses = iter((SimpleNamespace(returncode=0 if malformed else 1, stdout=json.dumps([[_active("required_linear_history")], [{"bad": True}] if malformed else {"message": "HTTP 429: Too Many Requests"}]), stderr="" if malformed else "HTTP 429"), SimpleNamespace(returncode=0, stdout=json.dumps(_classic()), stderr=""), SimpleNamespace(returncode=0 if malformed else 1, stdout=json.dumps([[_active("deletion")], [{"bad": True}] if malformed else {"message": "HTTP 429: Too Many Requests"}]), stderr="" if malformed else "HTTP 429"), SimpleNamespace(returncode=0, stdout=json.dumps(_classic()), stderr="")))
    monkeypatch.setattr(github_delivery, "run_gh", lambda *args, **kwargs: next(responses))
    merge = rules.evaluate_merge("main", github_delivery._read_branch_rules(tmp_path, "main", identity=IDENTITY), _setting("mergeCommitAllowed"))
    assert merge.state == rules.INCOMPATIBLE and "required_linear_history" in merge.evidence and evidence in merge.evidence
    cleanup = rules.evaluate_cleanup("001-feature", github_delivery._read_branch_rules(tmp_path, "001-feature", identity=IDENTITY), _setting("deleteBranchOnMerge"))
    assert cleanup.state == rules.INCOMPATIBLE and "deletion restricts" in cleanup.evidence and evidence in cleanup.evidence


@pytest.mark.parametrize("evaluate", [rules.evaluate_force_push, rules.evaluate_merge, rules.evaluate_cleanup])
def test_explicit_plan_limit_is_capability_unavailable_for_each_guarantee(evaluate) -> None:
    classic = rules.ClassicProtection(False, None, cause="plan-limitation", evidence="plan excludes this read")
    read = rules.RuleRead(True, classic=classic)
    if evaluate is rules.evaluate_force_push:
        result = evaluate("main", read)
    elif evaluate is rules.evaluate_merge:
        result = evaluate("main", read, _setting("mergeCommitAllowed"))
    else:
        result = evaluate("001-feature", read, _setting("deleteBranchOnMerge"))
    assert result.state == rules.CAPABILITY_UNAVAILABLE
    assert result.cause == "plan-limitation"
    assert "plan" in result.next_action


def test_cleanup_distinguishes_feature_conflicts_from_retained_trunk() -> None:
    parsed = rules.parse_active_rules([[_active("deletion")]])
    assert parsed is not None
    read = rules.RuleRead(True, parsed, classic=_complete_classic(allow_deletions=False, lock_branch=True, required_linear_history=False))
    result = rules.evaluate_cleanup("001-feature", read, _setting("deleteBranchOnMerge"), role="feature")
    assert result.state == rules.INCOMPATIBLE
    assert "deletion restricts" in result.evidence
    assert "allow_deletions" in result.evidence
    trunk = rules.evaluate_cleanup("main", read, _setting("deleteBranchOnMerge"), role="trunk")
    assert trunk.state == rules.COMPATIBLE
    assert "trunk is retained" in trunk.evidence


def test_cleanup_missing_classic_fields_stays_unverified() -> None:
    read = rules.RuleRead(True, (), classic=_complete_classic())
    result = rules.evaluate_cleanup("001-feature", read, _setting("deleteBranchOnMerge"))
    assert result.state == rules.UNVERIFIED
    assert "allow_deletions" in result.evidence
    assert "lock_branch" in result.evidence


def test_diagnose_preserves_merge_uncertainty_when_ruleset_detail_is_denied(tmp_path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    detail_denied = False
    classic = {name: {"enabled": value} for name, value in {
        "allow_force_pushes": False, "enforce_admins": True, "allow_deletions": True,
        "lock_branch": False, "required_linear_history": False,
    }.items()}

    def fake_gh(*args: str, cwd=None):
        endpoint = args[-1]
        if args[:3] == ("repo", "view", "--json"):
            return SimpleNamespace(returncode=0, stdout=_repository_payload(deleteBranchOnMerge=True, mergeCommitAllowed=True), stderr="")
        if endpoint == "repos/acme/demo/branches?per_page=100":
            return SimpleNamespace(returncode=0, stdout=json.dumps([[{"name": "main"}]]), stderr="")
        if "/rules/branches/" in endpoint:
            return SimpleNamespace(returncode=0, stdout=json.dumps([[_active("pull_request", parameters={"allowed_merge_methods": ["merge"]})]]), stderr="")
        if "/protection" in endpoint:
            return SimpleNamespace(returncode=0, stdout=json.dumps(classic), stderr="")
        if "/rulesets/" in endpoint:
            return SimpleNamespace(returncode=1, stdout="", stderr="permission denied") if detail_denied else SimpleNamespace(returncode=0, stdout=json.dumps(_detail([{"actor_type": "OrganizationAdmin", "bypass_mode": "always"}])), stderr="")
        raise AssertionError(endpoint)

    monkeypatch.setattr(github_delivery, "run_gh", fake_gh)
    monkeypatch.setattr(github_delivery, "delivery_base", lambda _root, **_kwargs: "main")
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    settings, findings = github_delivery.diagnose(tmp_path)
    merge = next(result for name, result in findings if name.startswith("merge commits"))
    assert merge.state == rules.COMPATIBLE and "always bypass" in merge.evidence
    detail_denied = True
    settings, findings = github_delivery.diagnose(tmp_path)
    merge = next(result for name, result in findings if name.startswith("merge commits"))
    assert merge.state == rules.UNVERIFIED and "detail unavailable" in merge.evidence
    assert github_delivery.overall_result(settings, findings).state == rules.UNVERIFIED
    assert "future branches are not certified" in github_delivery.render(settings, findings)


def test_classic_404_only_documents_absence_for_exact_message(tmp_path, monkeypatch) -> None:
    responses = iter((
        SimpleNamespace(returncode=1, stdout='{"message":"Branch not protected"}', stderr="HTTP 404"),
        SimpleNamespace(returncode=1, stdout='{"message":"Not Found"}', stderr="HTTP 404"),
    ))
    monkeypatch.setattr(github_delivery, "run_gh", lambda *args, **kwargs: next(responses))
    assert github_delivery._read_classic_protection(tmp_path, "main", IDENTITY).protected is False
    assert github_delivery._read_classic_protection(tmp_path, "main", IDENTITY).complete is False
    result = rules.evaluate_force_push("main", rules.RuleRead(True, classic=rules.ClassicProtection(False, None, cause="read-failure", evidence="forbidden")))
    assert result.cause == "read-failure"


def test_successful_classic_response_with_omitted_fields_is_hidden() -> None:
    protection = rules.parse_classic_protection(_classic())
    assert protection is not None
    result = rules.evaluate_cleanup(
        "001-feature",
        rules.RuleRead(True, classic=rules.ClassicProtection(True, True, protection.allow_force_pushes, protection.enforce_admins, cause="hidden-fields", evidence="optional fields omitted")),
        _setting("deleteBranchOnMerge"),
    )
    assert result.state == rules.UNVERIFIED
    assert result.cause == "hidden-fields"


def test_report_reads_paginated_inventory_and_effective_rules_as_gets(tmp_path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    calls: list[tuple[str, ...]] = []
    active = json.dumps([[_active()], [_active("required_signatures", 8)]])

    def fake_gh(*args: str, cwd=None):
        calls.append(args)
        if args[:3] == ("repo", "view", "--json"):
            return SimpleNamespace(returncode=0, stdout=_repository_payload(deleteBranchOnMerge=True, mergeCommitAllowed=True), stderr="")
        if args[-1] == "repos/acme/demo/branches?per_page=100":
            return SimpleNamespace(returncode=0, stdout=json.dumps([[{"name": "main"}, {"name": "001-feature"}, {"name": "001-feature"}], [{"name": "001-T001-task"}, {"name": "unrelated"}]]), stderr="")
        if "%24%28touch%20pwned%29" in args[-1]:
            return SimpleNamespace(returncode=0, stdout=active, stderr="")
        if "/rulesets/" in args[-1]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(_detail()), stderr="")
        if "/protection" in args[-1]:
            return SimpleNamespace(returncode=1, stdout='{"message":"Branch not protected"}', stderr="HTTP 404")
        return SimpleNamespace(returncode=0, stdout=active if any(marker in args[-1] for marker in ("/main?", "/001-T001-task?")) else "[[]]", stderr="")

    monkeypatch.setattr(github_delivery, "run_gh", fake_gh)
    monkeypatch.setattr(github_delivery, "delivery_base", lambda _root, **_kwargs: "main")
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    _settings, findings = github_delivery.diagnose(tmp_path)
    detail_calls = [call[-1] for call in calls if "/rulesets/" in call[-1]]
    assert detail_calls.count("repos/acme/demo/rulesets/7?includes_parents=true") == 1
    assert "repos/acme/demo/rulesets/8?includes_parents=true" in detail_calls
    github_delivery._read_branch_rules(tmp_path, "001-$(touch pwned)", identity=IDENTITY)
    detail_calls = [call[-1] for call in calls if "/rulesets/" in call[-1]]
    assert detail_calls.count("repos/acme/demo/rulesets/7?includes_parents=true") == 2
    assert [(name, result.state) for name, result in findings if name.startswith("force-push")] == [("force-push protection [main (trunk)]", rules.COMPATIBLE), ("force-push protection [001-feature (feature)]", rules.INCOMPATIBLE), ("force-push protection [001-T001-task (task)]", rules.COMPATIBLE)]
    assert github_delivery._read_branch_rules(tmp_path, "001-feature", identity=IDENTITY).complete
    assert rules.evaluate_force_push("001-feature", github_delivery._read_branch_rules(tmp_path, "001-feature", identity=IDENTITY)).cause == "missing-configuration"
    assert "Organization acme ruleset 7" in github_delivery.render(_settings, findings)
    assert all(call[1:3] == ("--hostname", "github.com") and call[3:5] == ("--method", "GET") for call in calls[1:])


def test_transport_failures_keep_distinct_causes_and_malformed_pages_unknown(tmp_path, monkeypatch) -> None:
    responses = iter((
        SimpleNamespace(returncode=1, stdout="", stderr="transport failed on page 2"),
        SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404: Not Found"),
        SimpleNamespace(returncode=0, stdout=json.dumps(_classic()), stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="branch not found"),
        SimpleNamespace(returncode=0, stdout=json.dumps(_classic()), stderr=""),
        SimpleNamespace(returncode=0, stdout='[[{"name":"main"}], {}]', stderr=""),
    ))
    monkeypatch.setattr(github_delivery, "run_gh", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    assert github_delivery._read_inventory(tmp_path, IDENTITY).cause == "partial-inventory"
    assert github_delivery._read_branch_rules(tmp_path, "main", identity=IDENTITY).cause == "ambiguous-read"
    assert github_delivery._read_branch_rules(tmp_path, "main", identity=IDENTITY).cause == "branch-disappeared"
    assert github_delivery._read_inventory(tmp_path, IDENTITY).cause == "malformed-response"


def test_trunk_resolution_failure_does_not_leak_raw_stderr(tmp_path, monkeypatch, capsys) -> None:
    def fail(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="Authorization: bearer github_pat_synthetic")

    monkeypatch.setattr(_common, "run_gh", fail)
    findings = github_delivery._branch_findings(tmp_path, IDENTITY)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "github_pat_synthetic" not in captured.out
    assert findings[0][1].cause == "trunk-unresolved"
