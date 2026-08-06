"""Shared test helpers: fake executables, isolation, and lock/consumer fixtures."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from spec_kit_code_review import env_files


SUPPORT_DIRECTORY = Path(__file__).resolve().parent
FIXTURES_DIRECTORY = SUPPORT_DIRECTORY.parent / "fixtures"
CONSUMER_FIXTURE = FIXTURES_DIRECTORY / "consumer"
ADVERSARIAL_FIXTURE = FIXTURES_DIRECTORY / "adversarial"

DEFAULT_OCR_VERSION = "ocr version v1.8.3"


def isolate_operator_global_env(case) -> None:
    """Point the operator-global env file at a nonexistent path for this test.

    Without this, a developer's real ``${XDG_CONFIG_HOME}/tserdeiro/spec-kit/env``
    leaks into every test that loads the environment snapshot.
    """

    absent = Path(tempfile.gettempdir()) / "spec-kit-code-review-tests-no-global-env"
    env_files.set_operator_env_override(absent)
    case.addCleanup(env_files.set_operator_env_override, None)


def _install_fake(source: Path, directory: Path, name: str, state: dict[str, Any] | None, state_env: str) -> tuple[str, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / name
    shutil.copyfile(source, executable)
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    environment: dict[str, str] = {}
    if state is not None:
        state_path = directory / f"{name}-state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        environment[state_env] = str(state_path)
    return str(executable), environment


def install_fake_gh(directory: Path, state: dict[str, Any] | None = None) -> tuple[str, dict[str, str]]:
    """Materialize the fake ``gh`` and the environment that drives it."""

    return _install_fake(SUPPORT_DIRECTORY / "fake_gh.py", directory, "gh", state, "SPECKIT_CODE_REVIEW_FAKE_GH_STATE")


def install_fake_ocr(directory: Path, state: dict[str, Any] | None = None) -> tuple[str, dict[str, str]]:
    """Materialize the fake ``ocr`` and the state file it reads.

    The state is written *beside* the executable as well as exported, because the
    extension runs the engine in a minimal, enumerated environment that a test
    fixture's own variable is deliberately not part of.
    """

    executable, environment = _install_fake(
        SUPPORT_DIRECTORY / "fake_ocr.py", directory, "ocr", state, "SPECKIT_CODE_REVIEW_FAKE_OCR_STATE"
    )
    if state is not None:
        (Path(executable).parent / "ocr-state.json").write_text(json.dumps(state), encoding="utf-8")
    return executable, environment


FAKE_OCR_SOURCE = SUPPORT_DIRECTORY / "fake_ocr.py"


def install_fake_ocr_at(executable: Path, state: dict[str, Any] | None = None) -> Path:
    """The fake engine at an arbitrary path -- the canonical one, in practice.

    The canonical binary is named ``opencodereview``, not ``ocr``, so the
    fallback cannot be exercised through ``install_fake_ocr``'s fixed name.
    """

    executable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FAKE_OCR_SOURCE, executable)
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if state is not None:
        (executable.parent / "ocr-state.json").write_text(json.dumps(state), encoding="utf-8")
    return executable


def install_fake_npm(directory: Path, state: dict[str, Any] | None = None) -> tuple[str, dict[str, str]]:
    """Materialize the fake ``npm``, so no test ever reaches the network.

    Called with ``None`` it installs a *blocker*: an ``npm`` that fails loudly.
    A directory on ``PATH`` without one would let a real ``npm install`` run
    from a test, which is the single thing this suite must never do.
    """

    if state is None:
        directory.mkdir(parents=True, exist_ok=True)
        blocker = directory / "npm"
        blocker.write_text(
            "#!/usr/bin/env sh\n"
            'echo "the test suite never runs a real npm install" >&2\n'
            "exit 127\n",
            encoding="utf-8",
        )
        blocker.chmod(blocker.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return str(blocker), {}

    from spec_kit_code_review.paths import platform_package

    state = {"platform_package": platform_package(), **state}
    executable, environment = _install_fake(
        SUPPORT_DIRECTORY / "fake_npm.py", directory, "npm", state, "SPECKIT_CODE_REVIEW_FAKE_NPM_STATE"
    )
    (Path(executable).parent / "npm-state.json").write_text(json.dumps(state), encoding="utf-8")
    return executable, environment


def install_payload_executable(directory: Path, name: str, marker: Path) -> str:
    """A candidate-shipped "tool" that records the fact that it ran.

    Used to prove the guard behaviourally: if the marker exists after a command,
    an executable from the tree under review was executed, whatever the exit
    code said.
    """

    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / name
    executable.write_text(
        "#!/usr/bin/env sh\n"
        f': > "{marker}"\n'
        'echo "ocr version v1.8.3"\n',
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(executable)


def pull_request_payload(
    *,
    number: int,
    repository: str,
    base_branch: str,
    base_commit: str,
    head_commit: str,
    cross_repository: bool = False,
    head_repository: str | None = None,
    state: str = "OPEN",
    title: str = "A candidate",
    body: str = "",
    author: str = "contributor",
    labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The exact ``gh pr view --json`` shape this extension asks for."""

    owner, _, name = repository.partition("/")
    head_owner, _, head_name = (head_repository or repository).partition("/")
    return {
        "number": number,
        "baseRefName": base_branch,
        "baseRefOid": base_commit,
        "headRefOid": head_commit,
        "headRepositoryOwner": {"login": head_owner},
        "headRepository": {"name": head_name},
        "isCrossRepository": cross_repository,
        "state": state,
        "url": f"https://github.com/{owner}/{name}/pull/{number}",
        "title": title,
        "body": body,
        "author": {"login": author},
        "labels": [{"name": name} for name in labels],
    }


