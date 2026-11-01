#!/usr/bin/env bash
# Fails if any commit it can see carries a Claude co-author trailer (AGENTS.md).
set -euo pipefail

found=$(git log -i -E --grep='^co-authored-by:.*(claude|anthropic)' --format='%h %s')
if [ -n "$found" ]; then
  echo "Claude co-author trailer on these commits:" >&2
  echo "$found" >&2
  exit 1
fi
