from __future__ import annotations

import os
import shutil
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from spec_kit_code_review.config import LOCAL_CONFIG_FILENAME, RULE_RELATIVE_PATH
from spec_kit_code_review.doctor import CHECK_GROUPS, DoctorOptions, run_doctor
from spec_kit_code_review.env_files import REPO_ENV_FILENAME, load_env_files
from spec_kit_code_review.errors import (
    EXIT_AUTHENTICATION,
    EXIT_CONFIGURATION,
    EXIT_PREREQUISITE,
    EXIT_SUCCESS,
    EXIT_USAGE,
)
from spec_kit_code_review.lockfile import lock_path, platform_key
from spec_kit_code_review.paths import OCR_TOOL_NAME, tool_executable, tool_root
from spec_kit_code_review.process import sha256_file
from tests.support.fixtures import (
    DEFAULT_OCR_VERSION,
    FAKE_OCR_SOURCE,
    copy_consumer_fixture,
    install_fake_gh,
    install_fake_npm,
    install_fake_ocr,
    install_fake_ocr_at,
    isolate_operator_global_env,
    write_lock,
)
from tests.support.repo import TemporaryRepository


class DoctorCase(unittest.TestCase):
    """A consumer repository with fake ``ocr``/``gh`` and a lock that pins them."""

    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.bin = self.workspace / "bin"
        self.evidence = self.workspace / "evidence"

        self.repository = TemporaryRepository(self.workspace / "consumer")
        self.addCleanup(self.repository.cleanup)
        copy_consumer_fixture(self.repository.path)
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "consumer fixture")
        self.repository.add_remote("origin", "git@github.com:tserdeiro/consumer.git")
        self.root = self.repository.path

        self.environment_overrides: dict[str, str] = {}
        self.ocr_state: dict | None = {"version": DEFAULT_OCR_VERSION}
        # Where the fake engine goes: behind the override, or at the canonical
        # pinned path with no override at all.
        self.ocr_at_canonical = False
        self.gh_state: dict | None = {"auth": {"authenticated": True, "scopes": ["repo", "read:org"]}, "user": "tester"}
        self.lock_version = DEFAULT_OCR_VERSION
        self.lock_digest: str | None = "match"
        self.lock_npm_package = "@alibaba-group/open-code-review"
        # The data root every canonical lookup and every install of this test
        # resolves to: a developer's real engine never takes part.
        self.data_home = self.workspace / "xdg-data"
        self.npm_state: dict | None = None
        self.engine_path: Path | None = None

    # -- environment ----------------------------------------------------

    def _canonical_engine(self) -> Path:
        return tool_executable(OCR_TOOL_NAME, "v1.8.3", {"XDG_DATA_HOME": str(self.data_home)})

    def _install_tools(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        self.engine_path = None
        if self.ocr_state is not None and self.ocr_at_canonical:
            self.engine_path = install_fake_ocr_at(self._canonical_engine(), self.ocr_state)
        elif self.ocr_state is not None:
            path, environment = install_fake_ocr(self.bin, self.ocr_state)
            overrides.update(environment)
            overrides["SPECKIT_CODE_REVIEW_OCR_BIN"] = path
            self.engine_path = Path(path)
        if self.gh_state is not None:
            path, environment = install_fake_gh(self.bin, self.gh_state)
            overrides.update(environment)
            overrides["SPECKIT_CODE_REVIEW_GH_BIN"] = path
        _, npm_environment = install_fake_npm(self.bin, self.npm_state)
        overrides.update(npm_environment)
        overrides.update(self.environment_overrides)
        return overrides

    def _path(self) -> str:
        """A PATH holding only this test's fakes plus the runtime tools doctor needs.

        The real ``ocr`` and ``gh`` of the developer's machine stay out of it, so
        an "absent tool" case really is absent; ``uv`` and ``specify`` are added
        back by directory because the runtime and speckit groups look for them.
        """

        directories = [str(self.bin)]
        for tool in ("uv", "specify", "python3"):
            located = shutil.which(tool)
            if located:
                directory = str(Path(located).resolve().parent)
                if directory not in directories:
                    directories.append(directory)
        directories.extend(["/usr/bin", "/bin"])
        return ":".join(directories)

    def _write_lock(self) -> None:
        digest = self.lock_digest
        if digest == "match":
            engine = self.engine_path
            digest = sha256_file(engine) if engine is not None and engine.is_file() else None
        write_lock(
            lock_path(self.root),
            version_string=self.lock_version,
            platform_key=platform_key() if digest else None,
            binary_digest=digest,
            npm_package=self.lock_npm_package,
        )

    def run_doctor(self, *, fix: bool = False, evidence_dir: Path | None = None):
        overrides = self._install_tools()
        self._write_lock()
        environment = {key: value for key, value in os.environ.items() if not key.startswith("SPECKIT_CODE_REVIEW_")}
        environment.update(overrides)
        environment["PATH"] = self._path()
        environment.setdefault("XDG_DATA_HOME", str(self.data_home))
        environment.setdefault("SPECKIT_CODE_REVIEW_EVIDENCE_DIR", str(evidence_dir or self.evidence))
        with mock.patch.dict(os.environ, environment, clear=True):
            snapshot = load_env_files(self.root, dict(os.environ))
            return run_doctor(DoctorOptions(root=self.root, environment=snapshot, fix=fix))

    def codes(self, report) -> set[str]:
        return {diagnostic.code for diagnostic in report.diagnostics}


class HealthyDoctorTests(DoctorCase):
    def test_every_group_passes_on_a_configured_consumer(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS, [d.message for d in report.diagnostics if d.severity != "info"])
        self.assertEqual(set(report.as_dict()["checks"]), set(CHECK_GROUPS))
        self.assertEqual(set(report.as_dict()["checks"].values()), {"pass"})

    def test_the_ocr_group_reports_path_version_and_digest(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("ocr_digest", self.codes(report))
        self.assertIn(DEFAULT_OCR_VERSION, [d.message for d in report.diagnostics])


class GitGroupTests(DoctorCase):
    def _shim_git(self, version: str) -> None:
        shim = self.bin / "git"
        shim.parent.mkdir(parents=True, exist_ok=True)
        # `git -C <root> --version` puts the flag last, so the shim scans every
        # argument instead of only $1, and delegates everything else to real git.
        shim.write_text(
            "#!/usr/bin/env sh\n"
            'for argument in "$@"; do\n'
            '  if [ "$argument" = "--version" ]; then\n'
            f'    echo "git version {version}"\n'
            "    exit 0\n"
            "  fi\n"
            "done\n"
            'exec /usr/bin/git "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def test_git_below_the_engine_minimum_is_a_prerequisite_failure(self) -> None:
        self._shim_git("2.39.5")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("git_version_unsupported", self.codes(report))

    def test_a_recent_git_passes_and_reports_the_worktree_state(self) -> None:
        self._shim_git("2.50.1")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("git_worktree_state", self.codes(report))


class OcrGroupTests(DoctorCase):
    def test_absent_ocr_is_a_prerequisite_failure_naming_the_fix_and_the_manual_install(self) -> None:
        self.ocr_state = None

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        message = next(d.message for d in report.diagnostics if d.code == "ocr_missing")
        self.assertIn("v1.8.3", message)
        # The new policy, both halves: `--fix` installs it, a review never does.
        self.assertIn("doctor --fix", message)
        self.assertIn("A review never installs anything", message)

    def test_the_remediation_names_the_npm_specifier_confirmed_for_the_pinned_tag(self) -> None:
        self.ocr_state = None
        report = self.run_doctor()

        message = next(d.message for d in report.diagnostics if d.code == "ocr_missing")
        # Doc "Rutas por usuario": into this distribution's data root, one
        # directory per version -- never a global install, which would outlive
        # the extension's own uninstall on the machine.
        self.assertIn("npm install --prefix", message)
        self.assertIn("--save-exact @alibaba-group/open-code-review@1.8.3", message)
        self.assertNotIn("npm install -g", message)
        self.assertIn("tserdeiro/spec-kit/tools/ocr/1.8.3", message)
        self.assertIn("/bin/opencodereview", message)
        self.assertIn("JS shim", message)
        self.assertIn("rm -rf", message)

    def test_the_remediation_takes_the_package_name_from_the_lock(self) -> None:
        # A future rename of the wrapper travels with the pin, not with this code.
        self.ocr_state = None
        self.lock_npm_package = "@alibaba-group/renamed-wrapper"

        report = self.run_doctor()

        message = next(d.message for d in report.diagnostics if d.code == "ocr_missing")
        self.assertIn("--save-exact @alibaba-group/renamed-wrapper@1.8.3", message)
        self.assertNotIn("npm install -g", message)

    def test_the_report_names_the_three_resolved_roots_and_the_canonical_path(self) -> None:
        # Resolved, never the templates: an operator has to be able to `ls` them.
        report = self.run_doctor()

        codes = {item.code: item.message for item in report.diagnostics}
        for code in ("paths_config_root", "paths_data_root", "paths_state_root"):
            with self.subTest(code=code):
                self.assertIn(code, codes)
                self.assertNotIn("XDG_", codes[code])
                self.assertNotIn("$", codes[code])
                self.assertIn("tserdeiro/spec-kit", codes[code])
        self.assertIn("/bin/opencodereview", codes["ocr_canonical_path"])
        self.assertNotIn("/.bin/ocr", codes["ocr_canonical_path"])
        self.assertIn("rm -rf", codes["ocr_uninstall_command"])

    def test_the_roots_honour_their_variables(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": "/tmp/cfg",
                "XDG_DATA_HOME": "/tmp/data",
                "XDG_STATE_HOME": "/tmp/state",
            },
            clear=False,
        ):
            report = self.run_doctor()

        codes = {item.code: item.message for item in report.diagnostics}
        self.assertEqual(codes["paths_config_root"], "/tmp/cfg/tserdeiro/spec-kit")
        self.assertEqual(codes["paths_data_root"], "/tmp/data/tserdeiro/spec-kit")
        self.assertEqual(codes["paths_state_root"], "/tmp/state/tserdeiro/spec-kit")

    def test_a_leftover_legacy_directory_is_reported_with_its_migration(self) -> None:
        import os
        from unittest import mock

        state = self.workspace / "state"
        (state / "spec-kit-code-review" / "some-repo").mkdir(parents=True)

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}, clear=False):
            report = self.run_doctor()

        legacy = next(item for item in report.diagnostics if item.code == "paths_legacy_directory")
        self.assertIn("pre-2026-08-02", legacy.message)
        self.assertIn("rm -rf", legacy.message)

    def test_no_legacy_warning_when_there_is_nothing_left_behind(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.workspace / "clean-state")}, clear=False):
            report = self.run_doctor()

        self.assertNotIn("paths_legacy_directory", self.codes(report))

    def test_a_version_different_from_the_pin_is_a_prerequisite_failure(self) -> None:
        self.ocr_state = {"version": "ocr version v1.9.0"}

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_version_mismatch", self.codes(report))

    def test_the_pin_is_the_platform_independent_identity(self) -> None:
        # The engine prints its platform and build time on the same line as its
        # identity. Pinning the whole string in a *shared* lock would fail for
        # every user on another platform, with a message blaming their correct
        # installation. Verified against the real v1.8.3 output.
        self.lock_version = "open-code-review v1.8.3 (80a579466)"
        for platform in ("darwin/arm64", "linux/amd64", "windows/amd64"):
            with self.subTest(platform=platform):
                self.ocr_state = {
                    "version": (
                        f"open-code-review v1.8.3 (80a579466) {platform}\n"
                        "built at: 2026-07-31T09:24:52Z\n"
                        "https://github.com/alibaba/open-code-review"
                    )
                }

                report = self.run_doctor()

                self.assertNotIn("ocr_version_mismatch", self.codes(report))

    def test_a_different_commit_is_still_a_mismatch(self) -> None:
        # The prefix is name, version *and* commit: a rebuild of the same
        # version from a different commit is a different binary.
        self.lock_version = "open-code-review v1.8.3 (80a579466)"
        self.ocr_state = {"version": "open-code-review v1.8.3 (deadbeef) darwin/arm64\nbuilt at: x"}

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_version_mismatch", self.codes(report))

    def test_a_digest_different_from_the_lock_is_a_prerequisite_failure(self) -> None:
        self.lock_digest = "b" * 64

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_digest_mismatch", self.codes(report))

    def test_a_platform_absent_from_the_lock_is_a_warning(self) -> None:
        self.lock_digest = None

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("ocr_digest_platform_unpinned", self.codes(report))

    def test_a_missing_delegation_subcommand_is_a_prerequisite_failure(self) -> None:
        self.ocr_state = {"version": DEFAULT_OCR_VERSION, "missing_subcommands": ["delegate rule"]}

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_subcommand_missing", self.codes(report))

    def test_telemetry_enabled_in_the_environment_is_reported_never_changed(self) -> None:
        self.environment_overrides["OCR_ENABLE_TELEMETRY"] = "1"

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("ocr_telemetry_enabled", self.codes(report))

    def test_an_ocr_inside_the_candidate_tree_is_refused(self) -> None:
        inside = self.root / "tools" / "ocr"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        inside.chmod(inside.stat().st_mode | stat.S_IXUSR)
        self.environment_overrides["SPECKIT_CODE_REVIEW_OCR_BIN"] = str(inside)

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("executable_inside_candidate", self.codes(report))

    def test_without_an_override_the_canonical_pinned_binary_is_used(self) -> None:
        # The whole point of the fallback: nothing exported, and the engine
        # installed where this distribution puts it is the one that is used.
        self.ocr_at_canonical = True

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS, [d.message for d in report.diagnostics if d.severity != "info"])
        path = next(d.message for d in report.diagnostics if d.code == "ocr_path")
        self.assertEqual(Path(path), self._canonical_engine().resolve())
        self.assertIn("ocr_digest", self.codes(report))

    def test_a_canonical_binary_whose_digest_differs_is_rejected(self) -> None:
        # The fallback is a *location*, never a reason to trust what is there.
        self.ocr_at_canonical = True
        self.lock_digest = "b" * 64

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_digest_mismatch", self.codes(report))

    def test_a_lock_without_this_extension_entry_falls_back_to_the_shipped_pin(self) -> None:
        report = self.run_doctor()
        self.assertEqual(report.code, EXIT_SUCCESS)

        overrides = self._install_tools()
        lock_path(self.root).write_text('schema_version: "1.0"\n', encoding="utf-8")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("SPECKIT_CODE_REVIEW_")}
        environment.update(overrides)
        environment["PATH"] = self._path()
        environment["XDG_DATA_HOME"] = str(self.data_home)
        environment["SPECKIT_CODE_REVIEW_EVIDENCE_DIR"] = str(self.evidence)
        with mock.patch.dict(os.environ, environment, clear=True):
            snapshot = load_env_files(self.root, dict(os.environ))
            unpinned = run_doctor(DoctorOptions(root=self.root, environment=snapshot))

        # The shipped engine.lock.yml pin applies, so the fake engine's digest
        # no longer passes as merely "unpinned": it fails closed.
        self.assertNotIn("ocr_pin_missing", self.codes(unpinned))
        self.assertNotEqual(unpinned.code, EXIT_SUCCESS)
        self.assertIn("ocr_digest_mismatch", self.codes(unpinned))


