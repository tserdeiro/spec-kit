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

cleanup() {
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

if ! command -v specify >/dev/null 2>&1; then
  echo "conformance requires specify-cli 1.0.1 on PATH" >&2
  exit 4
fi

specify_version_output=$(specify version 2>/dev/null)
if [[ "$specify_version_output" != *"CLI Version    1.0.1"* ]]; then
  echo "conformance requires specify-cli 1.0.1" >&2
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
)

installed_root="$consumer_root/.specify/extensions/linear"
cp "$repository_root/tests/fixtures/consumer/speckit-linear.yml" "$consumer_root/"
runtime="$installed_root/scripts/bash/run.sh"

# 1. The installed artifact materializes its commands.
test -f "$installed_root/extension.yml"
test -f "$installed_root/commands/push.md"
test -x "$runtime"
test -f "$consumer_root/.specify/extensions/.registry"

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
