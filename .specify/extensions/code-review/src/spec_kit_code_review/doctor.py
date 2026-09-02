"""Read-only preflight, plus the bounded local repairs of ``--fix``."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .config import (
    LOCAL_CONFIG_FILENAME,
    LOCAL_CONFIG_TEMPLATE,
    ROOT_CONFIG_FILENAME,
    RULE_RELATIVE_PATH,
    ResolvedConfig,
    dump_yaml_subset,
    load_config,
    local_config_path,
    shared_config_document,
    shared_config_path,
)
from .candidate import resolve_repository
from .env_files import ENV_PREFIX, REPO_ENV_FILENAME, EnvSnapshot
from .errors import (
    EXIT_AUTHENTICATION,
    EXIT_CONFIGURATION,
    EXIT_PREREQUISITE,
    EXIT_SUCCESS,
    AppError,
    Diagnostic,
)
from .engine import (
    DEFAULT_OCR_TAG,
    canonical_executable,
    install_engine,
    ocr_install_hint,
    resolve_engine,
)
from .evidence import enforce_permissions, permission_diagnostics, resolve_evidence_root
from .git import MINIMUM_GIT_VERSION, Git, open_git
from .github import open_github
from .gitignore import ensure_entries, missing_entries
from .paths import (
    OCR_NPM_PACKAGE,
    OCR_TOOL_NAME,
    ocr_install_command,
    ocr_uninstall_command,
    resolved_roots,
    tool_root,
)
from .lockfile import (
    SELF_PIN_FILENAME,
    extension_pin,
    load_lock,
    lock_path,
    platform_key,
    first_line,
    self_external_tool_pin,
    version_matches_pin,
)
from .process import run_command, sha256_file


CHECK_GROUPS: tuple[str, ...] = ("runtime", "speckit", "git", "ocr", "gh", "config", "rules", "evidence", "hooks")

def _speckit_requirement() -> tuple[tuple[str, ...], tuple[int, int] | None]:
    """The supported Spec Kit range, read from this extension's own manifest.

    One source of truth: `extension.yml`'s `requires.speckit_version` — the
    same line the installer enforces. The doctor gates on the floor's
    major.minor; an unreadable manifest disables the check with a warning
    instead of ever failing hard.
    """

    manifest = Path(__file__).resolve().parents[2] / "extension.yml"
    try:
        match = re.search(r'speckit_version:\s*"([^"]+)"', manifest.read_text(encoding="utf-8"))
    except OSError:
        match = None
    if match is None:
        return ((), None)
    range_parts = tuple(part.strip() for part in match.group(1).split(","))
    floor = next((part[2:] for part in range_parts if part.startswith(">=")), None)
    if floor is None:
        return (range_parts, None)
    numbers = floor.split(".")
    try:
        return (range_parts, (int(numbers[0]), int(numbers[1])))
    except (IndexError, ValueError):
        return (range_parts, None)


SPECKIT_VERSION_RANGE, SPECKIT_SUPPORTED_MAJOR_MINOR = _speckit_requirement()
MANAGED_LIFECYCLE_EVENT = "after_implement"
MANAGED_LIFECYCLE_COMMAND = "speckit.code-review"
REGISTRY_RELATIVE_PATH = Path(".specify/extensions.yml")

# The default rule set written by `--fix` when the repository has none.
RULE_TEMPLATE = """\
{
  "rules": [
    {
      "path": "**/*.py",
      "rule": "Review Python changes for correctness, security, and test coverage. Cite the exact lines that support each finding.",
      "merge_system_rule": true
    }
  ]
}
"""

# Ranked most severe first; `doctor` reports everything it saw and exits with
# the most severe code among the errors it found.
_CODE_PRIORITY: tuple[int, ...] = (EXIT_PREREQUISITE, EXIT_CONFIGURATION, EXIT_AUTHENTICATION)


@dataclass
class DoctorOptions:
    """Everything ``doctor`` was asked to do.

    ``root`` is always the repository **toplevel**, and ``git`` is the guarded
    client the session opened: both come from the CLI's single session choke
    point, so ``--fix`` can never write beside the caller's working directory
    and no executable is ever resolved from the tree under review.
    """

    root: Path
    environment: EnvSnapshot
    git: Git | None = None
    config_flag: str | None = None
    fix: bool = False
    timeout: int = 300


@dataclass
class GroupResult:
    """One check group's diagnostics and the exit code it justifies."""

    group: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    code: int = EXIT_SUCCESS

    def error(self, code: int, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)
        self.code = _worse(self.code, code)

    def warn(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def info(self, code: str, message: str, path: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(code, message, path, severity="info"))


@dataclass
class FixOutcome:
    """What ``--fix`` repaired, and what it has to say about what it could not.

    The diagnostics travel to the group they belong to instead of being printed
    on their own: a failed engine install is part of the ``ocr`` verdict, not a
    separate one.
    """

    applied: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class DoctorReport:
    """The full result of a ``doctor`` run."""

    groups: list[GroupResult] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        result: list[Diagnostic] = []
        for group in self.groups:
            result.extend(group.diagnostics)
        return result

    @property
    def code(self) -> int:
        code = EXIT_SUCCESS
        for group in self.groups:
            code = _worse(code, group.code)
        return code

    def as_dict(self) -> dict[str, Any]:
        return {
            "checks": {group.group: ("fail" if group.code else "pass") for group in self.groups},
            "fixes": list(self.fixes),
        }


def run_doctor(options: DoctorOptions) -> DoctorReport:
    """Run every check group without writing anything, unless ``--fix``."""

    report = DoctorReport()
    fixes = _apply_fixes(options) if options.fix else FixOutcome()
    report.fixes.extend(fixes.applied)
    config, config_error = _load_config(options)

    report.groups.append(_check_runtime(options))
    report.groups.append(_check_speckit(options))
    report.groups.append(_check_git(options))
    report.groups.append(_check_ocr(options, config, fixes.diagnostics))
    report.groups.append(_check_gh(options))
    report.groups.append(_check_config(options, config, config_error))
    report.groups.append(_check_rules(options))
    report.groups.append(_check_evidence(options, config))
    report.groups.append(_check_hooks(options))
    return report


# -- groups -----------------------------------------------------------------


def _check_runtime(options: DoctorOptions) -> GroupResult:
    result = GroupResult("runtime")
    if sys.version_info < (3, 11):
        result.error(
            EXIT_PREREQUISITE,
            Diagnostic("python_version", f"Python >= 3.11 is required; found {sys.version.split()[0]}"),
        )
    else:
        result.info("python", f"Python {sys.version.split()[0]}")
    if shutil.which("uv") is None:
        result.error(EXIT_PREREQUISITE, Diagnostic("uv_missing", "install uv before using this extension"))
    else:
        result.info("uv", "uv found on PATH")
    result.info("extension_version", f"spec-kit-code-review {__version__}")
    return result


@dataclass(frozen=True)
class SpeckitVersion:
    """The observed Spec Kit version."""

    text: str | None
    supported: bool | None
    diagnostic: Diagnostic


def speckit_version_diagnostic(*, timeout: int = 300) -> SpeckitVersion:
    """Read the installed Spec Kit version, read-only, without ever failing hard."""

    executable = shutil.which("specify")
    if executable is None:
        return SpeckitVersion(
            None,
            None,
            Diagnostic(
                "speckit_cli_missing",
                f"specify was not found on PATH; this extension requires {' '.join(SPECKIT_VERSION_RANGE)}",
                severity="warning",
            ),
        )
    invocation = run_command([executable, "version"], timeout=timeout)
    match = re.search(r"CLI Version\s+(\d+)\.(\d+)\.(\d+)", invocation.stdout or "")
    if not match:
        return SpeckitVersion(
            None,
            None,
            Diagnostic(
                "speckit_version_unparseable",
                "could not read the Spec Kit version from `specify version`",
                severity="warning",
            ),
        )
    observed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    text = ".".join(str(part) for part in observed)
    if SPECKIT_SUPPORTED_MAJOR_MINOR is None:
        return SpeckitVersion(
            text,
            None,
            Diagnostic(
                "speckit_range_unreadable",
                "could not read requires.speckit_version from extension.yml; version check skipped",
                severity="warning",
            ),
        )
    if observed[:2] != SPECKIT_SUPPORTED_MAJOR_MINOR:
        return SpeckitVersion(
            text,
            False,
            Diagnostic("speckit_version_unsupported", f"Spec Kit {text} is outside {' '.join(SPECKIT_VERSION_RANGE)}"),
        )
    return SpeckitVersion(text, True, Diagnostic("speckit_version", f"Spec Kit {text}", severity="info"))


def _check_speckit(options: DoctorOptions) -> GroupResult:
    result = GroupResult("speckit")
    specify_directory = options.root / ".specify"
    if not specify_directory.is_dir():
        result.error(
            EXIT_PREREQUISITE,
            Diagnostic("speckit_missing", "expected a Spec Kit consumer repository", str(specify_directory)),
        )
        return result
    result.info("speckit", ".specify directory found", str(specify_directory))
    version = speckit_version_diagnostic(timeout=options.timeout)
    if version.supported is False:
        result.error(EXIT_PREREQUISITE, version.diagnostic)
    else:
        result.diagnostics.append(version.diagnostic)
    return result


def _check_git(options: DoctorOptions) -> GroupResult:
    result = GroupResult("git")
    try:
        git = _git(options)
    except AppError as error:
        result.error(error.code, error.diagnostics[0] if error.diagnostics else Diagnostic("git_missing", str(error)))
        return result
    version = git.version()
    minimum = ".".join(str(part) for part in MINIMUM_GIT_VERSION)
    if not version.supported:
        result.error(
            EXIT_PREREQUISITE,
            Diagnostic(
                "git_version_unsupported",
                f"git >= {minimum} is required by the review engine; found {version.text}",
            ),
        )
    else:
        result.info("git_version", f"git {version.text}")
    try:
        toplevel = git.toplevel(options.root)
    except AppError as error:
        result.error(error.code, error.diagnostics[0] if error.diagnostics else Diagnostic("git_root", str(error)))
        return result
    result.info("git_root", str(toplevel), str(toplevel))
    status = git.status_porcelain()
    result.info("git_worktree_state", "clean" if not status.strip() else f"{len(status.splitlines())} pending change(s)")
    return result


def _legacy_paths() -> tuple[tuple[str, Path], ...]:
    """Where this extension used to write, before the namespace amendment."""

    home = Path.home()
    # xdg-allowed: these are deliberately the *pre-amendment* locations, which
    # `paths` no longer knows about; that is the whole point of reporting them.
    state = Path(os.environ.get("XDG_STATE_HOME") or (home / ".local" / "state"))
    config = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))
    return (
        ("evidence", state / "spec-kit-code-review"),
        ("configuration", config / "spec-kit-code-review"),
    )


