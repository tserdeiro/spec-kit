# Dogfooding log

Standing friction log for this repository's own workflow. **Graduated**
means implemented in a ready task PR; it does not mean merged, released,
or available to consumers. Open candidates stay here. Log-only commits
remain separate from phase-scoped commits.

## Upstream-rooted candidates (out of distribution control)

Recorded 2026-08-31 from the first consumer run; these live in
upstream-managed assets and wait for a reviewed upstream upgrade or
upstream PR. Distribution changes do not patch them; they neutralize only
the scoped behavior named below (`003-delivery-automation`, C-001):

- Core command templates instruct agents to *print* "Optional Hook"
  blocks instead of resolving hooks deterministically. **Partially
  graduated:** T002/#45 neutralizes product-phase output; the installed
  implement skill still exposes both optional-hook blocks.
- Hook resolution is LLM-interpreted YAML repeated ~50 lines twice in
  every command template: context cost per command, inconsistently
  executed.
- The git extension's `auto-commit.sh` stages `git add .` — it sweeps
  unrelated dirty files into hook commits. **Partially graduated:**
  T002/#45 bypasses it with scoped product-phase commits.
- The git extension's config template disables `auto_commit` for every
  event while the hook registry enables the hooks that invoke it: the
  announced command is a no-op as shipped. **Partially graduated:**
  T002/#45 replaces the product-phase behavior only.

## 2026-08-31 — source-repo run (feature 003-delivery-automation)

1. **Skills exist only for the init-time integration.** This repo was
   initialized with `ai: codex`, so a Claude Code session here has no
   `/speckit.*` commands; the flow was followed by reading
   `.agents/skills/*/SKILL.md` manually. `speckit.doctor --fix` mirrors
   skills only across *installed* agents — installing a second agent
   integration is still a manual `specify init` decision nobody surfaces.
2. **Graduated — the projection half was absent.** T001/#44 installs the
   released Linear and code-review extensions and onboards TDS on its
   ready branch. Main remains unchanged until human integration.
3. **The branch hook hints at the wrong persistence.** `before_specify`
   prints `To persist: export SPECIFY_FEATURE=...` while the flow's real
   persistence is `.specify/feature.json`, which the specify command
   writes anyway. Two mechanisms; the hint names the one nobody needs.
4. **Tooling installed by a task vanishes on sibling branches.** T001
   vendored the loop's Linear and review commands, but a sibling from the
   feature branch did not contain them while T001 was unmerged. Both later
   stacks had to base on T001. The dependency model sees code dependencies,
   not operational tooling; the loop should treat missing loop tooling as an
   implicit stacking dependency.
5. **The extension installer leaves uncommittable noise.** `specify
   extension add` writes `.specify/extensions/.cache/` without a shipped
   gitignore entry and builds a payload `.venv` on first run; neither belongs
   in consumer commits.

## 2026-09-01 — task delivery (T002–T011, T015)

1. **Graduated — stale Linear and manual gates.** T003/#46 reconciles at
   loop transitions; T005/#48 verifies or opens the feature gate. Both are
   ready, unmerged preset changes.
2. **Graduated — review state crossed sessions.** T004/#47 delegates a
   fresh review; two further reviews of T010/#53 found stale findings and
   reusable partial-publication state. The ready candidate binds both to
   their session and normalized plan; code-review 0.3.0 is unreleased.
3. **Graduated — setup failed late and opaquely.** T006/#49 names
   `onboard` before any network call; T007/#50 diagnoses the two GitHub
   delivery settings; T008/#51 states native versus reconciled coverage.
   Review corrected T008's false claim that a target-branch rule was
   required. `onboard` creates missing Team default mappings; the workspace
   GitHub connection and optional branch overrides remain manual.
4. **Graduated — generated tasks required manual deletion.** T009/#52
   ignores fenced examples. Linear 0.11.0 is not released, so consumers
   still need the workaround.
5. **Graduated — trunk parsing was reimplemented.** T011 began as a
   hand-written YAML scalar parser and needed repeated reviews for runtime,
   multiline, scalar, and literal-branch failures before #55 reused PyYAML
   from Specify. The ready resolver is 368/400 executable lines, not the
   forecast ~50.
6. **The T011/T015 split arrived late.** Runtime command wiring needed
   another 195 executable lines, so it became T015/#56 only after T011
   neared its budget. The task-sizing correction is recorded, not
   automated.
7. **PR #54 carried the wrong task identity.** It reused a T011 branch for
   the new wiring task; it was closed and replaced by T015/#56. Branch
   validation checks syntax, not that `T###` matches the selected task.
8. **Graduated — checked-out branch and active feature are independent.**
   `.specify/feature.json`/`SPECIFY_FEATURE_DIRECTORY` selects the feature;
   Git selects the current branch. T015/#56 now uses prerequisite `BRANCH`
   for the feature branch, validates the checkout separately, and keeps
   repository-derived names as inert arguments.
9. **Graduated — the tasks template still named the default branch.**
   T015/#56 changes it to the configured delivery base. Preset 0.8.0 is
   unreleased.
10. **Task ledgers diverge across the two stacks.** #45–#51 checks T002–T008;
    #52–#56 checks T009–T011/T015. Neither branch contains the full ledger
    until humans merge both; T012 must not manufacture that integration.
11. **Linear configuration vanishes in worktrees.** `speckit-linear.yml`
    and `.speckit-linear.env` are local and gitignored, so a new worktree
    is unlinked despite onboarding the primary checkout. Copying or
    re-establishing local configuration remains manual.
12. **The installed implement skill still announces optional hooks.** Its
    pre/post blocks remain visible during T012; T002 covers product-phase
    commands on a sibling ready PR, not this surface. FR-002 remains broader
    than the delivered task scope.
