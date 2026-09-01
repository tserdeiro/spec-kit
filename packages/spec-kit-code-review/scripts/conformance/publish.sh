#!/usr/bin/env bash
set -euo pipefail

# Acceptance for publication, through the *installed* extension.
#
# This is the only stage that writes, so what this script proves is mostly about
# what does NOT happen: a review without `--publish` never writes, an operation
# outside the allowlist fails closed, APPROVE is unreachable, a candidate that
# moved publishes nothing, and a second publication of the same candidate is
# refused rather than duplicated.
#
# `gh` here is this repository's own behavioural fake: it records every API call
# with its body and refuses anything the allowlist does not list -- so this can
# assert both that the extension never attempted a forbidden call and that it
# would have been rejected if it had.
#
# **Acceptance against a real pull request is not part of this script.** It is an
# explicitly human, explicitly authorized step, for the same reason the real
# `ocr` binary is: a remote write is not something a test suite should perform on
# someone's repository. The procedure is printed at the end.

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-code-review-publish.XXXXXX")
consumer_root="$temporary_root/consumer"
evidence_root="$temporary_root/evidence"
engine_bin="$temporary_root/bin"
engine_log="$temporary_root/engine-invocations.log"
gh_state="$temporary_root/gh-state.json"
api_log="$temporary_root/gh-api.jsonl"

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
(
  cd "$consumer_root"
  specify extension add "$repository_root" --dev >/dev/null
)
installed_root="$consumer_root/.specify/extensions/code-review"

cp "$repository_root/tests/support/fake_ocr.py" "$engine_bin/ocr"
chmod +x "$engine_bin/ocr"
cp "$repository_root/tests/support/fake_gh.py" "$engine_bin/gh"
chmod +x "$engine_bin/gh"
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

run() {
  SPECKIT_CODE_REVIEW_EVIDENCE_DIR="$evidence_root" \
  SPECKIT_CODE_REVIEW_OCR_BIN="$engine_bin/ocr" \
  SPECKIT_CODE_REVIEW_GH_BIN="$engine_bin/gh" \
  SPECKIT_CODE_REVIEW_FAKE_GH_STATE="$gh_state" \
    "$installed_root/scripts/bash/run.sh" "$@"
}
json() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)'"$1"')'
}
api_writes() {
  python3 - "$api_log" <<'WRITES'
import json
import os
import sys

path = sys.argv[1]
if os.path.exists(path):
    for line in open(path, encoding="utf-8"):
        if line.strip():
            call = json.loads(line)
            if call["method"] != "GET":
                print(call["method"], call["endpoint"])
WRITES
}

# -- a candidate on GitHub ------------------------------------------------------

mkdir -p "$consumer_root/.opencodereview" "$consumer_root/src"
cat >"$consumer_root/.opencodereview/rule.json" <<'RULES'
{
  "rules": [
    {"path": "src/**", "rule": "Validate every input.", "merge_system_rule": true}
  ]
}
RULES
python3 - "$consumer_root" <<'SEED'
import sys
from pathlib import Path

root = Path(sys.argv[1])
(root / "src" / "module.py").write_text("".join(f"line_{index} = {index}\n" for index in range(10)), encoding="utf-8")
SEED
git -C "$consumer_root" add --all
git -C "$consumer_root" commit --quiet -m "consumer baseline"
base_commit=$(git -C "$consumer_root" rev-parse HEAD)

git -C "$consumer_root" switch --quiet --create feature
python3 - "$consumer_root" <<'CANDIDATE'
import sys
from pathlib import Path

root = Path(sys.argv[1])
path = root / "src" / "module.py"
path.write_text(path.read_text(encoding="utf-8") + "added_a = 1\nadded_b = 2\n", encoding="utf-8")
CANDIDATE
git -C "$consumer_root" add --all
git -C "$consumer_root" commit --quiet -m "candidate work"
head_commit=$(git -C "$consumer_root" rev-parse HEAD)
git -C "$consumer_root" switch --quiet main

cat >"$engine_bin/ocr-state.json" <<STATE
{
  "files": [{"path": "src/module.py"}],
  "rules": {"src/module.py": ["Validate every input."]},
  "record_invocations": "$engine_log"
}
STATE

write_gh_state() {
  python3 - "$gh_state" "$base_commit" "$1" "$api_log" "${2:-OPEN}" "${3:-contributor}" <<'PRSTATE'
import json
import sys

path, base_commit, head_commit, api_log, state, author = sys.argv[1:7]
json.dump(
    {
        "auth": {"authenticated": True, "scopes": ["repo"]},
        "user": "reviewer",
        "record_api": api_log,
        "issue_comments": [],
        "pull_requests": {
            "128": {
                "number": 128,
                "baseRefName": "main",
                "baseRefOid": base_commit,
                "headRefOid": head_commit,
                "headRepositoryOwner": {"login": "tserdeiro"},
                "headRepository": {"name": "consumer"},
                "isCrossRepository": False,
                "state": state,
                "url": "https://github.com/tserdeiro/consumer/pull/128",
                "title": "A candidate",
                "body": "",
                "author": {"login": author},
                "labels": [],
            }
        },
    },
    open(path, "w", encoding="utf-8"),
)
PRSTATE
}
write_gh_state "$head_commit"