def _check_ocr(
    options: DoctorOptions,
    config: ResolvedConfig | None,
    fix_diagnostics: list[Diagnostic] | None = None,
) -> GroupResult:
    result = GroupResult("ocr")
    forbidden = _forbidden_roots(options)
    pin = external_tool_pin(options.root)
    tag = _engine_tag(pin, config)

    roots = resolved_roots()
    result.info("paths_config_root", roots["config"], roots["config"])
    result.info("paths_data_root", roots["data"], roots["data"])
    result.info("paths_state_root", roots["state"], roots["state"])
    result.info(
        "ocr_canonical_path",
        f"the canonical location for ocr {tag} is {canonical_executable(tag)}",
        str(tool_root(OCR_TOOL_NAME, tag)),
    )
    # The install command, always, resolved: `doctor --fix` runs its argv form,
    # and an operator who prefers to install it by hand needs the same command
    # rather than a derivation of it.
    result.info(
        "ocr_install_command",
        ocr_install_command(tag, package=(pin.npm_package if pin else None) or OCR_NPM_PACKAGE),
    )
    for diagnostic in fix_diagnostics or ():
        if diagnostic.severity == "error":
            result.error(EXIT_PREREQUISITE, diagnostic)
        else:
            result.warn(diagnostic)
    result.info("ocr_uninstall_command", ocr_uninstall_command(tag))
    for label, legacy in _legacy_paths():
        if legacy.exists():
            result.warn(
                Diagnostic(
                    "paths_legacy_directory",
                    f"{legacy} is a pre-2026-08-02 {label} directory of this extension. Nothing reads it any more. "
                    f"Move anything you still want, then remove it with: rm -rf {legacy}",
                    str(legacy),
                    severity="warning",
                )
            )

    override = options.environment.executable_override(f"{ENV_PREFIX}OCR_BIN")
    try:
        executable = resolve_engine(tag=tag, override=override, forbidden_roots=forbidden)
    except AppError as error:
        result.error(error.code, error.diagnostics[0] if error.diagnostics else Diagnostic("ocr_unusable", str(error)))
        return result

    if executable is None:
        result.error(
            EXIT_PREREQUISITE,
            Diagnostic("ocr_missing", ocr_install_hint(tag, pin.npm_package if pin else None)),
        )
        return result
    result.info("ocr_path", str(executable), str(executable))

    version_output = run_command([str(executable), "--version"], timeout=options.timeout)
    observed_version = (version_output.stdout or version_output.stderr or "").strip()
    if not version_output.ok:
        result.error(EXIT_PREREQUISITE, Diagnostic("ocr_version_failed", "`ocr --version` did not succeed", str(executable)))
        return result
    result.info("ocr_version", observed_version or "(empty)")

    if pin is None:
        result.warn(
            Diagnostic(
                "ocr_pin_missing",
                f"no engine pin in {lock_path(options.root)} nor in the extension's own {SELF_PIN_FILENAME}; "
                "the ocr version and digest cannot be verified",
                str(lock_path(options.root)),
                severity="warning",
            )
        )
    else:
        expected_version = pin.version_string
        if expected_version and not version_matches_pin(observed_version, expected_version):
            result.error(
                EXIT_PREREQUISITE,
                Diagnostic(
                    "ocr_version_mismatch",
                    f"`ocr --version` reported {first_line(observed_version)!r}; the lock pins {expected_version!r}",
                    str(executable),
                ),
            )
        elif not expected_version:
            result.warn(Diagnostic("ocr_version_unpinned", "the lock entry has no version_string", severity="warning"))
        key = platform_key()
        expected_digest = pin.binary_digest(key)
        observed_digest = sha256_file(executable)
        if expected_digest is None:
            result.warn(
                Diagnostic(
                    "ocr_digest_platform_unpinned",
                    f"the lock has no binary digest for {key}; the installed ocr cannot be verified on this platform",
                    severity="warning",
                )
            )
        elif observed_digest is None:
            result.warn(
                Diagnostic(
                    "ocr_digest_unreadable",
                    "the resolved ocr is not a readable regular file; its digest cannot be verified",
                    str(executable),
                    severity="warning",
                )
            )
        elif observed_digest != expected_digest:
            result.error(
                EXIT_PREREQUISITE,
                Diagnostic(
                    "ocr_digest_mismatch",
                    f"the installed ocr digest {observed_digest} does not match the {key} digest pinned in the lock",
                    str(executable),
                ),
            )
        else:
            result.info("ocr_digest", f"{key} digest matches the lock")

    for subcommand in (("delegate", "preview"), ("delegate", "rule")):
        invocation = run_command([str(executable), *subcommand, "--help"], timeout=options.timeout)
        if not invocation.ok:
            result.error(
                EXIT_PREREQUISITE,
                Diagnostic(
                    "ocr_subcommand_missing",
                    f"`ocr {' '.join(subcommand)} --help` failed; this ocr does not expose the delegation surface "
                    "this extension uses",
                    str(executable),
                ),
            )
        else:
            result.info("ocr_subcommand", f"ocr {' '.join(subcommand)} is available")

    telemetry = options.environment.values.get("OCR_ENABLE_TELEMETRY") or os.environ.get("OCR_ENABLE_TELEMETRY")
    if telemetry:
        result.info(
            "ocr_telemetry_enabled",
            "OCR_ENABLE_TELEMETRY is set in this environment; this extension never sets it, and never unsets it either",
        )
    return result


