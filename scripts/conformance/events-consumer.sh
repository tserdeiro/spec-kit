#!/usr/bin/env bash
# Conformance: live events wiring in a temporary consumer (T023, plan D12).
# Builds a fresh consumer, dev-installs both extensions and the preset,
# verifies the generated dispatcher is wired for Claude and Codex, then
# drives it with the same argv and stdin payload each agent's hook uses.
set -euo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
consumer_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-events-conformance.XXXXXX")
trap 'rm -rf "$consumer_root"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

cd "$consumer_root"
git init --quiet
git -c user.email=t023@example.invalid -c user.name=t023-fixture commit --quiet --allow-empty -m "chore: initial commit"
specify init --here --force --ignore-agent-tools --integration claude >/dev/null
# Codex first: extension add wires every installed integration (dogfooding entry 85); install --force would be a no-op.
specify integration install codex >/dev/null
specify extension add "$repository_root/packages/spec-kit-linear" --dev >/dev/null
specify extension add "$repository_root/packages/spec-kit-code-review" --dev >/dev/null
specify preset add --dev "$repository_root/presets/default" >/dev/null

[ -x .specify/events.py ] || fail "wiring: .specify/events.py was not generated"
for name in session-start guard post-tool-use; do
  grep -q "$name" .claude/settings.json || fail "wiring: claude settings.json missing $name"
  grep -q "$name" .codex/config.toml || fail "wiring: codex config.toml missing $name"
done
grep -q '__speckit_event__' .claude/settings.json || fail "wiring: claude marker missing"
grep -q 'speckit_marker = true' .codex/config.toml || fail "wiring: codex marker missing"
echo "ok: wiring"

# Doctor's stem rule (doctor.md step 6): events.<event>.command must equal a commands/*.md stem.
stems_ok() {
  awk '/^events:/{f=1;next} f&&/^[a-z]/{exit} f&&/command:/{print $2}' ".specify/extensions/$1/extension.yml" |
    while read -r cmd; do [ -f ".specify/extensions/$1/commands/$cmd.md" ] || exit 1; done
}
rc=0; stems_ok linear || rc=1; stems_ok code-review || rc=1
[ "$rc" -eq 0 ] || fail "doctor: an events command has no matching commands/*.md stem"
echo "ok: doctor-stems"

# Linear read-only when the developer's local files exist (lifecycle disabled, so push --hook no-ops; status's
# query-only reads still render the line); without them the handler stays silent (T011), and so must this probe.
expected=""
if [ -f "$repository_root/speckit-linear.yml" ] && [ -f "$repository_root/.speckit-linear.env" ]; then
  { cat "$repository_root/speckit-linear.yml"; printf '\nhooks:\n  lifecycle_enabled: false\n  auto_apply: false\n'; } > speckit-linear.yml
  cp "$repository_root/.speckit-linear.env" .speckit-linear.env
  echo '/.speckit-linear.env' >> .gitignore
  expected="Linear: 001 on 001-T001-probe — next T001 (unchecked); next: /speckit.pr"
fi

mkdir -p specs/001-events
printf '# Events probe\n' > specs/001-events/spec.md
printf '# Implementation Plan: Events probe\n' > specs/001-events/plan.md
printf '# Tasks: Events probe\n\n## Phase 1: Probe\n\n- [ ] T001 Probe outcome one\n  - **Depends on**: none\n' > specs/001-events/tasks.md
printf '{"feature_directory": "specs/001-events"}' > .specify/feature.json
git switch -c 001-T001-probe --quiet

# A fresh consumer has no .venv, so the dispatcher's own interpreter rule (C-005) resolves to python3 here too.
agent_py=.venv/bin/python; [ -x "$agent_py" ] || agent_py=python3
# Payloads use Claude Code's hook fields (tool_name/tool_input); Codex's hooks are rendered Claude-compatible by
# upstream and assumed to send the same fields -- its live run is what confirms them.
dispatch() { "$agent_py" .specify/events.py "$1" "$2" 60; }
err="$consumer_root/.guard.err"

line=$(printf '{}' | dispatch session-start session_start) || fail "session_start: dispatcher exit $?"
[ "$line" = "$expected" ] || fail "session_start: expected '$expected', got '$line'"
echo "ok: session_start${expected:+ (Linear read-only)}"

rc=0
printf '{"tool_name":"Bash","tool_input":{"command":"git push --force origin HEAD"}}' |
  dispatch guard pre_tool_use >/dev/null 2>"$err" || rc=$?
[ "$rc" -eq 2 ] && grep -q -- '--force' "$err" || fail "guard: force-push was not blocked"
echo "ok: guard-force-push"

rc=0
printf '{"tool_name":"Write","tool_input":{"file_path":"specs/001-events/spec.md"}}' |
  dispatch guard pre_tool_use >/dev/null 2>"$err" || rc=$?
[ "$rc" -eq 2 ] && grep -q 'protected path' "$err" || fail "guard: protected write was not blocked on the task branch"
echo "ok: guard-protected-write"

git switch -c 001-events --quiet
rc=0
printf '{"tool_name":"Write","tool_input":{"file_path":"specs/001-events/spec.md"}}' |
  dispatch guard pre_tool_use >/dev/null 2>"$err" || rc=$?
[ "$rc" -eq 0 ] || fail "guard: protected write was blocked on the feature branch"
echo "ok: guard-feature-exempt"
git switch 001-T001-probe --quiet

rc=0
printf '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | dispatch guard pre_tool_use >/dev/null 2>"$err" || rc=$?
[ "$rc" -eq 0 ] || fail "guard: an ordinary command was blocked"
echo "ok: guard-allow"

# The handler never prints (FR-005/FR-006): this proves the routing and the exit contract; the reconcile is T012's tests.
rc=0
out=$(printf '{"tool_name":"Bash","tool_input":{"command":"git push origin HEAD"}}' | dispatch post-tool-use post_tool_use) || rc=$?
[ "$rc" -eq 0 ] && [ -z "$out" ] || fail "post_tool_use: expected a silent no-op, got exit=$rc stdout=$out"
echo "ok: post_tool_use (silent by contract)"

echo "events conformance passed"
