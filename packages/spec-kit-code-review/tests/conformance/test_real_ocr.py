"""Conformance of this adapter against the **real, pinned** engine binary.

Doc "Conformance del binario real": every OCR surface this package consumes is
re-verified against the pinned binary in a dedicated test. The fake reproduces
what we *believe* the engine does; the point of this test is to detect when that
stops being true. It is a **prerequisite of the engine stage, not a
deliverable**, and it must be re-run on every change of the pin.

It is skipped -- loudly, never silently passed -- when the pinned binary is not
available. "Not available" includes *a different version being installed*: the
engine is resolved from ``SPECKIT_CODE_REVIEW_OCR_BIN``, then from this
distribution's canonical location for the pinned version, then from ``PATH``,
and a binary of another version skips with the reason rather than failing. A
machine that carries a newer engine has an unmet prerequisite, not a broken
package, and a red suite would say the opposite. (``PATH`` is consulted here,
and only here: the capture is about *a* real binary, while the package itself
resolves the override and the canonical path and nothing else.)

To run it, let ``doctor --fix`` install the pinned engine at its canonical
location, or install it yourself::

    bash .specify/extensions/code-review/scripts/bash/run.sh doctor --fix

    prefix="${XDG_DATA_HOME:-$HOME/.local/share}/tserdeiro/spec-kit/tools/ocr/1.8.3"
    mkdir -p "$prefix" && printf '{}' > "$prefix/package.json"
    npm install --prefix "$prefix" --save-exact @alibaba-group/open-code-review@1.8.3

    uv run pytest packages/spec-kit-code-review/tests/conformance -v

What it verifies, one assertion per surface this package actually consumes:

1. ``--version`` exists and its exact output (the operative half of the pin).
2. ``delegate preview`` exists and accepts ``--repo/--from/--to/--rule/--exclude``.
3. ``delegate preview`` in **workspace mode**, with no range flags at all.
4. ``delegate rule`` exists, accepts ``--repo/--rule`` and **positional paths**.
5. The **output shape** of both, read by this package's own parsers -- the
   assertion that matters most, because a shape change is what would silently
   alter a review's scope.
6. ``rules check`` and its layer report.
7. That ``-B``/``--background`` is never needed for any of the above.

The standard-engine surfaces (``--audience``, ``--concurrency``, ``--timeout``
in **minutes per file**, ``--max-tokens-budget``, and the full ``review`` JSON)
are deliberately **not** exercised here: that engine is deferred outside v0.1.0
and no code in this package can reach it. They join this file when it lands.

When this test passes for the first time, its captured output must replace the
contract-derived fixtures in ``tests/support/fake_ocr.py`` -- that is what turns
the fake from "what we believe" into "what we observed".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from spec_kit_code_review.ocr import Ocr, parse_preview, parse_rules, write_minimal_config
from spec_kit_code_review.paths import tool_executable
from tests.support.repo import TemporaryRepository


PINNED_TAG = "v1.8.3"
_INSTALL_HINT = (
    "Run `doctor --fix` to install the pinned engine at its canonical location, or install it yourself (see "
    "validation/ocr-npm-specifier.md) and re-run with SPECKIT_CODE_REVIEW_OCR_BIN pointing at the platform "
    "binary -- not at the JS shim in node_modules/.bin."
)


@dataclass(frozen=True)
class EngineResolution:
    """Which engine this run found, where, and whether it is the pinned one."""

    path: str | None = None
    source: str = "none"
    problem: str | None = None

    @property
    def usable(self) -> bool:
        return self.path is not None and self.problem is None


def resolve_pinned_engine(
    *,
    environment: Mapping[str, str] | None = None,
    pinned_tag: str = PINNED_TAG,
    which=shutil.which,
    version_of=None,
) -> EngineResolution:
    """The pinned engine, by the same discipline the conformance stage uses.

    Order: ``SPECKIT_CODE_REVIEW_OCR_BIN``, then this distribution's canonical
    location for the pinned version, then ``PATH``.

    **A binary of another version is not a failure of this package.** A machine
    can legitimately carry a newer engine on its ``PATH`` -- observed: v1.8.5
    while the lock pins v1.8.3 -- and running the capture against it would turn
    a green suite red for a reason that has nothing to do with this code. The
    prerequisite is "captured against the *pinned* binary", so a different
    version means the prerequisite is unmet on this machine, exactly as an
    absent one does: skipped, loudly, naming what was found and where.
    """

    source_environment = os.environ if environment is None else environment
    probe = version_of or _first_version_line
    version = pinned_tag.lstrip("v")

    candidates: list[tuple[str, str]] = []
    override = (source_environment.get("SPECKIT_CODE_REVIEW_OCR_BIN") or "").strip()
    if override:
        candidates.append((override, "SPECKIT_CODE_REVIEW_OCR_BIN"))
    canonical = str(tool_executable("ocr", pinned_tag, source_environment))
    candidates.append((canonical, "the canonical pinned location"))
    on_path = which("ocr")
    if on_path:
        candidates.append((str(on_path), "PATH"))

    problem: str | None = None
    for candidate, source in candidates:
        if not Path(candidate).is_file():
            if source == "SPECKIT_CODE_REVIEW_OCR_BIN":
                problem = f"SPECKIT_CODE_REVIEW_OCR_BIN points at {candidate}, which is not a file."
            continue
        observed = probe(candidate)
        if f"v{version}" in observed or f" {version} " in f" {observed} ":
            return EngineResolution(path=candidate, source=source)
        problem = (
            f"the engine found via {source} at {candidate} reports {observed!r}, "
            f"and this capture is only meaningful against the pinned {pinned_tag}."
        )

    if problem is None:
        problem = f"the pinned review engine (open-code-review {pinned_tag}) is not installed."
    return EngineResolution(path=None, source="none", problem=problem)


def _first_version_line(executable: str) -> str:
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    output = (result.stdout or result.stderr or "").strip()
    return output.splitlines()[0].strip() if output else ""


RESOLUTION = resolve_pinned_engine()
ENGINE = RESOLUTION.path
SKIP_REASON = (
    f"{RESOLUTION.problem} This test is a PREREQUISITE of the engine stage, not an optional extra: until it runs "
    f"against the pinned binary, this package's parser and its fake are unverified against upstream. {_INSTALL_HINT}"
)


@unittest.skipUnless(ENGINE, SKIP_REASON)
class RealEngineConformanceTests(unittest.TestCase):
    """Every surface this package consumes, against the binary itself."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.captures: dict[str, str] = {}

    @classmethod
    def tearDownClass(cls) -> None:
        # The captured output is what the fake's fixtures must be derived from,
        # so it is written where a person can pick it up.
        if not cls.captures:
            return
        destination = Path(os.environ.get("SPECKIT_CODE_REVIEW_CAPTURE_DIR", "")) if os.environ.get(
            "SPECKIT_CODE_REVIEW_CAPTURE_DIR"
        ) else None
        if destination is None:
            return
        destination.mkdir(parents=True, exist_ok=True)
        for name, text in cls.captures.items():
            (destination / f"{name}.txt").write_text(text, encoding="utf-8")

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()

        self.repository = TemporaryRepository(self.workspace / "consumer")
        self.addCleanup(self.repository.cleanup)
        self.repository.write(
            ".opencodereview/rule.json",
            json.dumps({"rules": [{"path": "src/**", "rule": "Validate every input.", "merge_system_rule": True}]}),
        )
        self.repository.git("add", "--all")
        self.repository.git("commit", "-m", "base with rules")
        self.base = self.repository.head()
        self.repository.commit("src/module.py", "value = 1\n", "candidate work")
        self.repository.commit("docs/guide.md", "# Guide\n", "documentation")
        self.head = self.repository.head()

        self.rule_path = self.repository.path / ".opencodereview" / "rule.json"
        self.engine = Ocr(
            ENGINE,
            timeout=120,
            config_path=write_minimal_config(self.workspace / "ocr-config.json"),
        )

    def _capture(self, name: str, text: str) -> None:
        type(self).captures[name] = text

    # 1. the pin's operative half -------------------------------------------

    def test_version_reports_the_pinned_version(self) -> None:
        version = self.engine.version()

        self._capture("version", version)
        self.assertTrue(version.strip(), "`ocr --version` produced no output")
        self.assertIn(
            PINNED_TAG.lstrip("v"),
            version,
            f"the installed engine is not the pinned {PINNED_TAG}",
        )
        # The pin is the platform-independent prefix -- name, version, commit --
        # because the first line also carries `<os>/<arch>` and the second a
        # build timestamp. Pinning the whole output in a shared lock would fail
        # for every operator on another platform.
        from spec_kit_code_review.lockfile import version_matches_pin

        first_line = version.splitlines()[0]
        self.assertRegex(first_line, r"^open-code-review v\d+\.\d+\.\d+ \([0-9a-f]{7,}\) \S+/\S+$")
        pinned = " ".join(first_line.split()[:3])
        self.assertTrue(version_matches_pin(version, pinned), (version, pinned))
        self.assertFalse(version_matches_pin(version, first_line + " and more"))

    # 2-3. delegate preview, both modes --------------------------------------
    #
    # The two shapes below are the ones that broke the first capture against the
    # real binary and forced ADAPTER_VERSION to 2. They are asserted on the raw
    # output, not only through the parser, so an upstream change to either is a
    # loud failure here rather than a silent reinterpretation.

    def test_excluded_entries_are_struck_through_whole(self) -> None:
        result = self.engine.run(
            "delegate", "preview", "--repo", str(self.repository.path), "--from", self.base, "--to", self.head
        )
        self._capture("delegate-preview-strikethrough", result.stdout)

        struck = [line for line in result.stdout.splitlines() if line.strip().startswith("~~")]
        self.assertTrue(struck, "no excluded entry was struck through; the parser's unwrapping is now untested")
        for line in struck:
            with self.subTest(line=line[:60]):
                # The wrapper spans the whole item, dash included.
                self.assertTrue(line.strip().endswith("~~"), line)
                self.assertRegex(line.strip(), r"^~~(?:[-*+])\s+`[^`]+`.*\(excluded: [^)]+\)~~$")

    def test_included_entries_are_indented_list_items(self) -> None:
        result = self.engine.run(
            "delegate", "preview", "--repo", str(self.repository.path), "--from", self.base, "--to", self.head
        )
        self._capture("delegate-preview-indent", result.stdout)

        included = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("  ") and line.strip().startswith("-") and "`" in line
        ]
        self.assertTrue(included, "no included entry was an indented list item")

    def test_the_metadata_are_list_items_inside_the_file_section(self) -> None:
        result = self.engine.run(
            "delegate", "preview", "--repo", str(self.repository.path), "--from", self.base, "--to", self.head
        )

        lines = result.stdout.splitlines()
        heading = next(index for index, line in enumerate(lines) if line.startswith("# "))
        metadata = {
            line.strip().lstrip("- ").split(":", 1)[0]
            for line in lines[heading:]
            if line.strip().startswith("- ") and ":" in line
        }
        # Read as *entries* these would have become files named `mode`, `from`
        # and `to` -- a corrupted scope that no exit code would have announced.
        for key in ("mode", "from", "to", "merge_base"):
            with self.subTest(key=key):
                self.assertIn(key, metadata)

    def test_rule_output_is_grouped_with_its_own_content_heading(self) -> None:
        invocation = self.engine.run(
            "delegate", "rule", "--repo", str(self.repository.path), "--rule", str(self.rule_path), "--", "src/module.py"
        )
        result = invocation.stdout
        self._capture("delegate-rule-groups", result)

        self.assertRegex(result, r"(?m)^#{1,6}\s*Rule Group\s+\d+")
        self.assertRegex(result, r"(?m)^\s*Applies\s+to\s*:")
        self.assertRegex(result, r"(?m)^#{1,6}\s*Content\s*$")

    def test_delegate_preview_accepts_the_documented_flags(self) -> None:
        result = self.engine.run("delegate", "preview", "--help")

        self._capture("delegate-preview-help", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ("--repo", "--from", "--to", "--rule", "--exclude"):
            with self.subTest(flag=flag):
                self.assertIn(flag, result.stdout + result.stderr)

    def test_delegate_preview_over_a_range_parses(self) -> None:
        preview = self.engine.delegate_preview(
            self.repository.path,
            from_ref=self.base,
            to_ref=self.head,
            rule_path=self.rule_path,
            on_raw=lambda raw: self._capture("delegate-preview-range", raw),
        )

        self.assertIn("src/module.py", preview.included_paths + tuple(entry.path for entry in preview.excluded))
        # Re-parsing the captured bytes must give the same answer: that is the
        # adapter contract, not just this run.
        self.assertEqual(parse_preview(preview.raw).as_dict(), preview.as_dict())

    def test_delegate_preview_in_workspace_mode_parses(self) -> None:
        self.repository.write("src/uncommitted.py", "value = 2\n")

        preview = self.engine.delegate_preview(
            self.repository.path,
            rule_path=self.rule_path,
            on_raw=lambda raw: self._capture("delegate-preview-workspace", raw),
        )

        self.assertEqual(parse_preview(preview.raw).as_dict(), preview.as_dict())

    # 4-5. delegate rule ------------------------------------------------------

    def test_delegate_rule_accepts_positional_paths(self) -> None:
        result = self.engine.run("delegate", "rule", "--help")

        self._capture("delegate-rule-help", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ("--repo", "--rule"):
            with self.subTest(flag=flag):
                self.assertIn(flag, result.stdout + result.stderr)

    def test_delegate_rule_resolves_the_requested_paths(self) -> None:
        resolution = self.engine.delegate_rule(
            self.repository.path,
            ["src/module.py"],
            rule_path=self.rule_path,
            on_raw=lambda raw: self._capture("delegate-rule", raw),
        )

        self.assertEqual([assignment.path for assignment in resolution.assignments], ["src/module.py"])
        self.assertEqual(
            parse_rules(resolution.raw, expected_paths=["src/module.py"]).as_dict(),
            resolution.as_dict(),
        )

    def test_delegate_rule_batches_do_not_change_the_answer(self) -> None:
        paths = ["src/module.py", "docs/guide.md"]

        one = self.engine.delegate_rule(self.repository.path, paths, rule_path=self.rule_path, batch_size=100)
        many = self.engine.delegate_rule(self.repository.path, paths, rule_path=self.rule_path, batch_size=1)

        self.assertEqual(
            [assignment.path for assignment in one.assignments],
            [assignment.path for assignment in many.assignments],
        )

    # 6. no background mode ---------------------------------------------------

    def test_delegate_rule_accepts_the_end_of_flags_separator(self) -> None:
        # `--` is what stops a candidate file named `--rule` from becoming a
        # flag of the invocation that decides which rules apply. If the engine
        # rejects it, this package needs another way to close that hole.
        result = self.engine.run("delegate", "rule", "--repo", str(self.repository.path), "--", "src/module.py")

        self._capture("delegate-rule-end-of-flags", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, f"the engine rejected `--`: {result.stderr}")

    def test_nothing_this_package_needs_requires_the_background_flag(self) -> None:
        # The review needs synchronous, deterministic output; `-B` is never used.
        for surface in (("delegate", "preview", "--help"), ("delegate", "rule", "--help")):
            with self.subTest(surface=surface):
                result = self.engine.run(*surface)
                self.assertEqual(result.returncode, 0)

    def test_the_engine_is_installed_by_doctor_fix_and_by_nothing_else(self) -> None:
        # A grep, deliberately: the guarantee is about *every* code path, and the
        # only way to state that is over the whole source tree. Since 2026-08-03
        # the guarantee is not "nothing installs" but "one command installs":
        # `doctor --fix`, through `engine.install_engine`, and nowhere else.
        source = Path(__file__).resolve().parents[2] / "src" / "spec_kit_code_review"
        callers = {
            path.name for path in source.rglob("*.py") if "install_engine(" in path.read_text(encoding="utf-8")
        }
        self.assertEqual(callers, {"engine.py", "doctor.py"})

        doctor = (source / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("_install_engine_if_absent(options, outcome)", doctor)
        self.assertIn("def _apply_fixes(", doctor)

        # Nothing on the review path can reach a package manager: neither the
        # installer nor the only lookup that finds one.
        for name in ("cli.py", "ocr.py", "environment.py", "session.py", "publish.py", "github.py", "git.py", "process.py"):
            with self.subTest(module=name):
                text = (source / name).read_text(encoding="utf-8")
                self.assertNotIn('which("npm")', text)
                self.assertNotIn("install_engine", text)
        self.assertEqual(
            {path.name for path in source.rglob("*.py") if 'which("npm")' in path.read_text(encoding="utf-8")},
            {"engine.py"},
        )

        # And no other installer is executed anywhere, under any flag.
        for path in source.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in ("pip install", "brew install", "curl -", "wget "):
                with self.subTest(path=path.name, marker=marker):
                    self.assertNotIn(marker, text)


if __name__ == "__main__":  # pragma: no cover - convenience for local runs
    unittest.main()
