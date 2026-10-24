#!/usr/bin/env bash
# The gate: what CI runs and what bead-loop runs on a worktree. Run inside the flox env:
#   flox activate -- bash scripts/check.sh
# Add each new check here so CI and the loop pick it up together.
set -euo pipefail
cd "$(dirname "$0")/.."

ruff check .
ruff format --check .
pytest
