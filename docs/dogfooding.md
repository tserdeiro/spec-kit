# Dogfooding log

Standing friction log: every non-automated chore, oddity, or improvement
candidate met while delivering this repository's own work through the
workflow. One dated entry per friction, appended as found. Items graduate
into a spec (and are marked so) or stay here as candidates.

## Upstream-rooted candidates (out of distribution control)

Recorded 2026-08-31 from the first consumer run; these live in
upstream-managed assets and wait for a reviewed upstream upgrade or
upstream PR — the distribution only neutralizes their behavior
(`003-delivery-automation`, C-001):

- Core command templates instruct agents to *print* "Optional Hook"
  blocks instead of resolving hooks deterministically.
- Hook resolution is LLM-interpreted YAML repeated ~50 lines twice in
  every command template: context cost per command, inconsistently
  executed.
- The git extension's `auto-commit.sh` stages `git add .` — it sweeps
  unrelated dirty files into hook commits.
- The git extension's config template disables `auto_commit` for every
  event while the hook registry enables the hooks that invoke it: the
  announced command is a no-op as shipped.

## 2026-08-31 — source-repo run (feature 003-delivery-automation)

1. **Skills exist only for the init-time integration.** This repo was
   initialized with `ai: codex`, so a Claude Code session here has no
   `/speckit.*` commands; the flow was followed by reading
   `.agents/skills/*/SKILL.md` manually. `speckit.doctor --fix` mirrors
   skills only across *installed* agents — installing a second agent
   integration is still a manual `specify init` decision nobody surfaces.
2. **The projection half of the flow is not installed where its own work
   is tracked.** This repository tracks work in Linear (TDS) yet had no
   Linear extension installed; features 001–002 could not have projected.
   Taken into `003-delivery-automation` (A-002).
3. **The branch hook hints at the wrong persistence.** `before_specify`
   prints `To persist: export SPECIFY_FEATURE=...` while the flow's real
   persistence is `.specify/feature.json`, which the specify command
   writes anyway. Two mechanisms; the hint names the one nobody needs.
