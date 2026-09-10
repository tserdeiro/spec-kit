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

# Default: derive every artifact name and version from this checkout's
# manifests, so a bumped tree conforms before it is ever published.
# --published: derive them from the public catalogs instead (the
# installer's view) and additionally assert the two agree.
mode="local"
case "${1:-}" in
  "") ;;
  --published) mode="published" ;;
  *) echo "Usage: bundles.sh [--published]" >&2; exit 2 ;;
esac

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

# The installed scripts require Python 3.11+ (C-005), and a developer
# machine's python3 may be older, so resolve the interpreter the same way
# upstream's own `py` scripts do -- this repository's .venv when present,
# else python3 on PATH -- once, for every scenario invoking an installed script.
PYTHON="$repository_root/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=$(command -v python3)
python_recent=$("$PYTHON" -c 'import sys; print(int(sys.version_info >= (3, 11)))')
[ "$python_recent" = "1" ] || {
  echo "conformance requires Python 3.11+ to run the installed scripts (found $("$PYTHON" -V 2>&1) at $PYTHON)" >&2
  exit 4
}

# The role -> extension matrix, derived by hand from the bundle manifests and
# asserted against them below, so a manifest edit that is not reflected here
# fails loudly instead of silently weakening the test.
ROLES="product developer reviewer"

# Local mode (default) derives every artifact name and version from this
# checkout's manifests. --published derives them from the catalogs instead,
# the way the installer does, and asserts the two agree — a mismatch is
# exactly what would ship a broken pin.
manifest_version() { sed -n 's/^  version: "\(.*\)"/\1/p' "$1" | head -1; }
# The bundles move together (publish.sh guards it), so the product manifest
# is the single source for the version this run builds and asserts.
BUNDLE_VERSION=$(manifest_version "$repository_root/bundles/product/bundle.yml")
[ -n "$BUNDLE_VERSION" ] || { echo "conformance could not read the bundle version from bundles/product/bundle.yml" >&2; exit 4; }
LINEAR_VERSION=$(manifest_version "$repository_root/packages/spec-kit-linear/extension.yml")
REVIEW_VERSION=$(manifest_version "$repository_root/packages/spec-kit-code-review/extension.yml")
PRESET_VERSION=$(manifest_version "$repository_root/presets/default/preset.yml")

catalog_zip() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]]['download_url'].rsplit('/',1)[-1])" "$@"
}
catalog_version() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]]['version'])" "$@"
}
catalog_download_url() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]]['download_url'])" "$@"
}

if [ "$mode" = "published" ]; then
  LINEAR_ZIP=$(catalog_zip "$repository_root/catalog/extensions.json" extensions linear)
  REVIEW_ZIP=$(catalog_zip "$repository_root/catalog/extensions.json" extensions code-review)
  PRESET_ZIP=$(catalog_zip "$repository_root/catalog/presets.json" presets default)

  mismatched=false
  check_published() {
    [ "$2" = "$3" ] || { echo "published catalog $1 $2 does not match manifest $3" >&2; mismatched=true; }
  }
  check_published linear "$(catalog_version "$repository_root/catalog/extensions.json" extensions linear)" "$LINEAR_VERSION"
  check_published code-review "$(catalog_version "$repository_root/catalog/extensions.json" extensions code-review)" "$REVIEW_VERSION"
  check_published preset "$(catalog_version "$repository_root/catalog/presets.json" presets default)" "$PRESET_VERSION"
  check_published bundles "$(catalog_version "$repository_root/catalog/bundles.json" bundles product)" "$BUNDLE_VERSION"
  ! $mismatched || exit 1

  # Published digests (plan D13, FR-014): the parity check above only
  # compares version strings; re-verify the actual published bytes for each
  # first-party extension against versions.lock.yml -- the release zip
  # `build-release.sh` uploaded, the tag's subtree archive, and its
  # manifest, recomputed exactly as `build-release.sh:45-51` does at
  # publication.
  command -v curl >/dev/null 2>&1 || {
    echo "conformance --published requires curl" >&2
    exit 4
  }

  # A lock scalar for one extension id, e.g. `lock_field linear tag`. The
  # file is flat and two-space indented: an id line starts its block, the
  # next id line (or EOF) ends it, so scan only inside that span.
  lock_field() {
    awk -v id="  $1:" -v key="    $2: " '
      $0 == id { inside = 1; next }
      inside && /^  [a-zA-Z]/ { inside = 0 }
      inside && index($0, key) == 1 { print substr($0, length(key) + 1); exit }
    ' "$repository_root/versions.lock.yml"
  }

  verify_published_digests() {
    local id="$1" tag pkg_path expected_zip expected_subtree expected_manifest
    local download_url zip_path http_code zip_note="" actual_zip commit_epoch actual_subtree actual_manifest
    tag=$(lock_field "$id" tag)
    pkg_path=$(lock_field "$id" path)
    expected_zip=$(lock_field "$id" release_zip_sha256)
    expected_subtree=$(lock_field "$id" subtree_archive_sha256)
    expected_manifest=$(lock_field "$id" manifest_sha256)
    [ -n "$tag" ] && [ -n "$pkg_path" ] && [ -n "$expected_zip" ] &&
      [ -n "$expected_subtree" ] && [ -n "$expected_manifest" ] ||
      fail "$id: versions.lock.yml is missing a published-digest field"

    git -C "$repository_root" rev-parse -q --verify "refs/tags/${tag}^{commit}" >/dev/null ||
      fail "$id: tag '$tag' not found locally -- run: git fetch --tags origin"

    # publish.sh runs this gate before pushing the tag or creating the
    # release (scripts/release/publish.sh:275, ahead of 296-316), so the
    # zip legitimately does not exist yet at that point: a 404 is expected
    # there, not a failure. Any other non-200 (including a transport
    # failure, which leaves http_code "000") is.
    download_url=$(catalog_download_url "$repository_root/catalog/extensions.json" extensions "$id")
    zip_path="$temporary_root/published-$id.zip"
    http_code=$(curl -sSL -o "$zip_path" -w '%{http_code}' "$download_url") || true
    case "$http_code" in
      200)
        actual_zip=$(shasum -a 256 "$zip_path" | awk '{print $1}')
        [ "$actual_zip" = "$expected_zip" ] ||
          fail "$id: release zip $download_url sha256 mismatch (expected $expected_zip, got $actual_zip)"
        ;;
      404)
        echo "pending: $id release zip not published yet ($download_url); its digest is verified by the next --published run"
        zip_note=" (release zip pending)"
        ;;
      *)
        fail "$id: release zip $download_url returned HTTP $http_code"
        ;;
    esac

    commit_epoch=$(git -C "$repository_root" log -1 --format=%ct "${tag}^{commit}")
    actual_subtree=$(git -C "$repository_root" archive --mtime="@${commit_epoch}" --format=tar \
      "${tag}:${pkg_path}" | shasum -a 256 | awk '{print $1}') ||
      fail "$id: could not archive $tag:$pkg_path"
    [ "$actual_subtree" = "$expected_subtree" ] ||
      fail "$id: subtree archive of $tag:$pkg_path sha256 mismatch (expected $expected_subtree, got $actual_subtree)"

    actual_manifest=$(git -C "$repository_root" show "${tag}:${pkg_path}/extension.yml" | shasum -a 256 | awk '{print $1}') ||
      fail "$id: could not read $tag:$pkg_path/extension.yml"
    [ "$actual_manifest" = "$expected_manifest" ] ||
      fail "$id: manifest $tag:$pkg_path/extension.yml sha256 mismatch (expected $expected_manifest, got $actual_manifest)"

    echo "ok: $id published digests$zip_note"
  }

  verify_published_digests linear
  verify_published_digests "code-review"
