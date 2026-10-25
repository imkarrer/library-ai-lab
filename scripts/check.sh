#!/usr/bin/env bash
# The gate: what CI runs and what bead-loop runs on a worktree. Run inside the flox env:
#   flox activate -- bash scripts/check.sh
# Add each new check here so CI and the loop pick it up together.
set -euo pipefail
cd "$(dirname "$0")/.."

# ruff's EXE001 (shebang on a non-executable file) is skipped on WSL, where file modes are
# unreliable, so it only ever failed in CI. Check the mode git will commit instead.
not_executable=$(git ls-files -s | while read -r mode _ _ path; do
  if [ "$mode" = 100644 ] && [ "$(head -c 2 "$path" 2>/dev/null)" = "#!" ]; then
    echo "$path"
  fi
done)
if [ -n "$not_executable" ]; then
  echo "Shebang but not executable in git (run: git update-index --chmod=+x <file>):" >&2
  echo "$not_executable" >&2
  exit 1
fi

ruff check .
ruff format --check .
python scripts/confidentiality.py
pytest -x tests/test_offline_minting.py