def _check_gh(options: DoctorOptions) -> GroupResult:
    result = GroupResult("gh")
    forbidden = _forbidden_roots(options)
    override = options.environment.executable_override(f"{ENV_PREFIX}GH_BIN")
    try:
        client = open_github(override=override, forbidden_roots=forbidden, timeout=options.timeout)
    except AppError as error:
        result.error(error.code, error.diagnostics[0] if error.diagnostics else Diagnostic("gh_unusable", str(error)))
        return result
    if client is None:
        result.warn(
            Diagnostic(
                "gh_missing",
                "gh was not found on PATH; reviewing a pull request and publishing need it, the working-tree review "
                "does not",
                severity="warning",
            )
        )
        return result
    result.info("gh_path", client.executable, client.executable)
    status = client.auth_status()
    if not status.authenticated:
        result.error(
            EXIT_AUTHENTICATION,
            Diagnostic("gh_unauthenticated", "run `gh auth login` yourself; this extension never manages tokens"),
        )
        return result
    result.info("gh_auth", "gh is authenticated")
    if status.scopes:
        result.info("gh_scopes", ", ".join(status.scopes))
        if "repo" not in status.scopes and "public_repo" not in status.scopes:
            result.warn(
                Diagnostic(
                    "gh_scopes_insufficient",
                    "the token has neither the repo nor the public_repo scope; reading a private pull request or "
                    "creating a review will fail",
                    severity="warning",
                )
            )
    login = client.authenticated_user()
    if login:
        result.info("gh_user", login)
    return result


