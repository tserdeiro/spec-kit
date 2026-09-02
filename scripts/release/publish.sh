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
  command -v uv >/dev/null 2>&1 || fail "bump requires uv to update uv.lock"
  bump_paths=(
    packages/spec-kit-linear/extension.yml packages/spec-kit-linear/pyproject.toml
    packages/spec-kit-linear/src/spec_kit_linear/__init__.py packages/spec-kit-linear/CHANGELOG.md
    packages/spec-kit-code-review/extension.yml packages/spec-kit-code-review/pyproject.toml
    packages/spec-kit-code-review/src/spec_kit_code_review/__init__.py packages/spec-kit-code-review/CHANGELOG.md
    presets/default/preset.yml
    bundles/product/bundle.yml bundles/developer/bundle.yml bundles/reviewer/bundle.yml
    uv.lock
  )
  rollback_bump() {
    status=$?
    trap - EXIT
    if [ "$status" -eq 0 ]; then
      exit 0
    fi
    rollback_status=0
    git restore --source=HEAD --staged --worktree -- "${bump_paths[@]}" || rollback_status=1
    if [ "$rollback_status" -ne 0 ]; then
      echo "ERROR: bump failed (exit $status); rollback incomplete" >&2
    else
      echo "ERROR: bump failed (exit $status); bump rolled back" >&2
    fi
    exit "$status"
  }
  trap rollback_bump EXIT
  python3 - "$@" <<'EOF'
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
  if uv lock; then
    :
  else
    uv_status=$?
    echo "ERROR: uv lock failed (exit $uv_status)" >&2
    exit "$uv_status"
  fi
  trap - EXIT
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

initial_commit=$(git rev-parse HEAD)
remote_tag_commit() {
  remote_refs=""
  remote_refs=$(git ls-remote origin "$1") || return 2
  printf '%s\n' "$remote_refs" | awk 'NR == 1 {print $1}'
}

lock_commit_for_version() {
  python3 - "$1" "$2" <<'PY'
import re, sys
package, version = sys.argv[1:]
section = "linear" if package == "spec-kit-linear" else "code-review"
text = open("versions.lock.yml").read()
match = re.search(rf"^  {section}:\n((?:    .*\n)+)", text, re.M)
if match:
    block = match.group(1)
    found_version = re.search(r"^    version: (\S+)$", block, re.M)
    found_commit = re.search(r"^    commit: (\S+)$", block, re.M)
    if found_version and found_commit and found_version.group(1) == version:
        print(found_commit.group(1))
PY
}

# Keep dry-run completely side-effect free. Remote release state is checked
# only by the real preparation path below.
pending_ext=()
for entry in spec-kit-linear:$linear_version spec-kit-code-review:$review_version; do
  tag="${entry%%:*}/v${entry##*:}"
  git rev-parse -q --verify "refs/tags/$tag" >/dev/null || pending_ext+=("$entry")
done
pending_bundles=true
git rev-parse -q --verify "refs/tags/bundles/v$bundle_version" >/dev/null && pending_bundles=false
for entry in "${pending_ext[@]}"; do
  log="packages/${entry%%:*}/CHANGELOG.md"
  grep -q "^## ${entry##*:}$" "$log" || fail "$log has no '## ${entry##*:}' section; write the changelog entry first"
  ! grep -q "^- TODO$" "$log" || fail "$log still has a TODO entry; write the changelog first"
done