def write_lock(
    path: Path,
    *,
    version_string: str | None = DEFAULT_OCR_VERSION,
    platform_key: str | None = None,
    binary_digest: str | None = None,
    release_tag: str = "v1.8.3",
    npm_package: str = "@alibaba-group/open-code-review",
) -> Path:
    """Write a ``versions.lock.yml`` carrying this extension's nested OCR pin."""

    lines = [
        'schema_version: "1.0"',
        "",
        "extensions:",
        "  code-review:",
        "    id: code-review",
        "    version: 0.1.0",
        "    provenance: first-party-monorepo",
        "    path: packages/spec-kit-code-review",
        "    external_tools:",
        "      open_code_review:",
        "        source: https://github.com/alibaba/open-code-review",
        "        license: Apache-2.0",
        f"        release_tag: {release_tag}",
    ]
    if version_string is not None:
        lines.append(f'        version_string: "{version_string}"')
    lines.append(f'        npm_package: "{npm_package}"')
    if platform_key and binary_digest:
        lines.append("        binaries:")
        lines.append(f'          {platform_key}: "{binary_digest}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def copy_consumer_fixture(destination: Path | None = None) -> tuple[tempfile.TemporaryDirectory[str] | None, Path]:
    """Copy the synthetic consumer fixture into a temporary directory."""

    if destination is not None:
        shutil.copytree(CONSUMER_FIXTURE, destination, dirs_exist_ok=True)
        return None, destination
    temporary = tempfile.TemporaryDirectory()
    target = Path(temporary.name) / "consumer"
    shutil.copytree(CONSUMER_FIXTURE, target)
    return temporary, target


def copy_adversarial_fixture(destination: Path) -> Path:
    """Copy the hostile candidate fixture into ``destination``."""

    shutil.copytree(ADVERSARIAL_FIXTURE, destination, dirs_exist_ok=True)
    return destination


def clean_environment(**overrides: str) -> dict[str, str]:
    """A process environment with every ``SPECKIT_CODE_REVIEW_`` key removed."""

    environment = {key: value for key, value in os.environ.items() if not key.startswith("SPECKIT_CODE_REVIEW_")}
    environment.update(overrides)
    return environment


def sealed_path(fake_bin) -> str:
    """A PATH of exactly two directories: the test's fakes, and symlinks to
    the real runtime tools the code under test needs (git, uv, specify,
    python3). System directories never enter it, so an "absent tool" really
    is absent on any machine — including CI runners, where `gh` lives in
    `/usr/bin` and would otherwise leak into the sealed environment.
    """

    import shutil as _shutil
    from pathlib import Path as _Path

    fake_bin = _Path(fake_bin)
    runtime = fake_bin.parent / "runtime-bin"
    runtime.mkdir(parents=True, exist_ok=True)
    for tool in ("git", "sh", "bash", "uv", "specify", "python3"):
        located = _shutil.which(tool)
        if located:
            link = runtime / tool
            if not link.exists():
                link.symlink_to(_Path(located).resolve())
    return f"{fake_bin}:{runtime}"
