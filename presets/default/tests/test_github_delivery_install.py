"""Installed-consumer coverage for the native GitHub delivery diagnosis."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import install_fake_delivery_gh

PRESET_ROOT = Path(__file__).parents[1]
PYTHON = sys.executable


def _environment(tmp_path: Path, fake_bin: Path, calls: Path, case: str) -> dict[str, str]:
    env = os.environ.copy()
    isolated = tmp_path / "consumer-state"
    env.update({
        "HOME": os.fspath(isolated / "home"),
        "XDG_CONFIG_HOME": os.fspath(isolated / "config"),
        "XDG_CACHE_HOME": os.fspath(isolated / "cache"),
        "XDG_DATA_HOME": os.fspath(isolated / "data"),
        "GH_CONFIG_DIR": os.fspath(isolated / "gh"),
        "GH_CALLS_LOG": os.fspath(calls),
        "GH_DELIVERY_CASE": case,
        "GH_DELIVERY_HOST": "ghe.example" if case == "enterprise" else "github.com",
        "GH_DELIVERY_REPO": "acme/demo",
        "PATH": os.pathsep.join((os.fspath(fake_bin), env.get("PATH", ""))),
        "PYTHONPATH": os.fspath(tmp_path / "empty-pythonpath"),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    })
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(name, None)
    return env


def _run_specify(consumer: Path, env: dict[str, str], *args: str) -> None:
    executable = shutil.which("specify", path=env["PATH"])
    assert executable, "the CI prerequisite must install the pinned Specify CLI"
    result = subprocess.run([executable, *args], cwd=consumer, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def _install_consumer(tmp_path: Path, case: str) -> tuple[Path, dict[str, str], Path]:
    fake_bin, calls = install_fake_delivery_gh(tmp_path / "fake-gh")
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    env = _environment(tmp_path, fake_bin, calls, case)
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main"], cwd=consumer, env=env, check=True)
    _run_specify(consumer, env, "init", "--here", "--force", "--ignore-agent-tools", "--integration", "codex")
    _run_specify(consumer, env, "preset", "add", "--dev", os.fspath(PRESET_ROOT))
    calls.write_text("", encoding="utf-8")
    return consumer, env, calls


def _git_state(consumer: Path, env: dict[str, str]) -> tuple[bytes, bytes | None, str, str]:
    config = (consumer / ".git/config").read_bytes()
    index = (consumer / ".git/index").read_bytes() if (consumer / ".git/index").exists() else None
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=consumer, env=env,
        text=True, capture_output=True, check=True,
    ).stdout
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=consumer, env=env,
        text=True, capture_output=True, check=True,
    ).stdout
    return config, index, status, branch


def _consumer_config(consumer: Path) -> tuple[tuple[str, bytes], ...]:
    paths = sorted(
        path for path in (consumer / ".specify").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    return tuple((os.fspath(path.relative_to(consumer)), path.read_bytes()) for path in paths)


@pytest.mark.parametrize(
    ("case", "returncode", "state_line", "evidence"),
    [
        ("compatible", 0, "Overall: compatible", "future branches are not certified"),
        ("cleanup-blocked", 1, "cleanup [001-feature (feature)]: incompatible", "allow_deletions.enabled=false"),
        ("permission-denied", 1, "cause=insufficient-permissions", "repository or organization owner"),
        ("failed-read", 1, "cause=read-failure", "Retry the repository settings read"),
        ("enterprise", 0, "Overall: compatible", "future branches are not certified"),
        ("queue-squash", 1, "merge commits [main (trunk)]: incompatible", "classic branch protection merge queue"),
        ("queue-rebase", 1, "merge commits [main (trunk)]: incompatible", "classic branch protection merge queue"),
        ("queue-merge", 1, "merge commits [main (trunk)]: unverified", "queue interaction"),
        ("queue-hidden", 1, "merge commits [main (trunk)]: unverified", "hidden-fields"),
        ("queue-malformed", 1, "merge commits [main (trunk)]: unverified", "malformed-response"),
        ("queue-partial", 1, "merge commits [main (trunk)]: unverified", "queue partial response"),
        ("queue-denied", 1, "merge commits [main (trunk)]: unverified", "repository or organization owner"),
        ("queue-failed", 1, "merge commits [main (trunk)]: unverified", "classic merge queue read"),
    ],
)
def test_installed_diagnosis_is_independent_and_read_only(
    tmp_path: Path, case: str, returncode: int, state_line: str, evidence: str
) -> None:
    consumer, env, calls = _install_consumer(tmp_path, case)
    installed = consumer / ".specify/presets/default"
    scripts = installed / "scripts/python"
    helper = scripts / "github_delivery.py"
    assert helper.is_file() and (scripts / "github_delivery_rules.py").is_file()
    manifest = (installed / "preset.yml").read_text(encoding="utf-8")
    assert 'name: "github-delivery"' in manifest and 'name: "github-delivery-rules"' in manifest
    generated_doctor = consumer / ".agents/skills/speckit-doctor/SKILL.md"
    doctor = generated_doctor.read_text(encoding="utf-8")
    doctor = " ".join(doctor.split())
    assert "python3 .specify/presets/default/scripts/python/github_delivery.py" in doctor
    assert "never pass `--fix` to this helper" in doctor
    assert "Categories 1 and 6 stay report-only" in doctor
    readme = (installed / "README.md").read_text(encoding="utf-8")
    readme = " ".join(readme.split())
    assert "current remote snapshot" in readme and "native action" in readme
    assert "synthetic generated-asset and installed-runtime evidence" in readme
    assert "reliability entry 23" in readme

    consumer_path = consumer.resolve()
    assert installed.resolve().is_relative_to(consumer_path)
    assert helper.resolve().is_relative_to(installed.resolve())
    import_probe = subprocess.run(
        [
            PYTHON, "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import github_delivery, github_delivery_rules; "
            "print(github_delivery.__file__); print(github_delivery_rules.__file__)",
            os.fspath(scripts),
        ],
        cwd=consumer, env=env, text=True, capture_output=True, check=True,
    )
    imported = import_probe.stdout.splitlines()
    assert len(imported) == 2 and all(Path(line).resolve().is_relative_to(consumer_path) for line in imported)
    assert all(os.fspath(PRESET_ROOT) not in line for line in imported)
    before = (_git_state(consumer, env), _consumer_config(consumer))
    result = subprocess.run([PYTHON, os.fspath(helper)], cwd=consumer, env=env, text=True, capture_output=True)
    assert result.returncode == returncode, result.stdout + result.stderr
    assert state_line in result.stdout and evidence in result.stdout
    assert os.fspath(PRESET_ROOT) not in env["PYTHONPATH"]
    assert (_git_state(consumer, env), _consumer_config(consumer)) == before

    observed_calls = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    assert observed_calls
    expected_host = env["GH_DELIVERY_HOST"]
    assert all(
        call[:1] == ["repo"]
        or (call[1:2] == ["graphql"] and call[2:4] == ["--hostname", expected_host] and call[4:6] == ["--method", "POST"])
        or (call[1:3] == ["--hostname", expected_host] and call[3:5] == ["--method", "GET"])
        for call in observed_calls
    )
