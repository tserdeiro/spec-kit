#!/usr/bin/env bash
# The whole maintainer release in one invocation (Stage 6, T005).
#
# `--bump <component>=<version> ...` rewrites every pin a release needs
# coherently — manifests, bundle pins, changelog skeletons — so the
# human only writes the changelog entries,
# reviews the diff, and commits. (Added after the 0.2.1 incident: the
# hand-made bump was the only step that could drift.)
#
# Then the plain invocation does everything mechanical, in the order the
# distribution's release flow established: refuse a dirty tree -> tag and
# build each extension whose manifest version has no tag yet -> rewrite the
# lock and catalogs from the manifests -> commit the pins -> tag and build
# the bundles -> push everything -> create the GitHub releases. `--dry-run`
# prints the plan and touches nothing.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
cd "$repo_root"

dry_run=false
[ "${1:-}" = "--dry-run" ] && dry_run=true
[ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] && {
  echo "Usage: publish.sh [--dry-run | --bump <linear|code-review|preset|bundles>=<x.y.z> ...]" >&2; exit 2; }

fail() { echo "ERROR: $1" >&2; exit 1; }

# --- Bump mode -------------------------------------------------------------
if [ "${1:-}" = "--bump" ]; then
  shift
  [ $# -ge 1 ] || fail "usage: publish.sh --bump <linear|code-review|preset|bundles>=<x.y.z> ..."
  [ -z "$(git status --porcelain)" ] || fail "the tree is dirty; commit or stash first"
  python3 - "$@" <<'EOF' || exit 1
import re, sys
from pathlib import Path

targets = {}
for arg in sys.argv[1:]:
    key, _, version = arg.partition("=")
    if key not in ("linear", "code-review", "preset", "bundles") or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"ERROR: invalid bump '{arg}'; expected <linear|code-review|preset|bundles>=<x.y.z>")
    targets[key] = version

if set(targets) & {"linear", "code-review", "preset"} and "bundles" not in targets:
    sys.exit("ERROR: the bundles pin what they install and move together; add bundles=<x.y.z>")

parse = lambda v: tuple(int(p) for p in v.split("."))
def current(text, path):
    m = re.search(r'^  version: "(\d+\.\d+\.\d+)"', text, re.M)
    if not m:
        sys.exit(f"ERROR: no version found in {path}")
    return m.group(1)

# Validate everything first, write only when the whole bump is coherent —
# a half-applied bump is exactly the drift this mode exists to prevent.
writes = []

manifests = {"linear": Path("packages/spec-kit-linear/extension.yml"),
             "code-review": Path("packages/spec-kit-code-review/extension.yml"),
             "preset": Path("presets/default/preset.yml")}
# The Python packaging metadata must tell the same version as the extension
# manifest, or `--version` lies (it did, at 0.2.0, until the docs truth pass).
package_metadata = {"linear": "packages/spec-kit-linear",
                    "code-review": "packages/spec-kit-code-review"}
for key, path in manifests.items():
    if key not in targets:
        continue
    text = path.read_text()
    old = current(text, path)
    if parse(targets[key]) <= parse(old):
        sys.exit(f"ERROR: {key} is already {old}; {targets[key]} does not move it forward")
    writes.append((path, text.replace(f'version: "{old}"', f'version: "{targets[key]}"', 1),
                   f"{old} -> {targets[key]}"))
    if key in package_metadata:
        package = Path(package_metadata[key])
        pyproject = package / "pyproject.toml"
        writes.append((pyproject, re.sub(r'^version = "[^"]+"', f'version = "{targets[key]}"',
                                         pyproject.read_text(), count=1, flags=re.M),
                       f"version -> {targets[key]}"))
        init = next((package / "src").glob("*/__init__.py"))
        writes.append((init, re.sub(r'__version__ = "[^"]+"', f'__version__ = "{targets[key]}"',
                                    init.read_text(), count=1),
                       f"__version__ -> {targets[key]}"))

if "bundles" in targets:
    for role in ("product", "developer", "reviewer"):
        path = Path(f"bundles/{role}/bundle.yml")
        text = path.read_text()
        old = current(text, path)
        if parse(targets["bundles"]) <= parse(old):
            sys.exit(f"ERROR: bundles/{role} is already {old}; {targets['bundles']} does not move it forward")
        text = text.replace(f'version: "{old}"', f'version: "{targets["bundles"]}"', 1)
        for key, pin in (("linear", "linear"), ("code-review", "code-review"), ("preset", "default")):
            if key in targets:
                text = re.sub(rf'(- id: "{pin}"\n      version: ")[^"]+', rf'\g<1>{targets[key]}', text)
        writes.append((path, text, f"{old} -> {targets['bundles']} (pins updated)"))