class GhGroupTests(DoctorCase):
    def test_an_authenticated_gh_reports_its_user_and_scopes(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("gh_user", self.codes(report))
        self.assertIn("tester", [d.message for d in report.diagnostics])

    def test_an_unauthenticated_gh_is_an_authentication_failure(self) -> None:
        self.gh_state = {"auth": {"authenticated": False}}

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_AUTHENTICATION)
        self.assertIn("gh_unauthenticated", self.codes(report))

    def test_insufficient_scopes_are_a_warning(self) -> None:
        self.gh_state = {"auth": {"authenticated": True, "scopes": ["read:org"]}, "user": "tester"}

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("gh_scopes_insufficient", self.codes(report))

    def test_an_absent_gh_is_only_a_warning(self) -> None:
        self.gh_state = None

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("gh_missing", self.codes(report))


class ConfigGroupTests(DoctorCase):
    def test_a_repository_env_file_tracked_in_head_is_a_configuration_failure(self) -> None:
        self.repository.commit(REPO_ENV_FILENAME, "SPECKIT_CODE_REVIEW_LOG_LEVEL=debug\n", "track the env file")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_CONFIGURATION)
        self.assertIn("repo_env_tracked", self.codes(report))

    def test_a_missing_local_overlay_and_gitignore_entries_are_warnings(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("local_config_missing", self.codes(report))
        self.assertIn("gitignore_entries_missing", self.codes(report))

    def test_an_invalid_shared_configuration_is_reported_with_its_own_code(self) -> None:
        (self.root / "speckit-code-review.yml").write_text('schema_version: "1.0"\npublish:\n  event: "approve"\n', encoding="utf-8")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_CONFIGURATION)

    def test_ignored_executable_overrides_from_the_repository_file_are_surfaced(self) -> None:
        (self.root / REPO_ENV_FILENAME).write_text("SPECKIT_CODE_REVIEW_OCR_BIN=./tools/evil-ocr\n", encoding="utf-8")

        report = self.run_doctor()

        self.assertIn("env_file_executable_override_ignored", self.codes(report))


