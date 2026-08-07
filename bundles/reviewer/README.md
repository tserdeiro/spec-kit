# Reviewer bundle

Step 7 of the feature workflow: the final review before a human
approves and merges.

## What it installs

- Preset `default` — spec, plan, tasks, checklist templates and the
  workflow commands.
- Extension `code-review` — `/speckit.code-review` final review
  (`--publish`).

The exact pinned versions live in [`bundle.yml`](bundle.yml) — this page
deliberately names none, so it cannot rot.

Integration-agnostic: it inherits the project's active agent integration.

## Install

Follow the canonical steps in the
[root README](../../README.md#-primeros-pasos) (register the three
catalogs once per repository, then `specify bundle install reviewer`).
This page does not duplicate them, so there is exactly one install path
to keep true.

## Verify

```bash
# Offline from this checkout: references resolve against the enclosing
# project, and this repository installs neither the preset nor the extensions.
specify bundle validate --path bundles/reviewer --offline
specify bundle build --path bundles/reviewer --output dist/

# Full reference resolution, from a consumer with the catalogs registered:
scripts/conformance/bundles.sh
```
