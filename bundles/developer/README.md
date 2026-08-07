# Developer bundle

Steps 4-7 of the feature workflow, plus the bug/chore short path:
implement one task per branch into the feature branch, open a draft PR,
self-review before `ready for review`.

## What it installs

- Preset `default` — spec, plan, tasks, checklist templates and the
  workflow commands.
- Extension `git` — branch creation and numbering (ships with Spec Kit).
- Extension `bug` — `/speckit.bug.assess|fix|test` triage trio (ships with
  Spec Kit).
- Extension `linear` — task, work-item and PR state projection.
- Extension `code-review` — `/speckit.code-review` self-review.

The exact pinned versions live in [`bundle.yml`](bundle.yml) — this page
deliberately names none, so it cannot rot.

Integration-agnostic: it inherits the project's active agent integration.

## Install

Follow the canonical steps in the
[root README](../../README.md#-primeros-pasos) (register the three
catalogs once per repository, then `specify bundle install developer`).
This page does not duplicate them, so there is exactly one install path
to keep true.

## Verify

```bash
# Offline from this checkout: references resolve against the enclosing
# project, and this repository installs neither the preset nor the extensions.
specify bundle validate --path bundles/developer --offline
specify bundle build --path bundles/developer --output dist/

# Full reference resolution, from a consumer with the catalogs registered:
scripts/conformance/bundles.sh
```