class RulesGroupTests(DoctorCase):
    def test_the_fixture_rules_are_reported_with_their_digest(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("rules_sha256", self.codes(report))
        self.assertIn("2 rule(s)", [d.message for d in report.diagnostics])

    def test_absent_rules_are_a_warning(self) -> None:
        (self.root / RULE_RELATIVE_PATH).unlink()

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("rules_absent", self.codes(report))

    def test_malformed_rules_are_a_configuration_failure(self) -> None:
        (self.root / RULE_RELATIVE_PATH).write_text("{not json", encoding="utf-8")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_CONFIGURATION)

    def test_a_rule_without_a_path_is_a_configuration_failure(self) -> None:
        (self.root / RULE_RELATIVE_PATH).write_text('{"rules": [{"rule": "no path"}]}', encoding="utf-8")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_CONFIGURATION)


class EvidenceGroupTests(DoctorCase):
    def test_an_evidence_root_inside_the_repository_is_a_usage_failure(self) -> None:
        report = self.run_doctor(evidence_dir=self.root / ".specify" / "review")

        self.assertEqual(report.code, EXIT_USAGE)
        self.assertIn("evidence_root_inside_repository", self.codes(report))

    def test_the_resolved_evidence_root_is_reported(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("evidence_root", self.codes(report))


class HooksGroupTests(DoctorCase):
    def test_the_registered_lifecycle_hook_is_recognized(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("lifecycle_hook_registered", self.codes(report))
        self.assertIn("git_hooks_absent", self.codes(report))

    def test_an_unregistered_lifecycle_hook_is_a_warning(self) -> None:
        (self.root / ".specify" / "extensions.yml").write_text("installed:\n- git\n", encoding="utf-8")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertIn("lifecycle_hook_unregistered", self.codes(report))

    def test_a_git_hook_referencing_this_extension_is_a_configuration_failure(self) -> None:
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "post-commit").write_text("#!/bin/sh\n# speckit.code-review run\n", encoding="utf-8")

        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_CONFIGURATION)
        self.assertIn("git_hooks_present", self.codes(report))


