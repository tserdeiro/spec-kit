# Portable lifecycle hook resolver

Status: design proposal for replacing 0003/0004, recorded on 2026-09-11.
Implementation and real-agent acceptance remain pending. Existing patches and
their verification results describe the CLI-dependent implementation, not this design.

## Runtime contract

A configured consumer runs lifecycle hooks without an installed Specify CLI or
access to this distribution's source checkout. Python 3.11+ and PyYAML are
explicit consumer prerequisites. Resolve the interpreter through upstream's
native selection mechanism, including project environments and Windows launchers.

Extract one upstream-owned `hooks_runtime` module. The CLI imports it; native
installation distributes the same source to the consumer. Proposed paths:
`src/specify_cli/hooks_runtime.py` and `.specify/hooks_runtime.py`. The installed
file has a directly executable entry point and imports only the standard library
and PyYAML. Config loading, condition evaluation and hook resolution have one
implementation. Extract or inject existing registry and invocation dependencies
so the runtime imports neither the CLI package nor agent integration modules;
do not create another integration registry.

Read `.specify/extensions.yml` and effective extension configuration at execution
time. Preserve manifest defaults, project configuration, local configuration and
environment precedence. Use the existing installed-extension registry where
native resolution needs it. Add no derived hook index or configuration snapshot.
An edit to the registry, configuration or environment takes effect on the next
invocation without reinstalling or refreshing.

The resolver returns ordered hook records with exact native invocations; the host
executes the skills and waits for completion. Preserve optional-hook authorization.
Use the executing integration's context, including its installed command/skill mode,
rather than assuming the project's active integration is the caller.

`specify check` and the distribution doctor check Python and `import yaml` using
the interpreter selected for the consumer scripts. PyYAML in the CLI's isolated
environment is not evidence that the consumer can import it. Missing prerequisites
receive a concrete diagnostic and remediation for that environment; the resolver
does not download packages during ordinary execution.

## Delivery sequence

1. **Behavior-preserving extraction.** Move native runtime logic and its direct
   dependencies into the shared module. Verify the existing CLI behavior against
   the same fixtures. Templates and manifest conditions retain their current
   behavior in this independently reviewable change.
2. **One functional change.** Deliver the consumer copy, interpreter/dependency
   checks, condition grammar, Git manifest conditions and all twenty lifecycle
   template calls together. Wire installation and refresh through the native shared
   paths reached by init and integration install/upgrade. Replace the obsolete hook
   note renderer and update its tests in this change. Verify archive/wheel packaging
   and installation, rather than relying on a source-tree copy alone.

This replaces the current 0003/0004 submission split. Publishing manifest conditions
first would make existing templates omit those hooks; publishing prose evaluation
first would introduce instructions immediately replaced by the resolver. Neither
intermediate state is the intended delivery. Existing patch files remain historical
review artifacts until the replacement is implemented and verified.

## Acceptance evidence

- Installed module bytes equal the packaged source after init, install and upgrade.
  Shared ownership survives another integration's removal or upgrade.
- An isolated consumer runs with Python and PyYAML but without `specify` on PATH,
  without an importable `specify_cli`, and without the source checkout or network.
- CLI and installed module agree on conditions, ordering and effective configuration.
  Cases include defaults, project/local overrides, environment changes, disabled
  hooks, equal priorities and overlapping extension environment prefixes.
- Changes to `extensions.yml`, extension configuration and environment are observed
  immediately. Unknown lifecycle events and malformed inputs report errors; an
  error must not appear as a successful empty hook list. Specify the validated
  fields explicitly while preserving documented native priority normalization.
- Generated commands call the resolver at both lifecycle sites, consume its returned
  invocation and stop on resolver errors. Different installed integrations and modes
  receive their own invocation syntax without changing the project's active agent.
- Dependency checks identify the actual consumer interpreter. Test missing PyYAML
  separately from an absent or incompatible Python interpreter.
- Run the full suite on each exact submission candidate and compare failures with
  its intact base. Record agent execution separately from generated-file validation.

### Manual-test map for the existing patches

This is a planning map, not an exemption or completed evidence. Recompute it from
the final PR diff, including transitive callers and command prerequisites.

| Patch | Required test focus |
| --- | --- |
| 0001 | Force init, preservation of integrations/settings, and at least `/speckit.specify` after scaffolding. |
| 0002 | Core commands reaching `git.commit`; verify stage boundaries in a temporary project. |
| 0003/0004 replacement | All ten core lifecycle pairs, optional authorization, effective conditions and multiple integration invocations. |
| 0005 | `/speckit.specify`, `git.feature`, and direct core/extension branch-creator output. |
| 0006 | `/speckit.specify` with composed preset content through the installed resolver. |
| 0007 | Packaging/init asset checks and an extension command whose data example contains paths. |
| 0008 | Direct and bundle preset installation, recovered script execution, and the affected command/scaffolding path. |
| 0009 | Sample integration installation without the agent binary; justify any real-agent exemption for this documentation/characterization change in the PR. |

Real-agent tests remain deferred by the user; this design does not authorize
publication or attest human testing. The preset's `trunk` regex is a separate
follow-up and is not removed by extracting this module.

## Verified source facts

Against distribution pin `cb610277fdea781fcfa83d20522c2db37c94068d`:

- PyYAML is already used for preset composition in both the
  [Python helper](https://github.com/github/spec-kit/blob/cb610277fdea781fcfa83d20522c2db37c94068d/scripts/python/common.py#L390)
  and the [Bash helper's embedded Python](https://github.com/github/spec-kit/blob/cb610277fdea781fcfa83d20522c2db37c94068d/scripts/bash/common.sh#L684).
  The latter imports `yaml` at line 696 and reports its absence. These are
  conditional composition paths, not proof that every consumer interpreter has
  PyYAML. The same Bash dependency exists at captured upstream `c173bf19`.
- The [generated events dispatcher](https://github.com/github/spec-kit/blob/cb610277fdea781fcfa83d20522c2db37c94068d/src/specify_cli/events.py#L109)
  uses `.registry` to filter disabled extensions, then reads manifest text and
  command frontmatter. It is a distribution precedent, not a complete JSON hook
  index or a reusable lifecycle-condition resolver.
- The captured upstream [contribution guide](https://github.com/github/spec-kit/blob/c173bf19a6654e3b05386ec3599349a55282b897/CONTRIBUTING.md#determining-which-tests-to-run)
  requires CLI checks and at least `/speckit.specify` for init/scaffolding changes,
  plus packaging checks for dependency changes. Pytest alone does not establish
  all required evidence for this series.
