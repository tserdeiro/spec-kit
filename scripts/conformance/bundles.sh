#!/usr/bin/env bash
# Conformance: role-bundle distribution.
#
# Scope: this script verifies that a *consumer* repository can install each
# role bundle and get exactly that role's component set -- the preset's four
# templates resolving from `default`, the role's extensions installed, the
# other roles' extensions absent -- and that removing the bundle cleans up
# what it owns and nothing else.
#
# Hermetic with respect to the internet, by construction. The bundles pin
# `linear`, `code-review`, and the `default` preset, none of which ship with
# Spec Kit, so the bundler resolves them through catalogs. Rather than fetch
# the published GitHub release assets, this script builds the artifacts from
# this checkout, serves them from a loopback HTTP server, and registers
# `catalog/extensions.json` and `catalog/presets.json` -- the very files this
# repository publishes -- with their download URLs rewritten to that server at
# the top of the catalog stack. So the real distribution path (catalog lookup
# -> pin check -> archive download -> primitive install) is what runs, and the
# published catalog schemas are what is exercised. `git` is bundled with Spec
# Kit and installs from the local Spec Kit assets.
#
# It is not network-isolated in general: `specify init` is a third-party CLI
# invocation and this script makes no claim about what it does. The guarantee
# is that no bundle component is fetched from a remote host.
set -euo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-bundles-conformance.XXXXXX")
serve_root="$temporary_root/serve"
server_pid=""

cleanup() {
  if [ -n "$server_pid" ]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$temporary_root"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

sorted_words() {
  # shellcheck disable=SC2086 - deliberate word splitting
  printf '%s\n' $1 | sort | tr '\n' ' '
}

# --------------------------------------------------------------------------
# Prerequisites.
# --------------------------------------------------------------------------

pinned_cli=$(sed -n 's/^  package_version: //p' "$repository_root/versions.lock.yml" 2>/dev/null | head -1)
if [ -z "$pinned_cli" ]; then
  echo "conformance requires the source checkout's versions.lock.yml (upstream pin unreadable)" >&2
  exit 4
fi
command -v specify >/dev/null 2>&1 || {
  echo "conformance requires specify-cli $pinned_cli on PATH" >&2
  exit 4
}
if [[ "$(specify version 2>/dev/null)" != *"CLI Version    $pinned_cli"* ]]; then
  echo "conformance requires specify-cli $pinned_cli" >&2
  exit 4
fi
command -v python3 >/dev/null 2>&1 || {
  echo "conformance requires python3" >&2
  exit 4
}
command -v git >/dev/null 2>&1 || {
  echo "conformance requires git" >&2
  exit 4
}

# The role -> extension matrix, derived by hand from the bundle manifests and
# asserted against them below, so a manifest edit that is not reflected here
# fails loudly instead of silently weakening the test.
ROLES="product developer reviewer"
# The bundles move together (publish.sh guards it), so the product manifest
# is the single source for the version this run builds and asserts.
BUNDLE_VERSION=$(sed -n 's/^  version: "\(.*\)"/\1/p' "$repository_root/bundles/product/bundle.yml" | head -1)
[ -n "$BUNDLE_VERSION" ] || { echo "conformance could not read the bundle version from bundles/product/bundle.yml" >&2; exit 4; }

# Artifact names come from the catalogs — the installer downloads exactly
# these basenames, so hardcoding them here is how the 0.3.0 publish failed
# conformance. The preset version for resolve assertions comes from its
# manifest, which is what the installed preset reports.
catalog_zip() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]]['download_url'].rsplit('/',1)[-1])" "$@"
}
LINEAR_ZIP=$(catalog_zip "$repository_root/catalog/extensions.json" extensions linear)
REVIEW_ZIP=$(catalog_zip "$repository_root/catalog/extensions.json" extensions code-review)
PRESET_ZIP=$(catalog_zip "$repository_root/catalog/presets.json" presets default)
PRESET_VERSION=$(sed -n 's/^  version: "\(.*\)"/\1/p' "$repository_root/presets/default/preset.yml" | head -1)
product_extensions="git linear"
developer_extensions="git linear code-review bug"
reviewer_extensions="code-review"
all_extensions="git linear code-review bug"
TEMPLATES="spec-template plan-template tasks-template checklist-template"

# --------------------------------------------------------------------------
# Build the artifacts the catalogs will serve, straight from this checkout.
# --------------------------------------------------------------------------