for key, package in (("linear", "spec-kit-linear"), ("code-review", "spec-kit-code-review")):
    if key not in targets:
        continue
    path = Path(f"packages/{package}/CHANGELOG.md")
    writes.append((path, path.read_text().replace(
        "# Changelog\n", f"# Changelog\n\n## {targets[key]}\n\n- TODO\n", 1),
        f"skeleton for {targets[key]}"))

for path, text, note in writes:
    path.write_text(text)
    print(f"  {path}: {note}")
EOF
  echo "bump applied; write the changelog entries (replace TODO), review the diff, commit, then run publish.sh"
  exit 0
fi

# --- Preconditions ---------------------------------------------------------
[ -z "$(git status --porcelain)" ] || fail "the tree is dirty; commit or stash first"
gh auth status >/dev/null 2>&1 || fail "gh is not authenticated (gh auth login)"

manifest_version() { sed -n 's/^  version: "\(.*\)"/\1/p' "$1" | head -1; }

linear_version=$(manifest_version packages/spec-kit-linear/extension.yml)
review_version=$(manifest_version packages/spec-kit-code-review/extension.yml)
preset_version=$(manifest_version presets/default/preset.yml)
bundle_version=$(manifest_version bundles/product/bundle.yml)

# The bundles move together, and their pins must match the manifests they
# will install — fail closed on drift instead of publishing a broken pin.
for role in product developer reviewer; do
  v=$(manifest_version "bundles/$role/bundle.yml")
  [ "$v" = "$bundle_version" ] || fail "bundles/$role is $v but product is $bundle_version; bundles move together"
done
python3 - "$linear_version" "$review_version" "$preset_version" <<'EOF' || fail "a bundle pin does not match its manifest version"
import sys
from pathlib import Path
linear, review, preset = sys.argv[1:4]
for role in ("product", "developer", "reviewer"):
    t = Path(f"bundles/{role}/bundle.yml").read_text()
    for ext, version in (("linear", linear), ("code-review", review)):
        if f'id: "{ext}"' in t and f'- id: "{ext}"\n      version: "{version}"' not in t:
            sys.exit(1)
    if f'- id: "default"\n      version: "{preset}"' not in t:
        sys.exit(1)
EOF

pending_ext=()
git rev-parse -q --verify "refs/tags/spec-kit-linear/v$linear_version" >/dev/null || pending_ext+=("spec-kit-linear:$linear_version")
git rev-parse -q --verify "refs/tags/spec-kit-code-review/v$review_version" >/dev/null || pending_ext+=("spec-kit-code-review:$review_version")
pending_bundles=true
git rev-parse -q --verify "refs/tags/bundles/v$bundle_version" >/dev/null && pending_bundles=false

# A pending extension must carry its written changelog entry — the bump
# only leaves a skeleton.
for entry in ${pending_ext[@]+"${pending_ext[@]}"}; do
  log="packages/${entry%%:*}/CHANGELOG.md"
  grep -q "^## ${entry##*:}$" "$log" || fail "$log has no '## ${entry##*:}' section; write the changelog entry first"
  ! grep -q "^- TODO$" "$log" || fail "$log still has a TODO entry; write the changelog first"
done

