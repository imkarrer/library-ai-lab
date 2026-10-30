"""Every inline <script> a page serves must parse: one syntax error kills the whole script,
and the page then does nothing with no error a test would otherwise see (lib-y4j)."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

# Inline JavaScript only: JSON data blocks (type="application/json") are not scripts.
_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.DOTALL)


def inline_scripts(html: str) -> list[str]:
    return [
        body
        for attrs, body in _SCRIPT_RE.findall(html)
        if "application/json" not in attrs and body.strip()
    ]


def assert_scripts_parse(html: str) -> None:
    scripts = inline_scripts(html)
    assert scripts, "the page serves no inline script to check"
    with tempfile.TemporaryDirectory() as tmp:
        for number, body in enumerate(scripts):
            path = Path(tmp) / f"script-{number}.js"
            path.write_text(body, encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"script {number}:\n{result.stderr}"
