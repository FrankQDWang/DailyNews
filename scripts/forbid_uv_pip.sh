#!/usr/bin/env bash
set -euo pipefail

if command -v rg >/dev/null 2>&1; then
  search_cmd=(
    rg -n "uv\\s+pip" .
    --glob '!uv.lock'
    --glob '!.venv/**'
    --glob '!**/*.md'
    --glob '!scripts/forbid_uv_pip.sh'
  )
else
  search_cmd=(
    grep -RInE "uv[[:space:]]+pip" .
    --exclude=uv.lock
    --exclude-dir=.venv
    --exclude=forbid_uv_pip.sh
    --exclude='*.md'
  )
fi

if "${search_cmd[@]}" > /tmp/uv_pip_hits_raw.txt; then
  grep -v "Enforce no uv pip" /tmp/uv_pip_hits_raw.txt > /tmp/uv_pip_hits.txt || true
fi

if [[ -s /tmp/uv_pip_hits.txt ]]; then
  echo "ERROR: Found forbidden 'uv pip' usage:"
  cat /tmp/uv_pip_hits.txt
  exit 1
fi

echo "OK: no 'uv pip' usage found."
