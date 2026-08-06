# Clean-consumer installation acceptance — Stage 2 exit

**Status: PERFORMED. Date: 2026-08-03.** A fresh git repository with no
`versions.lock.yml`, initialized with the pinned Specify CLI 0.13.0 and the
`codex` integration, following `docs/guide.md` only.

- Both extensions installed from the published GitHub release ZIPs (the
  upstream CLI shows an interactive "Untrusted Source" confirmation for
  external URLs — expected, answered by the human).
- `doctor --fix` npm-installed the pinned `ocr` 1.8.3 into a virgin
  `XDG_DATA_HOME` and verified the `darwin-arm64` digest against the pin the
  extension ships (`engine.lock.yml`, added in 0.2.1 after 0.2.0 failed this
  exact step): "doctor completed with no blocking problems".
- An advisory `review` of the working tree ran against the freshly installed
  real engine and produced its packet, including the over-budget warning.
- The installed Linear artifact answered `doctor --offline` (demanding the
  `onboard` binding, as documented) and generated `completions`.

Known limitations observed:

- The ZIP extraction drops the executable bit on `scripts/bash/run.sh`;
  harmless because every command invokes it via `bash`.
- The launcher's `uv run --frozen --offline` needs a warm uv cache and an
  available Python >=3.11; a machine that has never run `uv` needs one
  online `uv sync` first.

**Re-verified 2026-08-04** against the published `spec-kit-code-review/v0.2.1`
release ZIP: `engine.lock.yml` ships in the artifact, and `doctor --fix` on a
virgin data root installed and verified the engine with no blocking problems.
The defective `v0.2.0` release was deleted.
