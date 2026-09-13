"""Pure tests for shared-branch selection and active-rule evaluation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import github_delivery
import github_delivery_rules as rules
import _common


def _active(kind: str = "non_fast_forward", ident: int = 7) -> dict[str, object]:
    return {
        "type": kind,
        "ruleset_source_type": "Organization",
        "ruleset_source": "acme",
        "ruleset_id": ident,
    }


def test_active_rules_parse_pages_and_dedupe_rule_identity() -> None:
    payload = [[_active(), _active(), _active("required_signatures")]]
    parsed = rules.parse_active_rules(payload)
    assert parsed is not None
    assert [(item.type, item.identity) for item in parsed] == [
        ("non_fast_forward", ("Organization", "acme", 7)),
        ("required_signatures", ("Organization", "acme", 7)),
    ]


def test_non_fast_forward_keeps_source_while_classic_layer_is_pending() -> None:
    parsed = rules.parse_active_rules([[_active()]])
    assert parsed is not None
    result = rules.evaluate_force_push("main", rules.RuleRead(True, parsed))
    assert result.state == rules.UNVERIFIED
    assert "Organization acme ruleset 7" in result.evidence
    assert "classic protection" in result.evidence


def test_report_reads_paginated_inventory_and_effective_rules_as_gets(tmp_path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    calls: list[tuple[str, ...]] = []
    active = json.dumps([[_active()], [_active("required_signatures", 8)]])

    def fake_gh(*args: str, cwd=None):
        calls.append(args)
        if args[:3] == ("repo", "view", "--json"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}), stderr="")
        if args[-1] == "repos/{owner}/{repo}/branches?per_page=100":
            return SimpleNamespace(returncode=0, stdout=json.dumps([[{"name": "main"}, {"name": "001-feature"}, {"name": "001-feature"}], [{"name": "001-T001-task"}, {"name": "unrelated"}]]), stderr="")
        if "%24%28touch%20pwned%29" in args[-1]:
            assert "/rules/branches/" in args[-1]
            return SimpleNamespace(returncode=0, stdout=active, stderr="")
        return SimpleNamespace(returncode=0, stdout=active if any(marker in args[-1] for marker in ("/main?", "/001-T001-task?")) else "[[]]", stderr="")

    monkeypatch.setattr(github_delivery, "run_gh", fake_gh)
    monkeypatch.setattr(github_delivery, "delivery_base", lambda _root: "main")
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    _settings, findings = github_delivery.diagnose(tmp_path)
    github_delivery._read_branch_rules(tmp_path, "001-$(touch pwned)")
    assert [(name, result.state) for name, result in findings if name.startswith("force-push")] == [("force-push protection [main (trunk)]", rules.UNVERIFIED), ("force-push protection [001-feature (feature)]", rules.UNVERIFIED), ("force-push protection [001-T001-task (task)]", rules.UNVERIFIED)]
    assert github_delivery._read_branch_rules(tmp_path, "001-feature").complete
    assert rules.evaluate_force_push("001-feature", github_delivery._read_branch_rules(tmp_path, "001-feature")).cause == "classic-protection-unobserved"
    assert "cause=bypass-coverage-unobserved" in github_delivery.render(_settings, findings)
    assert all(call[1:3] == ("--method", "GET") for call in calls[1:])


def test_transport_failures_keep_distinct_causes_and_malformed_pages_unknown(tmp_path, monkeypatch) -> None:
    responses = iter((
        SimpleNamespace(returncode=1, stdout="", stderr="transport failed on page 2"),
        SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404: Not Found"),
        SimpleNamespace(returncode=1, stdout="", stderr="branch not found"),
        SimpleNamespace(returncode=0, stdout='[[{"name":"main"}], {}]', stderr=""),
    ))
    monkeypatch.setattr(github_delivery, "run_gh", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    assert github_delivery._read_inventory(tmp_path).cause == "partial-inventory"
    assert github_delivery._read_branch_rules(tmp_path, "main").cause == "read-failure"
    assert github_delivery._read_branch_rules(tmp_path, "main").cause == "branch-disappeared"
    assert github_delivery._read_inventory(tmp_path).cause == "malformed-response"


def test_trunk_resolution_failure_does_not_leak_raw_stderr(tmp_path, monkeypatch, capsys) -> None:
    def fail(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="Authorization: bearer github_pat_synthetic")

    monkeypatch.setattr(_common, "run_gh", fail)
    findings = github_delivery._branch_findings(tmp_path)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "github_pat_synthetic" not in captured.out
    assert findings[0][1].cause == "trunk-unresolved"
