#!/usr/bin/env bash
set -euo pipefail

# Acceptance for the review surface, through the *installed* extension: the
# extension installs into a real Spec Kit consumer, `doctor` behaves, an
# advisory review of the working tree runs, and an anchored review
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
cp "$repository_root/tests/support/fake_gh.py" "$engine_bin/gh"
chmod +x "$engine_bin/gh"
gh_state="$temporary_root/fake-gh-state.json"
printf '%s\n' '{"auth":{"authenticated":true,"scopes":["repo"]},"user":"tester","pull_requests":{}}' >"$gh_state"
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

invoke_installed() {
  SPECKIT_CODE_REVIEW_EVIDENCE_DIR="$evidence_root" \
  SPECKIT_CODE_REVIEW_OCR_BIN="$engine_bin/ocr" \
  SPECKIT_CODE_REVIEW_GH_BIN="$engine_bin/gh" \
  SPECKIT_CODE_REVIEW_FAKE_GH_STATE="$gh_state" \
    "$installed_root/scripts/bash/run.sh" "$@"
}
run() {
  if [ "$1" != review ]; then
    invoke_installed "$@"
    return
  fi
  local before_branch before_status result
  before_branch=$(git -C "$consumer_root" symbolic-ref --short HEAD)
  before_status=$(git -C "$consumer_root" status --porcelain)
  if invoke_installed "$@"; then result=0; else result=$?; fi
  test "$(git -C "$consumer_root" symbolic-ref --short HEAD)" = "$before_branch" || return 1
  test "$(git -C "$consumer_root" status --porcelain)" = "$before_status" || return 1
  return "$result"
}
set_pr() {
  python3 - "$gh_state" "$1" "$2" "$3" <<'PY'
import json
import sys
from pathlib import Path

state_path, base, head, branch = sys.argv[1:]
state = json.loads(Path(state_path).read_text(encoding="utf-8"))
state["pull_requests"]["128"] = {
    "number": 128,
    "baseRefName": "context-base",
    "baseRefOid": base,
    "headRefName": branch,
    "headRefOid": head,
    "headRepositoryOwner": "tserdeiro",
    "headRepository": "consumer",
    "isCrossRepository": False,
    "state": "OPEN",
    "url": "https://github.com/tserdeiro/consumer/pull/128",
    "title": "context conformance",
    "body": "",
    "author": {"login": "contributor"},
    "labels": [],
}
Path(state_path).write_text(json.dumps(state), encoding="utf-8")
PY
}
generate_findings() {
  local session_path=$1
  local output_path=$2
  local mode=${3:-valid}
  python3 - "$session_path" "$consumer_root" "$output_path" "$mode" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

session_path, repository, output_path, mode = sys.argv[1:]
session_dir = Path(session_path)
session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
inventory = json.loads((session_dir / "context-inventory.json").read_text(encoding="utf-8"))
reads = []
for required in inventory.get("selected" if mode == "selected" else "required", []):
    path = required["path"]
    source = next(item for item in inventory["sources"] if item["path"] == path)
    if path == "<pull-request-intent>":
        intent = session.get("pr_intent") or {}
        raw = (str(intent.get("title", "")) + "\n" + str(intent.get("body", ""))).encode("utf-8")
    else:
        raw = subprocess.run(["git", "-C", repository, "cat-file", "blob", f"{session['head_commit']}:{path}"], check=True, capture_output=True).stdout
    lines = raw.splitlines(keepends=True)
    start, end = int(required["start"]), int(required["end"])
    selected = b"".join(lines[start - 1:end])
    reads.append({"path": path, "version": source["version"], "start_line": start, "end_line": end,
                  "sha256": hashlib.sha256(selected).hexdigest(), "assessment": "receipt covers this required context", "scope": "FR-008"})
if mode == "invalid":
    first = dict(reads[0])
    first["version"] = "reference-only"
    second = dict(reads[min(1, len(reads) - 1)])
    second["assessment"] = ""
    third = dict(reads[min(2, len(reads) - 1)])
    third["sha256"] = "0" * 64
    reads = [first, second, third, *reads[3:]]
    reads.append({"path": "reference-only.md", "version": "reference-only", "start_line": 1, "end_line": 1,
                  "sha256": "0" * 64, "assessment": "external reference", "scope": "FR-008"})
if mode == "reference":
    reads = [{"path": item["path"], "version": item["version"]} for item in reads]
original = json.loads(Path(output_path).read_text()) if Path(output_path).exists() else {}
document = {"findings": original.get("findings", []), "coverage": {"candidate_id": session["candidate_id"],
    "packet_sha256": session["packet_sha256"], "inventory_sha256": session["packet"]["inventory_sha256"], "reads": reads}}
Path(output_path).write_text(json.dumps(document), encoding="utf-8")
PY
}

json() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)'"$1"')'
}

# -- doctor ---------------------------------------------------------------

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

# Commands that no longer exist stay gone.
for command in run local install status rules upgrade completions; do
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
generate_findings "$session" "$session/findings.json"

set +e
closed=$(run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --json)
closed_code=$?
set -e
test "$closed_code" -eq 1  # changes-requested
test "$(echo "$closed" | json '["verdict"]["value"]')" = "changes-requested"
test "$(echo "$closed" | json '["verdict"]["is_approval"]')" = "False"
test ! -d "$worktree"
for artifact in findings.json findings-normalized.json findings.md publication-plan.json review-packet.md session.json; do
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

# -- installed context coverage ---------------------------------------------
# Build a feature in the temporary consumer's own Git history. The launcher
# below is the installed copy; the source checkout is only used to install it.
git -C "$consumer_root" switch --quiet --create context-base
mkdir -p "$consumer_root/specs/007-review-context"
python3 - "$consumer_root/specs/007-review-context/tasks.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = [
    "# Tasks\n", "\n",
    "- [x] T007 Prepare the review context (forecast: 80 lines, PR strategy: single)\n",
    "  - **Traces**: FR-007\n",
    "  - **Depends on**: none\n",
    "  - **Boundaries**: Change `src/prelude.py`.\n",
    "  - **Evidence**: focused tests pass.\n",
    "  - **Delivery**: single PR.\n",
    "  - **Completion evidence**: focused tests pass.\n",
    "\n",
]
lines.extend(f"Unrelated history {index:04d}: Árbol 🙈 {'x' * 75} prose is outside the selected task.\n" for index in range(800))
lines.extend([
    "\n- [ ] T010 Complete the feature review (forecast: 100 lines, PR strategy: single)\n",
    "  - **Traces**: FR-009\n",
    "  - **Depends on**: none\n",
    "  - **Boundaries**: Change `src/full.py`.\n",
    "  - **Evidence**: focused tests pass.\n",
    "  - **Delivery**: single PR.\n",
    "  - **Completion evidence**: focused tests pass.\n",
    "\n- [ ] T009 Share the review requirement (forecast: 90 lines, PR strategy: single)\n",
    "  - **Traces**: FR-008\n",
    "  - **Depends on**: none\n",
    "  - **Boundaries**: Change `src/shared.py`.\n",
    "  - **Evidence**: focused tests pass.\n",
    "  - **Delivery**: single PR.\n",
    "  - **Completion evidence**: focused tests pass.\n",
    "\n- [ ] T008 Review a late task (forecast: 140 lines, PR strategy: single)\n",
    "  - **Traces**: FR-008\n",
    "  - **Depends on**: T007\n",
    "  - **Boundaries**: Change `src/late.py`.\n",
    "  - **Evidence**: focused tests pass.\n",
    "  - **Delivery**: single PR.\n",
    "  - **Completion evidence**: focused tests pass.\n",
])
path.write_text("".join(lines), encoding="utf-8")
PY
printf '%s\n' '{"feature":"007-review-context"}' >"$consumer_root/.specify/feature.json"
printf '%s\n' '# Feature' '' '- **FR-007**: The preparation is reviewable.' '- **FR-008**: Shared requirements are complete.' '- **FR-009**: The whole feature is reviewable.' >"$consumer_root/specs/007-review-context/spec.md"
printf '%s\n' '# Plan' '' 'The plan covers FR-007, FR-008, and FR-009.' >"$consumer_root/specs/007-review-context/plan.md"
mkdir -p "$consumer_root/specs/007-review-context/checklists"
printf '%s\n' '# Checklist' '' '- [x] CHK001 Context is available.' >"$consumer_root/specs/007-review-context/checklists/requirements.md"
git -C "$consumer_root" add -f .specify/feature.json
git -C "$consumer_root" add specs/007-review-context
git -C "$consumer_root" commit --quiet -m "feature context baseline"
context_base=$(git -C "$consumer_root" rev-parse HEAD)

git -C "$consumer_root" switch --quiet --create 007-T008-installed-coverage
mkdir -p "$consumer_root/src"
printf '%s\n' 'late = True' >"$consumer_root/src/late.py"
git -C "$consumer_root" add src/late.py
git -C "$consumer_root" commit --quiet -m "late task candidate"
late_head=$(git -C "$consumer_root" rev-parse HEAD)

