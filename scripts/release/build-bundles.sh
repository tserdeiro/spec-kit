#!/usr/bin/env bash
# Build the bundle-release artifacts for a bundles/vX.Y.Z tag: one zip per
# role bundle (via `specify bundle build`, reproducible by construction) and
# the default preset pack (git archive, --mtime pinned like build-release.sh).
set -euo pipefail

if [ "${1:-}" = "" ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: build-bundles.sh <tag> [output_dir]   e.g. bundles/v1.0.0" >&2
  exit 2
fi

tag="$1"
script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
output_dir="${2:-$repo_root/dist/release/bundles}"
cd "$repo_root"

commit=$(git rev-parse --verify "${tag}^{commit}") || {
  echo "ERROR: tag '$tag' does not resolve to a commit" >&2
  exit 4
}
commit_epoch=$(git log -1 --format=%ct "${tag}^{commit}")
git cat-file -e "${tag}:presets/default" || {
  echo "ERROR: presets/default does not exist at '$tag'" >&2
  exit 4
}
for role in product developer reviewer; do
  git cat-file -e "${tag}:bundles/$role" || {
    echo "ERROR: bundles/$role does not exist at '$tag'" >&2
    exit 4
  }
done
mkdir -p "$output_dir"

tag_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-bundles-tag.XXXXXX")
trap 'rm -rf "$tag_root"' EXIT
git archive --format=tar "$tag" bundles presets | tar -xf - -C "$tag_root"

preset_version=$(sed -n 's/^  version: "\(.*\)"/\1/p' "$tag_root/presets/default/preset.yml" | head -1)
[ -n "$preset_version" ] || { echo "ERROR: tag '$tag' has no preset version" >&2; exit 4; }
preset_zip_name="default-${preset_version}.zip"
preset_zip="$output_dir/$preset_zip_name"
[ ! -e "$preset_zip" ] || { echo "ERROR: output already contains $preset_zip_name" >&2; exit 5; }
git archive --mtime="@${commit_epoch}" --format=zip \
  "${tag}:presets/default" -o "$preset_zip"

bundle_version=$(sed -n 's/^  version: "\(.*\)"/\1/p' "$tag_root/bundles/product/bundle.yml" | head -1)
[ -n "$bundle_version" ] || { echo "ERROR: tag '$tag' has no bundle version" >&2; exit 4; }
zip_names=("$preset_zip_name")
for role in product developer reviewer; do
  zip_name="${role}-${bundle_version}.zip"
  [ ! -e "$output_dir/$zip_name" ] || { echo "ERROR: output already contains $zip_name" >&2; exit 5; }
  specify bundle build --path "$tag_root/bundles/$role" --output "$output_dir" >/dev/null
  [ -f "$output_dir/$zip_name" ] || {
    echo "ERROR: bundle build did not produce $zip_name" >&2
    exit 4
  }
  zip_names+=("$zip_name")
done

checksums_file="$output_dir/bundles-SHA256SUMS.txt"
[ ! -e "$checksums_file" ] || { echo "ERROR: output already contains bundles-SHA256SUMS.txt" >&2; exit 5; }
{
  echo "# ${tag} release checksums"
  echo "# commit: ${commit}"
  (cd "$output_dir" && shasum -a 256 "${zip_names[@]}")
} > "$checksums_file"
cat "$checksums_file"
