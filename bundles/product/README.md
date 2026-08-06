# Product bundle

Steps 1–3 of the feature workflow: business need → spec → plan → tasks, with
Linear as the projection.

## What it installs

- Preset `default` 0.2.0 (priority 10) — spec, plan, tasks, checklist templates.
- Extension `linear` 0.2.0 — `onboard`, `push`, `status`, `doctor`.

Integration-agnostic: it inherits the project's active agent integration.

## Install

Register this distribution's catalogs once per repository, then install:

```bash
base=https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog
specify bundle catalog add $base/bundles.json --id tserdeiro --policy install-allowed --priority 5
specify extension catalog add $base/extensions.json --name tserdeiro --install-allowed --priority 5
specify preset catalog add $base/presets.json --name tserdeiro --install-allowed --priority 5

specify bundle install product
```

## Verify

```bash
# Offline from this checkout: references resolve against the enclosing
# project, and this repository installs neither the preset nor the extensions.
specify bundle validate --path bundles/product --offline
specify bundle build --path bundles/product --output dist/

# Full reference resolution, from a consumer with the catalogs registered:
scripts/conformance/bundles.sh
```
