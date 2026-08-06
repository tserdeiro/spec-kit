from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spec_kit_code_review.errors import EXIT_ENGINE, AppError
from spec_kit_code_review.ocr import (
    ADAPTER_VERSION,
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


PREVIEW = """\
# Delegate preview

- **Mode**: range
- **From**: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
- **To**: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- **Merge base**: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

## Files

- `src/module.py`
- `tests/test_module.py`
- `docs/guide.md` — excluded: documentation is out of scope
"""


class PreviewParsingTests(unittest.TestCase):
    """The scope is read strictly; presentation is read loosely."""

    def test_the_documented_shape_is_read_completely(self) -> None:
        result = parse_preview(PREVIEW)

        self.assertEqual(result.mode, "range")
        self.assertEqual(result.merge_base, "a" * 40)
        self.assertEqual(result.included_paths, ("src/module.py", "tests/test_module.py"))
        self.assertEqual([entry.path for entry in result.excluded], ["docs/guide.md"])
        self.assertEqual(result.excluded[0].reason, "documentation is out of scope")
        self.assertEqual(result.adapter_version, ADAPTER_VERSION)
        self.assertEqual(result.raw, PREVIEW)

    def test_cosmetic_variation_does_not_change_the_scope(self) -> None:
        # Bullet style, emphasis, checkboxes, heading level and key casing are
        # presentation; the answer must not depend on them.
        variants = [
            PREVIEW,
            PREVIEW.replace("- `", "* `").replace("## Files", "### Selected files"),
            PREVIEW.replace("- `", "1. `").replace("**Mode**", "Mode"),
            PREVIEW.replace("- `", "- [x] `"),
            PREVIEW.replace("— excluded:", "(excluded:").replace("out of scope", "out of scope)"),
        ]
        for index, variant in enumerate(variants):
            with self.subTest(variant=index):
                result = parse_preview(variant)
                self.assertEqual(result.included_paths, ("src/module.py", "tests/test_module.py"))
                self.assertEqual([entry.path for entry in result.excluded], ["docs/guide.md"])

    def test_a_table_is_read_as_well_as_a_list(self) -> None:
        table = """\
# Delegate preview

## Files

| File | State | Reason |
| --- | --- | --- |
| src/module.py | included | |
| docs/guide.md | excluded | documentation |
"""

        result = parse_preview(table)

        self.assertEqual(result.included_paths, ("src/module.py",))
        self.assertEqual(result.excluded[0].reason, "documentation")

    def test_an_empty_scope_is_a_legitimate_answer(self) -> None:
        # An empty diff, or a diff where everything was excluded, is not an error.
        result = parse_preview("# Delegate preview\n\n## Files\n\n## Summary\n\nNothing to review.\n")

        self.assertEqual(result.included_paths, ())
        self.assertEqual(result.entries, ())

    def test_output_without_a_file_section_is_never_guessed_at(self) -> None:
        # The one failure mode that would silently shrink a review.
        for raw in (
            "Delegate preview complete. 3 entries considered.\n",
            "# Delegate preview\n\n- **Mode**: range\n- **From**: abc\n",
            "",
            "   \n",
        ):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(AppError) as caught:
                    parse_preview(raw)
                self.assertEqual(caught.exception.code, EXIT_ENGINE)
                self.assertEqual(caught.exception.diagnostics[0].code, "engine_output_unparseable")

    def test_the_failure_points_at_the_preserved_raw_output(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_preview("something entirely different\n")

        self.assertIn("preserved verbatim in the session evidence", caught.exception.diagnostics[0].message)

    def test_a_path_escaping_the_repository_is_refused(self) -> None:
        # Doc "Contenido no confiable": scope paths are validated before they
        # reach any later invocation, and a bad one is a failure, never a
        # silently dropped file.
        for hostile in ("../../etc/passwd", "/etc/passwd"):
            with self.subTest(path=hostile):
                with self.assertRaises(AppError) as caught:
                    parse_preview(f"# Preview\n\n## Files\n\n- `{hostile}`\n")
                self.assertEqual(caught.exception.code, EXIT_ENGINE)
                self.assertEqual(caught.exception.diagnostics[0].code, "engine_path_invalid")

    def test_prose_inside_the_file_section_is_a_failure_not_a_phantom_entry(self) -> None:
        # Conservation: every line of the file section produces exactly one
        # entry, or the shape is not the one this adapter knows how to read.
        # Guessing which lines are prose is how `"No files were excluded"`
        # became a file called `No`.
        with self.assertRaises(AppError) as caught:
            parse_preview("# Preview\n\n## Files\n\nThe engine considered the following entries.\n\n- `src/module.py`\n")

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("neither a list item nor a table row", caught.exception.message if hasattr(caught.exception, "message") else str(caught.exception))

    def test_a_file_listed_twice_is_counted_once(self) -> None:
        result = parse_preview("# Preview\n\n## Files\n\n- `src/module.py`\n- `src/module.py`\n")

        self.assertEqual(result.included_paths, ("src/module.py",))


class AdversarialFileNameTests(unittest.TestCase):
    """File names a pull request chooses, and the parser must survive.

    Every name below removed a file from the scope, corrupted it, or injected an
    option in an earlier version of this parser. A pull request picks its own
    file names, so each of these is a one-line attack.
    """

    HOSTILE_NAMES = (
        # Names containing an exclusion keyword: the state must come from the
        # annotation, never from the path.
        "excluded.py",
        "src/excluded.py",
        "filtered.go",
        "skipped.rs",
        "ignored.py",
        "src/ignored/module.py",
        "tests/test_excluded_paths.py",
        # Names Markdown unwrapping used to mangle.
        "__init__.py",
        "_private_.py",
        "**odd**.py",
        # Names with spaces and unicode.
        "src/my file.py",
        "docs/guía de estilo.md",
        "src/файл.py",
        # Overlapping prefixes and suffixes.
        "a.py",
        "vendor/a.py",
        "README.md",
        "docs/README.md",
    )

    def _preview_for(self, *paths: str) -> str:
        lines = ["# Delegate preview", "", "## Files", ""]
        lines.extend(f"- `{path}`" for path in paths)
        return "\n".join(lines) + "\n"

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

    def test_the_annotation_after_the_path_is_what_excludes(self) -> None:
        raw = "# Preview\n\n## Files\n\n- `excluded.py` — excluded: vendored\n"

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

    def test_a_name_that_cannot_be_delimited_is_refused_not_truncated(self) -> None:
        # A backtick inside the name closes its own span, so the line could mean
        # `a` or `a`b.py`. Truncating to the first would drop the file from the
        # review silently; this fails loudly instead.
        with self.assertRaises(AppError) as caught:
            parse_preview(self._preview_for("a`b.py"))

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertEqual(caught.exception.diagnostics[0].code, "engine_entry_ambiguous")

    def test_a_path_with_a_space_is_not_truncated(self) -> None:
        result = parse_preview(self._preview_for("src/my file.py"))

        self.assertEqual(result.included_paths, ("src/my file.py",))

    def test_underscored_names_are_not_renamed_by_unwrapping(self) -> None:
        result = parse_preview(self._preview_for("__init__.py", "_private_.py"))

        self.assertEqual(result.included_paths, ("__init__.py", "_private_.py"))

    def test_a_contradictory_duplicate_is_a_failure_not_a_coin_toss(self) -> None:
        raw = "# Preview\n\n## Files\n\n- `a.py` — excluded: vendored\n- `a.py`\n"

        with self.assertRaises(AppError) as caught:
            parse_preview(raw)

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("both included and excluded", str(caught.exception))

    def test_a_nested_heading_does_not_truncate_the_file_section(self) -> None:
        # A sub-grouping by directory or language is plausible in a format that
        # is still unverified; losing the files under it would be silent.
        raw = """\
# Delegate preview

## Files

### src

- `src/module.py`

### docs

- `docs/guide.md` — excluded: documentation

## Summary

Two entries considered.
"""

        result = parse_preview(raw)

        self.assertEqual(result.included_paths, ("src/module.py",))
        self.assertEqual([entry.path for entry in result.excluded], ["docs/guide.md"])

    def test_a_second_files_heading_re_opens_the_section(self) -> None:
        raw = """\
# Delegate preview

## Selected files

- `src/module.py`

## Excluded files

- `docs/guide.md` — excluded: documentation
"""

        result = parse_preview(raw)

        self.assertEqual(result.included_paths, ("src/module.py",))
        self.assertEqual([entry.path for entry in result.excluded], ["docs/guide.md"])

    def test_an_entry_line_with_no_extractable_path_is_a_failure(self) -> None:
        # Never a silent discard: that is how an entry disappeared entirely.
        for raw in (
            "# Preview\n\n## Files\n\n- \n",
            "# Preview\n\n## Files\n\n- ``\n",
            "# Preview\n\n## Files\n\n| | | |\n",
        ):
            with self.subTest(raw=raw[-12:]):
                with self.assertRaises(AppError) as caught:
                    parse_preview(raw)
                self.assertEqual(caught.exception.code, EXIT_ENGINE)


class ScopeCrossVerificationTests(unittest.TestCase):
    """The invariant that does not depend on the engine's output format."""

    def _preview(self, *paths: str) -> "PreviewResult":
        lines = ["# Delegate preview", "", "## Files", ""]
        lines.extend(f"- `{path}`" for path in paths)
        return parse_preview("\n".join(lines) + "\n")

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
        preview = parse_preview("# P\n\n## Files\n\n- `a.py`\n- `b.py` — excluded: vendored\n")

        verify_scope_against_git(preview, ["a.py", "b.py"])

    def test_an_empty_diff_and_an_empty_scope_agree(self) -> None:
        verify_scope_against_git(parse_preview("# P\n\n## Files\n"), [])

    def test_the_message_says_what_to_do_about_a_mismatch(self) -> None:
        with self.assertRaises(AppError) as caught:
            verify_scope_against_git(self._preview("a.py"), ["a.py", "b.py"])

        remedy = caught.exception.diagnostics[-1].message
        self.assertIn("never run on a guess", remedy)
        self.assertIn("re-verified against the pinned binary", remedy)


class RuleParsingTests(unittest.TestCase):
    """The rule cascade is read anchored on the paths we asked about."""

    RAW = """\
# Resolved rules

## src/module.py

- Production code must validate its inputs.
- Never interpolate repository content into a shell.

## tests/test_module.py

- Every behaviour change needs a failing test first.
"""

    def test_each_requested_path_gets_its_rules(self) -> None:
        result = parse_rules(self.RAW, expected_paths=["src/module.py", "tests/test_module.py"])

        self.assertEqual([assignment.path for assignment in result.assignments], ["src/module.py", "tests/test_module.py"])
        self.assertEqual(len(result.assignments[0].rules), 2)
        self.assertIn("validate its inputs", result.assignments[0].rules[0])
        self.assertEqual(len(result.assignments[1].rules), 1)

    def test_the_order_follows_the_request_not_the_output(self) -> None:
        result = parse_rules(self.RAW, expected_paths=["tests/test_module.py", "src/module.py"])

        self.assertEqual([assignment.path for assignment in result.assignments], ["tests/test_module.py", "src/module.py"])

    def test_a_group_heading_style_change_does_not_lose_a_group(self) -> None:
        # Anchoring on our own request is what makes this true.
        restyled = self.RAW.replace("## ", "**").replace("\n\n- ", "**\n\n- ")

        result = parse_rules(restyled, expected_paths=["src/module.py", "tests/test_module.py"])

        self.assertEqual(len(result.assignments), 2)

    def test_output_mentioning_none_of_the_requested_files_is_a_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_rules("# Resolved rules\n\n## other/file.py\n\n- Something else.\n", expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertEqual(caught.exception.diagnostics[0].code, "engine_output_unparseable")

    def test_empty_output_for_a_non_empty_request_is_a_failure(self) -> None:
        with self.assertRaises(AppError) as caught:
            parse_rules("", expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)

    def test_no_request_means_no_invocation_and_no_failure(self) -> None:
        self.assertEqual(parse_rules("", expected_paths=[]).assignments, ())


class OverlappingPathTests(unittest.TestCase):
    """Rule groups anchored on paths that contain one another."""

    RAW = """\
# Resolved rules

## vendor/a.py

- Vendored code is reviewed for licence only.

## a.py

- Production code must validate its inputs.

## docs/README.md

- Documentation must match the code.

## README.md

- The front page must stay accurate.
"""

    def test_a_shorter_path_does_not_swallow_a_longer_one(self) -> None:
        result = parse_rules(self.RAW, expected_paths=["a.py", "vendor/a.py"])

        assignments = {assignment.path: assignment.rules for assignment in result.assignments}
        self.assertEqual(assignments["a.py"], ("Production code must validate its inputs.",))
        self.assertEqual(assignments["vendor/a.py"], ("Vendored code is reviewed for licence only.",))

    def test_the_everyday_readme_case(self) -> None:
        result = parse_rules(self.RAW, expected_paths=["README.md", "docs/README.md"])

        assignments = {assignment.path: assignment.rules for assignment in result.assignments}
        self.assertEqual(assignments["README.md"], ("The front page must stay accurate.",))
        self.assertEqual(assignments["docs/README.md"], ("Documentation must match the code.",))

    def test_a_partial_answer_is_a_failure_not_a_quiet_gap(self) -> None:
        # "this file has no rules" and "the engine never mentioned this file"
        # must stay distinguishable.
        with self.assertRaises(AppError) as caught:
            parse_rules(self.RAW, expected_paths=["a.py", "never/mentioned.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)
        self.assertIn("never/mentioned.py", str(caught.exception))

    def test_a_substring_that_is_not_a_path_boundary_does_not_count(self) -> None:
        raw = "# Rules\n\n## src/module.pyc\n\n- A rule for the compiled file.\n"

        with self.assertRaises(AppError) as caught:
            parse_rules(raw, expected_paths=["src/module.py"])

        self.assertEqual(caught.exception.code, EXIT_ENGINE)


class EngineInvocationTests(unittest.TestCase):
    """Argv, isolation, batching and failure mapping, against the fake engine."""

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

    def test_rule_paths_are_positional_and_batched_in_request_order(self) -> None:
        paths = [f"src/file{index}.py" for index in range(5)]
        engine = self._engine(rules={path: [f"rule for {path}"] for path in paths})

        result = engine.delegate_rule(self.workspace, paths, rule_path=self.workspace / "rule.json", batch_size=2)

        self.assertEqual([assignment.path for assignment in result.assignments], paths)
        rule_invocations = [argv for argv in self._invocations() if argv[:2] == ["delegate", "rule"]]
        self.assertEqual(len(rule_invocations), 3)
        for argv in rule_invocations:
            # Paths come after every flag, so none can be read as an option.
            self.assertLess(argv.index("--rule"), min(argv.index(path) for path in paths if path in argv))

    def test_batching_does_not_change_the_answer(self) -> None:
        paths = [f"src/file{index}.py" for index in range(5)]
        engine = self._engine(rules={path: [f"rule for {path}"] for path in paths})

        one_batch = engine.delegate_rule(self.workspace, paths, batch_size=100)
        many_batches = engine.delegate_rule(self.workspace, paths, batch_size=1)

        self.assertEqual(
            [assignment.as_dict() for assignment in one_batch.assignments],
            [assignment.as_dict() for assignment in many_batches.assignments],
        )

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
