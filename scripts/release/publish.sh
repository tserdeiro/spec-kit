#!/usr/bin/env bash
# The whole maintainer release in one invocation (Stage 6, T005).
#
# The human bumps versions and changelogs first; this script does everything
# mechanical, in the order the distribution's release flow established:
# refuse a dirty tree -> tag and build each extension whose manifest version
# has no tag yet -> rewrite the lock and catalogs from the manifests ->
# commit the pins -> tag and build the bundles -> push everything -> create
# the GitHub releases. `--dry-run` prints the plan and touches nothing.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
cd "$repo_root"

dry_run=false
[ "${1:-}" = "--dry-run" ] && dry_run=true
[ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] && {
  echo "Usage: publish.sh [--dry-run]" >&2; exit 2; }

fail() { echo "ERROR: $1" >&2; exit 1; }

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
grep -q "BUNDLE_VERSION=\"$bundle_version\"" scripts/conformance/bundles.sh || \
  fail "scripts/conformance/bundles.sh pins another BUNDLE_VERSION; align it first"

pending_ext=()
git rev-parse -q --verify "refs/tags/spec-kit-linear/v$linear_version" >/dev/null || pending_ext+=("spec-kit-linear:$linear_version")
git rev-parse -q --verify "refs/tags/spec-kit-code-review/v$review_version" >/dev/null || pending_ext+=("spec-kit-code-review:$review_version")
pending_bundles=true
git rev-parse -q --verify "refs/tags/bundles/v$bundle_version" >/dev/null && pending_bundles=false

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

git add versions.lock.yml catalog
git commit -q -m "chore(release): record the release pins"

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
