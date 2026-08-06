# Repository operating contract

## Scope

This is the independent source repository for `tserdeiro/spec-kit`, not a fork
of `github/spec-kit` and not a consumer application. `docs/vision.md` is the authoritative product
vision; `docs/plan.md` is the staged-delivery contract derived from it. On
conflict, the vision wins.

## Engineering principles

- Do not preserve backward compatibility. Remove obsolete paths instead of
  adding compatibility layers, fallbacks, or migrations.
- Choose the simplest implementation that fully meets the current
  requirements. Avoid speculative abstractions, configuration, and
  indirection.
- Grow the system in layers. Start from the smallest version that works
  end-to-end, then add each capability on top of a product that already works.
  Never trade a working product for unfinished complexity.
- Keep components modular and concerns clearly separated.
- Prefer established, well-maintained libraries when they reduce overall
  complexity or improve reliability. Do not reimplement common functionality
  without a clear reason.
- Inspect the dependencies already in the project before writing an
  implementation or adding packages. Do not assume a library lacks a
  capability without checking its documentation and types.
- Make architectural decisions for the long term. Do not accept a stopgap that
  only works for now and is meant to be replaced later.
- Never attribute co-authorship to an AI agent in comments, pull requests,
  commits, or any other repository artifact.

## Communication style

- Be extremely concise in all responses, status updates, comments, pull
  requests, commit messages, and documents.
- Lead with the outcome. Include only the decision, essential evidence, and
  necessary action or status.
- Default to one short paragraph or up to three bullets. Do not add preambles,
  restate the request, narrate routine work, repeat information, or add closing
  summaries.
- Write documents with the smallest structure that fully serves their purpose.
  Use short sentences and remove generic context, duplicated explanations, and
  speculative sections.
- Expand only when the user asks, or when detail is necessary for correctness,
  safety, a required template, or reproducibility.

## Boundaries

- Compose the exact upstream version in `versions.lock.yml`; do not copy or
  reimplement Specify CLI or its integration registry.
- Keep the native `specify` and `speckit` command names unchanged.
- Keep integrations consumer-selected. The Stage 1 Codex, Pi, and Claude
  matrix is a minimum conformance sample, never a closed list.
- Consumer repositories own their feature artifacts, `.specify/feature.json`,
  selected integration files, and Git state. They must not depend on this
  source checkout at runtime.
- Treat `.specify/scripts`, `.specify/templates`, `.specify/workflows`, the Git
  extension payload, and generated agent skills as upstream-managed baseline
  assets. Change them only through a reviewed upstream upgrade. The authored
  constitution under `.specify/memory/` is project policy, not an upstream
  patch.

## Delivery discipline

- Implement stages from `docs/plan.md` sequentially and stop at the active
  stage. A command exposes only what its step needs; do not add commands,
  flags, presets, bundles, or synchronization ahead of their stage.
- Use fixtures and temporary repositories for branch-changing tests; do not
  change the main checkout's branch for conformance.
- Core `.specify/templates/` remain upstream-managed; workflow customization
  lives in the `default` preset (`presets/default/`), dev-installed locally
  with `specify preset add --dev presets/default` (`.specify/presets/` is
  untracked install state).
- Package conformance scripts live under `packages/*/scripts/conformance/`.
  Report generated-asset validation separately from actual agent runtime
  execution.
- Commit messages always use English, in the form `type(scope): subject`
  (e.g. `docs(readme): the front door`), one concern per commit.
- Repository documents are written in English, with one deliberate
  exception: the README and `docs/vision.md` are in Spanish for the
  consuming team.
- Never commit secrets, agent credentials, operator identity, or environment
  files. Git commits and remote publication remain human-controlled unless a
  user explicitly changes that operating agreement.

## Pull-request guidance

Any agent that creates or updates a pull-request body MUST use the canonical
`.github/PULL_REQUEST_TEMPLATE.md` with these sections in order:

1. `## Work item`
2. `## Outcome`
3. `## Changes`
4. `## Verification evidence`
5. `## Risk and delivery`
6. `## Review focus`

Record commands and truthful results in the evidence table. Do not add
attestations for status that deterministic GitHub checks already own. Product
correctness, risk acceptance, approval, commit, push, final review, and merge
remain human decisions.
