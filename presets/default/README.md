# `default` preset

The workflow templates for this distribution: `spec`, `plan`, `tasks`, and
`checklist`. The `tasks` template carries the branch-per-task and stacked-PR
delivery conventions; the rest trim the upstream core templates to what the
flow needs.

## Install

```bash
specify preset add --from https://github.com/tserdeiro/spec-kit/releases/download/bundles%2Fv1.0.0/default-1.0.0.zip
```

Local development:

```bash
specify preset add --dev presets/default
specify preset resolve tasks-template
```

The three role bundles (`product`, `developer`, `reviewer`) install this preset
for you; add it directly only when you want the templates without a role.
