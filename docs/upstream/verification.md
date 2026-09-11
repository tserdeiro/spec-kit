# Upstream patch verification

Revised on 2026-09-11 after the independent audit. These are source patches;
the installed CLI and distribution pin are unchanged.

| Check | Result |
| --- | --- |
| Pinned base | `cb610277fdea781fcfa83d20522c2db37c94068d` (`v1.0.4`) |
| Captured upstream submission base | `c173bf19a6654e3b05386ec3599349a55282b897` |
| Apply 0001–0009 in order on both bases | Passed; use `main/0004-...patch` on the submission base |
| Exported series equals each verification checkout | Passed |
| Complete pinned suite, `tests/` | **7,497 passed, 189 skipped, 3 failed** |
| Complete submission-base suite, `tests/` | **7,739 passed, 197 skipped, 3 failed** |
| Same three failing cases on each unpatched base | **3 failed, 4 passed** in the selected baseline checks |
| `uv run --offline --extra test specify --help`, both bases | Passed |
| `git diff --check`, patched upstream and distribution | Passed |

## Remaining test failures

All three failures also reproduce on each intact base in the same environment:

- `tests/integrations/test_events.py::TestCommandRunner::test_ps_variant_prefixed_with_powershell_launcher`: PowerShell is unavailable.
- `tests/unit/test_bundler_references.py::test_community_step_is_not_treated_as_bundled`.
- `tests/unit/test_bundler_references.py::test_unknown_step_type_still_errors_online`.

The latter two expect a definitive catalog lookup. Direct baseline diagnosis
returns `StepCatalogError: All configured step catalogs failed to fetch.`
They were not hidden, deselected or converted to passing assertions. The full
suite is not green in this environment. Skipped cases are not runtime evidence. Both complete runs reported 48 warnings;
they remain visible in the logs.

## Reproduce

In a clean temporary checkout at the chosen base, apply root patches 0001–0009
in numerical order with `git apply`. At `c173bf19`, substitute the rebased 0004
under `main/`; 0003 and the other patches apply unchanged.

```bash
uv sync --extra test
uv run --offline --extra test python -m pytest tests -q --tb=short
uv run --offline --extra test specify --help
git diff --check
```

Use the checkout's environment for pytest and child processes. `uv run` sets
the executable search path; invoking the venv Python alone previously left
Bash selecting system Python without PyYAML under test isolation.

On each unpatched base, the comparison command is:

```bash
uv run --offline --extra test python -m pytest \
  tests/integrations/test_events.py::TestCommandRunner::test_ps_variant_prefixed_with_powershell_launcher \
  tests/unit/test_bundler_references.py -q --tb=short
```

## Audit corrections

- **0003:** unchanged implementation, exported with narrower context so it
  applies after 0002 and on both bases without replacing upstream diagnostics.
- **0004:** rejects unknown lifecycle event arguments; removes obsolete hook
  note injection and its tests; adds generated-output and native invocation
  coverage. Documents native ordering, selected-event validation and stopping
  on resolver errors. The submission variant also updates upstream's newer
  hook-error regression and removes its newer Cline note tests.
- **0005:** removes obsolete persistence hints from core and Git-extension
  Bash/Python/PowerShell creators, with output regressions.
- **0006:** uses `python3`, updates Copilot's rendered contract, and exercises
  composed `TEMPLATE_CONTENT` through the installed native resolver.
- **0007:** uses CommonMark token maps, declares `markdown-it-py>=3.0`, and
  covers nested-list data fences across both path-rewriting passes. Only
  JSON/JSONC, YAML/YML, TOML, XML and CSV fences are protected; unlabelled and
  `text` fences retain path rewriting.
- **0008:** repairs permissions in the shared preset manager, covering direct
  installation and the actual bundle primitive route. Both new regressions
  fail on the intact pin and pass with the patch. Scope: POSIX shebang `.sh`
  files under `.specify/scripts` and `.specify/extensions`. The original
  mode-loss operation remains unidentified.
- **0009:** documentation and characterization of existing installation without
  an agent binary; no new behavior or flag.

PR drafts preserve the distribution's six canonical sections and include
upstream's Description, Testing and AI Disclosure content as subsections.
No human review, approval or understanding is attested by the agents.

## Delivery limits

**0004's runtime installation contract remains unresolved.** Its generated
core templates require the Specify CLI. This conflicts with the distribution's
clone-and-use promise unless the prerequisite is deliberately changed or a
portable native resolver is distributed. Agent runtime `events.py` dispatches
scripts; it does not replace lifecycle resolution of skill invocations and
live layered configuration. Passing tests does not close this design issue.
The [portable runtime proposal](hooks-runtime-design.md) records the intended
replacement architecture and acceptance checks; that replacement is not yet implemented.

The complete suites verify the combined series, not nine independent PR
candidates. The original focused result (1,150 passed, 71 skipped) was accurate
but insufficient: the audit found 23 additional failures outside that selection.
The new full-suite evidence supersedes that result for this revision.

No commit, push, release, merge, upstream PR or installed-CLI upgrade was made.
Live Codex/Linear acceptance and PR-budget work remain deferred. FR-016 retains
the agreed integration-preservation scope and active-only native registration.
