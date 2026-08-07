# Implementation Plan: Integration branch

**Feature directory**: `specs/002-integration-branch`
**Spec**: [spec.md](spec.md)

## Summary

Five small deliveries, all composition: retarget the preset's task loop
and PR command onto the feature branch, teach the product phase to close
with the draft feature PR, teach the closure ritual, and document the
model plus Linear's native GitHub integration in the README. No CLI code,
no extension code — the state derivation is already base-agnostic.

## Technical context

- **Language/runtime**: Markdown agent commands and templates (preset);
  README (Spanish).
- **Primary dependencies**: none new — `gh` stays the PR mechanism;
  Linear's GitHub integration is workspace configuration, not code.
- **Storage/state**: none new. `.specify/feature.json` keeps its role;
  branches and PRs remain the observable truth.
- **Verification**: `scripts/conformance/bundles.sh` green per task; the
  linear suite (`uv run pytest packages/spec-kit-linear/tests`) proves
  derivation is untouched; the end-to-end evidence is this feature
  itself, delivered through the model it builds.
- **Constraints**: composition only (C-001); a reviewed PR per task under
  the ~400-line budget; approval/merge human-only (FR-004).

## Constitution check

No new commands, no new flags, no new dependencies. Upstream assets
untouched — the feature branch upstream already creates simply gains its
purpose. Human product approval, PR approval, and merge remain the only
way anything lands. States stay derived; the native Linear integration
only adds freshness, never authority.

## Approach per task

1. **T001 — retarget the task loop** (`implement-append.md`): before the
   first task, bring the up-to-date default branch into the feature
   branch; every task branches from the feature branch; later refreshes
   are the developer's duty.
2. **T002 — retarget `/speckit.pr`** (`pr.md`): feature-task PRs target
   the feature branch and carry `Fixes <ISSUE-KEY>` in the Work item
   section; work items keep the default branch; the diff summarized is
   against the PR's base.
3. **T003 — the product-phase gate** (`tasks-template.md`): when
   `tasks.md` is complete, commit the artifacts on the feature branch and
   open the draft feature PR (`NNN-slug → default`) — the spec-review
   gate that later becomes the final feature PR.
4. **T004 — the closure ritual** (`implement-append.md`): with every task
   checked, mark the feature PR ready for the final human review; after
   the human **merge commit**, delete the feature branch and reconcile
   with `push`.
5. **T005 — README and Linear settings**: the workflow section teaches
   the model (`dev → NNN-slug → tareas → NNN-slug → dev`); a short block
   documents enabling the per-team GitHub integration and the magic-word
   linking; acceptance evidence recorded under `validation/`.

## Delivery

This feature dogfoods its own model: each task in one branch and one
draft PR **targeting `002-integration-branch`**, self-reviewed before
`ready for review`, human-merged into the feature branch; at the end, the
feature PR (opened at the close of this product phase) turns ready and a
human merges it into `main` with a merge commit. Preset changes reach
consumers in the next preset+bundles release, batched with queued chores
2 and 3.
