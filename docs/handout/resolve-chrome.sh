#!/usr/bin/env bash
# Print a Chrome/Chromium path Marp can launch.
#
# Prefer a browser this Flox env ships (Linux chromium, Darwin google-chrome),
# then a usable CHROME_PATH, then well-known app bundles. Always resolve to a
# physical path: Marp CLI treats anything under /mnt/<drive>/ as Windows Chrome
# and rewrites file:// URLs to \\wsl.localhost\… which then 404s.
set -euo pipefail

is_wsl_drive_path() {
  case "$1" in
    /mnt/[a-z]/* | /mnt/[A-Z]/*) return 0 ;;
    *) return 1 ;;
  esac
}

physical() {
  local p="$1" r=""
  if r="$(realpath "$p" 2>/dev/null)" && [ -x "$r" ]; then
    printf '%s\n' "$r"
    return 0
  fi
  if r="$(readlink -f "$p" 2>/dev/null)" && [ -x "$r" ]; then
    printf '%s\n' "$r"
    return 0
  fi
  printf '%s\n' "$(cd "$(dirname "$p")" && pwd -P)/$(basename "$p")"
}

usable() {
  [ -n "${1:-}" ] && [ -x "$1" ] && ! is_wsl_drive_path "$1"
}

pick=""
if [ -n "${FLOX_ENV:-}" ]; then
  for name in chromium google-chrome-stable google-chrome google-chrome-beta; do
    if usable "${FLOX_ENV}/bin/${name}"; then
      pick="${FLOX_ENV}/bin/${name}"
      break
    fi
  done
fi

if [ -z "$pick" ] && usable "${CHROME_PATH:-}"; then
  pick="${CHROME_PATH}"
fi

if [ -z "$pick" ]; then
  candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
  )
  for cmd in google-chrome-stable google-chrome chromium chromium-browser; do
    if c="$(command -v "$cmd" 2>/dev/null)"; then
      candidates+=("$c")
    fi
  done
  for c in "${candidates[@]}"; do
    if usable "$c"; then
      pick="$c"
      break
    fi
  done
fi

if [ -z "$pick" ]; then
  echo "resolve-chrome: no Chrome/Chromium executable found" >&2
  exit 1
fi

physical "$pick"
