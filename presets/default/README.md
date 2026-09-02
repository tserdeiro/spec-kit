# `default` preset

The workflow templates for this distribution: `spec`, `plan`, `tasks`, and
`checklist`, plus the workflow commands (`speckit.pr`, `speckit.bugfix`,
`speckit.chore`, `speckit.doctor`, and the `speckit.specify`,
`speckit.plan`, `speckit.tasks`, `speckit.analyze`, and
`speckit.implement` appends). The `tasks` template carries the
integration-branch delivery conventions — one task in flight per
developer, no parallel tasks; the rest trim the upstream core templates
to what the flow needs.

Phase close: product-phase commands (`specify`, `plan`, `tasks`,
`analyze`) never announce optional hooks — enabled ones run silently,
the rest are skipped — and end by committing the feature's artifacts,
staging `specs/<feature-directory>/` only (unrelated dirty files stay
untouched) and skipping silently when nothing changed.

## Install

```bash
specify preset add --from https://github.com/tserdeiro/spec-kit/releases/download/bundles%2Fv0.13.0/default-0.7.0.zip
```

Local development:

```bash
specify preset add --dev presets/default
specify preset resolve tasks-template
```

The three role bundles (`product`, `developer`, `reviewer`) install this preset
for you; add it directly only when you want the templates without a role.

## Delivery base

Set `trunk: <branch>` in `.specify/extensions/git/git-config.yml` when a
feature targets a branch other than GitHub's default. The feature-PR path
in `speckit.pr` and the first-task refresh in `speckit.implement` use that
explicit value first and fall back to the GitHub default when it is absent,
empty, or null. The value must load as a YAML string and pass Git branch
validation; numeric- or date-looking names must be quoted. Resolution is
owned by the preset's installed `scripts/resolve-delivery-base.py` helper.
Task PRs target the runtime-derived feature branch; work-item PRs keep
targeting the runtime GitHub default.