def _check_config(options: DoctorOptions, config: ResolvedConfig | None, config_error: AppError | None) -> GroupResult:
    result = GroupResult("config")
    if config_error is not None:
        result.error(
            config_error.code,
            config_error.diagnostics[0] if config_error.diagnostics else Diagnostic("config_invalid", str(config_error)),
        )
        return result
    assert config is not None  # config_error is None
    for diagnostic in config.diagnostics:
        result.warn(diagnostic)
    if config.shared_path is not None:
        result.info("config_shared", str(config.shared_path), str(config.shared_path))
    result.info("config_sha256", config.sha256)
    result.info("publish_event_ceiling", str(config.get("publish", "event")))

    local_path = local_config_path(options.root)
    if not local_path.is_file():
        result.warn(
            Diagnostic(
                "local_config_missing",
                f"{LOCAL_CONFIG_FILENAME} is absent; run `doctor --fix` to create the template",
                str(local_path),
                severity="warning",
            )
        )
    else:
        result.info("config_local", str(local_path), str(local_path))

    gitignore = options.root / ".gitignore"
    missing = missing_entries(gitignore)
    if missing:
        result.warn(
            Diagnostic(
                "gitignore_entries_missing",
                f"{', '.join(missing)} not listed in .gitignore; run `doctor --fix`",
                str(gitignore),
                severity="warning",
            )
        )

    for diagnostic in options.environment.diagnostics:
        result.warn(diagnostic)

    if _repo_env_tracked_in_head(options):
        result.error(
            EXIT_CONFIGURATION,
            Diagnostic(
                "repo_env_tracked",
                f"{REPO_ENV_FILENAME} is tracked in HEAD; a tooling environment file versioned by the repository is "
                "rejected outright",
                str(options.root / REPO_ENV_FILENAME),
            ),
        )
    return result


