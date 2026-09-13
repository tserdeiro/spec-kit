from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.errors import EXIT_ENGINE, AppError
from spec_kit_code_review.ocr import (
    ADAPTER_VERSION,
    SUPPORTED_SCHEMA_VERSION,
    PreviewResult,
    MINIMAL_CONFIG,
    OCR_CONFIG_ENV,
    Ocr,
    parse_preview,
    parse_rules,
    verify_scope_against_git,
    write_minimal_config,
)
from tests.support.fixtures import install_fake_ocr


def _preview_json(**overrides) -> str:
    payload = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "mode": "range",
        "repository": "/repo",
        "from": "a" * 40,
        "to": "b" * 40,
        "merge_base": "a" * 40,
        "total_files": 3,
        "reviewable_count": 2,
        "excluded_count": 1,
        "total_insertions": 2,
        "total_deletions": 0,
        "reviewable_files": [
            {"path": "src/module.py", "status": "modified", "insertions": 1, "deletions": 0},
            {"path": "tests/test_module.py", "status": "added", "insertions": 1, "deletions": 0},
        ],
        "excluded_files": [
            {
                "path": "docs/guide.md",
                "status": "modified",
                "insertions": 0,
                "deletions": 0,
                "exclude_reason": "documentation is out of scope",
            }
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


class PreviewParsingTests(unittest.TestCase):
    """The scope is read strictly from the engine's JSON."""

    def test_the_documented_shape_is_read_completely(self) -> None:
        raw = _preview_json()
        result = parse_preview(raw)

        self.assertEqual(result.mode, "range")
        self.assertEqual(result.merge_base, "a" * 40)
        self.assertEqual(result.included_paths, ("src/module.py", "tests/test_module.py"))
        self.assertEqual([entry.path for entry in result.excluded], ["docs/guide.md"])
        self.assertEqual(result.excluded[0].reason, "documentation is out of scope")
        self.assertEqual(result.adapter_version, ADAPTER_VERSION)
        self.assertEqual(result.raw, raw)

    def test_status_and_line_counts_are_carried_through(self) -> None:
        result = parse_preview(_preview_json())

        included = {entry.path: entry for entry in result.entries if entry.included}
        self.assertEqual(included["src/module.py"].status, "modified")
        self.assertEqual(included["src/module.py"].insertions, 1)
        self.assertEqual(included["tests/test_module.py"].status, "added")

    def test_workspace_mode_has_no_range(self) -> None:
        result = parse_preview(_preview_json(mode="workspace", **{"from": "", "to": "", "merge_base": ""}))

        self.assertEqual(result.mode, "workspace")
        self.assertIsNone(result.from_ref)
        self.assertIsNone(result.merge_base)

    def test_an_empty_scope_is_a_legitimate_answer(self) -> None:
        # An empty diff, or a diff where everything was excluded, is not an error.
        result = parse_preview(
            _preview_json(total_files=0, reviewable_count=0, excluded_count=0, reviewable_files=[], excluded_files=[])
        )

        self.assertEqual(result.included_paths, ())
        self.assertEqual(result.entries, ())

    def test_missing_output_is_never_guessed_at(self) -> None:
        # The one failure mode that would silently shrink a review.
        for raw in ("", "   \n", "not json at all", "[]", "42"):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(AppError) as caught:
                    parse_preview(raw)
                self.assertEqual(caught.exception.code, EXIT_ENGINE)
                self.assertEqual(caught.exception.diagnostics[0].code, "engine_output_unparseable")

    def test_the_failure_points_at_the_preserved_raw_output(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_preview("something entirely different")

        self.assertIn("preserved verbatim in the session evidence", caught.exception.diagnostics[0].message)

    def test_an_unverified_schema_version_is_refused(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_preview(_preview_json(schema_version="99"))

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("schema_version", caught.exception.diagnostics[0].message)

    def test_a_path_escaping_the_repository_is_refused(self) -> None:
        # Doc "Contenido no confiable": scope paths are validated before they
        # reach any later invocation, and a bad one is a failure, never a
        # silently dropped file.
        for hostile in ("../../etc/passwd", "/etc/passwd"):
            with self.subTest(path=hostile):
                with self.assertRaises(AppError) as caught:
                    parse_preview(
                        _preview_json(reviewable_files=[{"path": hostile, "status": "added"}], excluded_files=[])
                    )
                self.assertEqual(caught.exception.code, EXIT_ENGINE)
                self.assertEqual(caught.exception.diagnostics[0].code, "engine_path_invalid")

    def test_an_entry_with_no_path_is_a_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_preview(_preview_json(reviewable_files=[{"status": "added"}], excluded_files=[]))

        self.assertEqual(caught.exception.code, EXIT_ENGINE)

    def test_a_file_listed_twice_is_counted_once(self) -> None:
        result = parse_preview(
            _preview_json(
                reviewable_files=[
                    {"path": "src/module.py", "status": "modified"},
                    {"path": "src/module.py", "status": "modified"},
                ],
                excluded_files=[],
            )
        )

        self.assertEqual(result.included_paths, ("src/module.py",))


class AdversarialFileNameTests(unittest.TestCase):
    """File names a pull request chooses, and the parser must survive.

    A JSON string field carries any name verbatim -- there is no delimiter for
    a candidate to break out of -- so what matters here is that validation
    still runs, and that an exclusion keyword in a name is never confused with
    the ``exclude_reason`` field that actually carries the state.
    """

    HOSTILE_NAMES = (
        "excluded.py",
        "src/excluded.py",
        "filtered.go",
        "skipped.rs",
        "ignored.py",
        "__init__.py",
        "_private_.py",
        "src/my file.py",
        "docs/guía de estilo.md",
        "src/файл.py",
        "a.py",
        "vendor/a.py",
        "README.md",
        "docs/README.md",
    )

    def _preview_for(self, *paths: str) -> str:
        return _preview_json(
            reviewable_files=[{"path": path, "status": "modified"} for path in paths], excluded_files=[]
        )

    def test_every_hostile_name_stays_in_the_scope_unchanged(self) -> None:
        for name in self.HOSTILE_NAMES:
            with self.subTest(name=name):
                result = parse_preview(self._preview_for(name))
                self.assertEqual(result.included_paths, (name,), f"{name} did not survive the parser")

    def test_all_of_them_at_once_are_all_reported(self) -> None:
        result = parse_preview(self._preview_for(*self.HOSTILE_NAMES))

        self.assertEqual(result.included_paths, self.HOSTILE_NAMES)

    def test_an_exclusion_keyword_in_the_name_does_not_exclude_the_file(self) -> None:
        result = parse_preview(self._preview_for("src/excluded.py", "filtered.go"))

        self.assertEqual(result.included_paths, ("src/excluded.py", "filtered.go"))
        self.assertEqual(result.excluded, ())

    def test_only_the_excluded_files_array_excludes(self) -> None:
        raw = _preview_json(
            reviewable_files=[],
            excluded_files=[{"path": "excluded.py", "status": "modified", "exclude_reason": "vendored"}],
        )

        result = parse_preview(raw)

        self.assertEqual(result.included_paths, ())
        self.assertEqual(result.excluded[0].path, "excluded.py")
        self.assertEqual(result.excluded[0].reason, "vendored")

    def test_an_option_shaped_name_is_refused_rather_than_passed_on(self) -> None:
        # A file called `--rule` would otherwise become a *flag* of the very
        # invocation that decides which rules apply.
        for hostile in ("--rule", "-rf", "--repo"):
            with self.subTest(name=hostile):
                with self.assertRaises(AppError) as caught:
                    parse_preview(self._preview_for(hostile))
                self.assertEqual(caught.exception.code, EXIT_ENGINE)
                self.assertEqual(caught.exception.diagnostics[0].code, "engine_path_invalid")

    def test_a_path_with_a_space_is_not_truncated(self) -> None:
        result = parse_preview(self._preview_for("src/my file.py"))

        self.assertEqual(result.included_paths, ("src/my file.py",))

    def test_underscored_names_are_unaffected(self) -> None:
        result = parse_preview(self._preview_for("__init__.py", "_private_.py"))

        self.assertEqual(result.included_paths, ("__init__.py", "_private_.py"))

    def test_a_contradictory_duplicate_is_a_failure_not_a_coin_toss(self) -> None:
        raw = _preview_json(
            reviewable_files=[{"path": "a.py", "status": "modified"}],
            excluded_files=[{"path": "a.py", "status": "modified", "exclude_reason": "vendored"}],
        )

        with self.assertRaises(AppError) as caught:
            parse_preview(raw)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("both included and excluded", str(caught.exception))


class ScopeCrossVerificationTests(unittest.TestCase):
    """The invariant that does not depend on the engine's output format."""

    def _preview(self, *paths: str) -> "PreviewResult":
        return parse_preview(
            _preview_json(reviewable_files=[{"path": path, "status": "modified"} for path in paths], excluded_files=[])
        )

    def test_an_exact_match_passes(self) -> None:
        verify_scope_against_git(self._preview("a.py", "b.py"), ["b.py", "a.py"])

    def test_a_file_the_engine_never_mentioned_is_a_failure(self) -> None:
        # The silent-shrink failure: a file would go unreviewed and nobody told.
        with self.assertRaises(AppError) as caught:
            verify_scope_against_git(self._preview("a.py"), ["a.py", "secret.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("secret.py", caught.exception.diagnostics[0].message)

    def test_a_file_git_does_not_have_is_also_a_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            verify_scope_against_git(self._preview("a.py", "phantom.py"), ["a.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("phantom.py", caught.exception.diagnostics[0].message)

    def test_excluded_files_count_as_reported(self) -> None:
        preview = parse_preview(
            _preview_json(
                reviewable_files=[{"path": "a.py", "status": "modified"}],
                excluded_files=[{"path": "b.py", "status": "modified", "exclude_reason": "vendored"}],
            )
        )

        verify_scope_against_git(preview, ["a.py", "b.py"])

    def test_an_empty_diff_and_an_empty_scope_agree(self) -> None:
        verify_scope_against_git(
            parse_preview(_preview_json(total_files=0, reviewable_count=0, excluded_count=0, reviewable_files=[], excluded_files=[])),
            [],
        )

    def test_the_message_says_what_to_do_about_a_mismatch(self) -> None:
        with self.assertRaises(AppError) as caught:
            verify_scope_against_git(self._preview("a.py"), ["a.py", "b.py"])

        remedy = caught.exception.diagnostics[-1].message
        self.assertIn("never run on a guess", remedy)
        self.assertIn("re-verified against the pinned binary", remedy)


def _rule_json(*groups: dict) -> str:
    return json.dumps({"schema_version": SUPPORTED_SCHEMA_VERSION, "groups": list(groups)})


class RuleParsingTests(unittest.TestCase):
    """The rule cascade is read from the engine's rule groups."""

    def _raw(self) -> str:
        return _rule_json(
            {
                "group_id": 1,
                "source": "custom",
                "pattern": "src/**",
                "files": ["src/module.py"],
                "rule": "Production code must validate its inputs.",
            },
            {
                "group_id": 2,
                "source": "custom",
                "pattern": "tests/**",
                "files": ["tests/test_module.py"],
                "rule": "Every behaviour change needs a failing test first.",
            },
        )

    def test_each_requested_path_gets_its_rules(self) -> None:
        result = parse_rules(self._raw(), expected_paths=["src/module.py", "tests/test_module.py"])

        self.assertEqual([assignment.path for assignment in result.assignments], ["src/module.py", "tests/test_module.py"])
        self.assertEqual(result.assignments[0].rules, ("Production code must validate its inputs.",))
        self.assertEqual(result.assignments[1].rules, ("Every behaviour change needs a failing test first.",))

    def test_the_order_follows_the_request_not_the_output(self) -> None:
        result = parse_rules(self._raw(), expected_paths=["tests/test_module.py", "src/module.py"])

        self.assertEqual([assignment.path for assignment in result.assignments], ["tests/test_module.py", "src/module.py"])

    def test_a_file_in_two_groups_gets_both_rules(self) -> None:
        raw = _rule_json(
            {"group_id": 1, "source": "system", "pattern": "**/*.py", "files": ["src/module.py"], "rule": "System rule."},
            {"group_id": 2, "source": "custom", "pattern": "src/**", "files": ["src/module.py"], "rule": "Custom rule."},
        )

        result = parse_rules(raw, expected_paths=["src/module.py"])

        self.assertEqual(result.assignments[0].rules, ("System rule.", "Custom rule."))

    def test_output_mentioning_none_of_the_requested_files_is_a_failure(self) -> None:
        raw = _rule_json({"group_id": 1, "source": "custom", "pattern": "**", "files": ["other/file.py"], "rule": "x"})

        with self.assertRaises(AppError) as caught:
            parse_rules(raw, expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertEqual(caught.exception.diagnostics[0].code, "engine_output_unparseable")

    def test_empty_output_for_a_non_empty_request_is_a_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_rules("", expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)

    def test_no_request_means_no_invocation_and_no_failure(self) -> None:
        self.assertEqual(parse_rules("", expected_paths=[]).assignments, ())

    def test_an_unverified_schema_version_is_refused(self) -> None:
        raw = json.dumps({"schema_version": "99", "groups": []})

        with self.assertRaises(AppError) as caught:
            parse_rules(raw, expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("schema_version", caught.exception.diagnostics[0].message)


class OverlappingPathTests(unittest.TestCase):
    """Rule groups anchored on paths that contain one another."""

    def _raw(self) -> str:
        return _rule_json(
            {"group_id": 1, "source": "custom", "pattern": "vendor/**", "files": ["vendor/a.py"], "rule": "Vendored code is reviewed for licence only."},
            {"group_id": 2, "source": "custom", "pattern": "*.py", "files": ["a.py"], "rule": "Production code must validate its inputs."},
            {"group_id": 3, "source": "custom", "pattern": "docs/**", "files": ["docs/README.md"], "rule": "Documentation must match the code."},
            {"group_id": 4, "source": "custom", "pattern": "README.md", "files": ["README.md"], "rule": "The front page must stay accurate."},
        )

    def test_a_shorter_path_does_not_swallow_a_longer_one(self) -> None:
        result = parse_rules(self._raw(), expected_paths=["a.py", "vendor/a.py"])

        assignments = {assignment.path: assignment.rules for assignment in result.assignments}
        self.assertEqual(assignments["a.py"], ("Production code must validate its inputs.",))
        self.assertEqual(assignments["vendor/a.py"], ("Vendored code is reviewed for licence only.",))

    def test_the_everyday_readme_case(self) -> None:
        result = parse_rules(self._raw(), expected_paths=["README.md", "docs/README.md"])

        assignments = {assignment.path: assignment.rules for assignment in result.assignments}
        self.assertEqual(assignments["README.md"], ("The front page must stay accurate.",))
        self.assertEqual(assignments["docs/README.md"], ("Documentation must match the code.",))

    def test_a_partial_answer_is_a_failure_not_a_quiet_gap(self) -> None:
        # "this file has no rules" and "the engine never mentioned this file"
        # must stay distinguishable.
        with self.assertRaises(AppError) as caught:
            parse_rules(self._raw(), expected_paths=["a.py", "never/mentioned.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("never/mentioned.py", str(caught.exception))

    def test_a_compiled_variant_is_not_the_source_path(self) -> None:
        raw = _rule_json({"group_id": 1, "source": "custom", "pattern": "*", "files": ["src/module.pyc"], "rule": "A rule for the compiled file."})

        with self.assertRaises(AppError) as caught:
            parse_rules(raw, expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)


class EngineInvocationTests(unittest.TestCase):
    """Argv, isolation, and failure mapping, against the fake engine."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.log = self.workspace / "invocations.log"
        self.state = {
            "files": [
                {"path": "src/module.py"},
                {"path": "docs/guide.md", "included": False, "reason": "documentation"},
            ],
            "rules": {"src/module.py": ["Validate every input."]},
            "record_invocations": str(self.log),
        }

    def _engine(self, **overrides) -> Ocr:
        state = {**self.state, **overrides}
        executable, environment = install_fake_ocr(self.workspace / "bin", state)
        config_path = write_minimal_config(self.workspace / "evidence" / "ocr-config.json")
        # Deliberately *not* injecting anything the production path would not
        # pass: the fake finds its state beside its own executable.
        return Ocr(executable, timeout=30, config_path=config_path)

    def _invocations(self) -> list[list[str]]:
        if not self.log.is_file():
            return []
        return [line.split() for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_preview_passes_the_documented_argv(self) -> None:
        engine = self._engine()

        engine.delegate_preview(
            self.workspace,
            from_ref="a" * 40,
            to_ref="b" * 40,
            rule_path=self.workspace / "rule.json",
        )

        argv = self._invocations()[0]
        self.assertEqual(argv[:2], ["delegate", "preview"])
        self.assertIn("--repo", argv)
        self.assertIn("--format", argv)
        self.assertEqual(argv[argv.index("--format") + 1], "json")
        self.assertEqual(argv[argv.index("--from") + 1], "a" * 40)
        self.assertEqual(argv[argv.index("--to") + 1], "b" * 40)
        self.assertIn("--rule", argv)
        self.assertNotIn("--background", argv)
        self.assertNotIn("-B", argv)

    def test_the_workspace_mode_omits_the_range(self) -> None:
        engine = self._engine()

        engine.delegate_preview(self.workspace)

        argv = self._invocations()[0]
        self.assertNotIn("--from", argv)
        self.assertNotIn("--to", argv)

    def test_half_a_range_is_refused(self) -> None:
        engine = self._engine()

        with self.assertRaises(AppError) as caught:
            engine.delegate_preview(self.workspace, from_ref="a" * 40)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)

    def test_the_background_flag_can_never_be_passed(self) -> None:
        engine = self._engine()

        with self.assertRaises(AppError) as caught:
            engine.run("delegate", "preview", "--background")

        self.assertEqual(caught.exception.diagnostics[0].code, "engine_background")

    def test_rule_paths_are_positional_after_the_flag_list(self) -> None:
        paths = [f"src/file{index}.py" for index in range(5)]
        engine = self._engine(rules={path: [f"rule for {path}"] for path in paths})

        result = engine.delegate_rule(self.workspace, paths, rule_path=self.workspace / "rule.json")

        self.assertEqual([assignment.path for assignment in result.assignments], paths)
        rule_invocations = [argv for argv in self._invocations() if argv[:2] == ["delegate", "rule"]]
        self.assertEqual(len(rule_invocations), 1, "every selected path goes into one delegate rule call")
        argv = rule_invocations[0]
        self.assertIn("--format", argv)
        # Paths come after `--`, so none can be read as an option.
        self.assertLess(argv.index("--"), min(argv.index(path) for path in paths))

    def test_the_same_input_produces_the_same_scope_twice(self) -> None:
        engine = self._engine()

        first = engine.delegate_preview(self.workspace, from_ref="a" * 40, to_ref="b" * 40)
        second = engine.delegate_preview(self.workspace, from_ref="a" * 40, to_ref="b" * 40)

        self.assertEqual(first.as_dict(), second.as_dict())

    def test_a_non_zero_exit_is_an_engine_failure_with_redacted_stderr(self) -> None:
        engine = self._engine(preview_failure="exit-1")

        with self.assertRaises(AppError) as caught:
            engine.delegate_preview(self.workspace, from_ref="a" * 40, to_ref="b" * 40)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertEqual(caught.exception.diagnostics[0].code, "engine_failed")
        self.assertIn("the engine says no", caught.exception.diagnostics[0].message)

    def test_an_unrecognizable_shape_is_an_engine_failure(self) -> None:
        engine = self._engine(preview_failure="unknown-format")

        with self.assertRaises(AppError) as caught:
            engine.delegate_preview(self.workspace, from_ref="a" * 40, to_ref="b" * 40)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)

    def test_an_unverified_schema_version_from_the_engine_is_an_engine_failure(self) -> None:
        engine = self._engine(preview_failure="bad-schema")

        with self.assertRaises(AppError) as caught:
            engine.delegate_preview(self.workspace, from_ref="a" * 40, to_ref="b" * 40)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)

    def test_the_generated_config_isolates_the_operators_own(self) -> None:
        engine = self._engine()

        environment = engine._environment_for_call()

        self.assertEqual(environment[OCR_CONFIG_ENV], str(engine.config_path))
        payload = json.loads(Path(engine.config_path).read_text(encoding="utf-8"))
        self.assertEqual(payload, MINIMAL_CONFIG)
        # The extension never enables OCR telemetry, and never force-disables a
        # decision the operator made.
        self.assertNotIn("OCR_ENABLE_TELEMETRY", environment)
        self.assertNotIn("telemetry", json.dumps(payload).lower())

    def test_the_engine_starts_under_the_environment_it_is_given(self) -> None:
        # The real engine is an npm wrapper (`#!/usr/bin/env node`), so an
        # environment without PATH would stop it before it printed anything. The
        # fake has the same shape: its shebang needs a PATH lookup too.
        engine = self._engine()

        preview = engine.delegate_preview(self.workspace, from_ref="a" * 40, to_ref="b" * 40)

        self.assertEqual(preview.included_paths, ("src/module.py",))
        self.assertIn("PATH", engine._environment_for_call())

    def test_the_environment_is_the_enumerated_set_and_nothing_else(self) -> None:
        engine = Ocr(
            self.workspace / "bin" / "ocr",
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": "/home/operator",
                "LANG": "C",
                "SPECKIT_CODE_REVIEW_STRICT": "true",
                "AWS_SECRET_ACCESS_KEY": "should-never-travel",
                "GITHUB_TOKEN": "ghp_should-never-travel",
            },
            config_path=self.workspace / "config.json",
        )

        environment = engine._environment_for_call()

        self.assertEqual(
            set(environment),
            {"PATH", "HOME", "LANG", "OCR_CONFIG_PATH"},
            "only the enumerated variables reach the engine",
        )

    def test_no_model_credential_is_ever_defined(self) -> None:
        # Built from a *populated* environment, so the assertion means something:
        # these are present in the source and must not be forwarded.
        engine = Ocr(
            self.workspace / "bin" / "ocr",
            environment={
                "PATH": "/usr/bin:/bin",
                "ANTHROPIC_API_KEY": "sk-should-never-travel",
                "OCR_LLM_TOKEN": "should-never-travel",
                "OCR_LLM_URL": "https://should-never-travel.invalid",
                "OCR_USE_ANTHROPIC": "1",
                "OCR_ENABLE_TELEMETRY": "1",
                "GITHUB_TOKEN": "ghp_should-never-travel",
            },
        )

        environment = engine._environment_for_call()

        for forbidden in (
            "ANTHROPIC_API_KEY",
            "OCR_LLM_TOKEN",
            "OCR_LLM_URL",
            "OCR_USE_ANTHROPIC",
            "OCR_ENABLE_TELEMETRY",
            "GITHUB_TOKEN",
        ):
            with self.subTest(variable=forbidden):
                self.assertNotIn(forbidden, environment)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
