from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.config import (
    LOCAL_CONFIG_FILENAME,
    ROOT_CONFIG_FILENAME,
    RULE_RELATIVE_PATH,
    dump_yaml_subset,
    load_config,
    load_yaml_subset,
    resolve_config_path,
    shared_config_document,
)
from spec_kit_code_review.env_files import EnvSnapshot
from spec_kit_code_review.errors import EXIT_CONFIGURATION, AppError
from tests.support.fixtures import CONSUMER_FIXTURE, copy_consumer_fixture, isolate_operator_global_env


def _snapshot(**values: str) -> EnvSnapshot:
    return EnvSnapshot(values=dict(values), trusted=dict(values))


class YamlSubsetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _write(self, text: str) -> Path:
        path = self.root / "document.yml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_nested_mappings_scalars_and_scalar_lists(self) -> None:
        path = self._write(
            'schema_version: "1.0"\n'
            "budget:\n"
            "  limit: 400\n"
            "  executable_globs:\n"
            '    - "src/**"\n'
            '    - "tests/**"\n'
            "packet:\n"
            "  include_pr_body: true\n"
            "  missing: null\n"
        )

        document = load_yaml_subset(path)

        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(document["budget"]["limit"], 400)
        self.assertEqual(document["budget"]["executable_globs"], ["src/**", "tests/**"])
        self.assertIs(document["packet"]["include_pr_body"], True)
        self.assertIsNone(document["packet"]["missing"])

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        path = self._write('# a comment\nschema_version: "1.0"  # trailing\n\nreview:\n  language: "English"\n')

        document = load_yaml_subset(path)

        self.assertEqual(document["review"]["language"], "English")

    def test_tabs_duplicates_and_odd_indentation_are_rejected(self) -> None:
        for text in ("a:\n\tb: 1\n", 'a: "1"\na: "2"\n', "a:\n   b: 1\n", "- item\n"):
            with self.subTest(text=text):
                with self.assertRaises(AppError) as caught:
                    load_yaml_subset(self._write(text))
                self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_dump_round_trips_through_the_loader(self) -> None:
        document = {"engine": {"mode": "delegate", "timeout_seconds": 300}, "budget": {"executable_globs": ["src/**"]}}
        path = self._write(dump_yaml_subset(document))

        self.assertEqual(load_yaml_subset(path), document)


class ConfigResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary, self.root = copy_consumer_fixture()
        self.addCleanup(self.temporary.cleanup)

    def test_root_file_is_the_default_source(self) -> None:
        path, source = resolve_config_path(self.root)

        self.assertEqual(path, self.root / ROOT_CONFIG_FILENAME)
        self.assertEqual(source, "root")

    def test_flag_beats_environment_beats_root(self) -> None:
        environment = _snapshot(SPECKIT_CODE_REVIEW_CONFIG="/from/environment.yml")

        self.assertEqual(resolve_config_path(self.root, explicit="/from/flag.yml", environment=environment)[0], Path("/from/flag.yml"))
        self.assertEqual(resolve_config_path(self.root, environment=environment)[0], Path("/from/environment.yml"))

    def test_fixture_configuration_loads_with_its_values(self) -> None:
        config = load_config(self.root)

        self.assertEqual(config.shared_path, self.root / ROOT_CONFIG_FILENAME)
        self.assertEqual(config.get("engine", "mode"), "delegate")
        self.assertEqual(config.get("budget", "limit"), 400)
        self.assertEqual(config.get("publish", "event"), "request-changes")
        self.assertEqual(config.get("repository", "github"), "tserdeiro/consumer")
        self.assertEqual(len(config.sha256), 64)

    def test_defaults_apply_and_warn_when_the_file_is_absent(self) -> None:
        (self.root / ROOT_CONFIG_FILENAME).unlink()

        config = load_config(self.root)

        self.assertIsNone(config.shared_path)
        self.assertEqual(config.get("publish", "event"), "request-changes")
        self.assertEqual([diagnostic.code for diagnostic in config.diagnostics], ["config_absent"])

    def test_an_explicitly_selected_missing_file_is_an_error(self) -> None:
        with self.assertRaises(AppError) as caught:
            load_config(self.root, explicit=str(self.root / "absent.yml"))

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_local_overlay_wins_over_the_shared_file(self) -> None:
        (self.root / LOCAL_CONFIG_FILENAME).write_text('evidence:\n  root: "/tmp/evidence"\n', encoding="utf-8")

        config = load_config(self.root)

        self.assertEqual(config.local_path, self.root / LOCAL_CONFIG_FILENAME)
        self.assertEqual(config.get("evidence", "root"), "/tmp/evidence")
        self.assertEqual(config.get("evidence", "keep_sessions"), 20)

    def test_configuration_digest_changes_with_the_content(self) -> None:
        first = load_config(self.root).sha256
        (self.root / LOCAL_CONFIG_FILENAME).write_text('review:\n  severity_floor: "major"\n', encoding="utf-8")

        self.assertNotEqual(first, load_config(self.root).sha256)


class ConfigValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_operator_global_env(self)
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _shared(self, text: str) -> None:
        (self.root / ROOT_CONFIG_FILENAME).write_text(text, encoding="utf-8")

    def test_secrets_in_the_committed_file_are_rejected(self) -> None:
        for text in (
            'schema_version: "1.0"\ngithub:\n  token: "ghp_x"\n',
            'schema_version: "1.0"\nlocal:\n  operator_id: "someone"\n',
            'schema_version: "1.0"\nengine:\n  api_key: "sk-x"\n',
        ):
            with self.subTest(text=text):
                self._shared(text)
                with self.assertRaises(AppError) as caught:
                    load_config(self.root)
                self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_evidence_root_is_rejected_in_the_shared_file(self) -> None:
        self._shared('schema_version: "1.0"\nevidence:\n  root: "/tmp/evidence"\n')

        with self.assertRaises(AppError) as caught:
            load_config(self.root)

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_executable_paths_are_rejected_in_the_local_file(self) -> None:
        self._shared('schema_version: "1.0"\n')
        (self.root / LOCAL_CONFIG_FILENAME).write_text('local:\n  ocr_bin: "/tmp/ocr"\n', encoding="utf-8")

        with self.assertRaises(AppError) as caught:
            load_config(self.root)

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_publish_event_approve_is_rejected_as_configuration(self) -> None:
        self._shared('schema_version: "1.0"\npublish:\n  event: "approve"\n')

        with self.assertRaises(AppError) as caught:
            load_config(self.root)

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)
        self.assertIn("approve", str(caught.exception))

    def test_publish_event_ceiling_accepts_only_the_two_documented_values(self) -> None:
        for event, expected in (("comment", None), ("request-changes", None), ("merge", EXIT_CONFIGURATION)):
            with self.subTest(event=event):
                self._shared(f'schema_version: "1.0"\npublish:\n  event: "{event}"\n')
                if expected is None:
                    self.assertEqual(load_config(self.root).get("publish", "event"), event)
                else:
                    with self.assertRaises(AppError) as caught:
                        load_config(self.root)
                    self.assertEqual(caught.exception.code, expected)

    def test_schema_version_must_match(self) -> None:
        self._shared('schema_version: "2.0"\n')

        with self.assertRaises(AppError) as caught:
            load_config(self.root)

        self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)

    def test_numeric_fields_must_be_positive_integers(self) -> None:
        for text in ('schema_version: "1.0"\nbudget:\n  limit: 0\n', 'schema_version: "1.0"\nbudget:\n  limit: "many"\n'):
            with self.subTest(text=text):
                self._shared(text)
                with self.assertRaises(AppError) as caught:
                    load_config(self.root)
                self.assertEqual(caught.exception.code, EXIT_CONFIGURATION)


class SharedDocumentTests(unittest.TestCase):
    def test_install_document_is_valid_and_binds_the_repository(self) -> None:
        document = shared_config_document(repository="tserdeiro/spec-kit", remote="upstream", slug=None)

        self.assertEqual(document["repository"], {"slug": "spec-kit", "github": "tserdeiro/spec-kit", "remote": "upstream"})
        self.assertEqual(document["engine"]["ocr_version"], "v1.8.3")
        self.assertNotIn("root", document["evidence"])

    def test_the_shipped_template_matches_the_documented_rule_path(self) -> None:
        self.assertEqual(RULE_RELATIVE_PATH, ".opencodereview/rule.json")
        self.assertTrue((CONSUMER_FIXTURE / RULE_RELATIVE_PATH).is_file())


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
