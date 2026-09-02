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

## 2026-09-02 — correction round (T016–T019)

1. **The human gate was skipped for sixteen PRs.** #44–#58 were merged
   with zero reviews under the maintainer's account by the delivering
   agent; the review happened afterwards on the feature branch. Whether
   the loop may merge task PRs into the feature branch after a clean fresh
   review is an explicit policy decision still to make.
2. **Budget overruns were absorbed instead of stopping.** T011 landed at
   7× its forecast and T013 amended its own budget from 400 to 700 lines
   inside the PR that breached it. Rule candidate: past 2× the forecast the
   task pauses for a design re-check; a budget is never amended in the PR
   that exceeds it.
3. **Reviews pushed complexity instead of questioning it.** T011's fresh
   reviews requested YAML edge-case handling until a 190-line Python
   resolver with a re-exec into Specify's interpreter replaced a three-line
   shell resolution. Review rules need the repository's simplicity
   principles as findings.
4. **Implementation edited the product contract.** T011 added C-006 (a
   PyYAML requirement) to `spec.md` to justify its design. Task PRs must
   never edit `spec.md`; contract changes are their own human decision.
5. **Conformance failed by design before release.** T013 made the default
   `bundles.sh` reject the bumped tree and left `main` red on merge until
   publication. T019 inverts the modes.
6. **A plain `git revert` fails the repository's own naming check.** The
   default subject (`Revert "Merge pull request …"`) is not
   `type(scope): subject`; T016's fresh review caught it as blocking and
   the commit was reworded. The loop has no revert path; when it needs
   one, the subject must be authored (`revert(scope): …`).

## 2026-09-01 — task delivery (T002–T011, T015)

1. **Graduated — stale Linear and manual gates.** T003/#46 reconciles at
   loop transitions; T005/#48 verifies or opens the feature gate. Both are
   integrated, unreleased preset changes.
2. **Graduated — review state crossed sessions.** T004/#47 delegates a
   fresh review; two further reviews of T010/#53 found stale findings and
   reusable partial-publication state. The integrated candidate binds both to
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
   from Specify. The integrated resolver is 368/400 executable lines, not the
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
10. **Task ledgers diverged across the two stacks.** #45–#51 checked T002–T008;
    #52–#56 checked T009–T011/T015. Neither branch contained the full ledger
    before human integration; T012 correctly did not manufacture it.
11. **Linear configuration vanishes in worktrees.** `speckit-linear.yml`
    and `.speckit-linear.env` are local and gitignored, so a new worktree
    is unlinked despite onboarding the primary checkout. Copying or
    re-establishing local configuration remains manual.
12. **The installed implement skill still announces optional hooks.** Its
    pre/post blocks remain visible during T012; T002 covers the integrated
    product-phase path, not this surface. FR-002 remains broader than the
    delivered task scope.
13. **Release preparation started from only one task stack.** T013 initially
    bumped versions on top of #57, but that branch did not contain the
    T002–T008 stack whose Linear changes its changelog announced. The release
    gate must integrate both reviewed stacks before version preparation; the
    mismatch was caught before commit or publication.
14. **Pre-release conformance could hide a bad public catalog.** Rewriting
    every catalog version in the only conformance mode let `publish.sh` pass
    even if its catalog rewrite drifted. T013 makes the substitution explicit
    with `--local-manifests`; CI and publication keep catalog values
    authoritative.
15. **Bundle conformance does not validate historical lock hashes.** That is a
    separate future integrity check; T013 also corrected release bump
    atomicity, temporary-artifact isolation, and pre-remote rollback gaps.
16. **Stack integration serially reruns the full CI suite.** Collapsing each
    stack from its leaf changed the next PR's base and relaunched all package
    and bundle checks at every step. Correctness held, but integration time
    grows linearly with stack depth; the harness neither queues nor summarizes
    this work.
17. **A stale worktree blocked local branch cleanup after merge.** #55 merged
    and its remote branch was deleted, but `gh pr merge --delete-branch`
    returned failure because a clean `/private/tmp` worktree still held the
    local branch. The operator had to inspect and remove that worktree before
    cleanup could finish.
18. **Root-scoped package tests collide.** `uv run --project <package> pytest`
    from the repository root collected both package test trees and collided on
    `tests.conftest`; the reliable invocation had to scope the path explicitly:
    `pytest packages/<package>/tests`. T013 leaves pytest configuration alone.
19. **Automated review budget expanded after release hardening.** The review
    packet grew from 400 to 615 lines while T013 closed publication and
    rollback gaps; the effective authored executable total remains 549/700.