class FixTests(DoctorCase):
    def test_fix_materializes_the_local_files_and_tightens_the_evidence_root(self) -> None:
        self.evidence.mkdir()
        self.evidence.chmod(0o755)

        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_SUCCESS)
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(LOCAL_CONFIG_FILENAME, gitignore)
        self.assertIn(REPO_ENV_FILENAME, gitignore)
        self.assertTrue((self.root / LOCAL_CONFIG_FILENAME).is_file())
        self.assertEqual(oct(self.evidence.stat().st_mode)[-3:], "700")
        self.assertEqual(len(report.fixes), 3)

    def test_fix_writes_a_starting_rule_set_when_the_repository_has_none(self) -> None:
        (self.root / RULE_RELATIVE_PATH).unlink()

        report = self.run_doctor(fix=True)

        self.assertTrue((self.root / RULE_RELATIVE_PATH).is_file())
        self.assertEqual(report.code, EXIT_SUCCESS)

    def test_fix_with_nothing_to_repair_is_a_clean_no_op(self) -> None:
        self.run_doctor(fix=True)

        second = self.run_doctor(fix=True)

        self.assertEqual(second.fixes, [])
        self.assertEqual(second.code, EXIT_SUCCESS)

    def test_without_fix_nothing_is_written(self) -> None:
        self.run_doctor()

        self.assertFalse((self.root / LOCAL_CONFIG_FILENAME).exists())
        self.assertFalse((self.root / ".gitignore").exists())