mkdir -p "$serve_root"

python3 - "$repository_root" "$serve_root" "$LINEAR_ZIP" "$REVIEW_ZIP" "$PRESET_ZIP" <<'PY'
import pathlib
import sys
import zipfile

repository_root, serve_root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
linear_zip, review_zip, preset_zip = sys.argv[3:6]
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}

def archive(source: pathlib.Path, name: str) -> None:
    with zipfile.ZipFile(serve_root / name, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if SKIP & set(path.relative_to(source).parts):
                continue
            if path.is_file():
                bundle.write(path, path.relative_to(source).as_posix())

archive(repository_root / "packages/spec-kit-linear", linear_zip)
archive(repository_root / "packages/spec-kit-code-review", review_zip)
archive(repository_root / "presets/default", preset_zip)
PY

# The bundle artifacts themselves, built the way they will be published, so
# consumers install from an artifact rather than from this checkout.
artifacts_root="$temporary_root/artifacts"
mkdir -p "$artifacts_root"
for role in $ROLES; do
  specify bundle build --path "$repository_root/bundles/$role" \
    --output "$artifacts_root" >/dev/null ||
    fail "$role: bundle build failed"
  [ -f "$artifacts_root/$role-$BUNDLE_VERSION.zip" ] ||
    fail "$role: bundle build did not produce $role-$BUNDLE_VERSION.zip"
  cp "$artifacts_root/$role-$BUNDLE_VERSION.zip" "$serve_root/"
done

# --------------------------------------------------------------------------
# Serve the published catalogs, rewritten to point at those artifacts.
# --------------------------------------------------------------------------

python3 - "$repository_root" "$serve_root" "$temporary_root/port" <<'PY' &
import functools
import http.server
import json
import pathlib
import socketserver
import sys

repository_root, serve_root, port_file = (pathlib.Path(a) for a in sys.argv[1:4])

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # noqa: D102 - silence access logs
        pass


handler = functools.partial(Quiet, directory=str(serve_root))
with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    for name, key in (("extensions", "extensions"), ("presets", "presets"), ("bundles", "bundles")):
        source = repository_root / "catalog" / f"{name}.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["catalog_url"] = f"{base}/{name}.json"
        for entry in payload[key].values():
            entry["download_url"] = f"{base}/" + entry["download_url"].rsplit("/", 1)[-1]
        (serve_root / f"{name}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    port_file.write_text(str(httpd.server_address[1]), encoding="utf-8")
    httpd.serve_forever()
PY
server_pid=$!

for _ in $(seq 1 50); do
  [ -s "$temporary_root/port" ] && break
  sleep 0.1
done
[ -s "$temporary_root/port" ] || fail "the loopback catalog server did not start"
catalog_base="http://127.0.0.1:$(cat "$temporary_root/port")"

# --------------------------------------------------------------------------
# Helpers.
# --------------------------------------------------------------------------

# A consumer repository that never depends on this checkout at runtime: it
# knows the artifacts only through the catalogs.
new_consumer() {
  consumer_root="$temporary_root/$1"
  mkdir -p "$consumer_root"
  git -C "$consumer_root" init --quiet
  (
    cd "$consumer_root"
    specify init --here --force --ignore-agent-tools --integration codex >/dev/null
    specify extension catalog add "$catalog_base/extensions.json" \
      --name conformance --install-allowed --priority 1 >/dev/null
    specify preset catalog add "$catalog_base/presets.json" \
      --name conformance --install-allowed --priority 1 >/dev/null
    specify bundle catalog add "$catalog_base/bundles.json" \
      --id conformance --priority 1 >/dev/null
  )
}

extension_installed() {
  python3 - "$1/.specify/extensions/.registry" "$2" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if not path.exists():
    sys.exit(1)
registry = json.loads(path.read_text(encoding="utf-8")).get("extensions", {})
sys.exit(0 if sys.argv[2] in registry else 1)
PY
}

# The extension ids a bundle manifest declares. Read with awk rather than a
# YAML parser: PyYAML is not in the standard library and this script must not
# require an installed dependency to check its own fixtures.
manifest_extensions() {
  awk '
    /^  extensions:/ { inside = 1; next }
    /^  [a-z]+:/     { inside = 0 }
    inside && $1 == "-" && $2 == "id:" { gsub(/"/, "", $3); print $3 }
  ' "$repository_root/bundles/$1/bundle.yml" | tr '\n' ' '
}

# --------------------------------------------------------------------------
# 1. Each role bundle installs exactly its own component set, and removing it
#    leaves the consumer as it found it.
# --------------------------------------------------------------------------

for role in $ROLES; do
  eval "expected=\$${role}_extensions"

  # The matrix above is the contract this script asserts; keep it honest.
  declared=$(manifest_extensions "$role")
  [ "$(sorted_words "$declared")" = "$(sorted_words "$expected")" ] ||
    fail "$role: bundle.yml declares '$declared' but conformance expects '$expected'"

  new_consumer "$role"

  # An extension the consumer installed on its own, before any bundle: no
  # bundle owns it, so no bundle may ever remove it.
  (cd "$consumer_root" && specify extension add agent-context >/dev/null 2>&1) ||
    fail "$role: could not install the independent 'agent-context' extension"

  # `bundle validate` resolves references against the project enclosing the
  # manifest, so the manifest is staged inside the consumer: validating it
  # from this checkout would resolve against this checkout's catalogs.
  mkdir -p "$consumer_root/.conformance"
  cp -R "$repository_root/bundles/$role" "$consumer_root/.conformance/"
  (cd "$consumer_root" && specify bundle validate --path ".conformance/$role" >/dev/null) ||
    fail "$role: bundle validate failed"

  (cd "$consumer_root" && specify bundle install "$artifacts_root/$role-$BUNDLE_VERSION.zip" >/dev/null) ||
    fail "$role: bundle install failed"

  # 1a. The role's extensions are installed; the other roles' are not.
  for extension in $all_extensions; do
    if [[ " $expected " == *" $extension "* ]]; then
      extension_installed "$consumer_root" "$extension" ||
        fail "$role: extension '$extension' should be installed"
    else
      extension_installed "$consumer_root" "$extension" &&
        fail "$role: extension '$extension' is not part of this role but is installed"
    fi
  done

  # 1b. The preset resolves all four templates from `default`.
  for template in $TEMPLATES; do
    resolved=$(cd "$consumer_root" && specify preset resolve "$template" 2>&1 | tr -d '\n')
    [[ "$resolved" == *"default v$PRESET_VERSION"* ]] ||
      fail "$role: template '$template' does not resolve from the default preset"
    [[ "$resolved" == *".specify/presets/default/templates/$template.md"* ]] ||
      fail "$role: template '$template' resolves outside the installed preset"
  done

  # 1c. The bundle is reported as installed, at its pinned version.
  listed=$(cd "$consumer_root" && specify bundle list 2>&1 | tr -d '\n')
  [[ "$listed" == *"$role v$BUNDLE_VERSION"* ]] ||
    fail "$role: 'bundle list' does not report the installed bundle"

  # 1d. Removal uninstalls what the bundle owns.
  (cd "$consumer_root" && specify bundle remove "$role" >/dev/null) ||
    fail "$role: bundle remove failed"

  for extension in $expected; do
    extension_installed "$consumer_root" "$extension" &&
      fail "$role: extension '$extension' survived bundle remove"
  done
  [[ "$(cd "$consumer_root" && specify preset list 2>&1)" == *"No presets installed"* ]] ||
    fail "$role: the default preset survived bundle remove"
  [[ "$(cd "$consumer_root" && specify bundle list 2>&1)" == *"No bundles installed"* ]] ||
    fail "$role: 'bundle list' still reports the removed bundle"

  # 1e. ...and nothing else. The independently installed extension is
  # untouched, because no bundle ever owned it.
  extension_installed "$consumer_root" "agent-context" ||
    fail "$role: removing the bundle collaterally removed an independent extension"

  echo "ok: $role"
done

# --------------------------------------------------------------------------
# 2. Roles coexist: a component two bundles share survives the removal of one
#    of them. `developer` and `reviewer` both pin `code-review` and `default`.
# --------------------------------------------------------------------------

new_consumer "coexist"
(cd "$consumer_root" && specify bundle install "$artifacts_root/developer-$BUNDLE_VERSION.zip" >/dev/null)
(cd "$consumer_root" && specify bundle install "$artifacts_root/reviewer-$BUNDLE_VERSION.zip" >/dev/null)
(cd "$consumer_root" && specify bundle remove reviewer >/dev/null) ||
  fail "coexist: removing the reviewer bundle failed"

for extension in $developer_extensions; do
  extension_installed "$consumer_root" "$extension" ||
    fail "coexist: developer's '$extension' did not survive removing the reviewer bundle"
done
resolved=$(cd "$consumer_root" && specify preset resolve tasks-template 2>&1 | tr -d '\n')
[[ "$resolved" == *"default v$PRESET_VERSION"* ]] ||
  fail "coexist: the shared default preset did not survive removing the reviewer bundle"
listed=$(cd "$consumer_root" && specify bundle list 2>&1 | tr -d '\n')
[[ "$listed" == *"developer v$BUNDLE_VERSION"* && "$listed" != *"reviewer v$BUNDLE_VERSION"* ]] ||
  fail "coexist: 'bundle list' does not report developer alone"

echo "ok: coexist"

# --------------------------------------------------------------------------
# 3. The documented update path: a catalog-installed bundle survives
#    `bundle update --all`, which re-applies every owned component (the
#    0.13.0 CLI crashed here re-installing an already-installed extension).
# --------------------------------------------------------------------------

new_consumer "update"
(cd "$consumer_root" && specify bundle install developer >/dev/null) ||
  fail "update: catalog install of developer failed"
(cd "$consumer_root" && specify bundle update --all >/dev/null) ||
  fail "update: 'bundle update --all' failed"
listed=$(cd "$consumer_root" && specify bundle list 2>&1 | tr -d '\n')
[[ "$listed" == *"developer v$BUNDLE_VERSION"* ]] ||
  fail "update: 'bundle list' does not report developer after update"
for template in $TEMPLATES; do
  resolved=$(cd "$consumer_root" && specify preset resolve "$template" 2>&1 | tr -d '\n')
  [[ "$resolved" == *"default v$PRESET_VERSION"* ]] ||
    fail "update: template '$template' does not resolve after update"
done

echo "ok: update"

# --------------------------------------------------------------------------
# 4. The installed preset owns delivery-base parsing, and its command blocks
#    consume the helper's single validated result as inert argv data.
# --------------------------------------------------------------------------

new_consumer "trunk"
(cd "$consumer_root" && specify bundle install product >/dev/null) ||
  fail "trunk: product bundle install failed"

helper="$consumer_root/.specify/presets/default/scripts/resolve-delivery-base.py"
[ -f "$helper" ] || fail "trunk: installed delivery-base helper is missing"
trunk_config="$consumer_root/.specify/extensions/git/git-config.yml"
fake_bin="$consumer_root/.conformance/bin"
gh_calls="$consumer_root/.conformance/gh-calls.jsonl"
git_calls="$consumer_root/.conformance/git-calls.jsonl"
mkdir -p "$fake_bin"
real_git=$(command -v git)

cat > "$fake_bin/gh" <<'PY'
#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["GH_CALLS"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(args, ensure_ascii=False, separators=(",", ":")) + "\n")
if args[:2] == ["repo", "view"]:
    if os.environ.get("FAIL_COMMAND") == "gh":
        print("forced gh failure", file=sys.stderr)
        raise SystemExit(9)
    print(os.environ.get("GH_DEFAULT", "main"))
elif args[:2] == ["pr", "create"]:
    if os.environ.get("FAIL_COMMAND") == "gh-create":
        print("forced PR-create failure", file=sys.stderr)
        raise SystemExit(9)
    print("https://example.invalid/pr/1")
else:
    print("unexpected gh argv", file=sys.stderr)
    raise SystemExit(8)
PY
chmod +x "$fake_bin/gh"

cat > "$fake_bin/git" <<'PY'
#!/usr/bin/env python3
import json
import os
import subprocess
import sys

args = sys.argv[1:]
with open(os.environ["GIT_CALLS"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(args, ensure_ascii=False, separators=(",", ":")) + "\n")
if args == ["branch", "--show-current"]:
    print(os.environ.get("GIT_CURRENT_BRANCH", "003-feature"))
elif args and args[0] == "check-ref-format":
    result = subprocess.run([os.environ["REAL_GIT"], *args], check=False)
    raise SystemExit(result.returncode)
elif args and os.environ.get("FAIL_COMMAND") == args[0]:
    print(f"forced {args[0]} failure", file=sys.stderr)
    raise SystemExit(9)
PY
chmod +x "$fake_bin/git"

json_argv() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False, separators=(",", ":")))' "$@"
}

reset_command_logs() {
  : > "$gh_calls"
  : > "$git_calls"
}

set_config() {
  printf '%b' "$1" > "$trunk_config"
}

set_missing_config() {
  rm -f "$trunk_config"
}

run_helper() {
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_DEFAULT="${GH_DEFAULT:-main}" FAIL_COMMAND="${FAIL_COMMAND:-}" \
    REAL_GIT="$real_git" PATH="$fake_bin:$PATH" python3 "$helper")
}

run_helper_without_site_packages() {
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_DEFAULT="${GH_DEFAULT:-main}" FAIL_COMMAND="${FAIL_COMMAND:-}" \
    REAL_GIT="$real_git" PATH="$fake_bin:$PATH" python3 -S "$helper")
}

