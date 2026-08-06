# OCR npm specifier: empirical confirmation of the tag ↔ npm version mapping

Scope: Stage 1 of `packages/spec-kit-code-review`, per `spec-kit-code-review.md`
("Pin e integridad de OCR"), which leaves the npm version specifier of the
pinned baseline **to be confirmed empirically in Stage 1** and forbids inventing
one in the meantime.

Why it was open: the wrapper's committed `package.json` declares `0.0.0` as a
placeholder, so the contract records that "the npm version and the Git tag are
not the same identity" and that the operative pin is `version_string` plus the
binary digests. What had to be established is whether a *published* npm version
corresponds to the pinned Git tag, so that `doctor`'s remediation can print a
command a person can actually run.

## Evidence

Date: **2026-08-01**. Environment: macOS 15 (arm64), npm from the operator's own
toolchain, public registry, no authentication.

```console
$ npm view @alibaba-group/open-code-review versions --json
[
  "1.0.0",
  … 77 more versions …
  "1.8.0",
  "1.8.1",
  "1.8.2",
  "1.8.3",
  "1.8.4"
]
```

82 published versions in total; the `1.8.x` family is exactly
`1.8.0, 1.8.1, 1.8.2, 1.8.3, 1.8.4`.

```console
$ npm view @alibaba-group/open-code-review dist-tags
{ latest: '1.8.4' }

$ npm view @alibaba-group/open-code-review@1.8.3 name version dist.tarball dist.shasum
name = '@alibaba-group/open-code-review'
version = '1.8.3'
dist.tarball = 'https://registry.npmjs.org/@alibaba-group/open-code-review/-/open-code-review-1.8.3.tgz'
dist.shasum = '106104ae96cffb8d4737ddb7a651cd5b285d2044'
```

The corresponding upstream release exists, with per-platform binaries and a
checksum manifest:

```console
$ curl -sS https://api.github.com/repos/alibaba/open-code-review/releases/tags/v1.8.3
tag_name: v1.8.3   name: v1.8.3   published_at: 2026-07-31T09:33:56Z
assets: opencodereview-darwin-amd64, opencodereview-darwin-arm64,
        opencodereview-linux-amd64, opencodereview-linux-arm64,
        opencodereview-windows-amd64.exe, opencodereview-windows-arm64.exe,
        sha256sum.txt
```

## Conclusion

- The registry publishes `1.8.3` and the project publishes the GitHub release
  `v1.8.3`. For this version family the mapping **tag → npm version is the tag
  without its leading `v`**, and the specifier for the pinned baseline is
  `@alibaba-group/open-code-review@1.8.3`.
- `doctor` therefore prints an installation command carrying that specifier as
  the remediation when `ocr` is missing — a command for a **person** to run;
  agents never install, download, or update `ocr`. Since the 2026-08-02 paths
  decision the command installs with `--prefix` into this distribution's data
  root and `--save-exact`, and is **never** global: a tool this extension pins
  must not outlive its own uninstall on anyone's machine.
- The mapping is applied only to a tag shaped `vX.Y.Z`. Anything else is not
  guessed: the message then names the tag and the Releases page only
  (`npm_specifier()` in `src/spec_kit_code_review/paths.py`, consumed by
  `doctor` and `upgrade`).
- The package **name** is read from
  `extensions.code-review.external_tools.open_code_review.npm_package` in the
  lock, not from a constant, so a rename of the wrapper travels with the pin.

## Caveats, deliberately recorded

- **The pinned baseline is not `latest`.** `dist-tags.latest` is already `1.8.4`,
  and `1.8.4` was published after the `v1.8.3` baseline this contract selected.
  Moving the pin is a separate, human procedure ("Actualizacion y rollback"), and
  it requires re-running the adapter conformance test against the real binary
  and recalculating the digests.
- This confirms the *specifier*, not the wrapper's internal `package.json`
  version field, which remains a placeholder. The operative pin is still
  `version_string` (the exact `ocr --version` output) plus the per-platform
  binary digests.
- **`version_string` remains unconfirmed**: obtaining it requires installing the
  binary, which agents must never do. It stays `<pendiente>` in the lock until a
  person installs `ocr` and records it.
- The `versions.lock.yml` entry for this extension is **not** written by Stage 1:
  writing it belongs to the release stage. Until it exists, `doctor` reports
  `ocr_pin_missing` as a warning, which is the correct behaviour today.

## Release-stage inputs captured while confirming the above

From `https://github.com/alibaba/open-code-review/releases/download/v1.8.3/sha256sum.txt`
(the file's own SHA-256 is
`51c22d77815f841a28b0c5b52e13483938212bd659b96f0ca2ccd494475a3e22`):

```text
445c2c3d7528d6a642b2eb83dc76978d7a5558b838d0c385b0c841b094104c17  opencodereview-linux-amd64
4badb4b02fb9f7b4e91b5078fa78e88bfa8e3864f43bedd216b179494e9df4d7  opencodereview-linux-arm64
a5f884bb9a04abb2068e8f9f3b3c567cb65f0847f61876c7c44deb42b8c2d61a  opencodereview-darwin-amd64
ed12e4599a7d2ddf5ac09324193d9781bd0a4215e867631432bc04cf5918f324  opencodereview-darwin-arm64
13366f4c06fdded86f0b43018c4516db6445677803c14eca97df967c7c17ff0c  opencodereview-windows-amd64.exe
acc10c7f840aca9b20743e3dee1a2e76c91b7731a8cf8d215db26968b30a390e  opencodereview-windows-arm64.exe
```

These are recorded as evidence only. They are **not** a supply-chain audit:
`validation/ocr-supply-chain.md` does not exist yet, `audit_status` stays
`pending`, and the `reviewer` bundle cannot adopt this extension until it does.
