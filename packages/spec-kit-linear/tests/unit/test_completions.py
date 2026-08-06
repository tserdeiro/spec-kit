"""Tests for `spec-kit-linear completions bash|zsh` (contract "Comandos
públicos" > "completions (herramienta local)").

Covers:
- parser-introspection completeness: every subcommand and long flag the
  argparse tree (`cli.build_parser()`) declares shows up in both generated
  scripts, with no hand-maintained duplicate list anywhere;
- both generated scripts are syntactically loadable by their own shell
  (`bash -n` always; `zsh -n` only if `zsh` is on PATH, else the check is
  skipped with a stated reason -- never silently passed);
- `completions` itself never appears in `extension.yml`'s
  `provides.commands` (it is local-only developer sugar, not an
  agent-facing command -- see the contract amendment).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from spec_kit_linear.cli import build_parser, main
from spec_kit_linear.completions import (
    FILE_PATH_FLAGS,
    collect_completion_tree,
    generate_bash_script,
    generate_completion_script,
    generate_zsh_script,
)


class ParserIntrospectionCompletenessTests(unittest.TestCase):
    def test_every_subcommand_present_in_tree(self) -> None:
        tree = collect_completion_tree(build_parser())
        subparsers_action = next(
            action for action in build_parser()._actions if type(action).__name__ == "_SubParsersAction"
        )
        expected = set(subparsers_action.choices)
        self.assertEqual(set(tree), expected)

    def test_every_long_flag_present_in_tree(self) -> None:
        parser = build_parser()
        subparsers_action = next(
            action for action in parser._actions if type(action).__name__ == "_SubParsersAction"
        )
        tree = collect_completion_tree(parser)
        for name, subparser in subparsers_action.choices.items():
            expected_flags = {
                option
                for action in subparser._actions
                for option in action.option_strings
                if option.startswith("--")
            }
            self.assertEqual(set(tree[name]), expected_flags, f"subcommand {name!r}")

    def test_bash_script_contains_every_subcommand_and_flag(self) -> None:
        tree = collect_completion_tree(build_parser())
        script = generate_bash_script(tree)
        for name, flags in tree.items():
            self.assertIn(name, script)
            for flag in flags:
                self.assertIn(flag, script)

    def test_zsh_script_contains_every_subcommand_and_flag(self) -> None:
        tree = collect_completion_tree(build_parser())
        script = generate_zsh_script(tree)
        for name, flags in tree.items():
            self.assertIn(name, script)
            for flag in flags:
                self.assertIn(flag, script)

    def test_file_path_flags_fall_back_to_default_file_completion_in_bash(self) -> None:
        tree = collect_completion_tree(build_parser())
        script = generate_bash_script(tree)
        # Every file-path flag must route to `compgen -f` (default file
        # completion) rather than a fixed word list.
        for flag in FILE_PATH_FLAGS:
            self.assertIn(flag, script)
        self.assertIn("compgen -f", script)

    def test_file_path_flags_fall_back_to_files_in_zsh(self) -> None:
        tree = collect_completion_tree(build_parser())
        script = generate_zsh_script(tree)
        self.assertIn("_files", script)

    def test_unsupported_shell_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_completion_script("fish", build_parser())


class GeneratedScriptSyntaxTests(unittest.TestCase):
    def test_bash_script_is_syntactically_loadable(self) -> None:
        script = generate_completion_script("bash", build_parser())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "completions.bash"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_zsh_script_is_syntactically_loadable(self) -> None:
        if shutil.which("zsh") is None:
            self.skipTest("zsh is not on PATH in this environment")
        script = generate_completion_script("zsh", build_parser())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "completions.zsh"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run(["zsh", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


class CompletionsCliTests(unittest.TestCase):
    def test_completions_bash_prints_script_to_stdout(self) -> None:
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["completions", "bash"])
        self.assertEqual(code, 0)
        self.assertIn("_spec_kit_linear", out.getvalue())
        self.assertIn("complete -F _spec_kit_linear spec-kit-linear", out.getvalue())

    def test_completions_zsh_prints_script_to_stdout(self) -> None:
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["completions", "zsh"])
        self.assertEqual(code, 0)
        self.assertIn("#compdef spec-kit-linear", out.getvalue())

    def test_completions_rejects_unknown_shell(self) -> None:
        # argparse's own `choices` validation raises SystemExit directly
        # (there is no --json handling for a subparser-local usage error),
        # the same way any other subcommand's invalid `choices` argument
        # already behaves.
        with self.assertRaises(SystemExit) as context:
            main(["completions", "fish"])
        self.assertEqual(context.exception.code, 2)


class CompletionsNotAPublicCommandTests(unittest.TestCase):
    """doc "Comandos públicos": `completions` is local-only developer sugar
    and must never be registered under extension.yml's provides.commands."""

    def test_completions_absent_from_extension_manifest(self) -> None:
        manifest_path = Path(__file__).resolve().parents[2] / "extension.yml"
        text = manifest_path.read_text(encoding="utf-8")
        self.assertNotIn("speckit.linear.completions", text)
        self.assertNotIn("commands/completions.md", text)

    def test_no_completions_command_markdown_file(self) -> None:
        commands_dir = Path(__file__).resolve().parents[2] / "commands"
        self.assertFalse((commands_dir / "completions.md").exists())


if __name__ == "__main__":
    unittest.main()
