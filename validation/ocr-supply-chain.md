# open-code-review supply-chain audit — spec-kit-code-review

**Status: `approved`, signed off by the owner on 2026-08-02.** This file records
what was established, how, and what remains a judgement rather than a
measurement. The empirical work is below; the sign-off accepts the residual
risk named in "What is NOT established". The lock records
`audit_status: approved`, which is what lets the release gate open and what the
`reviewer` bundle's Stage 4 adoption depends on (`docs/plan.md`, extensions
contract). **The approval is scoped to the pinned version**: any change to the
OCR pin returns this to `pending` until the procedure below is repeated in
full.

## What is established

| Fact | Value | How |
|---|---|---|
| Upstream | https://github.com/alibaba/open-code-review | release page, `v1.8.3` |
| License | Apache-2.0 | repository `LICENSE` at the tag |
| Release tag | `v1.8.3` (2026-07-31) | release page |
| `sha256sum.txt` digest | `51c22d77815f841a28b0c5b52e13483938212bd659b96f0ca2ccd494475a3e22` | downloaded from the release, hashed locally |
| npm package | `@alibaba-group/open-code-review@1.8.3` | `validation/ocr-npm-specifier.md` |

Per-platform binary digests, transcribed from that `sha256sum.txt` and recorded
in `versions.lock.yml`:

```text
darwin-arm64  ed12e4599a7d2ddf5ac09324193d9781bd0a4215e867631432bc04cf5918f324
darwin-amd64  a5f884bb9a04abb2068e8f9f3b3c567cb65f0847f61876c7c44deb42b8c2d61a
linux-amd64   445c2c3d7528d6a642b2eb83dc76978d7a5558b838d0c385b0c841b094104c17
linux-arm64   4badb4b02fb9f7b4e91b5078fa78e88bfa8e3864f43bedd216b179494e9df4d7
```

These are **provenance evidence, not an audit**: they establish that a given
file is the file the upstream release published, and nothing about what that
file does.

## Empirical findings, 2026-08-02

Observations of the already-installed pinned binary. Agents never install
`ocr`; running an installed binary to watch what it does is not installing it,
and it is the only way these questions get answered.

| Question | Finding | Method |
|---|---|---|
| Third-party dependencies of the npm wrapper | **None.** `dependencies` is empty; `optionalDependencies` lists only its own six platform binaries | `package.json` of the installed wrapper |
| Wrapper install script | One `postinstall`, `node scripts/install.js` — the platform-binary resolver already described in the specifier record | same |
| Binary provenance | The installed `darwin-arm64` binary hashes to the digest this lock pins, so npm delivered exactly the GitHub Release artifact | `shasum -a 256` against `versions.lock.yml` |
| Endpoints compiled into the binary | 29 distinct hosts: the LLM providers it supports, schema and specification namespaces (`json-schema.org`, `w3.org`, `protobuf.dev`, `go.dev`), `opentelemetry.io`, `github.com`, and `openaipublic.blob.core.windows.net` | `strings` over the 43 MB binary |
| **Does `delegate` reach the network?** | **No.** `delegate preview` produces byte-identical output with `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` pointed at a dead port — Go's transport honours those — and twelve observed runs of `delegate preview` and `delegate rule` opened **zero** non-loopback sockets | proxy blackhole + `lsof -nP -i` polled for the lifetime of each process |
| Does it modify the repository under review? | **No.** The file tree is identical before and after | `find` digest before/after |
| What it writes outside the repository | One session file under `$HOME/.opencodereview/sessions/<encoded-repo-path>/<uuid>.jsonl`, **0 bytes in delegation mode** | run with a temporary `HOME` |
| Does that session file leak source? | **No.** A canary string planted in the diff does not appear; the file has no content at all | canary run |
| Telemetry | Not mentioned in output; off by default per upstream, opt-in via `OCR_ENABLE_TELEMETRY` | run with a clean `HOME` |

The load-bearing result is the network one: the extension's whole design
assumes `ocr delegate` is local, and that assumption is now measured rather
than trusted. Two residual notes: the session file's *path* discloses the
reviewed repository's location on disk even though its contents are empty, and
`~/.opencodereview` is created outside the `tserdeiro/spec-kit` namespace this
distribution otherwise keeps everything in.

## What is NOT established, and blocks `audit_status: approved`

1. **The binary itself is not audited.** 43 MB of compiled Go was observed from
   the outside, not read. The measurements above say what it did on this
   machine, for these inputs, at this version — they are not a proof about all
   inputs, and they cannot rule out behaviour conditioned on something these
   runs did not present. Only a person can decide that the observed behaviour,
   the Apache-2.0 licence, the upstream's provenance and the residual unknown
   together are acceptable for running over private source.
2. **`version_string` is now recorded, and its shape was a finding.** The
   2026-08-02 conformance capture obtained the exact output and the lock
   records `open-code-review v1.8.3 (80a579466)`. That is deliberately not the
   whole output: `ocr --version` also prints the platform and a build
   timestamp, so a lock carrying the full string would fail on every platform
   other than the one that wrote it. `doctor` verifies that the first line
   *starts with* the recorded identity; per-platform integrity comes from the
   `binaries` digests below. This item no longer blocks the audit.
3. **The wrapper and its dependency tree are reviewed; nothing blocks here.**
   It declares no third-party dependencies, only its own platform binaries, and
   the binary it delivered hashes to the pinned digest. Kept in this list so the
   reader sees it was asked, not skipped.
4. **Delegation mode's network behaviour is measured; nothing blocks here.**
   See the findings above. The assumption the extension is built on held under
   both a proxy blackhole and direct socket observation.
5. **The residual risk is a judgement, not a measurement.** Everything a person
   still has to weigh is in item 1: what the compiled binary might do under
   inputs these runs did not present.

## Procedure to complete it (human)

Steps 1 through 5 below were executed on 2026-08-02 and their results are in
"Empirical findings" above. They are kept as the procedure to repeat, in full,
on any change to the OCR pin — the findings expire with the version they were
taken against.

```bash
# 1. Install the pinned engine into this distribution's data root, never global
npm install --prefix "${XDG_DATA_HOME:-$HOME/.local/share}/tserdeiro/spec-kit/tools/ocr/1.8.3" \
  --save-exact @alibaba-group/open-code-review@1.8.3

# 2. Verify the binary the wrapper installed against the recorded digest.
#    Hash the platform binary, NOT node_modules/.bin/ocr: that entry is a JS
#    shim with a different digest, and hashing it produces a false mismatch.
#    Substitute your platform for darwin-arm64.
shasum -a 256 "${XDG_DATA_HOME:-$HOME/.local/share}/tserdeiro/spec-kit/tools/ocr/1.8.3/node_modules/@alibaba-group/ocr-darwin-arm64/bin/opencodereview"

# 3. Record the exact version string, and put it in versions.lock.yml
ocr --version

# 4. Review the wrapper: what it downloads, from where, and its dependencies
npm ls --prefix "${XDG_DATA_HOME:-$HOME/.local/share}/tserdeiro/spec-kit/tools/ocr/1.8.3" --all

# 5. Run the adapter's conformance capture against the real binary
SPECKIT_CODE_REVIEW_OCR_BIN="$(command -v ocr)" \
  uv run pytest packages/spec-kit-code-review/tests/conformance -v
```

Then set `audit_status: approved` in `versions.lock.yml`, record the date and
the person, and note here anything the review found. Until every step is done,
`pending` is the honest value and the release script refuses to build.
