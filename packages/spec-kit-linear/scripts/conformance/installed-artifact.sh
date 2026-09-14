#!/usr/bin/env bash
# Conformance: the installed artifact, verified hermetically.
#
# Scope: this script verifies that the
# *installed* extension resolves its configuration, materializes its
# commands, does not reference its source checkout, and fails closed when it
# cannot reach its endpoint. It deliberately does NOT verify that a rendered
# plan is idempotent: that needs a Linear read, has no offline mode, and so on
# any machine with the operator's credentials configured it made conformance
# query a real production workspace. Plan idempotence belongs to the unit
# tests against the fake GraphQL server, where it is already covered, and to
# the opt-in remote acceptance authorized by a person.
#
# Hermetic *with respect to Linear*, by construction:
# SPECKIT_LINEAR_GRAPHQL_ENDPOINT is pinned to a loopback destination before
# anything runs, and the script refuses to continue (exit 4) if the effective
# endpoint the installed artifact reports is the production one. The presence
# or absence of operator credentials on the machine cannot change what this
# script touches. It is not network-isolated in general: it shells out to
# `specify`, a third-party CLI, and to `uv`, and makes no claim about what
# those two do -- the guarantee is about this extension's Linear traffic.
set -euo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-linear-conformance.XXXXXX")
consumer_root="$temporary_root/consumer"
fake_server_pid=""

cleanup() {
  if [ -n "$fake_server_pid" ]; then
    kill "$fake_server_pid" >/dev/null 2>&1 || true
    wait "$fake_server_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$temporary_root"
}
trap cleanup EXIT

# --------------------------------------------------------------------------
# Hermetic environment. Set before any CLI invocation, and never conditional.
# --------------------------------------------------------------------------

# The real process environment always wins over .speckit-linear.env and
# ~/.config/speckit-linear/env (see env_files.py), so pinning here is what
# makes this script behave identically on an operator machine and on a bare
# one. Port 9 (discard) on loopback: a destination that is guaranteed local
# and that nothing is listening on, which is exactly the "cannot reach its
# endpoint" condition asserted below.
PRODUCTION_ENDPOINT="https://api.linear.app/graphql"
export SPECKIT_LINEAR_GRAPHQL_ENDPOINT="http://127.0.0.1:9/graphql"

# The override is a destination override, never a credential one. A throwaway
# key is exported so the failure asserted below is always the transport one
# (the endpoint is unreachable) and never the prerequisite one (no credential
# configured) -- otherwise this script would assert a different exit code on a
# machine with the operator's key than on a machine without it. The value is
# never sent anywhere: nothing listens on the pinned loopback port.
export LINEAR_API_KEY="conformance-placeholder-not-a-real-key"
unset LINEAR_OAUTH_ACCESS_TOKEN

# NOTE on uv's cache: it is deliberately left wherever the environment puts
# it (uv's default lives under $HOME). Redirecting it to a fresh directory
# here, combined with the launcher's `uv run --frozen --offline`, is exactly
# the defect that used to make this script fail before it could reach any real
# check -- an empty cache plus --offline can only ever fail, and warming it
# would test the network rather than this extension. A run with a modified
# HOME (a useful way to prove that the operator's ~/.config/speckit-linear/env
# cannot change the outcome) should therefore point uv's own HOME-derived
# directories at the real ones -- UV_CACHE_DIR at an already warm cache and
# UV_PYTHON_INSTALL_DIR at the managed interpreters -- so that what the run
# actually varies is this extension's environment, not uv's toolchain:
#
#   HOME=$(mktemp -d) UV_CACHE_DIR=~/.cache/uv \
#     UV_PYTHON_INSTALL_DIR=~/.local/share/uv/python scripts/conformance/installed-artifact.sh
#
# The guard below reports a cold cache plainly rather than failing obscurely.

if [ "$SPECKIT_LINEAR_GRAPHQL_ENDPOINT" = "$PRODUCTION_ENDPOINT" ]; then
  echo "conformance refuses to run against the Linear production endpoint" >&2
  exit 4
