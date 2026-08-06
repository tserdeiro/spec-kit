# Changelog

## 0.1.0

First release of the fresh repository. One context-aware review command —
the pending working-tree diff without a candidate, the anchored pull-request
candidate with one, publishing only with `--publish` — plus `doctor --fix`
(installs and digest-verifies the pinned engine from the `engine.lock.yml`
the extension ships) and `completions`. Delegates to Open Code Review
fail-closed; approving and merging are unreachable. Zero runtime
dependencies.
