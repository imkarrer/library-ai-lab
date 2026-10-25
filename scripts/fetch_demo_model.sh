#!/usr/bin/env bash
# Fetches the demo model's GGUF, once, online (ADR-0006's one setup exception), into the
# state directory the model service reads from. Run on the presenter's machine before the
# demo, never by the running assistant:
#
#   flox activate -- bash scripts/fetch_demo_model.sh
#
# Re-running skips a file that already verifies.
set -euo pipefail

REPO="unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF"
FILE="Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
SHA256="6c997b8af17debdfb01d890214400ccbab00db6acc0ba8da5de1cc906c4774d0"
URL="https://huggingface.co/${REPO}/resolve/main/${FILE}"

dest_dir="${FLOX_ENV_CACHE:?run inside the flox environment (FLOX_ENV_CACHE unset)}/models"
dest="$dest_dir/$FILE"

verify() {
  echo "$SHA256  $1" | sha256sum --check --status
}

mkdir -p "$dest_dir"

if [ -f "$dest" ] && verify "$dest"; then
  echo "Already fetched and verified: $dest" >&2
  exit 0
fi

echo "Fetching $FILE (Apache-2.0, Qwen/Qwen3-30B-A3B-Instruct-2507) to $dest ..." >&2
curl --fail --location --continue-at - --output "$dest.part" "$URL"
mv "$dest.part" "$dest"

if ! verify "$dest"; then
  echo "sha256 mismatch for $dest; deleting it" >&2
  rm -f "$dest"
  exit 1
fi

echo "Verified: $dest" >&2