def _check_rules(options: DoctorOptions) -> GroupResult:
    result = GroupResult("rules")
    path = options.root / RULE_RELATIVE_PATH
    if not path.is_file():
        result.warn(
            Diagnostic(
                "rules_absent",
                f"{RULE_RELATIVE_PATH} is absent; reviews run with an empty rule set until it exists. "
                "`doctor --fix` writes a starting point.",
                str(path),
                severity="warning",
            )
        )
        return result
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        result.error(EXIT_CONFIGURATION, Diagnostic("rules_unparseable", f"could not parse the rule file: {error}", str(path)))
        return result
    rules = payload.get("rules") if isinstance(payload, dict) else None
    if not isinstance(rules, list):
        result.error(EXIT_CONFIGURATION, Diagnostic("rules_shape", "expected a top-level `rules` array", str(path)))
        return result
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or not rule.get("path") or not rule.get("rule"):
            result.error(
                EXIT_CONFIGURATION,
                Diagnostic("rules_entry_invalid", f"rule #{index} needs both a `path` and a `rule`", str(path)),
            )
            return result
    result.info("rules_path", str(path), str(path))
    result.info("rules_count", f"{len(rules)} rule(s)")
    digest = sha256_file(path)
    if digest:
        result.info("rules_sha256", digest)
    return result


