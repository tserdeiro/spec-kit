from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spec_kit_linear.lifecycle_registry import (
    MANAGED_LIFECYCLE_COMMAND,
    MANAGED_LIFECYCLE_EVENTS,
    load_registry,
    registry_diagnostics,
)


def _entry(extension: str, command: str, *, enabled: bool = True) -> dict[str, object]:
    return {"extension": extension, "command": command, "enabled": enabled, "optional": True, "priority": "20", "prompt": "?", "description": "", "condition": None}


def _fully_registered_registry(*, enabled: bool = True) -> dict[str, object]:
    return {
        "installed": ["git", "linear"],
        "hooks": {event: [_entry("linear", MANAGED_LIFECYCLE_COMMAND, enabled=enabled)] for event in MANAGED_LIFECYCLE_EVENTS},
    }


class LifecycleRegistryParsingTests(unittest.TestCase):
    def test_load_registry_returns_none_when_the_file_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_registry(Path(tmp)))

    def test_load_registry_parses_a_real_spec_kit_style_file(self) -> None:
        content = """\
installed:
- git
settings:
  auto_execute_hooks: true
hooks:
  after_specify:
  - extension: git
    command: speckit.git.commit
    enabled: true
    optional: true
    priority: 10
    prompt: Commit specification changes?
    description: Auto-commit after specification
    condition: null
  after_plan:
  - extension: git
    command: speckit.git.commit
    enabled: true
    optional: true
    priority: 10
    prompt: Commit plan changes?
    description: Auto-commit after implementation planning
    condition: null
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".specify").mkdir()
            (root / ".specify" / "extensions.yml").write_text(content, encoding="utf-8")

            registry = load_registry(root)

        self.assertIsNotNone(registry)
        self.assertEqual(registry["installed"], ["git"])
        self.assertEqual(registry["settings"], {"auto_execute_hooks": True})
        after_specify = registry["hooks"]["after_specify"]
        self.assertEqual(len(after_specify), 1)
        self.assertEqual(after_specify[0]["extension"], "git")
        self.assertEqual(after_specify[0]["command"], "speckit.git.commit")
        self.assertIs(after_specify[0]["enabled"], True)
        self.assertIsNone(after_specify[0]["condition"])

    def test_load_registry_returns_none_for_unreadable_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".specify").mkdir()
            (root / ".specify" / "extensions.yml").write_bytes(b"\xff\xfe\x00\x01")

            self.assertIsNone(load_registry(root))


class LifecycleRegistryDiagnosticsTests(unittest.TestCase):
    def test_missing_registry_file_is_informational(self) -> None:
        diagnostics = registry_diagnostics(None, lifecycle_enabled=True)
        self.assertEqual([item.code for item in diagnostics], ["lifecycle_registry_missing"])
        self.assertEqual(diagnostics[0].severity, "info")

    def test_fully_registered_and_enabled_matches_cleanly(self) -> None:
        diagnostics = registry_diagnostics(_fully_registered_registry(enabled=True), lifecycle_enabled=True)
        self.assertEqual([item.code for item in diagnostics], ["lifecycle_registry_ok"])

    def test_unregistered_events_are_reported(self) -> None:
        registry = {"installed": ["git"], "hooks": {"after_specify": [_entry("git", "speckit.git.commit")]}}

        diagnostics = registry_diagnostics(registry, lifecycle_enabled=True)

        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "lifecycle_registry_unregistered")
        self.assertEqual(diagnostics[0].severity, "warning")
        for event in MANAGED_LIFECYCLE_EVENTS:
            self.assertIn(event, diagnostics[0].message)

    def test_reinstall_divergence_is_reported_when_gate_disabled_but_registry_enabled(self) -> None:
        diagnostics = registry_diagnostics(_fully_registered_registry(enabled=True), lifecycle_enabled=False)

        self.assertEqual([item.code for item in diagnostics], ["lifecycle_registry_divergence"])
        self.assertEqual(diagnostics[0].severity, "info")

    def test_no_divergence_reported_when_registry_and_gate_both_disabled(self) -> None:
        diagnostics = registry_diagnostics(_fully_registered_registry(enabled=False), lifecycle_enabled=False)

        self.assertEqual([item.code for item in diagnostics], ["lifecycle_registry_ok"])

    def test_missing_and_divergent_events_are_both_reported(self) -> None:
        registry = _fully_registered_registry(enabled=True)
        missing_event = MANAGED_LIFECYCLE_EVENTS[-1]
        del registry["hooks"][missing_event]

        diagnostics = registry_diagnostics(registry, lifecycle_enabled=False)

        self.assertEqual({item.code for item in diagnostics}, {"lifecycle_registry_unregistered", "lifecycle_registry_divergence"})
        unregistered = next(item for item in diagnostics if item.code == "lifecycle_registry_unregistered")
        self.assertIn(missing_event, unregistered.message)


class ManifestDerivationTests(unittest.TestCase):
    def test_the_managed_events_derive_from_the_manifest(self) -> None:
        # One source of truth: the events come from extension.yml's hooks
        # section (a hardcoded copy once warned about four pruned hooks).
        import re
        from pathlib import Path

        manifest = Path(__file__).resolve().parents[2] / "extension.yml"
        hooks_block = manifest.read_text(encoding="utf-8").split("\nhooks:\n", 1)[1]
        declared = []
        for line in hooks_block.splitlines():
            if line and not line.startswith(" "):
                break
            match = re.match(r"^  (\w+):\s*$", line)
            if match:
                declared.append(match.group(1))
        self.assertEqual(tuple(declared), MANAGED_LIFECYCLE_EVENTS)
        self.assertEqual(MANAGED_LIFECYCLE_EVENTS, ("after_plan", "after_tasks"))

    def test_the_lifecycle_hooks_ship_automatic(self) -> None:
        # "Linear como espejo automatico": a consumer install must register
        # after_plan/after_tasks as automatic, not as a question -- a manual
        # registry edit is overwritten by every bundle update.
        from pathlib import Path

        manifest = Path(__file__).resolve().parents[2] / "extension.yml"
        hooks_block = manifest.read_text(encoding="utf-8").split("\nhooks:\n", 1)[1].split("\ntags:", 1)[0]
        self.assertEqual(hooks_block.count("optional: false"), 2)
        self.assertNotIn("optional: true", hooks_block)
