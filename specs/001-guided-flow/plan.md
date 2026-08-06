# Implementation Plan: Guided flow

**Feature directory**: `specs/001-guided-flow`
**Spec**: [spec.md](spec.md)

## Summary

Five small deliveries, each composing an existing mechanism: one line in
the preset's tasks template (branch at task start), the `NEXT` column in
the linear extension's existing `status` output, two preset agent commands
(`/speckit.pr`, `/speckit.doctor`), and one maintainer script
(`scripts/release/publish.sh`) orchestrating the build scripts that
already exist.

## Technical context

- **Language/runtime**: Python ≥3.11 (linear extension, stdlib only);
  Markdown agent commands (preset); bash (release script).
- **Primary dependencies**: none new — `gh` stays the PR/release
  mechanism, already a prerequisite.
- **Storage/state**: none new; NEXT derives from the state the projection
  already computes.
- **Verification**: `uv run pytest packages/spec-kit-linear/tests` for
  NEXT; `scripts/conformance/bundles.sh` still green (preset grows two
  commands); a real dogfooded PR per task is the end-to-end evidence.
- **Target environment**: every upstream-supported agent (commands are
  `.md`); macOS/Linux shells for the release script.
- **Constraints**: no new CLI commands or flags (C-001); a reviewed PR per
  task stays under the ~400-line budget.

## Constitution check

No new surface, no new dependencies, human approval untouched, states
remain derived — every Stage 6 point composes mechanisms the plan already
sanctions.

## Approach per task

1. **T001 — template instructs the branch** (`presets/default`): the task
   block's start is explicit: create `NNN-T###-slug` before touching code.
2. **T002 — NEXT in `status`** (`packages/spec-kit-linear`): map each
   derived state (+ signals: branch/PR/review presence) to one suggested
   action string in `reporting.py`; text and `--json` both carry it.
3. **T003 — `/speckit.pr`** (`presets/default/commands`): agent command
   that reads the active feature/task, guarantees the branch invariant,
   fills `.github/PULL_REQUEST_TEMPLATE.md` from the artifacts, runs
   `gh pr create --draft`, and is idempotent when the PR exists.
4. **T004 — `/speckit.doctor`** (`presets/default/commands`): runs both
   installed doctors through their launchers and summarizes one result.
5. **T005 — `publish.sh`** (`scripts/release/`): dirty-tree refusal, tags,
   `build-release.sh`/`build-bundles.sh`, lock digest rewrite, push,
   `gh release create` per artifact set.

## Delivery

One branch and one draft PR per task, in order T001 → T005; each PR
self-reviewed with `/speckit.code-review` before `ready for review`;
states visible in Linear throughout; human review and merge per PR.