def _check_evidence(options: DoctorOptions, config: ResolvedConfig | None) -> GroupResult:
    result = GroupResult("evidence")
    try:
        evidence_root = resolve_evidence_root(
            environment=options.environment,
            config=config,
            forbidden_roots=_forbidden_roots(options),
        )
    except AppError as error:
        result.error(error.code, error.diagnostics[0] if error.diagnostics else Diagnostic("evidence_root_invalid", str(error)))
        return result
    result.info("evidence_root", str(evidence_root.path), str(evidence_root.path))
    for diagnostic in permission_diagnostics(evidence_root):
        result.diagnostics.append(diagnostic)
    return result


def lifecycle_hook_diagnostics(root: Path) -> list[Diagnostic]:
    """Validate -- never register -- the lifecycle hook declared in the manifest."""

    registry = root / REGISTRY_RELATIVE_PATH
    if not registry.is_file():
        return [
            Diagnostic(
                "lifecycle_registry_missing",
                f"{REGISTRY_RELATIVE_PATH} was not found; lifecycle hooks may not be registered yet",
                severity="info",
            )
        ]
    try:
        text = registry.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    if MANAGED_LIFECYCLE_COMMAND in text:
        return [
            Diagnostic(
                "lifecycle_hook_registered",
                f"{MANAGED_LIFECYCLE_EVENT} -> {MANAGED_LIFECYCLE_COMMAND} is registered",
                severity="info",
            )
        ]
    return [
        Diagnostic(
            "lifecycle_hook_unregistered",
            f"{MANAGED_LIFECYCLE_EVENT} -> {MANAGED_LIFECYCLE_COMMAND} is not registered yet; re-run "
            "`specify extension add` -- this extension never registers hooks itself",
            str(registry),
            severity="warning",
        )
    ]


def git_hook_diagnostics(root: Path) -> list[Diagnostic]:
    """Report any Git hook referencing this extension; it installs none by design."""

    hooks_directory = root / ".git" / "hooks"
    installed = _installed_git_hooks(hooks_directory)
    if installed:
        return [
            Diagnostic(
                "git_hooks_present",
                f"this extension installs no Git hooks, yet {', '.join(installed)} reference it",
                str(hooks_directory),
            )
        ]
    return [Diagnostic("git_hooks_absent", "no Git hook references this extension, as designed", severity="info")]


def _check_hooks(options: DoctorOptions) -> GroupResult:
    result = GroupResult("hooks")
    for diagnostic in lifecycle_hook_diagnostics(options.root):
        result.diagnostics.append(diagnostic)
    for diagnostic in git_hook_diagnostics(options.root):
        if diagnostic.severity == "error":
            result.error(EXIT_CONFIGURATION, diagnostic)
        else:
            result.diagnostics.append(diagnostic)
    return result


# -- fixes ------------------------------------------------------------------


def _apply_fixes(options: DoctorOptions) -> FixOutcome:
    """The repairs ``--fix`` is allowed to make.

    Missing ``.gitignore`` entries, the two configuration files, a starting rule
    set, the evidence-root permissions -- all strictly local to the repository
    toplevel and never overwriting a file the consumer already wrote -- and the
    pinned engine, when it is absent, into this distribution's data root.

    The engine is the only thing this command installs, it is installed nowhere
    else, and it is verified against the lock before it is left on disk. Every
    other command, ``review`` included, installs nothing on any path.
    """

    outcome = FixOutcome()
    applied = outcome.applied
    added = ensure_entries(options.root / ".gitignore")
    if added:
        applied.append(f"added {', '.join(added)} to .gitignore")

    shared_path = shared_config_path(options.root)
    if not shared_path.exists():
        repository = _repository_best_effort(options)
        shared_path.write_text(
            dump_yaml_subset(shared_config_document(repository=repository, remote="origin", slug=None)),
            encoding="utf-8",
        )
        applied.append(f"created {ROOT_CONFIG_FILENAME} (commit it in a reviewed change)")

    local_path = local_config_path(options.root)
    if not local_path.exists():
        local_path.write_text(LOCAL_CONFIG_TEMPLATE, encoding="utf-8")
        applied.append(f"created {LOCAL_CONFIG_FILENAME}")

    rule_path = options.root / RULE_RELATIVE_PATH
    if not rule_path.exists():
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        rule_path.write_text(RULE_TEMPLATE, encoding="utf-8")
        applied.append(f"created {RULE_RELATIVE_PATH} from the template")

    _install_engine_if_absent(options, outcome)

    try:
        evidence_root = resolve_evidence_root(
            environment=options.environment,
            config=None,
            forbidden_roots=_forbidden_roots(options),
        )
    except AppError:
        return outcome
    if enforce_permissions(evidence_root):
        applied.append(f"tightened {evidence_root.path} to 0700")
    return outcome


