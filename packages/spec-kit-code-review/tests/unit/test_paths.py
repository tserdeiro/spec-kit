"""The per-user paths of this distribution, and where the engine may live."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from spec_kit_code_review.paths import (
    OCR_TOOL_NAME,
    config_root,
    data_root,
    evidence_root,
    ocr_install_command,
    ocr_uninstall_command,
    operator_env_path,
    resolved_roots,
    state_root,
    tool_executable,
    tool_root,
)


NAMESPACE = ("tserdeiro", "spec-kit")


class RootTests(unittest.TestCase):
    def test_each_root_honours_its_own_variable(self) -> None:
        environment = {
            "XDG_CONFIG_HOME": "/cfg",
            "XDG_DATA_HOME": "/data",
            "XDG_STATE_HOME": "/state",
        }

        self.assertEqual(config_root(environment), Path("/cfg").joinpath(*NAMESPACE))
        self.assertEqual(data_root(environment), Path("/data").joinpath(*NAMESPACE))
        self.assertEqual(state_root(environment), Path("/state").joinpath(*NAMESPACE))

    def test_each_root_has_its_own_default(self) -> None:
        home = Path.home()

        self.assertEqual(config_root({}), home / ".config" / "tserdeiro" / "spec-kit")
        self.assertEqual(data_root({}), home / ".local" / "share" / "tserdeiro" / "spec-kit")
        self.assertEqual(state_root({}), home / ".local" / "state" / "tserdeiro" / "spec-kit")

    def test_an_empty_variable_is_not_a_root(self) -> None:
        # An exported-but-empty XDG variable is the shell's way of saying
        # nothing, not a request to write at the filesystem root.
        self.assertEqual(config_root({"XDG_CONFIG_HOME": "   "}), config_root({}))

    def test_a_tilde_in_a_variable_is_expanded(self) -> None:
        self.assertEqual(
            state_root({"XDG_STATE_HOME": "~/elsewhere"}),
            Path.home() / "elsewhere" / "tserdeiro" / "spec-kit",
        )

    def test_the_three_roots_are_separate_by_design(self) -> None:
        # The evidence carries diffs of the code under review; state is what is
        # not meant to be synced or backed up with a user's data.
        environment = {"XDG_CONFIG_HOME": "/cfg", "XDG_DATA_HOME": "/data", "XDG_STATE_HOME": "/state"}
        roots = {config_root(environment), data_root(environment), state_root(environment)}

        self.assertEqual(len(roots), 3)

    def test_the_process_environment_is_read_when_none_is_given(self) -> None:
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/from-process"}, clear=False):
            self.assertEqual(data_root(), Path("/from-process").joinpath(*NAMESPACE))


class LocationTests(unittest.TestCase):
    def test_the_operator_env_file_lives_in_the_config_root(self) -> None:
        self.assertEqual(operator_env_path({"XDG_CONFIG_HOME": "/cfg"}), Path("/cfg/tserdeiro/spec-kit/env"))

    def test_the_evidence_default_lives_in_the_state_root(self) -> None:
        self.assertEqual(
            evidence_root({"XDG_STATE_HOME": "/state"}), Path("/state/tserdeiro/spec-kit/code-review")
        )

    def test_a_tool_gets_one_directory_per_version(self) -> None:
        environment = {"XDG_DATA_HOME": "/data"}

        first = tool_root(OCR_TOOL_NAME, "v1.8.3", environment)
        second = tool_root(OCR_TOOL_NAME, "v1.9.0", environment)

        self.assertEqual(first, Path("/data/tserdeiro/spec-kit/tools/ocr/1.8.3"))
        self.assertNotEqual(first, second)
        self.assertEqual(first.parent, second.parent)

    def test_the_leading_v_is_dropped_only_when_it_prefixes_a_number(self) -> None:
        environment = {"XDG_DATA_HOME": "/data"}

        self.assertTrue(str(tool_root("ocr", "v1.8.3", environment)).endswith("/1.8.3"))
        self.assertTrue(str(tool_root("ocr", "1.8.3", environment)).endswith("/1.8.3"))
        # A version that merely starts with a letter keeps it.
        self.assertTrue(str(tool_root("ocr", "vnext", environment)).endswith("/vnext"))

    def test_the_executable_is_the_real_binary_not_the_npm_shim(self) -> None:
        # `node_modules/.bin/ocr` is a JS shim; the Go binary the lock's digests
        # are of lives in the platform package. Verified against a real install:
        # the shim's digest is not the pinned one, so naming it here would send
        # every operator into a digest mismatch after the fact.
        self.assertEqual(
            tool_executable("ocr", "v1.8.3", {"XDG_DATA_HOME": "/data"}, platform="darwin-arm64"),
            Path("/data/tserdeiro/spec-kit/tools/ocr/1.8.3/node_modules/@alibaba-group/ocr-darwin-arm64/bin/opencodereview"),
        )
        self.assertNotIn("/.bin/", str(tool_executable("ocr", "v1.8.3", {"XDG_DATA_HOME": "/data"})))

    def test_the_platform_package_follows_the_machine(self) -> None:
        from spec_kit_code_review.paths import platform_package

        self.assertEqual(platform_package("linux-amd64"), "ocr-linux-amd64")
        self.assertRegex(platform_package(), r"^ocr-[a-z0-9]+-[a-z0-9]+$")


class CommandTests(unittest.TestCase):
    def test_the_install_command_is_never_global(self) -> None:
        # A tool this extension pins must not outlive its uninstall on a
        # developer's machine.
        command = ocr_install_command("v1.8.3", {"XDG_DATA_HOME": "/data"})

        self.assertIn("npm install --prefix /data/tserdeiro/spec-kit/tools/ocr/1.8.3", command)
        self.assertIn("--save-exact @alibaba-group/open-code-review@1.8.3", command)
        self.assertNotIn(" -g ", command)

    def test_the_install_command_honours_a_renamed_package(self) -> None:
        command = ocr_install_command("v1.8.3", {"XDG_DATA_HOME": "/data"}, package="@scope/renamed")

        self.assertIn("--save-exact @scope/renamed@1.8.3", command)

    def test_the_uninstall_command_removes_exactly_that_version(self) -> None:
        environment = {"XDG_DATA_HOME": "/data"}

        self.assertEqual(
            ocr_uninstall_command("v1.8.3", environment), "rm -rf /data/tserdeiro/spec-kit/tools/ocr/1.8.3"
        )
        # Not the whole tools directory, and not the data root.
        self.assertNotIn("rm -rf /data/tserdeiro/spec-kit/tools ", ocr_uninstall_command("v1.8.3", environment))

    def test_the_reported_roots_are_resolved_not_templates(self) -> None:
        roots = resolved_roots({"XDG_CONFIG_HOME": "/cfg", "XDG_DATA_HOME": "/data", "XDG_STATE_HOME": "/state"})

        for value in roots.values():
            with self.subTest(value=value):
                self.assertNotIn("XDG_", value)
                self.assertNotIn("$", value)
                self.assertNotIn("~", value)
        self.assertEqual(roots["config"], "/cfg/tserdeiro/spec-kit")
        self.assertEqual(roots["evidence"], "/state/tserdeiro/spec-kit/code-review")
        self.assertEqual(roots["tools"], "/data/tserdeiro/spec-kit/tools")


class GuardInteractionTests(unittest.TestCase):
    """Why the canonical location is the data root and not somewhere nearer."""

    def test_the_canonical_location_passes_the_guard(self) -> None:
        # The positive half, and it is the load-bearing one: the canonical path
        # contains `node_modules/.bin`, so anyone tempted to harden the guard
        # with a *name* pattern instead of a containment check would break the
        # one location this contract prescribes. This test says so out loud.
        from tempfile import TemporaryDirectory

        from spec_kit_code_review.process import resolve_executable

        with TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "consumer"
            repository.mkdir()
            canonical = tool_executable(OCR_TOOL_NAME, "v1.8.3", {"XDG_DATA_HOME": str(base / "data")})
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_text("#!/bin/sh\n", encoding="utf-8")
            canonical.chmod(0o755)

            resolved = resolve_executable("ocr", override=str(canonical), forbidden_roots=[repository])

            self.assertEqual(resolved, canonical.resolve())
            self.assertIn("node_modules", str(resolved))

    def test_a_tool_inside_the_repository_is_refused_by_the_executable_guard(self) -> None:
        # This is the reason a per-project install is impossible rather than
        # merely undesirable, and it is the guard from stage 1, unchanged.
        from tempfile import TemporaryDirectory

        from spec_kit_code_review.errors import EXIT_PREREQUISITE, AppError
        from spec_kit_code_review.process import resolve_executable

        with TemporaryDirectory() as directory:
            repository = Path(directory)
            for relative in ("node_modules/.bin", ".specify/extensions/code-review/bin"):
                candidate = repository / relative / "ocr"
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text("#!/bin/sh\n", encoding="utf-8")
                candidate.chmod(0o755)
                with self.subTest(location=relative):
                    with self.assertRaises(AppError) as caught:
                        resolve_executable("ocr", override=str(candidate), forbidden_roots=[repository])
                    self.assertEqual(caught.exception.code, EXIT_PREREQUISITE)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