class EngineInstallTests(DoctorCase):
    """``doctor --fix`` installing the pinned engine, and refusing to keep it."""

    def setUp(self) -> None:
        super().setUp()
        self.ocr_state = None  # nothing installed, no override
        self.npm_log = self.workspace / "npm-invocations.log"
        self.npm_state = {
            "binary_source": str(FAKE_OCR_SOURCE),
            "binary_state": {"version": DEFAULT_OCR_VERSION},
            "record_invocations": str(self.npm_log),
        }
        # What the fake npm will put there, so the lock can pin its digest.
        self.lock_digest = sha256_file(FAKE_OCR_SOURCE)

    def _npm_invocations(self) -> list[str]:
        if not self.npm_log.is_file():
            return []
        return self.npm_log.read_text(encoding="utf-8").splitlines()

    def test_fix_installs_the_pinned_engine_and_the_review_is_then_healthy(self) -> None:
        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_SUCCESS, [d.message for d in report.diagnostics if d.severity != "info"])
        self.assertTrue(self._canonical_engine().is_file())
        self.assertTrue(any("installed ocr v1.8.3" in line for line in report.fixes), report.fixes)
        self.assertIn("ocr_digest", self.codes(report))

    def test_the_install_is_the_exact_pinned_argv_never_a_shell_string(self) -> None:
        self.run_doctor(fix=True)

        destination = tool_root(OCR_TOOL_NAME, "v1.8.3", {"XDG_DATA_HOME": str(self.data_home)})
        self.assertEqual(
            self._npm_invocations(),
            [f"install --prefix {destination} --save-exact @alibaba-group/open-code-review@1.8.3"],
        )
        # npm ignores `--save-exact` without a manifest in the prefix.
        self.assertTrue((destination / "package.json").is_file())

    def test_the_package_name_comes_from_the_lock(self) -> None:
        self.lock_npm_package = "@alibaba-group/renamed-wrapper"

        self.run_doctor(fix=True)

        self.assertIn("--save-exact @alibaba-group/renamed-wrapper@1.8.3", self._npm_invocations()[0])

    def test_a_digest_that_does_not_match_the_lock_removes_the_whole_tree(self) -> None:
        self.lock_digest = "b" * 64

        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_install_digest_mismatch", self.codes(report))
        self.assertFalse(tool_root(OCR_TOOL_NAME, "v1.8.3", {"XDG_DATA_HOME": str(self.data_home)}).exists())
        self.assertEqual(report.fixes, [fix for fix in report.fixes if "installed ocr" not in fix])

    def test_an_install_that_produces_no_binary_leaves_nothing_behind(self) -> None:
        self.npm_state = {"skip_binary": True, "record_invocations": str(self.npm_log)}

        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_install_incomplete", self.codes(report))
        self.assertFalse(tool_root(OCR_TOOL_NAME, "v1.8.3", {"XDG_DATA_HOME": str(self.data_home)}).exists())

    def test_a_failing_npm_is_reported_and_removes_the_directory(self) -> None:
        self.npm_state = {"exit_code": 1, "stderr": "npm ERR! code E404", "record_invocations": str(self.npm_log)}

        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        message = next(d.message for d in report.diagnostics if d.code == "ocr_install_failed")
        self.assertIn("E404", message)
        self.assertFalse(tool_root(OCR_TOOL_NAME, "v1.8.3", {"XDG_DATA_HOME": str(self.data_home)}).exists())

    def test_an_override_is_the_operators_decision_and_is_never_replaced(self) -> None:
        self.ocr_state = {"version": DEFAULT_OCR_VERSION}
        self.lock_digest = "match"

        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_SUCCESS, [d.message for d in report.diagnostics if d.severity != "info"])
        self.assertEqual(self._npm_invocations(), [])
        self.assertFalse(self._canonical_engine().exists())

    def test_an_engine_already_installed_is_not_reinstalled(self) -> None:
        self.ocr_state = {"version": DEFAULT_OCR_VERSION}
        self.ocr_at_canonical = True
        self.lock_digest = "match"

        report = self.run_doctor(fix=True)

        self.assertEqual(report.code, EXIT_SUCCESS)
        self.assertEqual(self._npm_invocations(), [])

    def test_without_fix_a_missing_engine_is_reported_and_nothing_is_installed(self) -> None:
        report = self.run_doctor()

        self.assertEqual(report.code, EXIT_PREREQUISITE)
        self.assertIn("ocr_missing", self.codes(report))
        self.assertEqual(self._npm_invocations(), [])
        self.assertFalse(self._canonical_engine().exists())


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