fi
case "$SPECKIT_LINEAR_GRAPHQL_ENDPOINT" in
  http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*) ;;
  *)
    echo "conformance requires a loopback SPECKIT_LINEAR_GRAPHQL_ENDPOINT; got '$SPECKIT_LINEAR_GRAPHQL_ENDPOINT'" >&2
    exit 4
    ;;
esac

# --------------------------------------------------------------------------
# Prerequisites.
# --------------------------------------------------------------------------

pinned_cli=$(sed -n 's/^  package_version: //p' "$repository_root/../../versions.lock.yml" 2>/dev/null | head -1)
if [ -z "$pinned_cli" ]; then
  echo "conformance requires the source checkout's versions.lock.yml (upstream pin unreadable)" >&2
  exit 4
fi
if ! command -v specify >/dev/null 2>&1; then
  echo "conformance requires specify-cli $pinned_cli on PATH" >&2
  exit 4
fi
specify_version_output=$(specify version 2>/dev/null)
if [[ "$specify_version_output" != *"CLI Version    $pinned_cli"* ]]; then
  echo "conformance requires specify-cli $pinned_cli" >&2
  exit 4
fi

# The installed launcher runs `uv run --frozen --offline`, which can only work
# against an already warm uv cache. `--offline` here too, deliberately: the
# point of this check is to *report* a cold cache, not to quietly fix one by
# downloading from PyPI, which would make the message below a lie and would
# put a network fetch inside a script whose whole premise is that it does not
# depend on one.
if ! uv sync --frozen --offline --project "$repository_root" >/dev/null 2>&1; then
  echo "conformance requires a warm uv cache: run 'uv sync' once with network access first" >&2
  exit 4
fi

# --------------------------------------------------------------------------
# Install the extension into a throwaway consumer repository.
# --------------------------------------------------------------------------

mkdir -p "$consumer_root"
git -C "$consumer_root" init --quiet
(
  cd "$consumer_root"
  specify init --here --force --ignore-agent-tools --integration codex >/dev/null
)
cp -R "$repository_root/tests/fixtures/consumer/specs" "$consumer_root/"
cp "$repository_root/tests/fixtures/consumer/.specify/feature.json" "$consumer_root/.specify/feature.json"

(
  cd "$consumer_root"
  specify extension add "$repository_root" --dev >/dev/null
  specify preset add --dev "$repository_root/../../presets/default" >/dev/null
)

installed_root="$consumer_root/.specify/extensions/linear"
cp "$repository_root/tests/fixtures/consumer/speckit-linear.yml" "$consumer_root/"
runtime="$installed_root/scripts/bash/run.sh"

# Give the isolated consumer a committed SDD ledger and a deterministic
# delivery base so the installed start and PR-routing helpers run against the
# same stale-feature fixture as the native status/push paths below.
git -C "$consumer_root" config user.email conformance@example.invalid
git -C "$consumer_root" config user.name Conformance
git -C "$consumer_root" symbolic-ref HEAD refs/heads/main
git -C "$consumer_root" add .
git -C "$consumer_root" commit -qm conformance
mkdir -p "$consumer_root/.specify/extensions/git"
printf 'trunk: "main"\n' >"$consumer_root/.specify/extensions/git/git-config.yml"
# The preset work-item setup starts from `origin/<trunk>` just like a real
# consumer. Keep that ref local so this isolated fixture exercises the setup
# command rather than creating its result by hand.
git -C "$consumer_root" update-ref refs/remotes/origin/main HEAD

# 1. The installed artifact materializes its commands.
test -f "$installed_root/extension.yml"
test -f "$installed_root/commands/push.md"
test -x "$runtime"
test -f "$consumer_root/.specify/extensions/.registry"
test -f "$consumer_root/.agents/skills/speckit-pr/SKILL.md"
grep -Fq 'exact native `branchName`' "$consumer_root/.agents/skills/speckit-pr/SKILL.md"
grep -Fq '`Fixes TEAM-number`' "$consumer_root/.agents/skills/speckit-pr/SKILL.md"