def _install_engine_if_absent(options: DoctorOptions, outcome: FixOutcome) -> None:
    """Install the pinned engine, unless the operator already chose a binary.

    An explicit ``SPECKIT_CODE_REVIEW_OCR_BIN`` is a decision, and ``--fix``
    does not second-guess it: whatever it points at is checked, never replaced.
    Without one, the canonical path is the only place this command installs to,
    and only when nothing is there.
    """

    pin = external_tool_pin(options.root)
    tag = _engine_tag(pin, None)
    if options.environment.executable_override(f"{ENV_PREFIX}OCR_BIN"):
        return
    if canonical_executable(tag).is_file():
        return
    key = platform_key()
    result = install_engine(
        tag=tag,
        package=(pin.npm_package if pin else None) or OCR_NPM_PACKAGE,
        expected_digest=pin.binary_digest(key) if pin else None,
        platform=key,
        timeout=options.timeout,
    )
    if result.applied:
        outcome.applied.append(result.applied)
    if result.diagnostic is not None:
        outcome.diagnostics.append(result.diagnostic)


# -- helpers ----------------------------------------------------------------


def _engine_tag(pin, config: ResolvedConfig | None) -> str:
    """The engine version this repository is pinned to: lock, config, default."""

    return (pin.release_tag if pin else None) or (config.get("engine", "ocr_version") if config else None) or DEFAULT_OCR_TAG


def _load_config(options: DoctorOptions) -> tuple[ResolvedConfig | None, AppError | None]:
    try:
        return load_config(options.root, explicit=options.config_flag, environment=options.environment), None
    except AppError as error:
        return None, error


def _repository_best_effort(options: DoctorOptions) -> str | None:
    try:
        return resolve_repository(_git(options), explicit=None, remote="origin")
    except AppError:
        return None


def external_tool_pin(root: Path):
    """The engine pin: the consumer-root lock when present, else the one the
    extension ships in its own ``engine.lock.yml``."""

    pin = extension_pin(load_lock(lock_path(root)))
    tool = pin.external_tool() if pin is not None else None
    if tool is not None:
        return tool
    return self_external_tool_pin()


def _git(options: DoctorOptions) -> Git:
    """The guarded Git client of this session, or one opened the same way."""

    if options.git is not None:
        return options.git
    return open_git(options.root, forbidden_roots=(options.root,), timeout=options.timeout)


def _forbidden_roots(options: DoctorOptions) -> tuple[Path, ...]:
    """The consumer toplevel and every active worktree of it (one implementation)."""

    try:
        return _git(options).forbidden_roots()
    except AppError:
        return (options.root.resolve(),)


def _repo_env_tracked_in_head(options: DoctorOptions) -> bool:
    try:
        git = _git(options)
        if git.head_commit() is None:
            return False
        return git.path_tracked_at("HEAD", REPO_ENV_FILENAME)
    except AppError:
        return False


def _installed_git_hooks(hooks_directory: Path) -> list[str]:
    if not hooks_directory.is_dir():
        return []
    found: list[str] = []
    for candidate in sorted(hooks_directory.iterdir()):
        if not candidate.is_file() or candidate.suffix == ".sample":
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "spec-kit-code-review" in text or "speckit.code-review" in text:
            found.append(candidate.name)
    return found


def _worse(current: int, candidate: int) -> int:
    if candidate == EXIT_SUCCESS:
        return current
    if current == EXIT_SUCCESS:
        return candidate
    for code in _CODE_PRIORITY:
        if current == code:
            return current
        if candidate == code:
            return candidate
    return current