else
  LINEAR_ZIP="spec-kit-linear-v${LINEAR_VERSION}.zip"
  REVIEW_ZIP="spec-kit-code-review-v${REVIEW_VERSION}.zip"
  PRESET_ZIP="default-${PRESET_VERSION}.zip"
fi

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
# Serve the catalogs, rewritten to point at those artifacts. Local mode also
# rewrites each entry's version and basename to this run's manifest values —
# what was actually just built above — instead of whatever the checked-in
# catalog files (the last published state) still say.
# --------------------------------------------------------------------------

local_overrides="{}"
if [ "$mode" = "local" ]; then
  local_overrides=$(python3 -c '
import json, sys
linear_v, linear_zip, review_v, review_zip, preset_v, preset_zip, bundle_v = sys.argv[1:8]
print(json.dumps({
    "extensions": {"linear": [linear_v, linear_zip], "code-review": [review_v, review_zip]},
    "presets": {"default": [preset_v, preset_zip]},
    "bundles": {r: [bundle_v, f"{r}-{bundle_v}.zip"] for r in ("product", "developer", "reviewer")},
}))
' "$LINEAR_VERSION" "$LINEAR_ZIP" "$REVIEW_VERSION" "$REVIEW_ZIP" "$PRESET_VERSION" "$PRESET_ZIP" "$BUNDLE_VERSION")
fi

python3 - "$repository_root" "$serve_root" "$temporary_root/port" "$local_overrides" <<'PY' &
import functools
import http.server
import json
import pathlib
import socketserver
import sys

repository_root, serve_root, port_file = (pathlib.Path(a) for a in sys.argv[1:4])
overrides = json.loads(sys.argv[4])

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
        for entry_id, entry in payload[key].items():
            if entry_id in overrides.get(key, {}):
                version, zip_name = overrides[key][entry_id]
                entry["version"] = version
                entry["download_url"] = f"{base}/{zip_name}"
            else:
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
# 4. The product bundle installs the preset's eight scripts and the
#    commands invoke them directly (plan D1, D2); the delivery base and
#    every resolved branch reach git and gh only as inert argv.
# --------------------------------------------------------------------------

new_consumer "trunk"
(cd "$consumer_root" && specify bundle install product >/dev/null) ||
  fail "trunk: product bundle install failed"

tasks_template="$consumer_root/.specify/presets/default/templates/tasks-template.md"
trunk_config="$consumer_root/.specify/extensions/git/git-config.yml"
fake_bin="$consumer_root/.conformance/bin"
gh_calls="$consumer_root/.conformance/gh-calls.jsonl"
git_calls="$consumer_root/.conformance/git-calls.jsonl"

# Branch identity (plan D7) reads the task ledger through the same
# check-prerequisites.sh FEATURE_DIR the base resolution already uses, so
# the fixture lives at a feature directory distinct from the branch names
# below. Its fenced "Task block format" sample must never be picked over
# the real ledger: the sample's T001 is unchecked, the real T001 is
# checked, so a correct scan finds T002 first. The unclosed "```oops"
# line has a backtick in its info string, so it is never a fence opener
# either (parser.py's rule) -- a wrong mirror would swallow every task
# below it and the match case would fail.
task_tasks_file="$consumer_root/specs/003-directory-different/tasks.md"
mkdir -p "$(dirname "$task_tasks_file")"
cat > "$task_tasks_file" <<'MD'
# Tasks: Directory fixture

## Task block format

```markdown
- [ ] T001 [US?] Deliver a concrete outcome in exact/path.ext
  - **Traces**: FR-001; outcome: sample
```

```oops `not a fence`

## Phase 1: Sample

- [x] T001 Sample outcome one
  - **Depends on**: none
  - **Delivery**: single PR (~20 authored lines)
  - **Completion evidence**: merged as PR #1
- [ ] T002 Sample outcome two
  - **Depends on**: T001
  - **Delivery**: single PR (~50 authored lines)
- [ ] T003 Sample outcome three
  - **Depends on**: T002
- [ ] T004 Sample outcome four
  - **Depends on**: T003
  - **Delivery**: single PR (~300 authored lines)
- [x] T005 Sample outcome five
  - **Depends on**: T004
  - **Completion evidence**: Pending
MD

scripts_dir="$consumer_root/.specify/presets/default/scripts/python"
for script in task_base pr_create budget_stop stack_propagate merge_root_first ledger_check skill_mirror ignore_entries; do
  [ -e "$scripts_dir/$script.py" ] || fail "trunk: $script.py is not installed"
done
[ -e "$scripts_dir/_common.py" ] || fail "trunk: _common.py is not installed"
task_base_script="$scripts_dir/task_base.py"
pr_create_script="$scripts_dir/pr_create.py"
budget_stop_script="$scripts_dir/budget_stop.py"
stack_propagate_script="$scripts_dir/stack_propagate.py"
merge_root_first_script="$scripts_dir/merge_root_first.py"
ledger_check_script="$scripts_dir/ledger_check.py"
skill_mirror_script="$scripts_dir/skill_mirror.py"
ignore_entries_script="$scripts_dir/ignore_entries.py"
grep -Fq 'feature enters the **delivery base** only' "$tasks_template" &&
  grep -Fq 'the explicit non-empty `trunk:` value' "$tasks_template" &&
  grep -Fq '**draft feature PR** (`NNN-slug` → delivery base)' "$tasks_template" ||
  fail "trunk: installed tasks template does not document the delivery base"
mkdir -p "$fake_bin"
real_git=$(command -v git)

cat > "$fake_bin/gh" <<'PY'
#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
with open(os.environ["GH_CALLS"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(args, ensure_ascii=False, separators=(",", ":")) + "\n")
if args == ["repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]:
    if os.environ.get("FAIL_COMMAND") == "gh":
        print("forced gh failure", file=sys.stderr)
        raise SystemExit(9)
    sys.stdout.write(os.environ.get("GH_DEFAULT", "main\n"))
elif args[:2] == ["pr", "create"]:
    print("https://example.invalid/pr/1")
elif args[:2] == ["pr", "list"]:
    fields = args[args.index("--json") + 1].split(",")
    prs = []
    for i, line in enumerate(os.environ.get("GH_PR_LIST", "").splitlines(), 1):
        head, base, draft = line.split(" ")
        pr = {"headRefName": head, "baseRefName": base, "isDraft": draft == "true"}
        if "number" in fields:
            pr["number"] = i
        prs.append(pr)
    sys.stdout.write(json.dumps(prs))
elif args[:2] == ["api", "-X"]:
    pass
elif args[:2] == ["pr", "merge"]:
    if os.environ.get("FAIL_PR_MERGE") == args[2]:
        print(f"forced merge failure for #{args[2]}", file=sys.stderr)
        raise SystemExit(9)
else:
    print("unexpected gh argv", file=sys.stderr)
    raise SystemExit(8)
PY
chmod +x "$fake_bin/gh"

cat > "$fake_bin/git" <<'PY'
#!/usr/bin/env python3
import json, os, subprocess, sys

args = sys.argv[1:]
observed = args == ["branch", "--show-current"] or (
    args and args[0] in {"check-ref-format", "fetch", "merge", "push", "switch", "diff", "worktree"}
)
if observed:
    with open(os.environ["GIT_CALLS"], "a", encoding="utf-8") as stream:
        stream.write(json.dumps(args, ensure_ascii=False, separators=(",", ":")) + "\n")
if args == ["branch", "--show-current"]:
    print(os.environ.get("GIT_CURRENT_BRANCH", "003-feature"))
elif args and args[0] == "check-ref-format":
    if os.environ.get("FAIL_COMMAND") == "git":
        print("forced git failure", file=sys.stderr)
        raise SystemExit(9)
    raise SystemExit(subprocess.run([os.environ["REAL_GIT"], *args], check=False).returncode)
elif args and os.environ.get("FAIL_COMMAND") == args[0]:
    print(f"forced {args[0]} failure", file=sys.stderr)
    raise SystemExit(9)
elif args[:2] == ["diff", "--numstat"]:
    sys.stdout.write(os.environ.get("GIT_NUMSTAT", ""))
elif args[:2] == ["merge-base", "--is-ancestor"]:
    pair = f"{args[2]} {args[3]}"
    raise SystemExit(0 if pair in os.environ.get("GIT_ANCESTORS", "").splitlines() else 1)
elif not observed:
    raise SystemExit(subprocess.run([os.environ["REAL_GIT"], *args], check=False).returncode)
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
  if [ "$1" = __missing_file__ ]; then
    rm -f "$trunk_config"
  else
    printf '%b' "$1" > "$trunk_config"
  fi
}

pr_skill="$consumer_root/.agents/skills/speckit-pr/SKILL.md"
implement_skill="$consumer_root/.agents/skills/speckit-implement/SKILL.md"
grep -Fq 'pr_create.py' "$pr_skill" ||
  fail "trunk: $pr_skill does not invoke pr_create.py"

run_pr_create() {
  local kind="$1" github_default="$2" fail_command="$3" named_task="${4:-}"
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_DEFAULT="$github_default" FAIL_COMMAND="$fail_command" REAL_GIT="$real_git" \
    GH_PR_LIST="${GH_PR_LIST:-}" GIT_ANCESTORS="${GIT_ANCESTORS:-}" \
    GIT_CURRENT_BRANCH="${GIT_CURRENT_BRANCH:-}" \
    PATH="$fake_bin:$PATH" \
    SPECIFY_FEATURE='team/web/003-feature$(safe)' \
    SPECIFY_FEATURE_DIRECTORY='specs/003-directory-different' \
    "$PYTHON" "$pr_create_script" "$kind" ${named_task:+"$named_task"})
}

pr_list_json_call() {
  json_argv pr list --state open --limit 1000 --json headRefName,baseRefName,isDraft
}
repo_view=$(json_argv repo view --json defaultBranchRef -q .defaultBranchRef.name)

# Configured trunk wins; quotes and a trailing comment are stripped; no
# GitHub lookup happens.
for config in 'trunk: release\n' 'trunk: "release"\n' 'trunk: '"'"'release'"'"'\n' 'trunk: release  # ship branch\n'; do
  set_config "$config"
  reset_command_logs
  output=$(run_pr_create feature main "") || fail "trunk: configured '$config' failed"
  [ "$output" = "base=release" ] || fail "trunk: configured '$config' printed the wrong base"
  [ ! -s "$gh_calls" ] || fail "trunk: configured '$config' queried GitHub"
  [ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch release)" ] ||
    fail "trunk: configured '$config' did not validate its base"
done

# Absent, empty, or unrelated config falls back to the GitHub default.
for config in __missing_file__ 'trunk: ""\n' 'other: value\n'; do
  set_config "$config"
  reset_command_logs
  output=$(run_pr_create feature main "") || fail "trunk: fallback '$config' failed"
  [ "$output" = "base=main" ] || fail "trunk: fallback '$config' printed the wrong base"
  [ "$(cat "$gh_calls")" = "$repo_view" ] || fail "trunk: fallback '$config' used incorrect gh argv"
done

# An invalid branch name stops before a PR ever opens.
set_config 'trunk: bad..branch\n'
reset_command_logs
run_pr_create feature main "" >/dev/null 2>&1 && fail "trunk: invalid branch name was accepted"
[ ! -s "$gh_calls" ] || fail "trunk: invalid branch name still opened a PR"

# A forced GitHub failure stops before Git validates anything.
set_config __missing_file__
reset_command_logs
run_pr_create feature main gh >/dev/null 2>&1 && fail "trunk: a failed GitHub lookup was ignored"
[ "$(cat "$gh_calls")" = "$repo_view" ] || fail "trunk: failed GitHub lookup used incorrect argv"
[ ! -s "$git_calls" ] || fail "trunk: validated a branch after a failed GitHub lookup"

# The task base ignores trunk config entirely; metacharacters in
# repository-derived names stay inert argv.
set_config 'trunk: unused\n'
reset_command_logs
GIT_CURRENT_BRANCH=003-T002-slug
output=$(run_pr_create task main "") || fail "trunk: task PR create failed"
[ "$output" = 'base=team/web/003-feature$(safe)' ] || fail "trunk: task PR printed the wrong base"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "trunk: task PR used incorrect gh argv"
[ "$(cat "$git_calls")" = "$(json_argv branch --show-current)
$(json_argv fetch origin)" ] ||
  fail "trunk: task PR used incorrect git argv"

# Branch identity (plan D7, FR-004): the branch's T### must match the task
# the user named, else the ledger's first unchecked task outside fenced
# blocks -- T002 in the fixture above, never the fenced sample's T001.
identity_err="$consumer_root/.conformance/identity.err"
reset_command_logs
GIT_CURRENT_BRANCH=003-T003-slug
identity_status=0
run_pr_create task main "" >/dev/null 2>"$identity_err" || identity_status=$?
[ "$identity_status" -eq 2 ] ||
  fail "identity: mismatched branch exited $identity_status, expected 2"
grep -Fq 'branch 003-T003-slug delivers T003 but the task to deliver is T002' \
  "$identity_err" || fail "identity: mismatch message did not name both tasks"
[ ! -s "$gh_calls" ] || fail "identity: mismatched branch still queried or created a PR"

reset_command_logs
GIT_CURRENT_BRANCH=003-T003-slug
output=$(run_pr_create task main "" T003) ||
  fail "identity: a named task did not override the ledger"
[ "$output" = 'base=team/web/003-feature$(safe)' ] || fail "identity: named task printed the wrong base"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "identity: named task used incorrect gh argv"

# A missing ledger is a coded diagnostic, never a bare awk crash.
mv "$task_tasks_file" "$task_tasks_file.hidden"
reset_command_logs
GIT_CURRENT_BRANCH=003-T002-slug
identity_status=0
run_pr_create task main "" >/dev/null 2>"$identity_err" || identity_status=$?
mv "$task_tasks_file.hidden" "$task_tasks_file"
[ "$identity_status" -eq 2 ] ||
  fail "identity: missing ledger exited $identity_status, expected 2"
grep -Eq 'error: task ledger not found: .*specs/003-directory-different/tasks\.md$' \
  "$identity_err" || fail "identity: missing-ledger message did not name the path"
[ ! -s "$gh_calls" ] || fail "identity: missing ledger still queried or created a PR"

# The work-item base resolves the delivery base exactly like the feature
# PR: configured trunk wins (still active from above), and the fallback
# both queries the GitHub default and validates it.
reset_command_logs
output=$(run_pr_create work-item main "") || fail "trunk: work-item PR create failed"
[ "$output" = "base=unused" ] || fail "trunk: work-item PR printed the wrong base"
[ ! -s "$gh_calls" ] || fail "trunk: work-item PR queried GitHub"
[ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch unused)" ] ||
  fail "trunk: work-item PR did not validate its configured base"

set_config __missing_file__
reset_command_logs
output=$(run_pr_create work-item 'default$(safe)' "") || fail "trunk: work-item PR create failed"
[ "$output" = 'base=default$(safe)' ] || fail "trunk: work-item PR printed the wrong base"
[ "$(cat "$gh_calls")" = "$repo_view" ] ||
  fail "trunk: work-item PR did not resolve the GitHub default at runtime"
[ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch 'default$(safe)')" ] ||
  fail "trunk: work-item PR did not validate its fallback base"

# The chore and bugfix commands no longer carry their own branch-creation
# block; both now invoke the installed task_base.py's work-item mode
# directly (plan D2), so their identity is structural rather than
# byte-for-byte -- one script, two callers.
chore_skill="$consumer_root/.agents/skills/speckit-chore/SKILL.md"
bugfix_skill="$consumer_root/.agents/skills/speckit-bugfix/SKILL.md"
doctor_skill="$consumer_root/.agents/skills/speckit-doctor/SKILL.md"
for skill in "$chore_skill" "$bugfix_skill"; do
  grep -Fq 'task_base.py work-item' "$skill" ||
    fail "trunk: $skill does not invoke task_base.py work-item"
done

switch_call() {
  json_argv switch -c wor-123-short-slug "origin/$1"
}

run_work_item_branch() {
  local github_default="$1"
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_DEFAULT="$github_default" REAL_GIT="$real_git" PATH="$fake_bin:$PATH" \
    "$PYTHON" "$task_base_script" work-item wor-123-short-slug)
}

# Configured trunk wins; no GitHub lookup happens.
set_config 'trunk: unused\n'
reset_command_logs
run_work_item_branch main >/dev/null || fail "trunk: work-item branch create failed"
[ ! -s "$gh_calls" ] || fail "trunk: work-item branch queried GitHub although trunk was configured"
[ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch unused)
$(json_argv fetch origin)
$(switch_call unused)" ] ||
  fail "trunk: work-item branch used incorrect git argv for the configured base"

# Absent config falls back to the GitHub default, queried and validated.
set_config __missing_file__
reset_command_logs
run_work_item_branch 'default$(safe)' >/dev/null || fail "trunk: work-item branch create failed"
[ "$(cat "$gh_calls")" = "$repo_view" ] ||
  fail "trunk: work-item branch did not resolve the GitHub default at runtime"
[ "$(cat "$git_calls")" = "$(json_argv check-ref-format --branch 'default$(safe)')
$(json_argv fetch origin)
$(switch_call 'default$(safe)')" ] ||
  fail "trunk: work-item branch did not validate its fallback base"

# The first-task refresh resolves the delivery base the same way and
# guards that the checkout is the expected feature branch.
run_refresh() {
  local github_default="$1" current_branch="$2" fail_command="$3"
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_DEFAULT="$github_default" GIT_CURRENT_BRANCH="$current_branch" \
    FAIL_COMMAND="$fail_command" REAL_GIT="$real_git" PATH="$fake_bin:$PATH" \
    SPECIFY_FEATURE_DIRECTORY='specs/003-feature' \
    "$PYTHON" "$task_base_script" refresh)
}
branch_call=$(json_argv branch --show-current)

set_config 'trunk: release\n'
reset_command_logs
run_refresh main 003-feature "" >/dev/null || fail "trunk: configured refresh failed"
[ "$(cat "$git_calls")" = "$branch_call
$(json_argv check-ref-format --branch release)
$(json_argv fetch origin)
$(json_argv merge origin/release)
$(json_argv push origin 003-feature)" ] || fail "trunk: configured refresh used incorrect Git argv"
[ ! -s "$gh_calls" ] || fail "trunk: configured refresh queried GitHub"

set_config __missing_file__
reset_command_logs
run_refresh main 003-feature "" >/dev/null || fail "trunk: fallback refresh failed"
[ "$(cat "$gh_calls")" = "$repo_view" ] || fail "trunk: fallback refresh did not query GitHub"
[ "$(cat "$git_calls")" = "$branch_call
$(json_argv check-ref-format --branch main)
$(json_argv fetch origin)
$(json_argv merge origin/main)
$(json_argv push origin 003-feature)" ] || fail "trunk: fallback refresh used incorrect Git argv"

reset_command_logs
run_refresh main wrong-branch "" >/dev/null 2>&1 && fail "trunk: refresh accepted the wrong current branch"
[ "$(cat "$git_calls")" = "$branch_call" ] || fail "trunk: wrong-branch refresh mutated Git state"
[ ! -s "$gh_calls" ] || fail "trunk: wrong-branch refresh queried GitHub"

set_config 'trunk: release\n'
reset_command_logs
run_refresh main 003-feature fetch >/dev/null 2>&1 && fail "trunk: refresh ignored a forced fetch failure"
[ "$(cat "$git_calls")" = "$branch_call
$(json_argv check-ref-format --branch release)
$(json_argv fetch origin)" ] || fail "trunk: refresh did not stop after a forced fetch failure"
[ ! -s "$gh_calls" ] || fail "trunk: refresh queried GitHub after a forced fetch failure"

# SC-001: none of the installed delivery commands carry a marked shell
# block for the agent to keep intact or edit by hand -- every one of them
# now invokes a script directly (plan D2).
for skill in "$implement_skill" "$pr_skill" "$chore_skill" "$bugfix_skill" "$doctor_skill"; do
  grep -Eq '^# [a-z-]+:(start|end)$' "$skill" &&
    fail "trunk: $skill still carries a :start/:end marker"
done

echo "ok: trunk"

# --------------------------------------------------------------------------
# 5. One linear stack per feature (plan D5): task_base.py's task mode picks
#    the next task's base from the open, non-draft task PRs, and
#    speckit.pr's task case resolves the same base for `gh pr create`.
# --------------------------------------------------------------------------

run_task_base() {
  local branch="$1" pr_list="$2" feature="${3:-}" fail_command="${4:-}"
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_PR_LIST="$pr_list" FAIL_COMMAND="$fail_command" REAL_GIT="$real_git" \
    PATH="$fake_bin:$PATH" \
    SPECIFY_FEATURE="$feature" SPECIFY_FEATURE_DIRECTORY='specs/003-feature' \
    "$PYTHON" "$task_base_script" task "$branch")
}

# No open task PR: branch from the feature branch.
reset_command_logs
output=$(run_task_base 003-T002-slug "") || fail "stack: task-base with no open PR failed"
[ "$output" = "base=003-feature" ] ||
  fail "stack: task-base with no open PR printed the wrong base"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "stack: task-base with no open PR used incorrect gh argv"
[ "$(cat "$git_calls")" = "$(json_argv fetch origin)
$(json_argv switch -c 003-T002-slug origin/003-feature)" ] ||
  fail "stack: task-base with no open PR used incorrect git argv"

# A slashed feature branch (branch_template repositories): the feature
# number is the final path segment's prefix, not the whole path's.
reset_command_logs
output=$(run_task_base 003-T002-slug "" 'team/web/003-feature$(safe)') ||
  fail "stack: task-base with a slashed feature branch failed"
[ "$output" = 'base=team/web/003-feature$(safe)' ] ||
  fail "stack: task-base with a slashed feature branch printed the wrong base"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "stack: task-base with a slashed feature branch used incorrect gh argv"
[ "$(cat "$git_calls")" = "$(json_argv fetch origin)
$(json_argv switch -c 003-T002-slug 'origin/team/web/003-feature$(safe)')" ] ||
  fail "stack: task-base with a slashed feature branch used incorrect git argv"

# One ready task PR: branch from its head, not the feature branch.
reset_command_logs
output=$(run_task_base 003-T002-slug '003-T001-x 003-feature false') ||
  fail "stack: task-base with one ready PR failed"
[ "$output" = "base=003-T001-x" ] ||
  fail "stack: task-base with one ready PR printed the wrong base"
[ "$(cat "$git_calls")" = "$(json_argv fetch origin)
$(json_argv switch -c 003-T002-slug origin/003-T001-x)" ] ||
  fail "stack: task-base with one ready PR used incorrect git argv"

# Two open tops: two stacks, refuse before touching Git.
reset_command_logs
stack_err="$consumer_root/.conformance/stack.err"
stack_status=0
run_task_base 003-T002-slug \
  $'003-T001-x 003-feature false\n003-T001-z 003-feature false' \
  >/dev/null 2>"$stack_err" || stack_status=$?
[ "$stack_status" -eq 2 ] || fail "stack: two-stack task-base exited $stack_status, expected 2"
grep -Fq 'error: two open task stacks' "$stack_err" ||
  fail "stack: two-stack task-base did not name the error"
[ ! -s "$git_calls" ] || fail "stack: two-stack task-base unexpectedly touched git"

# A draft task PR: a task is still in flight, refuse before touching Git.
reset_command_logs
stack_status=0
run_task_base 003-T002-slug '003-T001-x 003-feature true' \
  >/dev/null 2>"$stack_err" || stack_status=$?
[ "$stack_status" -eq 2 ] || fail "stack: draft task-base exited $stack_status, expected 2"
grep -Fq 'error: draft task PR still open' "$stack_err" ||
  fail "stack: draft task-base did not name the error"
[ ! -s "$git_calls" ] || fail "stack: draft task-base unexpectedly touched git"

# A forced fetch failure stops before the branch switch.
reset_command_logs
run_task_base 003-T002-slug "" "" fetch >/dev/null 2>&1 &&
  fail "stack: task-base ignored a forced fetch failure"
[ "$(cat "$git_calls")" = "$(json_argv fetch origin)" ] ||
  fail "stack: task-base did not stop after a forced fetch failure"

# speckit.pr's task case walks every open head and keeps the deepest
# ancestor of HEAD, regardless of the order gh returns them in.
reset_command_logs
GH_PR_LIST=$'003-T001-x 003-feature false\n003-T002-y 003-T001-x false'
GIT_ANCESTORS=$'origin/003-T001-x HEAD\norigin/003-T002-y HEAD\norigin/003-T001-x origin/003-T002-y'
GIT_CURRENT_BRANCH=003-T002-slug
output=$(run_pr_create task main "") || fail "stack: task PR with ancestor failed"
[ "$output" = "base=003-T002-y" ] || fail "stack: task PR with ancestor printed the wrong base"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "stack: task PR with ancestor used incorrect gh argv"
[ "$(cat "$git_calls")" = "$(json_argv branch --show-current)
$(json_argv fetch origin)" ] ||
  fail "stack: task PR with ancestor used incorrect git argv"

reset_command_logs
GH_PR_LIST=$'003-T002-y 003-T001-x false\n003-T001-x 003-feature false'
GIT_CURRENT_BRANCH=003-T002-slug
output=$(run_pr_create task main "") || fail "stack: reverse-order task PR with ancestor failed"
[ "$output" = "base=003-T002-y" ] || fail "stack: reverse-order task PR with ancestor printed the wrong base"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "stack: reverse-order task PR with ancestor used incorrect gh argv"

echo "ok: stack"

# --------------------------------------------------------------------------
# 6. Fix propagation through the stack (plan D6): stack_propagate.py
#    carries a commit on a fixed branch into every open task PR stacked on
#    it, in stack order, as merge commits, and stops naming the branch on a
#    conflict without touching the branches above it.
# --------------------------------------------------------------------------

run_stack_propagate() {
  local branch="$1" pr_list="$2" fail_command="${3:-}"
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_PR_LIST="$pr_list" FAIL_COMMAND="$fail_command" REAL_GIT="$real_git" \
    PATH="$fake_bin:$PATH" \
    "$PYTHON" "$stack_propagate_script" "$branch")
}

chain_prs=$'003-T002-b 003-T001-a false\n003-T003-c 003-T002-b false'

# A chain of two stacked PRs: each is merged in stack order and pushed, and
# the run finishes back on the fixed branch.
reset_command_logs
run_stack_propagate 003-T001-a "$chain_prs" >/dev/null || fail "propagate: chain failed"
[ "$(cat "$gh_calls")" = "$(pr_list_json_call)" ] ||
  fail "propagate: chain used incorrect gh argv"
[ "$(cat "$git_calls")" = "$(json_argv switch 003-T002-b)
$(json_argv merge --no-ff -m 'merge(task): carry the T001 fix into T002' 003-T001-a)
$(json_argv push origin 003-T002-b)
$(json_argv switch 003-T003-c)
$(json_argv merge --no-ff -m 'merge(task): carry the T001 fix into T003' 003-T002-b)
$(json_argv push origin 003-T003-c)
$(json_argv switch 003-T001-a)" ] ||
  fail "propagate: chain used incorrect git argv"

# A conflict on the first merge stops the loop: it aborts, exits 2, and
# the branch stacked above (003-T003-c) is never reached.
reset_command_logs
propagate_status=0
run_stack_propagate 003-T001-a "$chain_prs" merge >/dev/null 2>&1 || propagate_status=$?
[ "$propagate_status" -eq 2 ] ||
  fail "propagate: forced merge failure exited $propagate_status, expected 2"
[ "$(cat "$git_calls")" = "$(json_argv switch 003-T002-b)
$(json_argv merge --no-ff -m 'merge(task): carry the T001 fix into T002' 003-T001-a)
$(json_argv merge --abort)" ] ||
  fail "propagate: forced merge failure used incorrect git argv"

# Nothing stacked: exit 0 without touching Git at all.
reset_command_logs
run_stack_propagate 003-T001-a "" >/dev/null || fail "propagate: empty chain failed"
[ ! -s "$git_calls" ] || fail "propagate: empty chain unexpectedly touched git"

echo "ok: propagate"

# --------------------------------------------------------------------------
# 7. Budget stop at twice the forecast (plan D9): budget_stop.py measures
#    added lines the review budget counts against the task's forecast and
#    stops at the smaller of 2x and 400.
# --------------------------------------------------------------------------

run_budget_stop() {
  local task="$1" base="$2" numstat="$3"
  (cd "$consumer_root" && GIT_CALLS="$git_calls" GIT_NUMSTAT="$numstat" REAL_GIT="$real_git" \
    PATH="$fake_bin:$PATH" SPECIFY_FEATURE_DIRECTORY='specs/003-directory-different' \
    "$PYTHON" "$budget_stop_script" "$task" "$base")
}

# T001's forecast must skip the template's fenced sample block, whose own
# unchecked "T001" header and forecast-less Delivery line precede the real,
# checked T001 in file order.
reset_command_logs
budget_status=0
run_budget_stop T001 003-feature $'41\t0\tsrc/a.py\n' >/dev/null 2>&1 || budget_status=$?
[ "$budget_status" -eq 2 ] || fail "budget: fenced-sample T001 exited $budget_status, expected 2"
budget_out=$(run_budget_stop T001 003-feature $'40\t0\tsrc/a.py\n')
[ "$budget_out" = "budget: 40/40 (forecast ~20)" ] ||
  fail "budget: fenced-sample T001 output was '$budget_out'"

# Under budget: binary and excluded files (docs, uv.lock) contribute
# nothing; a tab-separated path containing a space is still counted whole.
reset_command_logs
budget_out=$(run_budget_stop T002 003-feature \
  $'30\t0\tsrc/a.py\n500\t0\tdocs/guide.md\n9\t0\tuv.lock\n-\t-\tassets/logo.png\n12\t0\tsrc/with space.py\n')
[ "$budget_out" = "budget: 42/100 (forecast ~50)" ] ||
  fail "budget: under-budget output was '$budget_out'"
[ "$(cat "$git_calls")" = "$(json_argv diff --numstat --no-renames '003-feature...HEAD')" ] ||
  fail "budget: under-budget used incorrect git argv"

# Over budget: stops naming the task, the added count, and the stop line.
reset_command_logs
budget_err="$consumer_root/.conformance/budget.err"
budget_status=0
run_budget_stop T002 003-feature $'101\t0\tsrc/a.py\n' >/dev/null 2>"$budget_err" || budget_status=$?
[ "$budget_status" -eq 2 ] || fail "budget: over-budget exited $budget_status, expected 2"
grep -Fq T002 "$budget_err" && grep -Fq 101 "$budget_err" && grep -Fq 100 "$budget_err" ||
  fail "budget: over-budget diagnosis did not name the task, count, and stop"

# No forecast on the ledger (T003): the 400-line default is the stop line.
reset_command_logs
budget_out=$(run_budget_stop T003 003-feature $'350\t0\tsrc/a.py\n')
[ "$budget_out" = "budget: 350/400 (forecast ~400)" ] ||
  fail "budget: no-forecast output was '$budget_out'"
budget_status=0
run_budget_stop T003 003-feature $'401\t0\tsrc/a.py\n' >/dev/null 2>"$budget_err" || budget_status=$?
[ "$budget_status" -eq 2 ] || fail "budget: no-forecast over exited $budget_status, expected 2"

# A forecast whose double exceeds 400 (T004, ~300) still stops at 400.
reset_command_logs
budget_status=0
run_budget_stop T004 003-feature $'401\t0\tsrc/a.py\n' >/dev/null 2>"$budget_err" || budget_status=$?
[ "$budget_status" -eq 2 ] || fail "budget: capped stop exited $budget_status, expected 2"
grep -Fq 400 "$budget_err" || fail "budget: capped stop diagnosis did not name the 400 cap"

echo "ok: budget"

# --------------------------------------------------------------------------
# 8. Doctor: safe skill mirror and ignore entries (plan D11). The mirror
#    step copies extension/preset skills, and every core command the
#    preset replaces, whole from the default integration; appends each
#    remaining core command's own layer to that integration's render,
#    never crossing integrations; and does both idempotently, restoring a
#    lagging render that `integration upgrade --force` reset to upstream's.
#    The ignore step adds the installer's cache and venv directories to
#    .gitignore. The scripts read only files, so a hand-made fixture stands
#    in for a real `specify` install.
# --------------------------------------------------------------------------

dir_checksum() { (cd "$1" && find . -type f | sort && find . -type f | sort | xargs cat) | shasum -a 256 | awk '{print $1}'; }
render() { mkdir -p "$mirror_root/.claude/skills/$1"; cat > "$mirror_root/.claude/skills/$1/SKILL.md"; }
init_options() { # $1 root, $2 ai key, $3 JSON array body (indented lines)
  mkdir -p "$1/.specify"
  printf '{"ai": "%s"}' "$2" > "$1/.specify/init-options.json"
  printf '{\n  "installed_integrations": [\n%s\n  ]\n}\n' "$3" > "$1/.specify/integration.json"
}

mirror_root="$temporary_root/mirror"
mkdir -p "$mirror_root/.specify/integrations" "$mirror_root/.specify/presets/default/commands"
init_options "$mirror_root" codex $'    "codex",\n    "claude"'
for spec in codex:agents claude:claude; do
  IFS=: read -r key suffix <<<"$spec"
  cat > "$mirror_root/.specify/integrations/$key.manifest.json" <<JSON
{"files": {
  ".$suffix/skills/speckit-implement/SKILL.md": "x",
  ".$suffix/skills/speckit-tasks/SKILL.md": "x",
  ".$suffix/skills/speckit-checklist/SKILL.md": "x"}}
JSON
done
cat > "$mirror_root/.specify/presets/default/preset.yml" <<'YAML'
provides:
  commands:
    - type: "command"
      name: "speckit.tasks"
      file: "commands/tasks-append.md"
      strategy: "append"
    - type: "command"
      name: "speckit.implement"
      file: "commands/implement.md"
      strategy: "replace"
YAML
printf '\n## Order (tserdeiro/spec-kit)\nline one\nline two\n' \
  > "$mirror_root/.specify/presets/default/commands/tasks-append.md"

# The mirror never reads a core render's content when deciding to leave it
# alone (only its directory name), so codex's tasks and checklist need only
# exist; its extension skill speckit-pr and its replaced core implement are
# the two it compares and copies whole.
for name in speckit-tasks speckit-checklist; do
  mkdir -p "$mirror_root/.agents/skills/$name"
  printf 'codex core render, content unused by this name\n' > "$mirror_root/.agents/skills/$name/SKILL.md"
done
mkdir -p "$mirror_root/.agents/skills/speckit-implement"
printf 'codex implement render, the preset replace composed for the default\n' \
  > "$mirror_root/.agents/skills/speckit-implement/SKILL.md"
mkdir -p "$mirror_root/.agents/skills/speckit-pr"
printf 'codex pr body, extension skill\n' > "$mirror_root/.agents/skills/speckit-pr/SKILL.md"

render speckit-implement <<'MD'
---
name: "speckit-implement"
frontmatter: "claude"
---
claude implement body
MD
render speckit-tasks <<'MD'
---
name: "speckit-tasks"
frontmatter: "claude"
---
claude tasks body
MD
checklist_claude="$mirror_root/.claude/skills/speckit-checklist/SKILL.md"
mkdir -p "$(dirname "$checklist_claude")"
printf 'claude checklist body, core, no append\n' > "$checklist_claude"
mkdir -p "$mirror_root/.claude/skills/speckit-pr"
printf 'stale content\n' > "$mirror_root/.claude/skills/speckit-pr/SKILL.md"
checklist_before=$(shasum -a 256 < "$checklist_claude")

before=$(dir_checksum "$mirror_root")
mirror_report=$(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" false) ||
  fail "mirror: fix=false run failed"
[ "$(dir_checksum "$mirror_root")" = "$before" ] || fail "mirror: fix=false changed a file"
for name in speckit-pr speckit-implement speckit-tasks; do
  printf '%s\n' "$mirror_report" | grep -Fq "$name" ||
    fail "mirror: fix=false did not name $name as pending"
done
printf '%s\n' "$mirror_report" | grep -Fq speckit-checklist &&
  fail "mirror: fix=false reported the untouchable core checklist"

(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" true) ||
  fail "mirror: fix=true run failed"

cmp -s "$mirror_root/.agents/skills/speckit-pr/SKILL.md" \
  "$mirror_root/.claude/skills/speckit-pr/SKILL.md" ||
  fail "mirror: speckit-pr is not byte-identical across integrations"
cmp -s "$mirror_root/.agents/skills/speckit-implement/SKILL.md" \
  "$mirror_root/.claude/skills/speckit-implement/SKILL.md" ||
  fail "mirror: the replaced speckit-implement is not byte-identical across integrations"
[ "$(shasum -a 256 < "$checklist_claude")" = "$checklist_before" ] ||
  fail "mirror: fix=true touched the untouchable core checklist"

for spec in "speckit-tasks:claude tasks body:tasks-append.md"; do
  IFS=: read -r name body append_file <<<"$spec"
  core=$(printf '%s\n%s\n%s\n%s\n%s\n' '---' "name: \"$name\"" 'frontmatter: "claude"' '---' "$body")
  append=$(cat "$mirror_root/.specify/presets/default/commands/$append_file")
  expected="$temporary_root/expected-$name.md"
  printf '%s\n\n\n%s\n' "$core" "$append" > "$expected"
  cmp -s "$expected" "$mirror_root/.claude/skills/$name/SKILL.md" ||
    fail "mirror: claude's $name is not its own render plus the preset append"
done

mid=$(dir_checksum "$mirror_root")
second=$(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" true) ||
  fail "mirror: second fix=true run failed"
[ "$second" = "mirror: nothing to do" ] || fail "mirror: second fix=true run was not a clean no-op: $second"
[ "$(dir_checksum "$mirror_root")" = "$mid" ] || fail "mirror: second fix=true run changed a file"

# `integration upgrade <key> --force` re-renders every core command of that
# integration from upstream alone (dogfooding entry 71): a replaced core
# reset that way, or missing outright, comes back whole on the next fix
# run, and an appended one gets its layer again -- the exact fixed point.
render speckit-implement <<'MD'
---
name: "speckit-implement"
metadata:
  source: "templates/commands/implement.md"
---
upstream core body, the replace lost
MD
render speckit-tasks <<'MD'
---
name: "speckit-tasks"
frontmatter: "claude"
---
claude tasks body
MD
reset_report=$(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" false) ||
  fail "mirror: fix=false run after the reset failed"
printf '%s\n' "$reset_report" | grep -Fq 'speckit-implement missing or differs' &&
  printf '%s\n' "$reset_report" | grep -Fq 'speckit-tasks in .claude/skills (claude) needs the preset append' ||
  fail "mirror: the two reset renders were not both reported"
(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" true) >/dev/null ||
  fail "mirror: fix=true run after the reset failed"
[ "$(dir_checksum "$mirror_root")" = "$mid" ] || fail "mirror: the reset renders did not come back to the fixed point"
rm -r "$mirror_root/.claude/skills/speckit-implement"
(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" true) >/dev/null ||
  fail "mirror: fix=true run with the replaced core missing failed"
[ "$(dir_checksum "$mirror_root")" = "$mid" ] || fail "mirror: the missing replaced core did not come back whole"

# A preset entry registered for append but pointing at a nonexistent file
# must fail closed, never truncate a render (review finding, major); reuse
# checklist's render, which has no append registration yet.
cat >> "$mirror_root/.specify/presets/default/preset.yml" <<'YAML'
    - type: "command"
      name: "speckit.checklist"
      file: "commands/missing-append.md"
      strategy: "append"
YAML
before=$(dir_checksum "$mirror_root")
broken_status=0
(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" true) >/dev/null 2>&1 || broken_status=$?
[ "$broken_status" -eq 2 ] || fail "mirror: a missing append file did not exit 2 (got $broken_status)"
[ "$(dir_checksum "$mirror_root")" = "$before" ] || fail "mirror: a missing append file still wrote a file"

# A registered command strategy the mirror cannot compose (wrap, prepend)
# stops the run before any write instead of skipping the command silently
# -- even with the tasks append still genuinely pending, reset here so the
# guard has real work in front of it to preempt, not an already-clean tree.
render speckit-tasks <<'MD'
---
name: "speckit-tasks"
frontmatter: "claude"
---
claude tasks body
MD
cat >> "$mirror_root/.specify/presets/default/preset.yml" <<'YAML'
    - type: "command"
      name: "speckit.checklist"
      file: "commands/checklist.md"
      strategy: "wrap"
YAML
before=$(dir_checksum "$mirror_root")
wrap_status=0
wrap_err=$(cd "$mirror_root" && "$PYTHON" "$skill_mirror_script" true 2>&1 >/dev/null) || wrap_status=$?
[ "$wrap_status" -eq 2 ] || fail "mirror: a wrap strategy did not exit 2 (got $wrap_status)"
[ "$wrap_err" = 'mirror: speckit-checklist registers command strategy "wrap" -- the mirror composes only append and replace' ] ||
  fail "mirror: a wrap strategy was not diagnosed before any write: $wrap_err"
[ "$(dir_checksum "$mirror_root")" = "$before" ] ||
  fail "mirror: a wrap strategy still wrote a file, with the reset tasks append left pending"

single_root="$temporary_root/mirror-single"
init_options "$single_root" codex '    "codex"'
single_status=0
single_out=$(cd "$single_root" && "$PYTHON" "$skill_mirror_script" false) || single_status=$?
[ "$single_status" -eq 0 ] && [ "$single_out" = "mirror: only one integration installed, skipped" ] ||
  fail "mirror: single-integration fixture did not skip cleanly"

echo "ok: mirror"

ignore_root="$temporary_root/ignore"
mkdir -p "$ignore_root"
git -C "$ignore_root" init --quiet
printf '.venv/\n' > "$ignore_root/.gitignore"

before=$(shasum -a 256 < "$ignore_root/.gitignore")
ignore_report=$(cd "$ignore_root" && "$PYTHON" "$ignore_entries_script" false) ||
  fail "ignore: fix=false run failed"
[ "$(shasum -a 256 < "$ignore_root/.gitignore")" = "$before" ] || fail "ignore: fix=false changed .gitignore"
printf '%s\n' "$ignore_report" | grep -Fq '.specify/extensions/.cache/' &&
  printf '%s\n' "$ignore_report" | grep -Fq '.specify/presets/.cache/' &&
  printf '%s\n' "$ignore_report" | grep -Fq '.specify/integrations/.cache/' ||
  fail "ignore: fix=false did not report the three cache entries"
printf '%s\n' "$ignore_report" | grep -Fq '.venv/' &&
  fail "ignore: fix=false reported the entry the fixture .gitignore already covers"

(cd "$ignore_root" && "$PYTHON" "$ignore_entries_script" true) ||
  fail "ignore: fix=true run failed"
[ "$(cat "$ignore_root/.gitignore")" = "$(printf '.venv/\n\n# tserdeiro/spec-kit installer state\n.specify/extensions/.cache/\n.specify/presets/.cache/\n.specify/integrations/.cache/')" ] ||
  fail "ignore: fix=true did not append exactly the three missing entries"

mid=$(shasum -a 256 < "$ignore_root/.gitignore")
second=$(cd "$ignore_root" && "$PYTHON" "$ignore_entries_script" true) ||
  fail "ignore: second fix=true run failed"
[ "$second" = "ignore: nothing to do" ] || fail "ignore: second fix=true run was not a clean no-op: $second"
[ "$(shasum -a 256 < "$ignore_root/.gitignore")" = "$mid" ] || fail "ignore: second fix=true run changed .gitignore"

echo "ok: ignore"

# --------------------------------------------------------------------------
# 9. Root-first merge on explicit human request (plan D1, D5;
#    merge_root_first.py): retarget-then-merge walks the open task-PR
#    stack root first regardless of listing order, never requests
#    --delete-branch (the guard T014 will build), and a mid-stack failure
#    stops before the next retarget.
# --------------------------------------------------------------------------

merge_list_call=$(json_argv pr list --state open --limit 1000 --json number,headRefName,baseRefName,isDraft)
merge_root_first_pr_list=$'003-T003-c 003-T002-b false\n003-T001-a 003-feature false\n003-T002-b 003-T001-a false'

run_merge_root_first() {
  local pr_list="$1" fail_pr_merge="${2:-}"
  (cd "$consumer_root" && GH_CALLS="$gh_calls" GIT_CALLS="$git_calls" \
    GH_PR_LIST="$pr_list" FAIL_PR_MERGE="$fail_pr_merge" REAL_GIT="$real_git" \
    PATH="$fake_bin:$PATH" SPECIFY_FEATURE_DIRECTORY='specs/003-feature' \
    "$PYTHON" "$merge_root_first_script")
}

# A three-PR stack listed out of order: line order assigns the gh-reported
# PR numbers (1, 2, 3), but the walk still retargets and merges root first
# (#2, then #3, then #1), never requesting branch deletion.
reset_command_logs
output=$(run_merge_root_first "$merge_root_first_pr_list") ||
  fail "merge-root-first: three-PR stack failed"
[ "$output" = 'merged #2 003-T001-a
merged #3 003-T002-b
merged #1 003-T003-c' ] || fail "merge-root-first: wrong merge order or output: $output"
[ "$(cat "$gh_calls")" = "$merge_list_call
$(json_argv api -X PATCH 'repos/{owner}/{repo}/pulls/2' -f base=003-feature)
$(json_argv pr merge 2 --merge)
$(json_argv api -X PATCH 'repos/{owner}/{repo}/pulls/3' -f base=003-feature)
$(json_argv pr merge 3 --merge)
$(json_argv api -X PATCH 'repos/{owner}/{repo}/pulls/1' -f base=003-feature)
$(json_argv pr merge 1 --merge)" ] ||
  fail "merge-root-first: incorrect gh argv sequence"
[ "$(cat "$git_calls")" = "$(json_argv worktree prune)" ] ||
  fail "merge-root-first: incorrect git argv"
grep -Fq -- '--delete-branch' "$gh_calls" &&
  fail "merge-root-first: requested branch deletion"

# A mid-stack failure (the second PR's merge) stops before the next PR's
# retarget: #1's PATCH/merge never happen.
reset_command_logs
merge_status=0
run_merge_root_first "$merge_root_first_pr_list" 3 >/dev/null 2>&1 || merge_status=$?
[ "$merge_status" -eq 2 ] ||
  fail "merge-root-first: forced merge failure exited $merge_status, expected 2"
[ "$(cat "$gh_calls")" = "$merge_list_call
$(json_argv api -X PATCH 'repos/{owner}/{repo}/pulls/2' -f base=003-feature)
$(json_argv pr merge 2 --merge)
$(json_argv api -X PATCH 'repos/{owner}/{repo}/pulls/3' -f base=003-feature)
$(json_argv pr merge 3 --merge)" ] ||
  fail "merge-root-first: forced merge failure did not stop before the next retarget"

echo "ok: merge-root-first"

# --------------------------------------------------------------------------
# 10. Ledger completeness gate before ready-for-review (plan D1;
#     ledger_check.py): a checked task with real completion evidence
#     passes; an unchecked task or one whose evidence is still "Pending"
#     names exactly what is missing.
# --------------------------------------------------------------------------

run_ledger_check() {
  (cd "$consumer_root" && SPECIFY_FEATURE_DIRECTORY='specs/003-directory-different' \
    "$PYTHON" "$ledger_check_script" "$1")
}

output=$(run_ledger_check T001) || fail "ledger-check: checked task with evidence failed"
[ "$output" = "ledger: T001 checked, completion evidence filled" ] ||
  fail "ledger-check: checked task with evidence printed the wrong confirmation"

ledger_err="$consumer_root/.conformance/ledger.err"
ledger_status=0
run_ledger_check T002 >/dev/null 2>"$ledger_err" || ledger_status=$?
[ "$ledger_status" -eq 2 ] || fail "ledger-check: unchecked task exited $ledger_status, expected 2"
grep -Fq 'is not checked' "$ledger_err" ||
  fail "ledger-check: unchecked task did not name the gap"

ledger_status=0
run_ledger_check T005 >/dev/null 2>"$ledger_err" || ledger_status=$?
[ "$ledger_status" -eq 2 ] || fail "ledger-check: pending evidence exited $ledger_status, expected 2"
grep -Fq 'has no completion evidence' "$ledger_err" ||
  fail "ledger-check: pending evidence did not name the gap"

echo "ok: ledger-check"
echo "conformance passed"
