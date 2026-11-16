#!/usr/bin/env bash
# Fetches the demo models into the Nix store, once, online (ADR-0006's model exception).
# Every file is pinned by digest in models/pins, so a changed or truncated download fails.
#
#   bash scripts/fetch_models.sh                about 17 GB from the Ollama registry
#   bash scripts/fetch_models.sh --from-ollama  files already pulled into ~/.ollama/models
#                                               first, then download only what is missing
#
# Runs outside flox: the environment that installs the models can't activate before they
# are here. Re-running fetches nothing that is already in the store.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
bin="$(dirname "$(command -v nix || echo /nix/var/nix/profiles/default/bin/nix)")"
nix() { "$bin/nix" --extra-experimental-features 'nix-command flakes' "$@"; }
models="$here/models#packages.aarch64-darwin"

if [ "${1:-}" = "--from-ollama" ]; then
  src="${OLLAMA_MODELS:-$HOME/.ollama/models}/blobs"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  # A file added under the name the derivation fetches to lands on its store path, as long
  # as its bytes match the digest; a file that doesn't is added elsewhere and fetched.
  for hex in $(nix eval --raw "$models.default.blobs" \
    --apply 'bs: builtins.concatStringsSep " " (map (b: builtins.substring 7 64 b.digest) bs)'); do
    [ -f "$src/sha256-$hex" ] || continue
    ln -f "$src/sha256-$hex" "$tmp/ollama-blob-$hex" 2>/dev/null ||
      cp "$src/sha256-$hex" "$tmp/ollama-blob-$hex"
    "$bin/nix-store" --add-fixed sha256 "$tmp/ollama-blob-$hex" >/dev/null
    rm -f "$tmp/ollama-blob-$hex"
  done
fi

nix build "$models.online" --no-link --print-out-paths
echo "Models are in the store; activation builds them without a network." >&2