python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); assert data["extensions"]["linear"]["registered_commands"]' "$consumer_root/.specify/extensions/.registry"

# 2. The installed runtime has no dependency on the source checkout it came
# from. Portable on purpose: `rg` is not guaranteed to exist as a binary, and
# when it does not an `rg`-based assertion silently passes -- a check that
# never runs is worse than no check.
if grep -RFq -e "$repository_root" "$installed_root"; then
  echo "installed runtime references its source checkout" >&2
  exit 1
fi

# --------------------------------------------------------------------------
# 3. The installed artifact resolves its configuration -- and, on the very
# first invocation, tells us which endpoint it actually resolved. This is the
# refusal gate: everything after it is known not to be talking to production.
# `doctor --offline` contacts nothing, so asking here is safe.
# --------------------------------------------------------------------------

set +e
"$runtime" doctor --offline --root "$consumer_root" --json >"$temporary_root/doctor.json" 2>"$temporary_root/doctor.err"
doctor_code=$?
set -e
if [ "$doctor_code" -ne 0 ]; then
  # Exit 4, not doctor's own code: this script is refusing to run, and its
  # refusals are all 4. Passing doctor's code through would report, say, a
  # missing prerequisite as if conformance itself had failed that way.
  echo "conformance refuses to run: the installed artifact could not resolve its configuration (doctor --offline exited $doctor_code)" >&2
  cat "$temporary_root/doctor.err" >&2
  exit 4
fi

effective_endpoint=$(python3 - "$temporary_root/doctor.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1]))
endpoint = payload.get("endpoint")
# No endpoint field means the artifact did not report a non-production
# destination: either it is on production, or it is a build that predates the
# mandatory notice. Both are a refusal.
print(endpoint.get("url", "missing") if isinstance(endpoint, dict) else "missing")
PY
)

if [ "$effective_endpoint" = "missing" ] || [ -z "$effective_endpoint" ]; then
  echo "conformance refuses to run: the installed artifact did not report a non-production GraphQL endpoint" >&2
  exit 4
fi
if [ "$effective_endpoint" = "$PRODUCTION_ENDPOINT" ]; then
  echo "conformance refuses to run: the effective endpoint is Linear production" >&2
  exit 4
fi
if [ "$effective_endpoint" != "$SPECKIT_LINEAR_GRAPHQL_ENDPOINT" ]; then
  echo "conformance refuses to run: effective endpoint '$effective_endpoint' is not the pinned '$SPECKIT_LINEAR_GRAPHQL_ENDPOINT'" >&2
  exit 4
fi

# The notice is mandatory and unsilenceable; check it reached stderr.
if ! grep -Fq "NOT LINEAR PRODUCTION" "$temporary_root/doctor.err"; then
  echo "a non-production endpoint must be announced prominently on every invocation" >&2
  exit 1
fi

# --------------------------------------------------------------------------
# 4. The installed artifact fails closed when it cannot reach its endpoint.
# Exit code 8 is this contract's transport/service code (linear_client.py
# raises it for URLError/timeout), not a silent success and not a fallback to
# some other destination.
# --------------------------------------------------------------------------

expect_unreachable() {
  label="$1"
  shift
  set +e
  "$runtime" "$@" >"$temporary_root/$label.out" 2>"$temporary_root/$label.err"
  code=$?
  set -e
  if [ "$code" -ne 8 ]; then
    echo "$label: expected exit 8 (transport) against an unreachable endpoint; got $code" >&2
    cat "$temporary_root/$label.err" >&2
    exit 1
  fi
  if ! grep -Fq "NOT LINEAR PRODUCTION" "$temporary_root/$label.err"; then
    echo "$label: the non-production endpoint notice must be present on every invocation" >&2
    exit 1
  fi
}

