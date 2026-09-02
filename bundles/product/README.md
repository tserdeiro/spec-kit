# Product bundle

Steps 1-3 of the feature workflow: specs, plans, and tasks,
projected into Linear, closed by the draft feature PR (the gate).

## What it installs

- Preset `default` — spec, plan, tasks, checklist templates and the
  workflow commands.
- Extension `git` — feature branching and delivery-base configuration
  (ships with Spec Kit).
- Extension `linear` — Project, Issue and state projection.

The exact pinned versions live in [`bundle.yml`](bundle.yml) — this page
deliberately names none, so it cannot rot.

Integration-agnostic: it inherits the project's active agent integration.

## Install

Follow the canonical steps in the
[root README](../../README.md#-primeros-pasos) (register the three
catalogs once per repository, then `specify bundle install product`).
This page does not duplicate them, so there is exactly one install path
to keep true.

## Verify

```bash
# Offline from this checkout: references resolve against the enclosing
# project, and this repository installs neither the preset nor the extensions.
specify bundle validate --path bundles/product --offline
specify bundle build --path bundles/product --output dist/

# Full reference resolution, from a consumer with the catalogs registered:
scripts/conformance/bundles.sh
```
