# Conformance capture against the real `ocr` binary

**Status: PERFORMED.** Date: 2026-08-02. Engine: open-code-review v1.8.3, commit
`80a579466`, installed by the repository owner into this distribution's data
root and used read-only for this capture. The extension never installed, moved
or updated it.

```text
$ ocr --version
open-code-review v1.8.3 (80a579466) darwin/arm64
built at: 2026-07-31T09:24:52Z
https://github.com/alibaba/open-code-review
```

- Binary: `<data-root>/tools/ocr/1.8.3/node_modules/@alibaba-group/ocr-darwin-arm64/bin/opencodereview`
- SHA-256: `ed12e4599a7d2ddf5ac09324193d9781bd0a4215e867631432bc04cf5918f324` -- **matches** `external_tools.open_code_review.binaries.darwin-arm64` in `versions.lock.yml`
- The npm shim at `node_modules/.bin/ocr` is a different file (`bcdd8917771245de0ccba171995c076dea26896cf3df6204414486ce1ea2ed4e`)
  and is correctly rejected by `doctor` with `ocr_digest_mismatch`.

## Result

`SPECKIT_CODE_REVIEW_OCR_BIN=<binary> uv run pytest tests/conformance -v`:
**16 passed, 188 subtests passed.**

The first capture ran 12 tests and **2 failed**, both on `delegate preview`, and
the adapter failed *closed* -- exit code 9, no guessed scope. Reconciling parser
and fake against the real output is what `ADAPTER_VERSION` exists for; it is now
`2`, and every divergence below is asserted directly on the raw output, so an
upstream change breaks loudly instead of being reinterpreted.

## Divergences found, and how they were reconciled

### 1. Excluded entries are struck through, wrapper including the dash

```text
# Files (2 reviewable / 3 total)

- mode: range
- from: HEAD~1
- to: HEAD
- merge_base: fb9e036c9f9fdaf059e6668fe663d73a5378ee26
- total_insertions: 4
- total_deletions: 2

~~- `docs/guide.md` [modified] +1/-0 (excluded: unsupported_ext)~~
  - `src/m.py` [modified] +2/-1
  - `src/other.py` [modified] +1/-1
```

The adapter expected every entry to be a list item. `~~- ` is not one, so the
parse failed with exit code 9. The parser now unwraps `~~ ... ~~` **only when it
spans a whole list item**; `~~` is not accepted as a delimiter anywhere else,
and the state still comes from what follows the path token, never from the
decoration around it.

### 2. Included entries are indented; metadata are list items in the same section

Two-space indentation was already tolerated. The metadata were not: `- mode:
range` parsed as *a file named `mode`*. That is worse than the loud failure --
a corrupted scope that no exit code announces. Metadata keys are now recognized
inside the file section, and only when the line carries no backticked or quoted
path token, so a file genuinely named `mode` still reports as the file it is.

### 3. `--exclude` reports its own reason

```text
# Files (1 reviewable / 3 total)

- mode: range
- from: HEAD~1
- to: HEAD
- merge_base: fb9e036c9f9fdaf059e6668fe663d73a5378ee26
- total_insertions: 4
- total_deletions: 2

~~- `docs/guide.md` [modified] +1/-0 (excluded: unsupported_ext)~~
  - `src/m.py` [modified] +2/-1
~~- `src/other.py` [modified] +1/-1 (excluded: user_exclude)~~
```

`user_exclude` beside `unsupported_ext`: both are read as reasons and both
entries are excluded. This is the second test that failed in the first capture.

### 4. Workspace mode omits the range metadata

```text
# Files (2 reviewable / 7 total)

- mode: workspace
- total_insertions: 220
- total_deletions: 0

  - `src/m.py` [modified] +1/-0
~~- `preview-exclude.txt` [added] +12/-0 (excluded: unsupported_ext)~~
~~- `preview-workspace.txt` [added] +0/-0 (excluded: unsupported_ext)~~
~~- `preview.txt` [added] +12/-0 (excluded: unsupported_ext)~~
~~- `rule-mixed.txt` [added] +102/-0 (excluded: unsupported_ext)~~
  - `rule.json` [added] +1/-0
~~- `rule.txt` [added] +92/-0 (excluded: unsupported_ext)~~
```

### 5. `delegate rule` is grouped, and the old reading silently produced nothing

Not anticipated before the capture, and the most dangerous of the six: the
parse *succeeded* and returned **zero rules for every file**.

```text
### Rule Group 1: custom / src/**

Applies to:
- src/m.py

#### Content

## System-Specific Rules (Mandatory)
...
### Rule Group 2: custom / **/*.md

Applies to:
- docs/guide.md

#### Content

Docs must be accurate.
```

The rule text under `#### Content` carries its own headings and list items, so
slicing from the first mention of a path to the next heading stopped at
`#### Content` and captured only the "Applies to" list -- every line of which is
a path, all filtered out as titles. The parser now reads the group structure:
heading, `Applies to`, `#### Content`, until the next group. Coverage is still
anchored on the requested paths, the positional reading remains the fallback for
an unrecognized shape, and **groups that parse but carry no rule text at all are
now exit code 9** rather than an empty answer that looks valid.

### 6. `version_string` cannot be a global value (design defect)

`ocr --version` prints `open-code-review v1.8.3 (80a579466) darwin/arm64` plus a
build timestamp. `doctor` compared the whole output for equality, so a string
captured on one machine and committed to a **shared** lock would fail for every
operator on another platform -- exit code 4, blaming a correct installation. The
pin is now the platform-independent prefix (name, version, commit) and the check
is a prefix match on the first line. Per-platform integrity is what the
`binaries` digest map is for, and that check is unchanged.

## What this capture does not establish

The supply-chain audit (`validation/ocr-supply-chain.md`) remains `pending`:
this capture establishes the output format and the digest of the binary that was
run, not what that binary does, what the npm wrapper fetches, or its dependency
tree.