# Every surface that can reach Linear, so the assertion covers the same set
# the rule does rather than a convenient subset of it.
expect_unreachable status status --root "$consumer_root" --feature 001 --json
expect_unreachable push push --root "$consumer_root" --feature 001 --dry-run --json
expect_unreachable onboard onboard --root "$consumer_root" --team-key WOR --repository sample-repository --dry-run --json
# No flag silences the notice: --quiet is the strongest one there is.
expect_unreachable status-quiet status --root "$consumer_root" --feature 001 --quiet

for label in status push onboard; do
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); assert data["code"] == 8, data["code"]; assert data["endpoint"]["override_active"] is True, data["endpoint"]; assert data["endpoint"]["is_production"] is False, data["endpoint"]' "$temporary_root/$label.out"
done

# --------------------------------------------------------------------------
# 4a. The packaged bridge reads native Issue identity and preserves the exact
# branch name. This loopback GraphQL server is intentionally query-only: its
# request log is checked below so the installed bridge cannot acquire a
# mutation path while this conformance script exercises the start/PR matrix.
# --------------------------------------------------------------------------

fake_server="$temporary_root/fake-linear.py"
cat >"$fake_server" <<'PY'
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TEAM_ID = "22222222-2222-4222-8222-222222222222"


def context(identifier: str, branch: str) -> dict[str, object]:
    return {
        "id": f"issue-{identifier.lower()}",
        "identifier": identifier,
        "title": f"Native {identifier}",
        "description": f"Context for {identifier}",
        "url": f"https://linear.invalid/issue/{identifier}",
        "branchName": branch,
        "team": {"id": TEAM_ID, "key": "WOR", "name": "Work"},
    }


def binding() -> dict[str, object]:
    return {
        "viewer": {"organization": {"id": "11111111-1111-4111-8111-111111111111"}},
        "team": {"id": TEAM_ID, "key": "WOR", "name": "Work"},
        "projectLabelGroup": {"id": "33333333-3333-4333-8333-333333333333", "name": "Repository", "isGroup": True},
        "projectLabel": {"id": "44444444-4444-4444-8444-444444444444", "name": "sample-repository", "isGroup": False, "parent": {"id": "33333333-3333-4333-8333-333333333333"}},
        "projectView": {"id": "55555555-5555-4555-8555-555555555555", "name": "sample-repository / Features", "type": "project", "shared": True, "projectFilterData": {"labels": {"some": {"id": {"eq": "44444444-4444-4444-8444-444444444444"}}}}},
        "issueView": {"id": "66666666-6666-4666-8666-666666666666", "name": "sample-repository / Work", "type": "issue", "shared": True, "filterData": {"project": {"labels": {"some": {"id": {"eq": "44444444-4444-4444-8444-444444444444"}}}}}},
    }


