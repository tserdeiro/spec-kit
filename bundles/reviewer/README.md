# Reviewer bundle

Step 7 of the feature workflow: the final agentic review on the pull request,
plus human review. Approval and merge stay human.

## What it installs

- Preset `default` 0.1.0 (priority 10) — spec, plan, tasks, checklist templates.
- Extension `code-review` 0.1.0 — `/speckit.code-review` with `--publish`.

Integration-agnostic: it inherits the project's active agent integration.

## Install

Register this distribution's catalogs once per repository, then install:

```bash
base=https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog
specify bundle catalog add $base/bundles.json --id tserdeiro --policy install-allowed --priority 5
specify extension catalog add $base/extensions.json --name tserdeiro --install-allowed --priority 5
specify preset catalog add $base/presets.json --name tserdeiro --install-allowed --priority 5

specify bundle install reviewer
```

## Verify

```bash
# Offline from this checkout: references resolve against the enclosing
# project, and this repository installs neither the preset nor the extensions.
specify bundle validate --path bundles/reviewer --offline
specify bundle build --path bundles/reviewer --output dist/

# Full reference resolution, from a consumer with the catalogs registered:
scripts/conformance/bundles.sh
```
