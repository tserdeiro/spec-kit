#!/usr/bin/env bash
set -euo pipefail

# Acceptance for the review surface, through the *installed* extension: the
# extension installs into a real Spec Kit consumer, `doctor` and `completions`
# behave, an advisory review of the working tree runs, and an anchored review
# opens a session, writes a packet, takes findings back and closes -- withdrawing
# the temporary worktree and leaving the operator's checkout untouched.
#
# The engine here is this repository's own fake: it stands in for the pinned
# binary so this script can run anywhere. Verifying that the real binary behaves
# the way the fake claims is a separate step -- `tests/conformance/test_real_ocr.py`
# -- against whatever `doctor --fix` installed at the canonical path.

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-code-review-review.XXXXXX")
# macOS TMPDIR ends in "/", so the template yields "T//…"; the CLI records
# resolved paths, so normalize before any path comparison against its logs.
temporary_root=$(CDPATH= cd -- "$temporary_root" && pwd -P)
consumer_root="$temporary_root/consumer"
evidence_root="$temporary_root/evidence"
engine_bin="$temporary_root/bin"
engine_log="$temporary_root/engine-invocations.log"

cleanup() {
  if [ -d "$consumer_root/.git" ]; then
    git -C "$consumer_root" worktree prune >/dev/null 2>&1 || true
  fi
  rm -rf "$temporary_root"
}
trap cleanup EXIT

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
# against an already warm uv cache. Say so plainly instead of letting uv fail
# with a download error that looks like a bug in this extension.
if ! uv sync --frozen --project "$repository_root" >/dev/null 2>&1; then
  echo "conformance requires a warm uv cache: run 'uv sync' once with network access first" >&2
  exit 4
fi

mkdir -p "$consumer_root" "$engine_bin"
git -C "$consumer_root" init --quiet
git -C "$consumer_root" config user.email "conformance@example.invalid"
git -C "$consumer_root" config user.name "Conformance"
git -C "$consumer_root" config commit.gpgsign false
git -C "$consumer_root" remote add origin git@github.com:tserdeiro/consumer.git
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

installed_root="$consumer_root/.specify/extensions/code-review"
test -f "$installed_root/extension.yml"
test -f "$installed_root/uv.lock"
test -f "$installed_root/commands/code-review.md"
test -f "$installed_root/commands/doctor.md"
test -f "$installed_root/commands/completions.md"
test -x "$installed_root/scripts/bash/run.sh"
test -f "$consumer_root/.specify/extensions/.registry"

# The installed runtime must not reference the development checkout.
if grep -R -F -- "$repository_root" "$installed_root" >/dev/null 2>&1; then
  echo "installed runtime references its source checkout" >&2
  exit 1
fi

# The stand-in engine, and a lock that pins exactly it.
cp "$repository_root/tests/support/fake_ocr.py" "$engine_bin/ocr"
chmod +x "$engine_bin/ocr"
engine_digest=$(shasum -a 256 "$engine_bin/ocr" | cut -d' ' -f1)
case "$(uname -s)" in
  Darwin) platform_os="darwin" ;;
  Linux) platform_os="linux" ;;
  *) platform_os="$(uname -s | tr '[:upper:]' '[:lower:]')" ;;
esac
case "$(uname -m)" in
  arm64 | aarch64) platform_arch="arm64" ;;
  x86_64 | amd64) platform_arch="amd64" ;;
  *) platform_arch="$(uname -m)" ;;
esac
cat >"$consumer_root/versions.lock.yml" <<LOCK
schema_version: "1.0"

extensions:
  code-review:
    id: code-review
    version: 0.1.0
    provenance: first-party-monorepo
    path: packages/spec-kit-code-review
    external_tools:
      open_code_review:
        source: https://github.com/alibaba/open-code-review
        license: Apache-2.0
        release_tag: v1.8.3
        version_string: "ocr version v1.8.3"
        npm_package: "@alibaba-group/open-code-review"
        binaries:
          ${platform_os}-${platform_arch}: "$engine_digest"
LOCK

engine_state() {
  cat >"$engine_bin/ocr-state.json"
}

run() {
  SPECKIT_CODE_REVIEW_EVIDENCE_DIR="$evidence_root" \
  SPECKIT_CODE_REVIEW_OCR_BIN="$engine_bin/ocr" \
    "$installed_root/scripts/bash/run.sh" "$@"
}
json() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)'"$1"')'
}

# -- doctor and completions ---------------------------------------------------

run doctor --root "$consumer_root" --fix --json >/dev/null
test -f "$consumer_root/speckit-code-review.yml"
test -f "$consumer_root/speckit-code-review.local.yml"
test -f "$consumer_root/.opencodereview/rule.json"
grep -q "speckit-code-review.local.yml" "$consumer_root/.gitignore"
grep -q ".speckit-code-review.env" "$consumer_root/.gitignore"

# `--fix` never overwrites what the consumer already wrote.
rules_before=$(cat "$consumer_root/.opencodereview/rule.json")
run doctor --root "$consumer_root" --fix --json >/dev/null
test "$rules_before" = "$(cat "$consumer_root/.opencodereview/rule.json")"

# The install command doctor prints is never global and never per-project.
install_command=$(run doctor --root "$consumer_root" --json | json '["diagnostics"]')
echo "$install_command" | grep -q "npm install --prefix"
if echo "$install_command" | grep -q "npm install -g"; then
  echo "doctor suggested a global install" >&2
  exit 1
fi

