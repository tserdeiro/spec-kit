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
mkdir -p "$output_dir"

preset_version=$(git show "${tag}:presets/default/preset.yml" | sed -n 's/^  version: "\(.*\)"/\1/p' | head -1)
preset_zip="$output_dir/default-${preset_version}.zip"
git archive --mtime="@${commit_epoch}" --format=zip \
  "${tag}:presets/default" -o "$preset_zip"

# `specify bundle build` reads the working tree, not the tag.
[ "$(git rev-parse HEAD)" = "$commit" ] ||
  { echo "ERROR: HEAD is not at $tag ($commit); checkout the tag before building" >&2; exit 4; }
for role in product developer reviewer; do
  specify bundle build --path "bundles/$role" --output "$output_dir" >/dev/null
done

checksums_file="$output_dir/bundles-SHA256SUMS.txt"
{
  echo "# ${tag} release checksums"
  echo "# commit: ${commit}"
  (cd "$output_dir" && shasum -a 256 ./*.zip)
} > "$checksums_file"
cat "$checksums_file"
