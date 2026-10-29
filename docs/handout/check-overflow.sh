#!/usr/bin/env bash
#
# Fails if any page's content runs past the bottom of its US Letter page, or is silently
# clipped inside a scroll container.
#
# Marp clips a page that is too long: the source looks fine, the preview looks fine, and the
# last paragraph of page 4 is simply not on the paper. Worth a headless browser to catch.
#
# Fonts are local stacks (palette.css), so the measurement is for this machine's fonts: run it
# on the machine that prints. Ported from imkarrer/flox-buildkite-plugin docs/talks.
#
# Usage: ./check-overflow.sh [handout.md]

set -euo pipefail

DOC="${1:-librarian-handout.md}"
cd "$(dirname "$0")"

if [ ! -f "$DOC" ]; then
  echo "check-overflow: no such document: $DOC" >&2
  exit 2
fi

if ! command -v marp >/dev/null 2>&1; then
  echo "check-overflow: marp not found; run inside 'flox activate'" >&2
  exit 2
fi

BROWSER="${CHROME_PATH:-}"
if [ -z "$BROWSER" ] || [ ! -x "$BROWSER" ]; then
  echo "check-overflow: no browser; set CHROME_PATH (the flox hook does this)" >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The bare template lays every page out at full size with none hidden, which is what makes
# them measurable in one pass.
marp --no-stdin --config-file .marprc.yml "$DOC" --template bare -o "$TMP/bare.html" >/dev/null 2>&1

cat >>"$TMP/bare.html" <<'PROBE'
<script>
  // Let layout settle. A timer rather than requestAnimationFrame because rAF does not
  // reliably fire under --virtual-time-budget.
  function afterLayout() {
    return new Promise(function (resolve) {
      setTimeout(resolve, 250);
    });
  }

  function measure() {
    var problems = [];
    // Each page is its own <svg><foreignObject><section>. If a section ever contains
    // another, the document was parsed wrong and every measurement is garbage.
    if (document.querySelector("section section")) return null;
    document.querySelectorAll("section").forEach(function (section, index) {
      var page = index + 1;
      var slack = 2; // sub-pixel layout noise
      if (section.scrollHeight > section.clientHeight + slack) {
        problems.push(
          "page " + page + ": content runs " +
          (section.scrollHeight - section.clientHeight) + "px past the page"
        );
      }
      // Anything with a non-visible overflow silently eats its own content.
      section.querySelectorAll("*").forEach(function (el) {
        if (getComputedStyle(el).overflow === "visible") return;
        if (el.scrollHeight > el.clientHeight + slack) {
          problems.push(
            "page " + page + ": ." + (el.className || el.tagName.toLowerCase()) +
            " clips " + (el.scrollHeight - el.clientHeight) + "px of its content"
          );
        }
      });
    });
    return problems;
  }

  function publish(text) {
    var out = document.createElement("div");
    out.id = "overflow-report";
    out.textContent = text;
    document.body.appendChild(out);
  }

  (document.fonts ? document.fonts.ready : Promise.resolve())
    .then(afterLayout)
    .then(function () {
      var problems = measure();
      if (problems === null) return "BADPARSE";
      return problems.length ? "FAIL\n" + problems.join("\n") : "OK";
    })
    .then(publish)
    .catch(function (err) { publish("ERROR\n" + err); });
</script>
PROBE

# A throwaway profile: sharing the default user-data-dir between runs lets a lingering
# instance return a half-parsed DOM, which looks like a layout bug.
"$BROWSER" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --hide-scrollbars \
  --no-first-run \
  --no-default-browser-check \
  --disable-extensions \
  --user-data-dir="$TMP/profile" \
  --virtual-time-budget=15000 \
  --dump-dom \
  "file://$TMP/bare.html" \
  >"$TMP/dom.html" 2>/dev/null

REPORT="$(
  python3 -I - "$TMP/dom.html" <<'PY'
import html, re, sys
dom = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r'<div id="overflow-report">(.*?)</div>', dom, re.S)
print(html.unescape(m.group(1)).strip() if m else "NOREPORT")
PY
)"

case "$REPORT" in
  OK)
    echo "check-overflow: every page fits."
    ;;
  NOREPORT)
    echo "check-overflow: probe did not run; could not measure pages." >&2
    exit 2
    ;;
  BADPARSE)
    echo "check-overflow: pages nested inside each other; the HTML parsed wrong." >&2
    exit 2
    ;;
  *)
    echo "check-overflow: $REPORT" >&2
    exit 1
    ;;
esac
