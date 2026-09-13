"""Focused tests for the read-only GitHub delivery settings report."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
import github_delivery

SCRIPT = Path(github_delivery.__file__)


def _fake_gh(tmp_path: Path, monkeypatch, response: str = "{}", fail: bool = False) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$GH_CALLS_LOG\"\n"
        "if [ \"$GH_FAIL\" = 1 ]; then printf '%s\\n' \"${GH_FAIL_TEXT:-fake read failed}\" >&2; exit 1; fi\n"
        "if [ \"$*\" = 'api --method GET --paginate --slurp repos/{owner}/{repo}/branches?per_page=100' ]; then printf '[[]]'; exit 0; fi\n"
        "if [ \"$*\" != 'repo view --json deleteBranchOnMerge,mergeCommitAllowed' ]; then\n"
        "  echo 'write or unexpected argv rejected' >&2; exit 9\n"
        "fi\n"
        "printf '%s' \"$GH_RESPONSE\"\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    log = tmp_path / "gh-argv.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("GH_CALLS_LOG", str(log))
    monkeypatch.setenv("GH_RESPONSE", response)
    monkeypatch.setenv("GH_FAIL", "1" if fail else "0")
    return log


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    (repo / ".git").mkdir()
    (repo / ".specify/extensions/git").mkdir(parents=True)
    (repo / ".specify/extensions/git/git-config.yml").write_text("trunk: main\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, text=True, capture_output=True)


def test_true_settings_are_reported_but_scope_stays_unverified(tmp_path: Path, monkeypatch) -> None:
    log = _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "deleteBranchOnMerge: compatible (observed true)" in result.stdout
    assert "mergeCommitAllowed: compatible (observed true)" in result.stdout
    assert "force-push protection [main (trunk)]: unverified" in result.stdout
    assert "Overall: unverified" in result.stdout
    assert "classic protection" in result.stdout
    assert "T001" not in result.stdout
    assert log.read_text(encoding="utf-8").splitlines() == [
        "repo view --json deleteBranchOnMerge,mergeCommitAllowed",
        "api --method GET --paginate --slurp repos/{owner}/{repo}/branches?per_page=100",
    ]


def test_false_setting_has_configuration_remediation(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": False, "mergeCommitAllowed": False}))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "deleteBranchOnMerge: incompatible" in result.stdout
    assert "Automatically delete head branches" in result.stdout
    assert "mergeCommitAllowed: incompatible" in result.stdout
    assert "Allow merge commits" in result.stdout
    assert "cause=conflicting-configuration" in result.stdout


def test_missing_field_is_unverified_instead_of_false(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True}))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "deleteBranchOnMerge: compatible" in result.stdout
    assert "mergeCommitAllowed: unverified" in result.stdout
    assert "cause=missing-field" in result.stdout
    assert "incompatible" not in result.stdout


def test_failed_read_keeps_both_settings_unverified(tmp_path: Path, monkeypatch) -> None:
    log = _fake_gh(tmp_path, monkeypatch, fail=True)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("unverified") >= 4
    assert "cause=read-failure" in result.stdout
    assert "fake read failed" in result.stdout
    assert log.read_text(encoding="utf-8").splitlines() == [
        "repo view --json deleteBranchOnMerge,mergeCommitAllowed",
        "api --method GET --paginate --slurp repos/{owner}/{repo}/branches?per_page=100",
    ]


def test_absent_gh_is_capability_unavailable_without_a_call(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    log = tmp_path / "calls.log"
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setenv("GH_CALLS_LOG", str(log))
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "capability-unavailable" in result.stdout
    assert "github-cli-unavailable" in result.stdout
    assert "GitHub CLI" in result.stdout
    assert not log.exists()


def test_malformed_response_is_unverified(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, "[]")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("cause=malformed-response") == 2
    assert "unverified" in result.stdout


def test_helper_rejects_mutation_flags_without_invoking_gh(tmp_path: Path, monkeypatch) -> None:
    log = _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
    result = subprocess.run([sys.executable, str(SCRIPT), "--fix"], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 2
    assert "usage: github_delivery.py" in result.stderr
    assert log.read_text(encoding="utf-8") == ""


def test_report_does_not_modify_consumer_files(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / ".gitignore"
    marker.write_text("consumer state\n", encoding="utf-8")
    _fake_gh(tmp_path, monkeypatch, json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}))
    assert _run(tmp_path).returncode == 1
    assert marker.read_text(encoding="utf-8") == "consumer state\n"


def test_plan_detection_does_not_infer_from_permission_wording() -> None:
    response = SimpleNamespace(stderr="requires organization permission from enterprise administrators", stdout="")
    assert github_delivery._failure_cause(response) == "insufficient-permissions"
    assert github_delivery._failure_cause(SimpleNamespace(stderr="Protection temporarily unavailable", stdout="")) == "read-failure"
    assert github_delivery._failure_cause(SimpleNamespace(stderr="Feature unavailable due to permissions", stdout="")) == "insufficient-permissions"
    assert github_delivery._failure_cause(SimpleNamespace(stderr="permission lookup temporarily unavailable", stdout="")) == "read-failure"


def test_read_failure_can_be_resolved_by_a_fresh_successful_retry(tmp_path: Path, monkeypatch) -> None:
    responses = iter((SimpleNamespace(returncode=1, stdout="", stderr="HTTP 403: Forbidden"), SimpleNamespace(returncode=0, stdout='[[{"name":"main"}]]', stderr="")))
    monkeypatch.setattr(github_delivery, "run_gh", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    assert github_delivery._read_inventory(tmp_path).cause == "ambiguous-read"
    assert github_delivery._read_inventory(tmp_path).complete


@pytest.mark.parametrize(
    ("value", "secret"),
    [( '{"token":"opaque-json-token"}', "opaque-json-token"), ("Authorization: Basic basic-secret", "basic-secret"), ("api_key=api-secret", "api-secret")],
)
def test_safe_detail_redacts_each_secret_shape(value: str, secret: str) -> None:
    assert secret not in github_delivery._safe_detail(value)


def test_hostile_failure_is_sanitized_in_real_helper_output(tmp_path: Path, monkeypatch) -> None:
    _fake_gh(tmp_path, monkeypatch, fail=True)
    monkeypatch.setenv("GH_FAIL_TEXT", 'Authorization: Basic shell-secret {"token":"json-secret"}\x1b[31m')
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "shell-secret" not in result.stdout + result.stderr
    assert "json-secret" not in result.stdout + result.stderr
    assert "\x1b" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("endpoint", "message", "cause", "state"),
    [
        ("settings", "HTTP 403: endpoint unavailable on your current plan", "plan-limitation", github_delivery.CAPABILITY_UNAVAILABLE),
        ("inventory", "HTTP 403: Forbidden", "ambiguous-read", github_delivery.UNVERIFIED),
        ("rules", "HTTP 429: Too Many Requests", "rate-limited", github_delivery.UNVERIFIED),
        ("classic", "HTTP 403: permission denied", "insufficient-permissions", github_delivery.UNVERIFIED),
        ("detail", "HTTP 401: Bad credentials", "authentication-failure", github_delivery.UNVERIFIED),
    ],
)
def test_diagnose_and_render_preserve_endpoint_causes(tmp_path: Path, monkeypatch, endpoint: str, message: str, cause: str, state: str) -> None:
    (tmp_path / ".git").mkdir()
    active = json.dumps([[{"type": "non_fast_forward", "ruleset_source_type": "Organization", "ruleset_source": "acme", "ruleset_id": 7}]])
    calls: list[tuple[str, ...]] = []

    def fake_gh(*args: str, cwd=None):
        calls.append(args)
        path = args[-1]
        if args[0] == "repo" and args[:3] != ("repo", "view", "--json"):
            raise AssertionError(args)
        if args[0] == "api" and args[1:3] != ("--method", "GET"):
            raise AssertionError(args)
        failed = ((endpoint == "settings" and args[0] == "repo") or (endpoint == "inventory" and "branches?" in path) or (endpoint == "rules" and "/rules/branches/" in path) or (endpoint == "classic" and "/protection" in path) or (endpoint == "detail" and "/rulesets/" in path))
        if failed:
            return SimpleNamespace(returncode=1, stdout=json.dumps({"message": message}), stderr=message)
        if args[0] == "repo":
            return SimpleNamespace(returncode=0, stdout=json.dumps({"deleteBranchOnMerge": True, "mergeCommitAllowed": True}), stderr="")
        if "branches?" in path:
            return SimpleNamespace(returncode=0, stdout=json.dumps([[{"name": "main"}]]), stderr="")
        if "/rules/branches/" in path:
            return SimpleNamespace(returncode=0, stdout=active if endpoint == "detail" else "[[]]", stderr="")
        if "/protection" in path:
            return SimpleNamespace(returncode=1, stdout=json.dumps({"message": "Branch not protected"}), stderr="HTTP 404")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"id": 7, "source_type": "Organization", "source": "acme", "enforcement": "active", "bypass_actors": []}), stderr="")

    monkeypatch.setattr(github_delivery, "run_gh", fake_gh)
    monkeypatch.setattr(github_delivery, "delivery_base", lambda _root: "main")
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    settings, findings = github_delivery.diagnose(tmp_path)
    report = github_delivery.render(settings, findings)
    assert github_delivery.render(*github_delivery.diagnose(tmp_path)) == report
    assert f"cause={cause}" in report
    assert any(result.state == state and result.cause == cause for result in (*settings.values(), *(result for _, result in findings)))
    assert all(call[0] == "repo" or call[1:3] == ("--method", "GET") for call in calls)


def test_diagnose_sanitizes_error_text_in_rendered_report(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / ".git").mkdir()
    def fail(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout='{"message":"token=json-secret"}', stderr="Authorization: Basic shell-secret")
    monkeypatch.setattr(github_delivery, "run_gh", fail)
    monkeypatch.setattr(github_delivery, "delivery_base", lambda _root: "main")
    monkeypatch.setattr(github_delivery.shutil, "which", lambda _name: "/bin/gh")
    settings, findings = github_delivery.diagnose(tmp_path)
    report = github_delivery.render(settings, findings)
    captured = capsys.readouterr()
    assert "json-secret" not in report + captured.out + captured.err
    assert "shell-secret" not in report + captured.out + captured.err


def test_doctor_keeps_github_category_report_only_on_plain_and_fix_paths() -> None:
    doctor = Path(__file__).parents[1] / "commands" / "doctor.md"
    text = doctor.read_text(encoding="utf-8").replace("\n", " ")
    assert "including under `--fix`; never pass `--fix` to this helper" in text
    assert "Categories 1 and 6 stay report-only" in text
