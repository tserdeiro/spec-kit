#!/usr/bin/env bash
set -euo pipefail

package_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
repository_root=$(CDPATH= cd -- "$package_root/../.." && pwd -P)

temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/spec-kit-code-review-native.XXXXXX")
cleanup() { rm -rf "$temporary_root"; }
trap cleanup EXIT

base_path=${PATH}
git254=${SPECKIT_NATIVE_GIT254:-"$(command -v git || true)"}
git255=${SPECKIT_NATIVE_GIT255:-"$(command -v git || true)"}
manager_modules=${SPECKIT_NATIVE_MANAGER_NODE_MODULES:-}
python_source=${SPECKIT_NATIVE_PYTHON:-"$repository_root/.venv/bin/python3"}

version_of() {
  "$1" --version | sed -n 's/^git version //p' | head -1
}
require_git() {
  local executable=$1 expected=$2 variable_name=$3 observed
  if [ ! -x "$executable" ]; then
    echo "conformance requires Git $expected at $executable; set $variable_name" >&2
    exit 4
  fi
  observed=$(version_of "$executable")
  case "$observed" in
    "$expected".*) ;;
    *) echo "conformance requires Git $expected, found ${observed:-unreadable} at $executable" >&2; exit 4 ;;
  esac
  echo "Git $observed: $executable"
}
require_git "$git254" 2.54 SPECKIT_NATIVE_GIT254
require_git "$git255" 2.55 SPECKIT_NATIVE_GIT255

manager_install_hint="npm install --ignore-scripts --prefix ${TMPDIR:-/tmp}/spec-kit-native-managers husky@9.1.7 lefthook@2.1.12"
if [ -z "$manager_modules" ] || [ ! -d "$manager_modules" ]; then
  echo "conformance requires Husky 9.1.7 and Lefthook 2.1.12; set SPECKIT_NATIVE_MANAGER_NODE_MODULES or run '$manager_install_hint' in a disposable directory" >&2
  exit 4
fi
for manager in husky lefthook; do
  if [ ! -f "$manager_modules/$manager/package.json" ]; then
    echo "conformance requires Husky 9.1.7 and Lefthook 2.1.12 in $manager_modules; run '$manager_install_hint' in a disposable directory" >&2
    exit 4
  fi
  manager_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manager_modules/$manager/package.json" | head -1)
  case "$manager:$manager_version" in
    husky:9.1.7|lefthook:2.1.12) echo "$manager $manager_version: recorded fixture" ;;
    *) echo "conformance requires recorded $manager version (found ${manager_version:-unreadable})" >&2; exit 4 ;;
  esac
done

pinned_cli=$(sed -n 's/^  package_version: //p' "$repository_root/versions.lock.yml" | head -1)
specify_bin=$(command -v specify || true)
if [ -z "$pinned_cli" ] || [ -z "$specify_bin" ]; then
  echo "conformance requires the pinned specify-cli $pinned_cli on PATH" >&2
  exit 4
fi
if ! specify_output=$(specify version 2>/dev/null); then
  echo "conformance requires specify-cli $pinned_cli; specify version failed" >&2
  exit 4
fi
if [[ "$specify_output" != *"CLI Version    $pinned_cli"* ]]; then
  echo "conformance requires specify-cli $pinned_cli" >&2
  exit 4
fi
echo "Specify CLI $pinned_cli: $specify_bin"

if [ ! -x "$python_source" ] || ! "$python_source" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  echo "conformance requires Python 3.11+ at $python_source; set SPECKIT_NATIVE_PYTHON" >&2
  exit 4
fi
if ! command -v uv >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
  echo "conformance requires uv and Node.js on PATH for the installed extension and manager fixtures" >&2
  exit 4
fi
echo "Python: $("$python_source" --version 2>&1); Node: $(node --version); uv: $(uv --version)"

mkdir -p "$temporary_root/bin"
fake_ocr="$temporary_root/bin/ocr"
fake_gh="$temporary_root/bin/gh"
cp "$package_root/tests/support/fake_ocr.py" "$fake_ocr"
cp "$package_root/tests/support/fake_gh.py" "$fake_gh"
chmod +x "$fake_ocr" "$fake_gh"
gh_state="$temporary_root/fake-gh.json"
printf '%s\n' '{"auth":{"authenticated":true,"scopes":["repo"]},"user":"conformance","pull_requests":{}}' >"$gh_state"
tripwire_bin="$temporary_root/tripwire"
mkdir -p "$tripwire_bin"
for name in ocr gh specify curl ssh; do
  printf '%s\n' '#!/bin/sh' 'printf "%s\\n" "$(basename "$0")" >> "${SPECKIT_T004_TRIPWIRE_LOG:?}"' 'exit 97' >"$tripwire_bin/$name"
  chmod +x "$tripwire_bin/$name"
