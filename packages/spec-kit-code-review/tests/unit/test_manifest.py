from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from spec_kit_code_review import __version__, cli
from spec_kit_code_review.completions import collect_completion_tree
from spec_kit_code_review.config import RULE_RELATIVE_PATH
from spec_kit_code_review.doctor import RULE_TEMPLATE


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PACKAGE_ROOT / "extension.yml"
COMMAND_NAMESPACE = "speckit.code-review"
IMPLEMENTED_COMMANDS = {"review", "doctor", "completions"}


def _manifest_text() -> str:
    return MANIFEST.read_text(encoding="utf-8")


class ManifestTests(unittest.TestCase):
    def test_schema_and_identity(self) -> None:
        text = _manifest_text()

        self.assertIn('schema_version: "1.0"', text)
        self.assertIn("id: code-review", text)
        self.assertIn(f'version: "{__version__}"', text)
        self.assertIn('speckit_version: ">=1.0.1,<1.1.0"', text)

    def test_the_doctor_gates_on_the_manifest_requirement(self) -> None:
        # Drift guard: the manifest range and the doctor's constants must
        # move together (the v1.0.1 upgrade caught them apart).
        from spec_kit_code_review.doctor import (
            SPECKIT_SUPPORTED_MAJOR_MINOR,
            SPECKIT_VERSION_RANGE,
        )

        self.assertIn(f'speckit_version: "{",".join(SPECKIT_VERSION_RANGE)}"', _manifest_text())
        floor = SPECKIT_VERSION_RANGE[0].removeprefix(">=")
        self.assertEqual(tuple(int(part) for part in floor.split("."))[:2], SPECKIT_SUPPORTED_MAJOR_MINOR)

    def test_hooks_are_a_top_level_key_never_nested_under_provides(self) -> None:
        text = _manifest_text()

        self.assertRegex(text, r"(?m)^hooks:$")
        provides_block = text.split("\nprovides:\n", 1)[1].split("\nhooks:\n", 1)[0]
        self.assertNotIn("hooks:", provides_block)

    def test_the_single_lifecycle_hook_is_the_documented_one(self) -> None:
        text = _manifest_text().split("\nhooks:\n", 1)[1]

        self.assertIn("after_implement:", text)
        self.assertIn("command: speckit.code-review", text)
        self.assertIn("optional: true", text)
        self.assertIn("priority: 30", text)
        self.assertEqual(len(re.findall(r"(?m)^  [a-z_]+:$", text.split("\ntags:", 1)[0])), 1)

    def test_no_git_hooks_are_declared_anywhere(self) -> None:
        self.assertNotIn("git_hooks", _manifest_text())

    def test_every_declared_command_file_exists_and_matches_its_name(self) -> None:
        text = _manifest_text()
        entries = re.findall(r"- name: (\S+)\n\s+file: (\S+)", text)

        self.assertEqual(len(entries), 3)
        for name, relative in entries:
            with self.subTest(command=name):
                self.assertTrue(name.startswith(COMMAND_NAMESPACE), name)
                path = PACKAGE_ROOT / relative
                self.assertTrue(path.is_file(), relative)
                self.assertIn(f"name: {name}", path.read_text(encoding="utf-8"))


class LauncherTests(unittest.TestCase):
    def test_the_bash_launcher_is_executable_and_self_locating(self) -> None:
        launcher = PACKAGE_ROOT / "scripts" / "bash" / "run.sh"
        text = launcher.read_text(encoding="utf-8")

        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertIn('extension_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)', text)
        self.assertIn("exit 4", text)
        self.assertIn("uv run --frozen --offline --project", text)
        self.assertIn("python -m spec_kit_code_review.cli", text)

    def test_the_powershell_launcher_mirrors_it_including_the_exit_code(self) -> None:
        text = (PACKAGE_ROOT / "scripts" / "powershell" / "run.ps1").read_text(encoding="utf-8")

        self.assertIn("exit 4", text)
        self.assertIn("uv run --frozen --offline --project", text)
        self.assertIn("python -m spec_kit_code_review.cli", text)

    def test_no_launcher_or_manifest_hardcodes_a_development_checkout(self) -> None:
        for relative in ("scripts/bash/run.sh", "scripts/powershell/run.ps1", "extension.yml"):
            with self.subTest(path=relative):
                text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/home/", text)


class PackagingTests(unittest.TestCase):
    def test_the_package_ships_its_own_lockfile_and_declares_no_runtime_dependency(self) -> None:
        pyproject = (PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertTrue((PACKAGE_ROOT / "uv.lock").is_file())
        self.assertIn("dependencies = []", pyproject)
        self.assertIn('dev = ["pytest>=8"]', pyproject)
        self.assertNotIn("[project.scripts]", pyproject)
        self.assertIn('requires-python = ">=3.11"', pyproject)

    def test_the_lockfile_pins_only_this_package_and_its_dev_dependencies(self) -> None:
        lock = (PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8")

        self.assertIn('name = "spec-kit-code-review"', lock)
        self.assertIn('name = "pytest"', lock)

    def test_templates_and_licence_ship_with_the_package(self) -> None:
        for relative in (
            "LICENSE",
            "README.md",
            "CHANGELOG.md",
            ".extensionignore",
            "config/speckit-code-review.template.yml",
            "config/speckit-code-review.local.template.yml",
            "scripts/conformance/review.sh",
            "scripts/conformance/publish.sh",
        ):
            with self.subTest(path=relative):
                self.assertTrue((PACKAGE_ROOT / relative).is_file(), relative)

    def test_the_rule_template_is_a_valid_starting_rule_set(self) -> None:
        import json

        payload = json.loads(RULE_TEMPLATE)

        self.assertTrue(payload["rules"][0]["path"])
        self.assertTrue(payload["rules"][0]["rule"])
        self.assertEqual(RULE_RELATIVE_PATH, ".opencodereview/rule.json")

    def test_the_extension_ignore_excludes_tests_and_caches(self) -> None:
        text = (PACKAGE_ROOT / ".extensionignore").read_text(encoding="utf-8")

        for entry in ("tests/", "__pycache__/", ".venv/"):
            self.assertIn(entry, text)


class CommandSurfaceTests(unittest.TestCase):
    def test_only_the_implemented_commands_are_wired_into_the_cli(self) -> None:
        self.assertEqual(set(collect_completion_tree(cli.build_parser())), IMPLEMENTED_COMMANDS)

    def test_the_manifest_and_the_cli_agree_on_the_surface(self) -> None:
        commands = _manifest_text().split("\n  commands:\n", 1)[1].split("\nhooks:\n", 1)[0]
        declared = set(re.findall(r"- name: (\S+)", commands))

        self.assertEqual(declared, {"speckit.code-review", "speckit.code-review.doctor", "speckit.code-review.completions"})

    def test_the_shared_configuration_template_is_loadable_and_valid(self) -> None:
        from spec_kit_code_review.config import load_config
        from tempfile import TemporaryDirectory
        import shutil

        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(
                PACKAGE_ROOT / "config" / "speckit-code-review.template.yml", root / "speckit-code-review.yml"
            )
            config = load_config(root)

        self.assertEqual(config.get("engine", "ocr_version"), "v1.8.3")
        self.assertEqual(config.get("budget", "limit"), 400)
        self.assertEqual(config.get("publish", "event"), "request-changes")


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
