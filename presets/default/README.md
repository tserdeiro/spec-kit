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