assert_helper_success() {
  if [ "$1" = __missing_file__ ]; then
    set_missing_config
  else
    set_config "$1"
  fi
  reset_command_logs
  GH_DEFAULT="$4"
  output=$(run_helper)
  unset GH_DEFAULT
  [ "$output" = "$2" ] || fail "trunk helper emitted '$output' instead of '$2'"
  [ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch "$2")" ] ||
    fail "trunk helper did not Git-validate '$2' as one argv element"
  if [ "$3" = configured ]; then
    [ ! -s "$gh_calls" ] || fail "trunk helper queried GitHub for configured '$2'"
  else
    [ "$(cat "$gh_calls")" = "$(json_argv repo view --json defaultBranchRef -q .defaultBranchRef.name)" ] ||
      fail "trunk helper did not query the GitHub default with exact argv"
  fi
}

assert_helper_failure() {
  set_config "$1"
  reset_command_logs
  if failure=$(run_helper 2>&1); then
    fail "trunk helper accepted invalid YAML: $1"
  fi
  [[ "$failure" == error:* ]] || fail "trunk helper did not explain its failure"
  [ ! -s "$gh_calls" ] || fail "trunk helper queried GitHub after invalid configuration"
}

assert_helper_success 'trunk: release\n' release configured main
assert_helper_success 'trunk: "+"\n' + configured main
assert_helper_success 'trunk: "@"\n' @ configured main
assert_helper_success 'trunk: "café"\n' café configured main
assert_helper_success 'trunk: "release;safe"\n' 'release;safe' configured main
assert_helper_success 'trunk: null\n' main fallback main
assert_helper_success 'other: value\n' main fallback main
assert_helper_success 'nested:\n  trunk: release\n' main fallback main
assert_helper_success __missing_file__ main fallback main
assert_helper_success 'trunk: null\n' 'fallback;safe' fallback 'fallback;safe'

