#!/usr/bin/env bash
set -euo pipefail

required_files=(AGENTS.md PLANS.md .env.example)
for f in "${required_files[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: required file missing: $f"
    exit 1
  fi
done

if command -v rg >/dev/null 2>&1; then
  search_cmd=(rg -n "OPENAI_API_KEY" .env.example)
else
  search_cmd=(grep -n "OPENAI_API_KEY" .env.example)
fi

if "${search_cmd[@]}" > /tmp/openai_key_hits.txt; then
  echo "ERROR: .env.example should be DeepSeek-only; remove OPENAI_API_KEY"
  cat /tmp/openai_key_hits.txt
  exit 1
fi

echo "OK: repository contracts passed"
