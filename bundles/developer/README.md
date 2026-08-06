# Developer bundle

Steps 4–6 of the feature workflow, plus the bug/chore short path: implement one task per branch, open a draft
PR, self-review before `ready for review`.

## What it installs

- Preset `default` 0.2.1 (priority 10) — spec, plan, tasks, checklist templates.
- Extension `git` 1.0.0 — branch creation and numbering (ships with Spec Kit).
- Extension `bug` 1.0.0 — `/speckit.bug.assess|fix|test` triage trio (ships with Spec Kit).
- Extension `linear` 0.2.0 — task, work-item and PR state projection.
- Extension `code-review` 0.1.1 — `/speckit.code-review` self-review.

Integration-agnostic: it inherits the project's active agent integration.

## Install

Register this distribution's catalogs once per repository, then install:

```bash
base=https://raw.githubusercontent.com/tserdeiro/spec-kit/main/catalog
specify bundle catalog add $base/bundles.json --id tserdeiro --policy install-allowed --priority 5
specify extension catalog add $base/extensions.json --name tserdeiro --install-allowed --priority 5
specify preset catalog add $base/presets.json --name tserdeiro --install-allowed --priority 5

specify bundle install developer
```

## Verify

```bash
# Offline from this checkout: references resolve against the enclosing
# project, and this repository installs neither the preset nor the extensions.
specify bundle validate --path bundles/developer --offline
specify bundle build --path bundles/developer --output dist/

# Full reference resolution, from a consumer with the catalogs registered:
scripts/conformance/bundles.sh
```