engine_state <<STATE
{
  "files": [{"path": "src/late.py"}],
  "rules": {"src/late.py": ["Validate every input."]},
  "record_invocations": "$engine_log"
}
STATE
set_pr "$context_base" "$late_head" "007-T008-installed-coverage"
late_opened=$(run review --root "$consumer_root" 128 --json)
late_session=$(echo "$late_opened" | json '["session"]["path"]')
test "$(echo "$late_opened" | json '["review_scope"]["kind"]')" = "task"
test "$(echo "$late_opened" | json '["review_scope"]["task_ids"][0]')" = "T008"
late_packet="$late_session/review-packet.md"
test "$(wc -c <"$late_packet" | tr -d ' ')" -le 400000
grep -q 'git show' "$late_packet"
test "$(python3 - "$late_session/session.json" "$late_session/context-inventory.json" <<'PY'
import json
import sys
session = json.load(open(sys.argv[1], encoding="utf-8"))
inventory = json.load(open(sys.argv[2], encoding="utf-8"))
task = next(item for item in session["sdd"]["task_entries"] if item["id"] == "T008")
start, end = task["source_range"]
assert session["sdd"]["tasks"]["bytes"] > 60000
assert inventory["omitted_required"], "fixture must require additional reads"
from pathlib import Path
packet = (Path(sys.argv[1]).parent / "review-packet.md").read_bytes()
packet.decode("utf-8")
assert len(packet) <= inventory["effective_limits"]["total_bytes"]
assert inventory["effective_limits"]["per_source_bytes"] == 60000
assert any(item["path"].endswith("/tasks.md") and item["start"] <= start and item["end"] >= end for item in inventory["required"])
print(True)
PY
)" = "True"

# Packet excerpts alone leave omitted required ranges unread; full reads close.
for mode in selected reference valid; do
  if [ "$mode" != selected ]; then
    late_opened=$(run review --root "$consumer_root" 128 --json)
  fi
  generate_findings "$late_session" "$late_session/findings.json" "$mode"
  set +e
  late_closed=$(run review --root "$consumer_root" --findings "$late_session/findings.json" --session "$late_session" --json)
  close_code=$?
  set -e
  if [ "$mode" = valid ]; then
    test "$close_code" -eq 0
    test "$(echo "$late_closed" | json '["coverage"]["complete"]')" = True
    test "$(echo "$late_closed" | json '["verdict"]["value"]')" = no-blocking-findings
  else
    test "$close_code" -eq 6
    test "$(echo "$late_closed" | json '["verdict"]["value"]')" = inconclusive
    echo "$late_closed" | json '["coverage"]["uncovered"]' | grep -q tasks.md
  fi
done

# A second changed path reaches a task that shares FR-008. The selected late
# task remains present after unrelated ledger growth and the packet stays bounded.
printf '%s\n' 'shared = True' >"$consumer_root/src/shared.py"
git -C "$consumer_root" add src/shared.py
git -C "$consumer_root" commit --quiet -m "shared task candidate"
multi_head=$(git -C "$consumer_root" rev-parse HEAD)
engine_state <<STATE
{
  "files": [{"path": "src/late.py"}, {"path": "src/shared.py"}],
  "rules": {"src/late.py": ["Validate every input."], "src/shared.py": ["Validate every input."]},
  "record_invocations": "$engine_log"
}
STATE
set_pr "$context_base" "$multi_head" "007-T008-installed-coverage"
multi_opened=$(run review --root "$consumer_root" 128 --json)
multi_session=$(echo "$multi_opened" | json '["session"]["path"]')
test "$(echo "$multi_opened" | json '["review_scope"]["kind"]')" = "multi-task"
echo "$multi_opened" | json '["review_scope"]["task_ids"]' | grep -q 'T008'
echo "$multi_opened" | json '["review_scope"]["task_ids"]' | grep -q 'T009'
python3 - "$multi_session/context-inventory.json" <<'PY'
import json, sys
inventory = json.load(open(sys.argv[1]))
assert any(item["path"].endswith("/spec.md") and item["start"] <= 4 <= item["end"] for item in inventory["required"]), inventory["required"]
PY
grep -q 'git show' "$multi_session/review-packet.md"

# Invalid, failed/reference-only and wrong receipts remain inconclusive and
# expose their exact causes rather than silently crediting the ledger.
invalid_findings="$multi_session/findings.json"
generate_findings "$multi_session" "$invalid_findings" invalid
set +e
invalid_closed=$(run review --root "$consumer_root" --findings "$invalid_findings" --session "$multi_session" --json)
invalid_code=$?
set -e
test "$invalid_code" -eq 6
test "$(echo "$invalid_closed" | json '["verdict"]["value"]')" = "inconclusive"
echo "$invalid_closed" | json '["verdict"]["causes"]' | grep -q 'coverage_source_mismatch'
echo "$invalid_closed" | json '["verdict"]["causes"]' | grep -q 'coverage_read_assessment'
echo "$invalid_closed" | json '["verdict"]["causes"]' | grep -q 'coverage_hash_mismatch'

