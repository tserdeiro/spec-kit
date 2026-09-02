---
name: speckit.linear.onboard
description: Bind this repository to a Linear team. Resolves every ID read-only; never mutates Linear.
---

# Spec Kit Linear onboard

The single entry path for a repository. It resolves everything by name and
writes `speckit-linear.yml` at the repository root:

```bash
bash .specify/extensions/linear/scripts/bash/run.sh onboard --team-key WOR --repository spec-kit
bash .specify/extensions/linear/scripts/bash/run.sh onboard --team-key WOR --repository spec-kit --dry-run
```

`--repository SLUG` and one of `--team-id`/`--team-key` are required.
`onboard` reads Linear to resolve the workspace, the Team, the `Repository`
Project Label group and its `<slug>` child label, the `<slug> / Features` and
`<slug> / Work` Shared Views, and four Team workflow states: `completed`,
`unstarted`, and the two `started` states named `In Progress` and `In
Review`. It issues no GraphQL mutation of any kind.

`--dry-run` previews the resolution and the config diff without writing;
otherwise the configuration is written and `.speckit-linear.env` is added to
`.gitignore`. `speckit-linear.yml` itself is committed: it carries no secrets,
so teammates and CI inherit the binding from Git.

Re-running is idempotent. Anything `onboard` could not find in Linear is
listed in `changes.missing_remote_resources` with a warning naming exactly
what to create by hand; create it and run `onboard` again.