write_findings() {
  cat >"$1/findings.json" <<'FINDINGS'
{
  "findings": [
    {
      "path": "src/module.py",
      "start_line": 11,
      "end_line": 12,
      "side": "RIGHT",
      "severity": "blocking",
      "category": "correctness",
      "title": "The added values are never validated",
      "content": "`added_a` and `added_b` are assigned without validation."
    }
  ]
}
FINDINGS
}

open_review() {
  run review --root "$consumer_root" 128 --json | json "['session']['path']"
}

# -- a review without --publish writes nothing ----------------------------------

session=$(open_review)
write_findings "$session"
rm -f "$api_log"
set +e
run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --json >/dev/null
preview_code=$?
set -e
test "$preview_code" -eq 1  # changes-requested
test -z "$(api_writes)"
test -f "$session/publication-plan.json"

# -- `--publish` without a review to publish is a usage error -------------------

rm -f "$api_log"
set +e
premature=$(run review --root "$consumer_root" 128 --publish --json 2>/dev/null)
premature_code=$?
set -e
test "$premature_code" -eq 2
echo "$premature" | grep -q "publish_without_review"
test -z "$(api_writes)"

# -- the real publication -------------------------------------------------------

session=$(open_review)
write_findings "$session"
rm -f "$api_log"
set +e
published=$(run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --publish --json)
published_code=$?
set -e
test "$published_code" -eq 1  # the review completed; the candidate needs work
test "$(echo "$published" | json "['publication']['executed']")" = "True"
test "$(echo "$published" | json "['publication']['event']")" = "REQUEST_CHANGES"
test "$(echo "$published" | json "['publication']['posted_inline']")" = "1"

# Exactly two writes, both on the allowlist, and every read before the first.
python3 - "$api_log" <<'SEQUENCE'
import json
import sys

calls = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
observed = [f"{call['method']} {call['endpoint']}" for call in calls]
writes = [item for item in observed if not item.startswith("GET ")]
assert writes == [
    "POST repos/tserdeiro/consumer/pulls/128/reviews",
    "POST repos/tserdeiro/consumer/issues/128/comments",
], observed
first_write = observed.index(writes[0])
assert all(item.startswith("GET ") for item in observed[:first_write]), observed
# The re-verification is the last read before the first write.
assert max(index for index, item in enumerate(observed) if item == "GET pr-view/128") < first_write, observed
for call in calls:
    if call["method"] == "POST" and call["endpoint"].endswith("/reviews"):
        # An empty body is a 422 from the real API, and a review without
        # `commit_id` anchors to whatever the head is when the request arrives.
        assert str(call["body"].get("body") or "").strip(), call
        assert call["body"].get("commit_id"), call
    event = str((call.get("body") or {}).get("event", "")).upper()
    assert event != "APPROVE", call
    assert call["method"] in ("GET", "POST"), call
SEQUENCE

# The summary carries the per-candidate marker and says what the verdict is not.
python3 - "$api_log" <<'SUMMARY'
import json
import sys

calls = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
summary = next(call for call in calls if call["endpoint"].endswith("/issues/128/comments") and call["method"] == "POST")
body = summary["body"]["body"]
assert "speckit-code-review:summary:" in body, body[:200]
assert "not an approval" in body, body[:200]
SUMMARY

test -f "$session/publication-result.json"
test "$(python3 -c "import json;print(json.load(open('$session/session.json'))['published'])")" = "True"

# -- a second publication of the same candidate is refused ----------------------

session=$(open_review)
write_findings "$session"
rm -f "$api_log"
set +e
duplicate=$(run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --publish --json 2>/dev/null)
duplicate_code=$?
set -e
test "$duplicate_code" -eq 2
echo "$duplicate" | grep -q "publish_already_published"
test -z "$(api_writes)"

# -- drift publishes nothing ----------------------------------------------------

session=$(open_review)
write_findings "$session"
git -C "$consumer_root" switch --quiet feature
printf 'moved = 1\n' >>"$consumer_root/src/module.py"
git -C "$consumer_root" add --all
git -C "$consumer_root" commit --quiet -m "the head moved after the review"
moved_head=$(git -C "$consumer_root" rev-parse HEAD)
git -C "$consumer_root" switch --quiet main
write_gh_state "$moved_head"
rm -f "$api_log"
set +e
drifted=$(run review --root "$consumer_root" --findings "$session/findings.json" --session "$session" --publish --json 2>/dev/null)
drift_code=$?
set -e
test "$drift_code" -eq 8
echo "$drifted" | grep -q "drift_head"
test -z "$(api_writes)"

echo "publication conformance passed (against the repository's fake gh)"
echo
echo "Remote acceptance is a separate, human, explicitly authorized step:"
echo "  1. open a draft pull request on a repository you own"
echo "  2. run: review <pr> --findings <file> --session <session> --publish"
echo "  3. confirm on GitHub that exactly one review and one summary comment appeared,"
echo "     that neither is an approval, and that nothing was edited or deleted"
