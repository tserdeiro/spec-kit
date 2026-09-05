# Changelog

## 0.4.0

- A task pull request (base branch `NNN-…`) that touches a `protected_paths`
  entry — `specs/*/spec.md` and the constitution by default, configurable —
  now gets an automatic `blocking`/`contract` finding and
  `changes-requested`, whatever the reviewing agent found. A pull request
  based on the delivery trunk is exempt.
- The base rule template `doctor --fix` writes now states the
  repository's engineering principles as a `**/*` rule ahead of the
  Python-specific one: over-engineering and speculative abstraction are
  `major` findings, a new runtime dependency is `blocking`. A repository
  with an existing rule file merges it in by hand.

## 0.3.0

- Normalized findings are written to `findings-normalized.json`; the
  agent's `findings.json` input is preserved untouched.
- `--findings` must equal the exact session path it closes.
- A `~user` findings path that fails to expand is a usage error.
- The docs show the accepted findings shape.

## 0.2.1

- The doctor derives its supported Spec Kit range from `extension.yml`
  — one source of truth; the hardcoded copies that drifted on the
  v1.0.1 upgrade are gone — and the conformance harness derives the
  pinned CLI from the source checkout's `versions.lock.yml`.

## 0.2.0

- The distribution's upstream pin moved from `github/spec-kit` v0.13.0 to
  v1.0.1: the manifest requires specify-cli `>=1.0.1,<1.1.0`, the doctor
  validates the installed CLI against that same range (a test now keeps
  them from drifting apart), and the conformance harness gates on 1.0.1.

## 0.1.1

- The persisted session `repository_root` is expanded on read; phase 2 of
  the review works again for any repository under the home directory
  (`.specify/bugs/session-root-redaction/`).

## 0.1.0

First release of the fresh repository. One context-aware review command —
the pending working-tree diff without a candidate, the anchored pull-request
candidate with one, publishing only with `--publish` — plus `doctor --fix`
(installs and digest-verifies the pinned engine from the `engine.lock.yml`
the extension ships) and `completions`. Delegates to Open Code Review
fail-closed; approving and merging are unreachable. Zero runtime
dependencies.