def for_branch(branch: str) -> dict[str, object] | None:
    if branch == "users/alice/WOR-12-native-shape":
        return context("WOR-12", branch)
    if branch == "WOR-13-fix":
        return context("WOR-13", branch)
    if branch == "WOR-99-conflict":
        return context("WOR-12", branch)
    return None


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        query = request.get("query", "")
        variables = request.get("variables", {})
        Path(sys.argv[2]).open("a", encoding="utf-8").write(query.replace("\n", " ") + "\n")
        if "issueVcsBranchSearch" in query:
            data: dict[str, object] = {}
            for alias, variable in re.findall(r"(issue\d+): issueVcsBranchSearch\(branchName: \$(branch\d+)\)", query):
                data[alias] = for_branch(str(variables[variable]))
        elif "query BindingInspection" in query:
            data = binding()
        elif "query FeatureProjects" in query:
            data = {"projects": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
        elif "query WorkItemIssues" in query:
            data = {"issues": {"nodes": [
                {"id": f"issue-{int(number)}", "identifier": f"WOR-{int(number)}", "title": f"Native WOR-{int(number)}", "updatedAt": "2099-01-01T00:00:00Z", "url": f"https://linear.invalid/issue/WOR-{int(number)}", "state": {"id": "state-todo", "name": "Todo"}}
                for number in variables.get("numbers", [])
            ], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
        elif "query IssueContexts" in query:
            # A strict textual key with no native branch match stays
            # unresolved; the direct issue-key start query below still
            # returns its canonical context.
            data = {"issues": {"nodes": [
                context(f"WOR-{int(number)}", f"wor-{int(number)}-native")
                for number in variables.get("numbers", []) if int(number) != 12
            ], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
        elif "query IssueContext" in query:
            identifier = str(variables["id"]).upper()
            branch = "users/alice/WOR-12-native-shape" if identifier == "WOR-12" else f"{identifier.lower()}-native"
            data = {"issue": context(identifier, branch)}
        else:
            data = {}
        payload = json.dumps({"data": data}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        return


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
Path(sys.argv[1]).write_text(str(server.server_address[1]), encoding="utf-8")
server.serve_forever()
PY
uv run --frozen --offline --project "$repository_root" python "$fake_server" "$temporary_root/linear-port" "$temporary_root/linear-requests" &
fake_server_pid=$!
for _ in $(seq 1 100); do
  [ -s "$temporary_root/linear-port" ] && break
  sleep 0.01
done
if [ ! -s "$temporary_root/linear-port" ]; then
  echo "fake Linear server did not start" >&2
  exit 1
fi
export SPECKIT_LINEAR_GRAPHQL_ENDPOINT="http://127.0.0.1:$(cat "$temporary_root/linear-port")/graphql"

bridge="$installed_root/scripts/python/resolve_work_item.py"
bridge_json() {
  printf '%s' "$1" | uv run --frozen --offline --project "$repository_root" python "$bridge" --root "$consumer_root"
}

native=$(bridge_json '{"issue_key":"WOR-12"}')
python3 - "$native" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["status"] == "resolved"
resolution = payload["resolution"]
assert resolution["identifier"] == "WOR-12"
assert resolution["branch_name"] == "users/alice/WOR-12-native-shape"
assert resolution["team"]["key"] == "WOR"
PY

observed=$(bridge_json '{"branch_names":["users/alice/WOR-12-native-shape","old-title","WOR-99-conflict","009-feature"],"pull_requests":[{"head_branch":"users/alice/old-title","body":"## work item\n\n- tracker: fixes wor-13\n"},{"head_branch":"users/alice/conflicting","body":"## Work item\n\n- Tracker: Fixes WOR-12\n- Tracker: Fixes WOR-13\n"},{"head_branch":"009-feature","body":""}]}')
python3 - "$observed" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["status"] == "partial"
observations = payload["observations"]
assert [item["status"] for item in observations] == ["resolved", "unresolved", "conflict", "excluded", "resolved", "conflict", "excluded"]
assert observations[0]["resolution"]["branch_name"] == "users/alice/WOR-12-native-shape"
assert observations[4]["resolution"]["identifier"] == "WOR-13"
assert observations[2]["affected_issue_keys"] == ["WOR-12", "WOR-99"]
PY

python3 - "$temporary_root/linear-requests" <<'PY'
import sys
from pathlib import Path

requests = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert requests and all(line.startswith("query ") for line in requests)
assert not any("mutation" in line.lower() for line in requests)
PY

# The installed preset helpers and extension entry points cross their real
# subprocess boundaries. The active feature fixture is deliberately stale so
# successful native status/push runs prove the resolver wins before ledger
# selection. Setup is exercised through task_base.py; only its isolated
# origin/main ref is synthetic.
start_helper="$consumer_root/.specify/presets/default/scripts/python/work_item_start.py"
task_base_helper="$consumer_root/.specify/presets/default/scripts/python/task_base.py"
pr_helper="$consumer_root/.specify/presets/default/scripts/python/pr_create.py"
git -C "$consumer_root" switch -q main
native_start=$(cd "$consumer_root" && uv run --frozen --offline --project "$repository_root" python "$task_base_helper" work-item WOR-12)
python3 - "$native_start" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["issue_key"] == "WOR-12"
assert payload["branch_name"] == "users/alice/WOR-12-native-shape"
assert payload["configured"] is True
PY
test "$(git -C "$consumer_root" branch --show-current)" = "users/alice/WOR-12-native-shape"
test "$(git -C "$consumer_root" rev-parse HEAD)" = "$(git -C "$consumer_root" rev-parse origin/main)"

mv "$consumer_root/speckit-linear.yml" "$consumer_root/speckit-linear.configured.yml"
fallback_start=$(cd "$consumer_root" && uv run --frozen --offline --project "$repository_root" python "$start_helper" WOR-13 "Fallback title")
mv "$consumer_root/speckit-linear.configured.yml" "$consumer_root/speckit-linear.yml"
python3 - "$fallback_start" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["issue_key"] == "WOR-13"
assert payload["branch_name"] == "wor-13-fallback-title"
assert payload["configured"] is False
PY

pr_base=$(cd "$consumer_root" && uv run --frozen --offline --project "$repository_root" python "$pr_helper" work-item)
test "$pr_base" = "base=main"

# Repeating start from the delivery branch adopts the exact existing native
# head. A conflicting native head then blocks before checkout changes.
git -C "$consumer_root" switch -q main
adopted_start=$(cd "$consumer_root" && uv run --frozen --offline --project "$repository_root" python "$task_base_helper" work-item WOR-12)
python3 - "$adopted_start" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["branch_name"] == "users/alice/WOR-12-native-shape"
assert payload["configured"] is True
PY
test "$(git -C "$consumer_root" branch --show-current)" = "users/alice/WOR-12-native-shape"

fake_bin="$temporary_root/bin"
mkdir -p "$fake_bin"
cat >"$fake_bin/gh" <<'SH'
#!/usr/bin/env sh
printf '[[]]\n'
SH
chmod +x "$fake_bin/gh"
export PATH="$fake_bin:$PATH"

git -C "$consumer_root" branch users/alice/unresolved-title main
git -C "$consumer_root" branch WOR-12-unresolved main
git -C "$consumer_root" branch WOR-99-conflict main
git -C "$consumer_root" switch -q main
set +e
unresolved_start=$(cd "$consumer_root" && uv run --frozen --offline --project "$repository_root" python "$task_base_helper" work-item WOR-12 2>"$temporary_root/unresolved-start.err")
unresolved_code=$?
set -e
if [ "$unresolved_code" -ne 2 ] || ! grep -Fq "existing branch identity is unresolved" "$temporary_root/unresolved-start.err"; then
  echo "unresolved native setup must stop before checkout" >&2
  cat "$temporary_root/unresolved-start.err" >&2
  exit 1
fi
test "$(git -C "$consumer_root" branch --show-current)" = "main"
git -C "$consumer_root" branch -D -q WOR-12-unresolved
set +e
conflict_start=$(cd "$consumer_root" && uv run --frozen --offline --project "$repository_root" python "$task_base_helper" work-item WOR-12 2>"$temporary_root/conflict-start.err")
conflict_code=$?
set -e
if [ "$conflict_code" -ne 2 ] || ! grep -Fq "existing branch identity is conflict" "$temporary_root/conflict-start.err"; then
  echo "conflicting native setup must stop before checkout" >&2
  cat "$temporary_root/conflict-start.err" >&2
  exit 1
fi
test "$(git -C "$consumer_root" branch --show-current)" = "main"
git -C "$consumer_root" branch WOR-12-unresolved main

git -C "$consumer_root" switch -q users/alice/WOR-12-native-shape
before_head=$(git -C "$consumer_root" rev-parse HEAD)
native_status=$("$runtime" status --root "$consumer_root" --json)
python3 - "$native_status" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["status"]["task_rows"] == []
assert any(item["identifier"] == "WOR-12" for item in payload["status"]["work_items"])
PY

native_push=$("$runtime" push --root "$consumer_root" --dry-run --json)
python3 - "$native_push" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["plans"] == []
assert payload["work_item_plan"]["operations"] == []
PY

git -C "$consumer_root" switch -q users/alice/unresolved-title
unresolved_status=$("$runtime" status --root "$consumer_root" --json)
python3 - "$unresolved_status" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["status"]["task_rows"] == []
PY

git -C "$consumer_root" switch -q WOR-12-unresolved
unresolved_identity_status=$("$runtime" status --root "$consumer_root" --json)
python3 - "$unresolved_identity_status" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["status"]["task_rows"] == []
items = payload["status"]["work_items"]
assert [(item["identifier"], item["derived_state"], item["state_source"]) for item in items] == [("WOR-12", None, "unknown"), ("WOR-99", None, "unknown")]
PY

unresolved_push=$("$runtime" push --root "$consumer_root" --dry-run --json)
python3 - "$unresolved_push" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["plans"] == []
assert payload["work_item_plan"]["operations"] == []
PY

git -C "$consumer_root" switch -q WOR-99-conflict
conflict_status=$("$runtime" status --root "$consumer_root" --json)
python3 - "$conflict_status" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["status"]["task_rows"] == []
items = payload["status"]["work_items"]
assert [(item["identifier"], item["derived_state"], item["state_source"]) for item in items] == [("WOR-12", None, "unknown"), ("WOR-99", None, "unknown")]
PY

conflict_push=$("$runtime" push --root "$consumer_root" --dry-run --json)
python3 - "$conflict_push" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["code"] == 0
assert payload["plans"] == []
assert payload["work_item_plan"]["operations"] == []
PY

test "$(git -C "$consumer_root" rev-parse HEAD)" = "$before_head"
test "$(git -C "$consumer_root" branch --show-current)" = "WOR-99-conflict"
python3 - "$temporary_root/linear-requests" <<'PY'
import sys
from pathlib import Path

requests = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert requests and all(line.startswith("query ") for line in requests)
assert not any("mutation" in line.lower() for line in requests)
PY

# --------------------------------------------------------------------------
# 5. Mode conflicts are refused before any transport is attempted.
#
# Asserted by code *and* reason. "Exited non-zero" would be unfalsifiable
# here: against an unreachable endpoint every invocation exits non-zero by
# construction, so such a check could not fail even if the refusal
# disappeared -- the same class of never-running assertion this file calls
# out above for `rg`. Both cases below must fail as *usage* errors (exit 2),
# which is also proof they fail before any transport is attempted, since
# reaching the endpoint would have produced exit 8 instead.
# --------------------------------------------------------------------------

expect_usage_refusal() {
  label="$1"
  expected_diagnostic="$2"
  shift 2
  set +e
  "$runtime" "$@" >"$temporary_root/$label.out" 2>"$temporary_root/$label.err"
  code=$?
  set -e
  if [ "$code" -ne 2 ]; then
    echo "$label: expected exit 2 (usage refusal); got $code" >&2
    cat "$temporary_root/$label.out" "$temporary_root/$label.err" >&2
    exit 1
  fi
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); codes=[d["code"] for d in data["diagnostics"]]; assert sys.argv[2] in codes, codes' "$temporary_root/$label.out" "$expected_diagnostic"
}

expect_usage_refusal push-both-modes push_mode push --root "$consumer_root" --feature 001 --dry-run --apply --json
expect_usage_refusal onboard-both-modes onboard_mode onboard --root "$consumer_root" --team-key WOR --repository sample-repository --dry-run --apply --json

# --------------------------------------------------------------------------
# 6. Read-only paths never reach the mutation executor.
# --------------------------------------------------------------------------

if grep -nE '\.mutation\(' \
  "$repository_root/src/spec_kit_linear/remote_discovery.py" \
  "$repository_root/src/spec_kit_linear/reporting.py" \
  "$repository_root/src/spec_kit_linear/cli.py" | grep -v 'LinearMutationExecutor'; then
  echo "read-only paths must not invoke mutations" >&2
  exit 1
fi

echo "conformance passed"
