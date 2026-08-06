#!/usr/bin/env bash
# Build the reproducible release artifact for a first-party extension from
# its per-package tag (e.g. spec-kit-linear/v0.3.0). Produces the release
# ZIP plus the digests versions.lock.yml records.
#
# `<tag>:<path>` resolves to a bare tree, so git archive would stamp
# wall-clock mtimes; pinning --mtime to the tagged commit's committer time
# keeps both archives byte-reproducible.
set -euo pipefail

if [ "${1:-}" = "" ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: build-release.sh <package-tag> [output_dir]" >&2
  echo "  <package-tag>  e.g. spec-kit-linear/v0.3.0" >&2
  exit 2
fi

tag="$1"
package="${tag%%/*}"
version="${tag#"${package}"/v}"
if [ "$version" = "$tag" ] || [ "$package" = "$tag" ]; then
  echo "ERROR: expected a tag of the form <package>/vX.Y.Z, got '$tag'" >&2
  exit 2
fi
package_path="packages/${package}"

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
output_dir="${2:-$repo_root/dist/release/$package}"
cd "$repo_root"

commit=$(git rev-parse --verify "${tag}^{commit}") || {
  echo "ERROR: tag '$tag' does not resolve to a commit" >&2
  exit 4
}
git cat-file -e "${tag}:${package_path}" || {
  echo "ERROR: '${package_path}' does not exist at '${tag}'" >&2
  exit 4
}

mkdir -p "$output_dir"
commit_epoch=$(git log -1 --format=%ct "${tag}^{commit}")
zip_name="${package}-v${version}.zip"
final_zip="$output_dir/$zip_name"

subtree_archive_sha256=$(git archive --mtime="@${commit_epoch}" --format=tar \
  "${tag}:${package_path}" | shasum -a 256 | awk '{print $1}')
git archive --mtime="@${commit_epoch}" --format=zip \
  "${tag}:${package_path}" -o "$final_zip"
zip_sha256=$(shasum -a 256 "$final_zip" | awk '{print $1}')
manifest_sha256=$(git show "${tag}:${package_path}/extension.yml" \
  | shasum -a 256 | awk '{print $1}')

checksums_file="$output_dir/${package}-v${version}.SHA256SUMS.txt"
{
  echo "# ${package} v${version} release checksums"
  echo "# tag: ${tag}"
  echo "# commit: ${commit}"
  echo "${subtree_archive_sha256}  subtree-archive.tar"
  echo "${zip_sha256}  ${zip_name}"
  echo "${manifest_sha256}  extension.yml"
} > "$checksums_file"

echo "tag:                    $tag"
echo "commit:                 $commit"
echo "subtree archive sha256: $subtree_archive_sha256"
echo "zip sha256:             $zip_sha256"
echo "manifest sha256:        $manifest_sha256"
echo "zip:                    $final_zip"
echo "checksums:              $checksums_file"
