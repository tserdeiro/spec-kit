#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
extension_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

if [ "$#" -ne 1 ]; then
  echo "Spec Kit commit-msg requires exactly one Git message file; repair the hook command and retry" >&2
  exit 4
fi
if [ ! -f "$extension_root/src/spec_kit_code_review/commit_msg.py" ]; then
  echo "Spec Kit commit-msg runtime is incomplete; reinstall the code-review extension and retry" >&2
  exit 4
fi

if consumer_root=$(git rev-parse --show-toplevel 2>/dev/null); then
  :
else
  consumer_root=$(pwd -P)
fi
venv_python="$consumer_root/.venv/bin/python"
if [ -e "$venv_python" ]; then
  if [ ! -f "$venv_python" ] || [ ! -x "$venv_python" ]; then
    echo "Spec Kit commit-msg cannot execute $venv_python; repair or remove it, then retry" >&2
    exit 4
  fi
  interpreter="$venv_python"
else
  interpreter=$(command -v python3 2>/dev/null || true)
  if [ -z "$interpreter" ]; then
    echo "Spec Kit commit-msg needs Python 3.11+; install python3 or create .venv/bin/python, then retry" >&2
    exit 4
  fi
fi

if ! "$interpreter" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  echo "Spec Kit commit-msg needs a working Python 3.11+ interpreter; repair $interpreter and retry" >&2
  exit 4
fi

export PYTHONPATH="$extension_root/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$interpreter" -m spec_kit_code_review.commit_msg "$1"