set_config 'trunk: release\n'
reset_command_logs
output=$(run_helper_without_site_packages)
[ "$output" = release ] || fail "trunk helper required third-party Python packages"
[ ! -s "$gh_calls" ] || fail "trunk helper queried GitHub during runtime fallback"
[ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch release)" ] ||
  fail "trunk helper without site packages did not preserve Git validation"

assert_helper_failure 'trunk: 123\n'
assert_helper_failure 'trunk: release\ntrunk: other\n'
assert_helper_failure '- trunk: release\n'
assert_helper_failure 'trunk: |-\n  release\n'
assert_helper_failure 'trunk: release\n  /candidate\n'
assert_helper_failure 'trunk:\n  nested: release\n'
assert_helper_failure 'trunk: bad..branch\n'

set_config 'trunk: null\n'
reset_command_logs
FAIL_COMMAND=gh GH_DEFAULT=main
if failure=$(run_helper 2>&1); then
  fail "trunk helper ignored a GitHub lookup failure"
fi
[ ! -s "$git_calls" ] || fail "trunk helper validated after a failed GitHub lookup"
[ "$(cat "$gh_calls")" = "$(json_argv repo view --json defaultBranchRef -q .defaultBranchRef.name)" ] ||
  fail "trunk helper ran a secondary gh command after failure"
unset FAIL_COMMAND GH_DEFAULT

set_config 'trunk: null\n'
reset_command_logs
GH_DEFAULT=bad..branch
if failure=$(run_helper 2>&1); then
  fail "trunk helper accepted an invalid GitHub fallback"
fi
[[ "$failure" == *"GitHub default branch is not a valid Git branch name"* ]] ||
  fail "trunk helper did not explain invalid GitHub fallback"
unset GH_DEFAULT

echo "ok: trunk"
echo "conformance passed"
