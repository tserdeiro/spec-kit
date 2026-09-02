#!/usr/bin/env bash
set -euo pipefail

publish="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/publish.sh"
loop="$(sed -n '/release_needs_create=()/,/^done$/p' "$publish")"
build_line="$(grep -n 'build-release.sh "\$tag"' <<<"$loop" | cut -d: -f1)"
digest_line="$(grep -n 'digest_args+=' <<<"$loop" | cut -d: -f1)"
release_line="$(grep -n 'release_has_assets "\$tag"' <<<"$loop" | cut -d: -f1)"

[ -n "$build_line" ] && [ -n "$digest_line" ] && [ -n "$release_line" ]
[ "$build_line" -lt "$release_line" ] && [ "$digest_line" -lt "$release_line" ]
echo "publish retry keeps extension digests independent of remote release state"
