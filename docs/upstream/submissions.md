# Proposed upstream PR bodies

Prepared for review; none of these submissions has been published. Bodies retain the distribution's six required sections and include upstream's Description, Testing and AI Disclosure content as subsections. Human review is still pending. A rebased variant is available for captured upstream `main` at `c173bf19`; verify any newer submission base before publication. The verification below targets the distribution's pinned commit.

# 0001: fix(init): preserve installed integrations on force reinitialization

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 35, 81, 97.

## Outcome

### Description

Preserve installed integrations and their per-integration settings across force reinitialization. Keep native active-only command registration.

## Changes

Preserve the existing integration list and settings during force reinitialization; verify that the second integration remains registered without changing native command ownership.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/integrations/test_cli.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Check preservation of the second integration and its settings without registering its commands.

# 0002: fix(git): scope automatic staging to the lifecycle event

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 24.

## Outcome

### Description

Scope phase staging to its feature artifacts or constitution. Implementation events retain whole-tree staging; unresolved feature paths retain tracked-only staging.

## Changes

Update the Bash, PowerShell and Python staging paths by lifecycle event; cover feature artifacts, constitution, implementation events and missing-feature behavior.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/extensions/git` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Review staging boundaries, already-staged changes, and Bash/Python/PowerShell parity.

# 0003: fix(git): honor optional commit hook configuration

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 25, 37, 84.

## Outcome

### Description

Evaluate per-event auto-commit configuration with the shared default only when the event section is absent. Support the required native condition grammar.

## Changes

Add configuration conditions to the sixteen commit hooks and implement composite condition parsing with per-event/default precedence tests.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/test_hook_condition_grammar.py tests/extensions/git/test_git_extension.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Check precedence, malformed conditions, event overrides, and default inheritance.

# 0004: fix(hooks): resolve lifecycle hooks through the native CLI

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 22, 23, 84.

## Outcome

### Description

Expose native hook resolution through specify hook check and replace twenty duplicated template procedures. Invalid registry metadata fails explicitly; the agent still executes returned skill invocations.

## Changes

Register the native hook-check CLI, validate registry metadata, and replace all twenty template hook procedures with JSON resolution and explicit failure handling.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/test_hook_command.py tests/test_command_template_hook_conditions.py tests/test_hook_condition_grammar.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Runtime decision pending: core templates require the installed Specify CLI. Consumer portability without that CLI is not resolved by this patch.
- Event argument and selected hook fields are validated; unrelated events and priority normalization retain native behavior.
- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: depends on 0003; rebase after that prerequisite.
- Approval and merge remain human decisions.

## Review focus

Check optional authorization, mandatory hooks, malformed metadata, and every template failure path.

# 0005: fix(git): clarify branch hook output and feature persistence

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 18, 36.

## Outcome

### Description

Remove human persistence hints from branch-hook JSON output. Document feature.json persistence and argument quoting, and cover native script output in temporary consumers.

## Changes

Remove persistence hints from JSON execution, correct text guidance and quoting instructions, and replace obsolete hint tests with output-contract coverage.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/test_git_extension_branch_output.py tests/extensions/git` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Check stdout/stderr separation, quoted descriptions, and native script parity.

# 0006: fix(specify): invoke the native template resolver

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 38.

## Outcome

### Description

Name the installed resolver for each script variant and consume its composed TEMPLATE_CONTENT. Report resolver or JSON failures before continuing.

## Changes

Specify Bash, PowerShell and Python resolver invocations and require the composed TEMPLATE_CONTENT response before writing the specification.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/test_native_template_resolver_contract.py tests/test_resolve_template_python_parity.py tests/integrations/test_integration_copilot.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Check resolver paths, flags, winning preset composition, and failure behavior.

# 0007: fix(rendering): preserve paths in illustrative data fences

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 66.

## Outcome

### Description

Preserve raw CommonMark data-fence spans during both path rewriting stages. Keep executable and prose package references relocatable; declare markdown-it-py directly.

## Changes

Use CommonMark fence spans in both path-rewriting passes, declare markdown-it-py explicitly, and test generated consumer commands with illustrative and executable paths.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/test_agent_config_consistency.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Data fences are preserved for JSON/JSONC, YAML/YML, TOML, XML and CSV. Unlabelled and `text` fences still undergo path rewriting.
- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Check raw example preservation alongside real package paths, including indented and nested Markdown.

# 0008: fix(presets): restore executable scripts after installation

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 73.

## Outcome

### Description

Run the existing native executable-script repair after successful preset installation. The regression starts with an installed Bash script missing execute bits; it verifies repair, not the original cause of their loss.

## Changes

Invoke `ensure_executable_scripts` in the shared preset manager and verify recovery of an installed `check-prerequisites.sh` through direct installation and the bundle primitive route.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/integrations/test_preset_modes.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Repairs POSIX shebang `.sh` files under `.specify/scripts` and `.specify/extensions`, including bundle-mediated preset installs. The original mode-loss operation remains unidentified.
- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Review all preset installation paths and the native helper's scope.

# 0009: docs(integrations): clarify installation without agent binaries

## Work item

- Tracker: N/A.
- Delivery type: Bug fix.
- Spec Kit evidence: [distribution dogfooding](https://github.com/tserdeiro/spec-kit/blob/main/docs/dogfooding.md), entries 95.

## Outcome

### Description

Document and test that integration installation scaffolds files without requiring the selected agent executable. Keep runtime prerequisites separate; no flag is added.

## Changes

Document file-scaffolding behavior and add an integration-install test with executable lookup unavailable.

## Verification evidence

### Testing

- [ ] Tested locally with `uv run specify --help`
- [ ] Ran existing tests with `uv sync && uv run pytest`
- [ ] Tested with a sample project (if applicable)

Leave these checks unmarked until the final submission candidate has the corresponding evidence. Combined-series results below do not attest an independent PR or a newer upstream base.

### AI Disclosure

- [ ] I **did not** use AI assistance for this contribution
- [x] I **did** use AI assistance (describe below)

AI tools assisted implementation, test authoring and review: Codex with Luna agents prepared and revised patches; Claude provided an independent audit. Human understanding and final review remain to be confirmed by the submitting maintainer.

| Check | Command or evidence | Result |
| --- | --- | --- |
| Focused coverage | `tests/integrations/test_integration_subcommand.py` | Covered by the complete combined suites; see [verification](https://github.com/tserdeiro/spec-kit/blob/main/docs/upstream/verification.md) for exact results and baseline failures. No isolated-PR full-suite claim. |
| Patch application | Clean pinned checkout and `git diff --check` | Verified as part of the complete series. |
| Runtime acceptance | Real agent sessions and live Linear reconciliation | Deferred; not claimed by these fixtures. |

## Risk and delivery

- Rollout: merge upstream, then consume through a reviewed distribution upgrade.
- Rollback: revert the corresponding upstream change.
- Stack: independent patch against the pinned commit.
- Approval and merge remain human decisions.

## Review focus

Check that installation succeeds without a binary and that later execution is not claimed to work without it.