echo "release plan:"
for entry in ${pending_ext[@]+"${pending_ext[@]}"}; do echo "  - ${entry%%:*} v${entry##*:}"; done
$pending_bundles && echo "  - bundles v$bundle_version (default preset v$preset_version)"
[ ${#pending_ext[@]} -eq 0 ] && ! $pending_bundles && { echo "  (nothing: every manifest version is already tagged)"; exit 0; }
$dry_run && { echo "dry-run: nothing executed"; exit 0; }

# --- Extensions: tag, build, collect digests -------------------------------
digest_args=()
for entry in ${pending_ext[@]+"${pending_ext[@]}"}; do
  package="${entry%%:*}"; version="${entry##*:}"
  tag="$package/v$version"
  git tag "$tag"
  out=$(./scripts/release/build-release.sh "$tag")
  echo "$out" | grep -E 'sha256|commit:' | sed "s/^/  [$package] /"
  digest_args+=("$package=$(echo "$out" | python3 -c "
import re, sys
t = sys.stdin.read()
print(','.join(re.search(rf'{k}:\s+(\S+)', t).group(1) for k in
      ('commit', 'subtree archive sha256', 'zip sha256', 'manifest sha256')))")")
done

# --- Lock and catalogs from the manifests ----------------------------------
python3 - "$linear_version" "$review_version" "$preset_version" "$bundle_version" ${digest_args[@]+"${digest_args[@]}"} <<'EOF'
import json, re, sys
from pathlib import Path
linear, review, preset, bundles = sys.argv[1:5]
digests = dict(arg.split("=", 1) for arg in sys.argv[5:])

lock = Path("versions.lock.yml").read_text()
for section, package, version in (("linear", "spec-kit-linear", linear),
                                  ("code-review", "spec-kit-code-review", review)):
    if package not in digests:
        continue
    commit, subtree, zipd, manifest = digests[package].split(",")
    block = re.search(rf"(  {section}:\n(?:    .*\n)+)", lock).group(1)
    new = block
    new = re.sub(r"version: \S+", f"version: {version}", new, count=1)
    new = re.sub(rf"tag: {package}/v\S+", f"tag: {package}/v{version}", new)
    new = re.sub(r"commit: \S+", f"commit: {commit}", new)
    new = re.sub(r"subtree_archive_sha256: \S+", f"subtree_archive_sha256: {subtree}", new)
    new = re.sub(r"release_zip_sha256: \S+", f"release_zip_sha256: {zipd}", new)
    new = re.sub(r"manifest_sha256: \S+(?=\n    conformance)", f"manifest_sha256: {manifest}", new)
    lock = lock.replace(block, new)
Path("versions.lock.yml").write_text(lock)

base = "https://github.com/tserdeiro/spec-kit/releases/download"
c = json.loads(Path("catalog/extensions.json").read_text())
for ext, package, version in (("linear", "spec-kit-linear", linear),
                              ("code-review", "spec-kit-code-review", review)):
    c["extensions"][ext]["version"] = version
    c["extensions"][ext]["download_url"] = f"{base}/{package}%2Fv{version}/{package}-v{version}.zip"
Path("catalog/extensions.json").write_text(json.dumps(c, indent=2) + "\n")

c = json.loads(Path("catalog/presets.json").read_text())
c["presets"]["default"]["version"] = preset
c["presets"]["default"]["download_url"] = f"{base}/bundles%2Fv{bundles}/default-{preset}.zip"
Path("catalog/presets.json").write_text(json.dumps(c, indent=2) + "\n")

c = json.loads(Path("catalog/bundles.json").read_text())
for role in ("product", "developer", "reviewer"):
    c["bundles"][role]["version"] = bundles
    c["bundles"][role]["download_url"] = f"{base}/bundles%2Fv{bundles}/{role}-{bundles}.zip"
Path("catalog/bundles.json").write_text(json.dumps(c, indent=2) + "\n")
print("lock and catalogs rewritten")
EOF

# --- Conformance at the consistent point --------------------------------
# Lock and catalogs now match the manifests; prove the whole composition
# still installs before anything is committed, tagged, or published. On
# failure, revert the rewrite and abort with nothing to undo. (Added after
# the 0.2.1 release shipped while conformance was red: the operator's bump
# had omitted the catalogs and nothing here checked.)
if ! bash scripts/conformance/bundles.sh; then
  git checkout -- versions.lock.yml catalog
  for entry in ${pending_ext[@]+"${pending_ext[@]}"}; do
    git tag -d "${entry%%:*}/v${entry##*:}" >/dev/null 2>&1 || true
  done
  fail "bundle conformance failed; the rewrite and the local tags were reverted, nothing was published"
fi

git add versions.lock.yml catalog
# Nothing staged means the tree already recorded the pins (a bump that
# carried the catalog rewrite); the tag then lands on that commit.
git diff --cached --quiet || git commit -q -m "chore(release): record the release pins"

# --- Bundles: tag at the pin commit, build ---------------------------------
if $pending_bundles; then
  git tag "bundles/v$bundle_version"
  rm -rf dist/release/bundles
  ./scripts/release/build-bundles.sh "bundles/v$bundle_version" | tail -5
fi

# --- Push and publish ------------------------------------------------------
git push
for entry in ${pending_ext[@]+"${pending_ext[@]}"}; do
  package="${entry%%:*}"; version="${entry##*:}"
  git push origin "$package/v$version"
  gh release create "$package/v$version" \
    "dist/release/$package/$package-v$version.zip" \
    "dist/release/$package/$package-v$version.SHA256SUMS.txt" \
    --title "$package v$version" --notes "See the package CHANGELOG." >/dev/null
  echo "released: $package v$version"
done
if $pending_bundles; then
  git push origin "bundles/v$bundle_version"
  gh release create "bundles/v$bundle_version" \
    "dist/release/bundles/default-$preset_version.zip" \
    "dist/release/bundles/product-$bundle_version.zip" \
    "dist/release/bundles/developer-$bundle_version.zip" \
    "dist/release/bundles/reviewer-$bundle_version.zip" \
    "dist/release/bundles/bundles-SHA256SUMS.txt" \
    --title "Role bundles v$bundle_version" --notes "Install: see the README." >/dev/null
  echo "released: bundles v$bundle_version"
fi
echo "publish complete"
