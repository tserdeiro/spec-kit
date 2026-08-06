---
name: speckit.linear.status
description: Report the local feature state and its Linear projection. Never writes.
---

# Spec Kit Linear status

```bash
bash .specify/extensions/linear/scripts/bash/run.sh status --current
```

`status` uses GraphQL queries only. It renders one row per `Txxx` with its
local checkbox, the state derived from observable reality and what produced
it (`checkbox`, `branch`, or `pr`), the remote Issue identifier, workflow
state, and assignee (`—` where not applicable), plus any Issue living in the
Feature Project that was created directly in Linear and carries no bridge
marker. A feature with no Feature Project yet still lists its local tasks.
A **Work items** block follows when any branch or pull request is named after
a Linear Issue key (`<team key>-<number>`, optionally `-suffix`): one row per
bug or chore with its derived state, the observation and branch it came from,
and the Issue's current title and state — or a note that no such Issue exists.
The block is omitted when nothing was observed. `--json` exposes the same
data as `status.task_rows`/`status.remote_only_issues`/`status.work_items`.

Set exactly one of `LINEAR_API_KEY` or `LINEAR_OAUTH_ACCESS_TOKEN`.