for shell in bash zsh; do
  script=$(run completions "$shell")
  echo "$script" | grep -q "review"
  echo "$script" | grep -q -- "--publish"
done

# Commands that no longer exist stay gone.
for command in run local install status rules upgrade; do
  set +e
  run "$command" --root "$consumer_root" >/dev/null 2>&1
  status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    echo "$command must not exist any more" >&2
    exit 1
  fi
done

# -- an advisory review of the working tree -----------------------------------

git -C "$consumer_root" add --all
git -C "$consumer_root" commit --quiet -m "consumer baseline"
mkdir -p "$consumer_root/src"
printf 'value = 1\n' >"$consumer_root/src/module.py"
engine_state <<STATE
{
  "files": [{"path": "src/module.py"}],
  "rules": {"src/module.py": ["Validate every input."]},
  "record_invocations": "$engine_log"
}
STATE

advisory=$(run review --root "$consumer_root" --json)
packet_path=$(echo "$advisory" | json '["packet"]["path"]')
grep -q "## 1. Workspace (no candidate)" "$packet_path"
grep -q "the output is advisory" "$packet_path"
test -z "$(git -C "$consumer_root" status --porcelain -- .specify)"
# Nothing was materialized and no session was opened.
test ! -d "$evidence_root/$(basename "$packet_path")/worktree"
if find "$evidence_root" -name session.json | grep -q .; then
  echo "an advisory review opened a session" >&2
  exit 1
fi

git -C "$consumer_root" add --all
git -C "$consumer_root" commit --quiet -m "baseline module"

# -- an anchored review -------------------------------------------------------

git -C "$consumer_root" switch --quiet --create feature
printf 'value = 2\n' >"$consumer_root/src/module.py"
mkdir -p "$consumer_root/docs"
printf '# Guide\n' >"$consumer_root/docs/guide.md"
git -C "$consumer_root" add --all
git -C "$consumer_root" commit --quiet -m "candidate work"
head_commit=$(git -C "$consumer_root" rev-parse HEAD)
git -C "$consumer_root" switch --quiet main
# Work in progress the review must never touch.
printf 'work in progress\n' >"$consumer_root/scratch.txt"
status_before=$(git -C "$consumer_root" status --porcelain)
branch_before=$(git -C "$consumer_root" rev-parse --abbrev-ref HEAD)

engine_state <<STATE
{
  "files": [
    {"path": "src/module.py"},
    {"path": "docs/guide.md", "included": false, "reason": "documentation is out of scope"}
  ],
  "rules": {"src/module.py": ["Validate every input."]},
  "record_invocations": "$engine_log"
}
STATE

opened=$(run review --root "$consumer_root" --base main --head "$head_commit" --json)
session=$(echo "$opened" | json '["session"]["path"]')
worktree=$(echo "$opened" | json '["environment"]["worktree_path"]')
test -d "$worktree"
test -f "$session/review-packet.md"
test "$(echo "$opened" | json '["scope"]["included_count"]')" = "1"
test "$(git -C "$consumer_root" status --porcelain)" = "$status_before"
test "$(git -C "$consumer_root" rev-parse --abbrev-ref HEAD)" = "$branch_before"
# The rule file the engine received came from a commit, inside the evidence.
grep -q -- "--rule $evidence_root" "$engine_log"

# The findings the agent would produce, closed back into the session.
cat >"$session/findings.json" <<'FINDINGS'
{"findings": [{
  "path": "src/module.py",
  "start_line": 1,
  "end_line": 1,
  "side": "RIGHT",
  "severity": "blocking",
  "category": "correctness",
  "title": "The value is never validated",
  "content": "`value = 2` is assigned without validation."
}]}
FINDINGS

set +e
closed=$(run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --json)
closed_code=$?
set -e
test "$closed_code" -eq 1  # changes-requested
test "$(echo "$closed" | json '["verdict"]["value"]')" = "changes-requested"
test "$(echo "$closed" | json '["verdict"]["is_approval"]')" = "False"
test ! -d "$worktree"
for artifact in findings.json findings.md publication-plan.json review-packet.md session.json; do
  test -f "$session/$artifact"
done
test "$(git -C "$consumer_root" status --porcelain)" = "$status_before"
test "$(git -C "$consumer_root" rev-parse --abbrev-ref HEAD)" = "$branch_before"

# A packet edited between the phases is refused with nothing normalized.
opened=$(run review --root "$consumer_root" --base main --head "$head_commit" --json)
session=$(echo "$opened" | json '["session"]["path"]')
printf '\nan extra line\n' >>"$session/review-packet.md"
set +e
run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --json >/dev/null 2>&1
drift_code=$?
set -e
test "$drift_code" -eq 8

# An output shape the adapter does not recognize is exit 9, never a guessed scope.
git -C "$consumer_root" worktree remove --force "$session/worktree" >/dev/null 2>&1 || true
rm -rf "$session"
engine_state <<STATE
{
  "files": [{"path": "src/module.py"}],
  "rules": {"src/module.py": ["Validate every input."]},
  "preview_failure": "unknown-format",
  "record_invocations": "$engine_log"
}
STATE
set +e
run review --root "$consumer_root" --base main --head "$head_commit" --json >/dev/null 2>&1
engine_code=$?
set -e
test "$engine_code" -eq 9
test "$(git -C "$consumer_root" rev-parse --abbrev-ref HEAD)" = "$branch_before"

echo "review conformance passed (against the repository's fake engine)"
echo "the pinned binary is verified separately:"
echo "  uv run pytest tests/conformance -v"
