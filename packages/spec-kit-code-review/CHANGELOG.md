# Changelog

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