done

mode_of() {
  stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1"
}
count_lines() {
  if [ -f "$1" ]; then wc -l <"$1" | tr -d ' '; else printf '0'; fi
}
count_validators() {
  if [ -f "$1" ]; then grep -c -- '-m spec_kit_code_review.commit_msg' "$1" || true; else printf '0'; fi
}
git_env() {
  local git_bin=$1 repo=$2; shift 2
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null PATH="$(dirname -- "$git_bin"):$repo/node_modules/.bin:$base_path" "$git_bin" -C "$repo" "$@"
}

exercise() {
  local label=$1 git_bin=$2 manager=$3
  local repo="$temporary_root/${label} consumer" home="$temporary_root/home-$label"
  local installed_root manager_hook manager_log reject_marker validator_log tripwire_log
  local hooks_path dispatcher_digest dispatcher_mode manager_digest manager_mode path_before
  local before commit_code editor_script
  mkdir -p "$repo" "$home"
  echo "--- $label: $manager with $(version_of "$git_bin") ---"
  git_env "$git_bin" "$repo" init --quiet --initial-branch=main
  git_env "$git_bin" "$repo" config user.name Conformance
  git_env "$git_bin" "$repo" config user.email conformance@example.invalid
  git_env "$git_bin" "$repo" config commit.gpgsign false
  (cd "$repo" && HOME="$home" XDG_CONFIG_HOME="$home/config" PATH="$(dirname -- "$git_bin"):$base_path" specify init --here --force --ignore-agent-tools --integration codex >/dev/null)
  (cd "$repo" && HOME="$home" XDG_CONFIG_HOME="$home/config" PATH="$(dirname -- "$git_bin"):$base_path" specify extension add "$package_root" --dev >/dev/null)
  installed_root="$repo/.specify/extensions/code-review"
  for path in extension.yml scripts/bash/run.sh scripts/bash/commit-msg.sh src/spec_kit_code_review/commit_msg.py src/spec_kit_code_review/commit_policy.py; do
    test -f "$installed_root/$path"
  done
  test -x "$installed_root/scripts/bash/run.sh"
  if grep -R -F -- "$repository_root" "$installed_root" >/dev/null 2>&1; then
    echo "installed runtime references its source checkout" >&2
    return 1
  fi
  engine_digest=$(shasum -a 256 "$fake_ocr" | cut -d' ' -f1)
  case "$(uname -s)" in Darwin) platform_os=darwin ;; Linux) platform_os=linux ;; *) platform_os=$(uname -s | tr '[:upper:]' '[:lower:]') ;; esac
  case "$(uname -m)" in arm64|aarch64) platform_arch=arm64 ;; x86_64|amd64) platform_arch=amd64 ;; *) platform_arch=$(uname -m) ;; esac
  printf '%s\n' 'schema_version: "1.0"' '' 'extensions:' '  code-review:' '    id: code-review' '    version: 0.5.0' '    provenance: first-party-conformance' '    external_tools:' '      open_code_review:' '        version_string: "ocr version v1.8.3"' '        binaries:' "          $platform_os-$platform_arch: \"$engine_digest\"" >"$repo/versions.lock.yml"

  reject_marker="$repo/reject-manager"
  manager_log="$repo/manager.log"
  manager_hook="$repo/manager-hook.sh"
  printf '%s\n' '#!/bin/sh' "printf '%s\\n' \"\$1\" >> \"$manager_log\"" "if test -f \"$reject_marker\"; then echo 'consumer manager rejected the commit' >&2; exit 1; fi" >"$manager_hook"
  chmod +x "$manager_hook"
  case "$manager" in
    plain)
      hooks_path=$(git_env "$git_bin" "$repo" rev-parse --path-format=absolute --git-path hooks)
      printf '%s\n' '#!/bin/sh' "exec \"$manager_hook\" \"\$1\"" >"$hooks_path/commit-msg"
      chmod +x "$hooks_path/commit-msg"
      dispatcher_digest=$(shasum -a 256 "$hooks_path/commit-msg" | cut -d' ' -f1)
      dispatcher_mode=$(mode_of "$hooks_path/commit-msg")
      path_before=$(git_env "$git_bin" "$repo" config --get core.hooksPath || true)
      ;;
    husky)
      printf '%s\n' '{"name":"t004-husky-consumer"}' >"$repo/package.json"
      cp -R "$manager_modules" "$repo/node_modules"
      (cd "$repo" && HOME="$home" PATH="$repo/node_modules/.bin:$(dirname -- "$git_bin"):$base_path" node "$repo/node_modules/husky/bin.js" init >/dev/null)
      printf '%s\n' 'true' >"$repo/.husky/pre-commit"
      printf '%s\n' '#!/bin/sh' "exec \"$manager_hook\" \"\$1\"" >"$repo/.husky/commit-msg"
      chmod +x "$repo/.husky/commit-msg"
      dispatcher_digest=$(shasum -a 256 "$repo/.husky/_/commit-msg" | cut -d' ' -f1)
      dispatcher_mode=$(mode_of "$repo/.husky/_/commit-msg")
      manager_digest=$(shasum -a 256 "$repo/.husky/commit-msg" | cut -d' ' -f1)
      manager_mode=$(mode_of "$repo/.husky/commit-msg")
      path_before=$(git_env "$git_bin" "$repo" config --get core.hooksPath)
      ;;
    lefthook)
      printf '%s\n' '{"name":"t004-lefthook-consumer"}' >"$repo/package.json"
      cp -R "$manager_modules" "$repo/node_modules"
      printf '%s\n' 'commit-msg:' '  jobs:' '    - name: consumer manager' '      run: sh manager-hook.sh {1}' >"$repo/lefthook.yml"
      (cd "$repo" && PATH="$repo/node_modules/.bin:$(dirname -- "$git_bin"):$base_path" lefthook install >/dev/null)
      hooks_path=$(git_env "$git_bin" "$repo" rev-parse --path-format=absolute --git-path hooks)
      dispatcher_digest=$(shasum -a 256 "$hooks_path/commit-msg" | cut -d' ' -f1)
      dispatcher_mode=$(mode_of "$hooks_path/commit-msg")
      path_before=$(git_env "$git_bin" "$repo" config --get core.hooksPath || true)
      ;;
    *) echo "unknown manager fixture $manager" >&2; return 1 ;;
  esac

  run_doctor() {
    HOME="$home" XDG_CONFIG_HOME="$home/config" UV_CACHE_DIR="$temporary_root/uv-cache" UV_PYTHON="$python_source" UV_NO_DEV=1 UV_NO_SYNC=1 \
      SPECKIT_CODE_REVIEW_OCR_BIN="$fake_ocr" SPECKIT_CODE_REVIEW_GH_BIN="$fake_gh" SPECKIT_CODE_REVIEW_FAKE_GH_STATE="$gh_state" \
      SPECKIT_CODE_REVIEW_EVIDENCE_DIR="$temporary_root/evidence-$label" PATH="$(dirname -- "$git_bin"):$base_path" \
      "$installed_root/scripts/bash/run.sh" doctor --root "$repo" --fix --json
  }
  run_doctor
  run_doctor
  test "$(git_env "$git_bin" "$repo" config --get core.hooksPath || true)" = "$path_before"
  case "$manager" in
    plain) test "$(shasum -a 256 "$hooks_path/commit-msg" | cut -d' ' -f1)" = "$dispatcher_digest"; test "$(mode_of "$hooks_path/commit-msg")" = "$dispatcher_mode" ;;
    husky) test "$(shasum -a 256 "$repo/.husky/_/commit-msg" | cut -d' ' -f1)" = "$dispatcher_digest"; test "$(mode_of "$repo/.husky/_/commit-msg")" = "$dispatcher_mode"; test "$(shasum -a 256 "$repo/.husky/commit-msg" | cut -d' ' -f1)" = "$manager_digest"; test "$(mode_of "$repo/.husky/commit-msg")" = "$manager_mode" ;;
    lefthook) test "$(shasum -a 256 "$hooks_path/commit-msg" | cut -d' ' -f1)" = "$dispatcher_digest"; test "$(mode_of "$hooks_path/commit-msg")" = "$dispatcher_mode" ;;
  esac

  local config_commands config_events
  config_commands=$(git_env "$git_bin" "$repo" config --get-all hook.speckit-commit-message.command)
  config_events=$(git_env "$git_bin" "$repo" config --get-all hook.speckit-commit-message.event)
  test "$config_commands" = 'sh .specify/extensions/code-review/scripts/bash/commit-msg.sh'
  test "$config_events" = commit-msg
  test "$(git_env "$git_bin" "$repo" hook list -z --show-scope commit-msg | tr '\0' '\n' | grep -c 'speckit-commit-message')" -eq 1

  validator_log="$repo/validator.log"
  UV_CACHE_DIR="$temporary_root/uv-cache" uv venv --quiet --python "$python_source" "$repo/.venv"
  mv "$repo/.venv/bin/python" "$repo/.venv/bin/python-real"
  rm -f "$repo/.venv/bin/python3"
  ln -s python-real "$repo/.venv/bin/python3"
  printf '%s\n' '#!/bin/sh' "printf '%s\\n' \"\$*\" >> \"$validator_log\"" "exec \"$repo/.venv/bin/python-real\" \"\$@\"" >"$repo/.venv/bin/python"
  chmod +x "$repo/.venv/bin/python"
  tripwire_log="$repo/tripwire.log"
  export SPECKIT_T004_TRIPWIRE_LOG="$tripwire_log"
  local commit_path="$repo/node_modules/.bin:$tripwire_bin:$(dirname -- "$git_bin"):$base_path"
  git_commit() { GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null PATH="$commit_path" "$git_bin" -C "$repo" "$@"; }
  editor_script="$temporary_root/editor-$label.sh"

  printf '%s\n' baseline >"$repo/baseline.txt"
  git_commit add baseline.txt
  git_commit commit --quiet -m 'chore(core): baseline'
  test "$(count_validators "$validator_log")" -eq 1
  test "$(count_lines "$manager_log")" -eq 1

  printf '%s\n' change >"$repo/file.txt"
  git_commit add file.txt
  printf '%s\n' 'feat(core): file message' '' 'body' >"$repo/message file.txt"
  git_commit commit --quiet -F "$repo/message file.txt"
  test "$(count_validators "$validator_log")" -eq 2
  test "$(count_lines "$manager_log")" -eq 2

  printf '%s\n' invalid >"$repo/file-invalid.txt"
  git_commit add file-invalid.txt
  printf '%s\n' invalid >"$repo/bad message file.txt"
  before=$(git_env "$git_bin" "$repo" rev-parse HEAD)
  set +e
  git_commit commit --quiet -F "$repo/bad message file.txt"
  commit_code=$?
  set -e
  test "$commit_code" -ne 0
  test "$(git_env "$git_bin" "$repo" rev-parse HEAD)" = "$before"
  test "$(count_validators "$validator_log")" -eq 3
  test "$(count_lines "$manager_log")" -eq 3
  git_commit reset --quiet
  rm -f "$repo/file-invalid.txt"

  printf '%s\n' '#!/bin/sh' 'printf "%s\\n" "fix(core): editor message" > "$1"' >"$editor_script"
  chmod +x "$editor_script"
  GIT_EDITOR="$editor_script" git_commit commit --quiet --allow-empty
  test "$(count_validators "$validator_log")" -eq 4
  test "$(count_lines "$manager_log")" -eq 4

  printf '%s\n' '#!/bin/sh' 'printf "%s\\n" invalid > "$1"' >"$editor_script"
  before=$(git_env "$git_bin" "$repo" rev-parse HEAD)
  set +e
  GIT_EDITOR="$editor_script" git_commit commit --quiet --allow-empty
  commit_code=$?
  set -e
  test "$commit_code" -ne 0
  test "$(git_env "$git_bin" "$repo" rev-parse HEAD)" = "$before"
  test "$(count_validators "$validator_log")" -eq 5
  test "$(count_lines "$manager_log")" -eq 5

  printf '%s\n' invalid >"$repo/invalid.txt"
  git_commit add invalid.txt
  before=$(git_env "$git_bin" "$repo" rev-parse HEAD)
  set +e
  git_commit commit --quiet -m invalid
  commit_code=$?
  set -e
  test "$commit_code" -ne 0
  test "$(git_env "$git_bin" "$repo" rev-parse HEAD)" = "$before"
  test "$(count_validators "$validator_log")" -eq 6
  test "$(count_lines "$manager_log")" -eq 6
  git_commit reset --quiet
  rm -f "$repo/invalid.txt"

  touch "$reject_marker"
  printf '%s\n' blocked >"$repo/blocked.txt"
  git_commit add blocked.txt
  before=$(git_env "$git_bin" "$repo" rev-parse HEAD)
  set +e
  git_commit commit --quiet -m 'feat(core): manager rejection'
  commit_code=$?
  set -e
  test "$commit_code" -ne 0
  test "$(git_env "$git_bin" "$repo" rev-parse HEAD)" = "$before"
  test "$(count_validators "$validator_log")" -eq 7
  test "$(count_lines "$manager_log")" -eq 7
  rm -f "$reject_marker"
  git_commit reset --quiet
  rm -f "$repo/blocked.txt"

  printf '%s\n' accepted >"$repo/accepted.txt"
  git_commit add accepted.txt
  git_commit commit --quiet -m 'feat(core): accepted'
  test "$(count_validators "$validator_log")" -eq 8
  test "$(count_lines "$manager_log")" -eq 8
  test ! -s "$tripwire_log"
  test ! -e "$repo/.specify/agent-events.log"
  echo "$label $manager passed: eight validator calls, eight prior-hook calls, two fixes, manager bytes/modes preserved"
}

exercise git254-plain "$git254" plain
exercise git254-husky "$git254" husky
exercise git254-lefthook "$git254" lefthook
exercise git255-plain "$git255" plain
exercise git255-husky "$git255" husky
exercise git255-lefthook "$git255" lefthook

echo "native installed commit-msg conformance passed"