# Additional valid receipts cover every required range and permit closure.
set_pr "$context_base" "$multi_head" "007-T008-installed-coverage"
multi_opened=$(run review --root "$consumer_root" 128 --json)
multi_session=$(echo "$multi_opened" | json '["session"]["path"]')
valid_findings="$multi_session/findings.json"
generate_findings "$multi_session" "$valid_findings"
valid_closed=$(run review --root "$consumer_root" --findings "$valid_findings" --session "$multi_session" --json)
test "$(echo "$valid_closed" | json '["verdict"]["value"]')" = "no-blocking-findings"
test "$(echo "$valid_closed" | json '["coverage"]["complete"]')" = "True"

# A feature branch selects the full feature, while an issue-key branch with
# bug artifacts takes the legitimate ledger-free short path.
git -C "$consumer_root" switch --quiet context-base
git -C "$consumer_root" switch --quiet --create 007-review-context
printf '%s\n' 'full = True' >"$consumer_root/src/full.py"
git -C "$consumer_root" add src/full.py
git -C "$consumer_root" commit --quiet -m "complete feature candidate"
full_head=$(git -C "$consumer_root" rev-parse HEAD)
engine_state <<STATE
{"files": [{"path": "src/full.py"}], "rules": {"src/full.py": ["Validate every input."]}, "record_invocations": "$engine_log"}
STATE
set_pr "$context_base" "$full_head" "007-review-context"
full_opened=$(run review --root "$consumer_root" 128 --json)
test "$(echo "$full_opened" | json '["review_scope"]["kind"]')" = "feature"
echo "$full_opened" | python3 -c 'import json,sys; assert set(json.load(sys.stdin)["review_scope"]["task_ids"]) == {"T007", "T008", "T009", "T010"}'
full_session=$(echo "$full_opened" | json '["session"]["path"]')
generate_findings "$full_session" "$full_session/findings.json"
run review --root "$consumer_root" --findings "$full_session/findings.json" --session "$full_session" --json >/dev/null

git -C "$consumer_root" switch --quiet context-base
git -C "$consumer_root" switch --quiet --create bug-123
mkdir -p "$consumer_root/.specify/bugs/fix-123" "$consumer_root/src"
printf '%s\n' '# Assessment' '' 'The bug is isolated.' >"$consumer_root/.specify/bugs/fix-123/assessment.md"
printf '%s\n' '# Fix' '' 'Validate the bug input.' >"$consumer_root/.specify/bugs/fix-123/fix.md"
printf '%s\n' '# Test' '' 'The regression test passes.' >"$consumer_root/.specify/bugs/fix-123/test.md"
printf '%s\n' 'bug = fixed' >"$consumer_root/src/bug.py"
git -C "$consumer_root" add .specify/bugs src/bug.py
git -C "$consumer_root" commit --quiet -m "fix isolated bug"
bug_head=$(git -C "$consumer_root" rev-parse HEAD)
engine_state <<STATE
{"files": [{"path": "src/bug.py"}, {"path": ".specify/bugs/fix-123/assessment.md"}, {"path": ".specify/bugs/fix-123/fix.md"}, {"path": ".specify/bugs/fix-123/test.md"}], "rules": {"src/bug.py": ["Validate every input."]}, "record_invocations": "$engine_log"}
STATE
set_pr "$context_base" "$bug_head" "bug-123"
bug_opened=$(run review --root "$consumer_root" 128 --json)
test "$(echo "$bug_opened" | json '["review_scope"]["kind"]')" = "short-path"
test "$(echo "$bug_opened" | json '["review_scope"]["task_ids"]' | tr -d '[]' | tr -d ' ')" = ""
bug_session=$(echo "$bug_opened" | json '["session"]["path"]')
generate_findings "$bug_session" "$bug_session/findings.json"
run review --root "$consumer_root" --findings "$bug_session/findings.json" --session "$bug_session" --json >/dev/null

git -C "$consumer_root" switch --quiet main
test "$(git -C "$consumer_root" status --porcelain)" = "$status_before"
test "$(git -C "$consumer_root" rev-parse --abbrev-ref HEAD)" = "$branch_before"

echo "review conformance passed (against the repository's fake engine)"
echo "the pinned binary is verified separately:"
echo "  uv run pytest tests/conformance -v"
