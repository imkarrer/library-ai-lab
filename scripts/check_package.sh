#!/usr/bin/env bash
# The package that ships starts with nothing but its own store paths: no flox activate, no
# PYTHONPATH, an empty environment. Run after `flox build library-assistant`.
set -euo pipefail
cd "$(dirname "$0")/.."

app="$(readlink result-library-assistant)/bin/library-assistant"
work="$(mktemp -d)"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"

(cd "$work" && exec env -i HOME="$work" PATH=/usr/bin:/bin \
  LIBRARY_ASSISTANT_HOST=127.0.0.1 LIBRARY_ASSISTANT_PORT="$port" "$app" >"$work/log" 2>&1) &
pid=$!
trap 'kill "$pid" 2>/dev/null || true; rm -rf "$work"' EXIT

for _ in $(seq 1 60); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/about")" = 200 ]; then
    echo "check-package: the built package serves /about."
    exit 0
  fi
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.5
done
echo "check-package: the built package did not start:" >&2
cat "$work/log" >&2
exit 1
