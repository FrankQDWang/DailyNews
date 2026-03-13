#!/usr/bin/env bash
set -euo pipefail

if rg -n "uv\\s+pip" . \
  --glob '!uv.lock' \
  --glob '!.venv/**' \
  --glob '!**/*.md' \
  --glob '!scripts/forbid_uv_pip.sh' \
  > /tmp/uv_pip_hits.txt; then
  echo "ERROR: Found forbidden 'uv pip' usage:"
  cat /tmp/uv_pip_hits.txt
  exit 1
fi

echo "OK: no 'uv pip' usage found."