release_state_readonly() {
  release_tag="$1"; shift
  check_json=$(mktemp "${TMPDIR:-/tmp}/spec-kit-release.XXXXXX")
  check_error=$(mktemp "${TMPDIR:-/tmp}/spec-kit-release.XXXXXX")
  encoded_tag=${release_tag//\//%2F}
  if gh api "repos/{owner}/{repo}/releases/tags/$encoded_tag" >"$check_json" 2>"$check_error"; then
    python3 - "$check_json" "$@" <<'PY'
import json, sys
assets = {asset["name"] for asset in json.load(open(sys.argv[1])).get("assets", [])}
missing = sorted(set(sys.argv[2:]) - assets)
if missing:
    print(f"missing assets: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(3)
PY
    state=$?
  elif grep -Eiq '404|not found' "$check_error"; then
    state=1
  else
    sed -n '1,2p' "$check_error" >&2
    state=2
  fi
  rm -f "$check_json" "$check_error"
  return "$state"
}

echo "release plan:"
for entry in "${pending_ext[@]}"; do echo "  - ${entry%%:*} v${entry##*:}"; done
$pending_bundles && echo "  - bundles v$bundle_version (default preset v$preset_version)"
if $dry_run; then
  echo "remote plan (read-only):"
  dry_run_status=0
  for entry in spec-kit-linear:$linear_version spec-kit-code-review:$review_version; do
    package="${entry%%:*}"; version="${entry##*:}"; tag="$package/v$version"
    local_tag_exists=false
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
      local_tag_exists=true
      local_tag_commit=$(git rev-parse "$tag^{commit}")
      expected_tag_commit=$(lock_commit_for_version "$package" "$version")
      [ -n "$expected_tag_commit" ] || expected_tag_commit="$initial_commit"
      if [ "$local_tag_commit" != "$expected_tag_commit" ]; then
        echo "ERROR: local tag $tag does not point to the expected release commit" >&2
        dry_run_status=1
        continue
      fi
    fi
    remote_tag=$(remote_tag_commit "refs/tags/$tag^{}") || {
      echo "ERROR: could not resolve remote tag $tag" >&2
      dry_run_status=1
      continue
    }
    [ -n "$remote_tag" ] || remote_tag=$(remote_tag_commit "refs/tags/$tag") || {
      echo "ERROR: could not resolve remote tag $tag" >&2
      dry_run_status=1
      continue
    }
    if [ -n "$remote_tag" ]; then
      if $local_tag_exists; then
        if [ "$remote_tag" != "$local_tag_commit" ]; then
          echo "ERROR: remote tag $tag points to a different commit" >&2
          dry_run_status=1
          continue
        fi
        echo "  - $tag: tag aligned; no tag push"
      else
        echo "ERROR: remote tag $tag exists without a local tag; fetch it before rerunning" >&2
        dry_run_status=1
      fi
    elif $local_tag_exists; then
      echo "  - $tag: tag push required"
    else
      echo "  - $tag: local tag creation and tag push required"
    fi
  done
  bundle_tag="bundles/v$bundle_version"
  local_bundle_tag=false
  if git rev-parse -q --verify "refs/tags/$bundle_tag" >/dev/null; then
    local_bundle_tag=true
    local_bundle_commit=$(git rev-parse "$bundle_tag^{commit}")
    if [ "$local_bundle_commit" != "$initial_commit" ]; then
      echo "ERROR: local tag $bundle_tag does not point to the current pin commit" >&2
      dry_run_status=1
    fi
  fi
  remote_tag=$(remote_tag_commit "refs/tags/$bundle_tag^{}") || {
    echo "ERROR: could not resolve remote tag $bundle_tag" >&2
    dry_run_status=1
    remote_tag=""
  }
  [ -n "$remote_tag" ] || {
    remote_tag=$(remote_tag_commit "refs/tags/$bundle_tag") || {
      echo "ERROR: could not resolve remote tag $bundle_tag" >&2
      dry_run_status=1
      remote_tag=""
    }
  }
  if [ -n "$remote_tag" ]; then
    if $local_bundle_tag; then
      if [ "$remote_tag" != "$local_bundle_commit" ]; then
        echo "ERROR: remote tag $bundle_tag points to a different commit" >&2
        dry_run_status=1
      else
        echo "  - $bundle_tag: tag aligned; no tag push"
      fi
    else
      echo "ERROR: remote tag $bundle_tag exists without a local tag; fetch it before rerunning" >&2
      dry_run_status=1
    fi
  elif $local_bundle_tag; then
    echo "  - $bundle_tag: tag push required"
  else
    echo "  - $bundle_tag: local tag creation and tag push required"
  fi
  for entry in spec-kit-linear:$linear_version spec-kit-code-review:$review_version; do
    package="${entry%%:*}"; version="${entry##*:}"; tag="$package/v$version"
    if release_state_readonly "$tag" "$package-v$version.zip" "$package-v$version.SHA256SUMS.txt"; then
      echo "  - $tag: release complete"
    else
      state=$?
      if [ "$state" -eq 1 ]; then
        echo "  - $tag: release/assets to create"
      elif [ "$state" -eq 3 ]; then
        echo "ERROR: $tag exists but is missing required assets" >&2
        dry_run_status=1
      else
        echo "ERROR: unable to inspect release $tag" >&2
        dry_run_status=1
      fi
    fi
  done
  if release_state_readonly "bundles/v$bundle_version" \
    "default-$preset_version.zip" "product-$bundle_version.zip" \
    "developer-$bundle_version.zip" "reviewer-$bundle_version.zip" \
    "bundles-SHA256SUMS.txt"; then
    echo "  - bundles/v$bundle_version: release complete"
  else
    state=$?
    if [ "$state" -eq 1 ]; then
      echo "  - bundles/v$bundle_version: release/assets to create"
    elif [ "$state" -eq 3 ]; then
      echo "ERROR: bundles/v$bundle_version exists but is missing required assets" >&2
      dry_run_status=1
    else
      echo "ERROR: unable to inspect release bundles/v$bundle_version" >&2
      dry_run_status=1
    fi
  fi
  echo "dry-run: nothing executed"
  exit "$dry_run_status"
fi

temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-publish.XXXXXX")
remote_started=false
created_tags=()

rollback_before_remote() {
  status=$?
  trap - EXIT
  if [ "$status" -eq 0 ]; then
    rm -rf "$temporary_root"
    exit 0
  fi
  if $remote_started; then
    rm -rf "$temporary_root"
    echo "ERROR: publication started remotely; local rollback was not attempted" >&2
    exit "$status"
  fi

  rollback_status=0
  if [ "$(git rev-parse HEAD)" != "$initial_commit" ]; then
    git reset --hard "$initial_commit" >/dev/null 2>&1 || rollback_status=$((rollback_status + 1))
  fi
  git restore --source="$initial_commit" --staged --worktree \
    versions.lock.yml catalog presets/default/README.md \
    || rollback_status=$((rollback_status + 1))
  for tag in ${created_tags[@]+"${created_tags[@]}"}; do
    git tag -d "$tag" >/dev/null 2>&1 || rollback_status=$((rollback_status + 1))
  done
  rm -rf "$temporary_root" || rollback_status=$((rollback_status + 1))
  if [ "$rollback_status" -ne 0 ]; then
    echo "ERROR: pre-remote release step failed; rollback incomplete ($rollback_status failures)" >&2
  else
    echo "ERROR: pre-remote release step failed; local tags, commits, and artifacts were reverted" >&2
  fi
  exit "$status"
}
trap rollback_before_remote EXIT

extension_targets=("spec-kit-linear:$linear_version" "spec-kit-code-review:$review_version")
tag_needs_push=()
for entry in "${extension_targets[@]}"; do
  package="${entry%%:*}"; version="${entry##*:}"; tag="$package/v$version"
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    local_commit=$(git rev-parse "$tag^{commit}")
    expected_commit=$(lock_commit_for_version "$package" "$version")
    [ -n "$expected_commit" ] || expected_commit="$initial_commit"
    [ "$local_commit" = "$expected_commit" ] || fail "local tag $tag does not point to the expected release commit"
    remote_tag=$(remote_tag_commit "refs/tags/$tag^{}") || fail "could not resolve remote tag $tag"
    [ -n "$remote_tag" ] || remote_tag=$(remote_tag_commit "refs/tags/$tag") || fail "could not resolve remote tag $tag"
    if [ -n "$remote_tag" ]; then
      [ "$remote_tag" = "$local_commit" ] || fail "remote tag $tag points to a different commit"
    else
      tag_needs_push+=("$tag")
    fi
  else
    remote_tag=$(remote_tag_commit "refs/tags/$tag^{}") || fail "could not resolve remote tag $tag"
    [ -n "$remote_tag" ] || remote_tag=$(remote_tag_commit "refs/tags/$tag") || fail "could not resolve remote tag $tag"
    [ -z "$remote_tag" ] || fail "remote tag $tag exists without a local tag; fetch it before rerunning"
    git tag "$tag"
    created_tags+=("$tag")
    tag_needs_push+=("$tag")
  fi
done

release_has_assets() {
  release_tag="$1"; shift
  release_json="$temporary_root/${release_tag//\//-}.json"
  release_error="$temporary_root/${release_tag//\//-}.err"
  encoded_tag=${release_tag//\//%2F}
  if gh api "repos/{owner}/{repo}/releases/tags/$encoded_tag" >"$release_json" 2>"$release_error"; then
    python3 - "$release_json" "$@" <<'PY'
import json, sys
payload = json.loads(open(sys.argv[1]).read())
assets = {asset["name"] for asset in payload.get("assets", [])}
required = set(sys.argv[2:])
missing = sorted(required - assets)
if missing:
    print(f"release is missing required assets: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(3)
PY
    return $?
  fi
  if grep -Eiq '404|not found' "$release_error"; then
    return 1
  fi
  echo "ERROR: could not determine whether release $release_tag exists:" >&2
  sed -n '1,3p' "$release_error" >&2
  return 2
}

release_needs_create=()
digest_args=()
for entry in "${extension_targets[@]}"; do
  package="${entry%%:*}"; version="${entry##*:}"; tag="$package/v$version"
  zip_name="$package-v$version.zip"
  sums_name="$package-v$version.SHA256SUMS.txt"
  if release_has_assets "$tag" "$zip_name" "$sums_name"; then
    continue
  else
    state=$?
    [ "$state" -eq 1 ] || fail "release $tag exists but is incomplete or could not be checked"
  fi
  release_needs_create+=("$entry")
  output_dir="$temporary_root/$package"
  out=$(./scripts/release/build-release.sh "$tag" "$output_dir")
  echo "$out" | grep -E 'sha256|commit:' | sed "s/^/  [$package] /"
  digest_args+=("$package=$(echo "$out" | python3 -c "
import re, sys
t = sys.stdin.read()
print(','.join(re.search(rf'{k}:\\s+(\\S+)', t).group(1) for k in
      ('commit', 'subtree archive sha256', 'zip sha256', 'manifest sha256')))")")
done

# --- Extensions: tag, build, collect digests -------------------------------

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

# The preset README's direct-install URL rots on every release unless it is
# rewritten from the same pins the catalogs use (it pointed at a deleted
# 1.0.0 once, and at 0.7.0 after the 0.7.1 release).
p = Path("presets/default/README.md")
p.write_text(re.sub(r"releases/download/bundles%2Fv[^/]+/default-[^\s]+\.zip",
                    f"releases/download/bundles%2Fv{bundles}/default-{preset}.zip",
                    p.read_text()))

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
  fail "bundle conformance failed before remote publication"
fi

git add versions.lock.yml catalog presets/default/README.md
# Nothing staged means the tree already recorded the pins (a bump that
# carried the catalog rewrite); the tag then lands on that commit.
git diff --cached --quiet || git commit -q -m "chore(release): record the release pins"

# --- Bundles: tag at the pin commit, build ---------------------------------
bundle_tag="bundles/v$bundle_version"
bundle_tag_needs_push=false
if git rev-parse -q --verify "refs/tags/$bundle_tag" >/dev/null; then
  bundle_commit=$(git rev-parse "$bundle_tag^{commit}")
  current_commit=$(git rev-parse HEAD)
  [ "$bundle_commit" = "$current_commit" ] || fail "local tag $bundle_tag does not point to the pin commit"
  remote_bundle_tag=$(remote_tag_commit "refs/tags/$bundle_tag^{}") || fail "could not resolve remote tag $bundle_tag"
  [ -n "$remote_bundle_tag" ] || remote_bundle_tag=$(remote_tag_commit "refs/tags/$bundle_tag") || fail "could not resolve remote tag $bundle_tag"
  if [ -n "$remote_bundle_tag" ]; then
    [ "$remote_bundle_tag" = "$bundle_commit" ] || fail "remote tag $bundle_tag points to a different commit"
  else
    tag_needs_push+=("$bundle_tag")
  fi
else
  remote_bundle_tag=$(remote_tag_commit "refs/tags/$bundle_tag^{}") || fail "could not resolve remote tag $bundle_tag"
  [ -n "$remote_bundle_tag" ] || remote_bundle_tag=$(remote_tag_commit "refs/tags/$bundle_tag") || fail "could not resolve remote tag $bundle_tag"
  [ -z "$remote_bundle_tag" ] || fail "remote tag $bundle_tag exists without a local tag; fetch it before rerunning"
  git tag "$bundle_tag"
  created_tags+=("$bundle_tag")
  tag_needs_push+=("$bundle_tag")
  bundle_tag_needs_push=true
fi

bundle_release_needs_create=false
if release_has_assets "$bundle_tag" \
  "default-$preset_version.zip" "product-$bundle_version.zip" \
  "developer-$bundle_version.zip" "reviewer-$bundle_version.zip" \
  "bundles-SHA256SUMS.txt"; then
  :
else
  state=$?
  [ "$state" -eq 1 ] || fail "release $bundle_tag exists but is incomplete or could not be checked"
  bundle_release_needs_create=true
  ./scripts/release/build-bundles.sh "$bundle_tag" "$temporary_root/bundles" | tail -5
fi

# --- Push and publish ------------------------------------------------------
# From this point forward remote state may change. The EXIT trap therefore
# reports failures without pretending local rollback can undo a push or a
# GitHub release.
remote_started=true
git push
for tag in "${tag_needs_push[@]}"; do
  git push origin "$tag"
done
for entry in "${release_needs_create[@]}"; do
  package="${entry%%:*}"; version="${entry##*:}"
  gh release create "$package/v$version" \
    "$temporary_root/$package/$package-v$version.zip" \
    "$temporary_root/$package/$package-v$version.SHA256SUMS.txt" \
    --title "$package v$version" --notes "See the package CHANGELOG." >/dev/null
  echo "released: $package v$version"
done
if $bundle_release_needs_create; then
  gh release create "$bundle_tag" \
    "$temporary_root/bundles/default-$preset_version.zip" \
    "$temporary_root/bundles/product-$bundle_version.zip" \
    "$temporary_root/bundles/developer-$bundle_version.zip" \
    "$temporary_root/bundles/reviewer-$bundle_version.zip" \
    "$temporary_root/bundles/bundles-SHA256SUMS.txt" \
    --title "Role bundles v$bundle_version" --notes "Install: see the README." >/dev/null
  echo "released: bundles v$bundle_version"
fi
echo "publish complete"
