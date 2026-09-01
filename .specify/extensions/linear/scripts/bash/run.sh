#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
extension_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

if [ ! -f "$extension_root/pyproject.toml" ]; then
  echo "spec-kit-linear runtime is incomplete: pyproject.toml is missing" >&2
  exit 4
fi

export PYTHONPATH="$extension_root/src${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --frozen --offline --project "$extension_root" python -m spec_kit_linear.cli "$@"
