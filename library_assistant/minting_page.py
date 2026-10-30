"""The offline Minting page, filled in for one staff account (ADR-0002 addendum, lib-ers).

The page is the repo's `offline-minting.html` byte for byte except its install-config
block, which carries the assistant's address and that account's new Registration key, so
the Teacher never types either. Tokens are still made in the Teacher's browser and never
reach the assistant: this module only hands out the page.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PAGE_PATH = Path(__file__).resolve().parent.parent / "offline-minting.html"

# The empty block the shipped page carries; filled_minting_page replaces it.
CONFIG_PLACEHOLDER = '<script type="application/json" id="install-config">{}</script>'


def _script_safe_json(value: dict[str, str]) -> str:
    """JSON that cannot close its <script> element or open a comment inside it."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def filled_minting_page(
    assistant_url: str, username: str, registration_key: str
) -> str:
    page = PAGE_PATH.read_text(encoding="utf-8")
    if page.count(CONFIG_PLACEHOLDER) != 1:
        raise RuntimeError(f"{PAGE_PATH.name} has lost its install-config block")
    config = _script_safe_json(
        {
            "assistant_url": assistant_url.rstrip("/"),
            "username": username,
            "registration_key": registration_key,
        }
    )
    return page.replace(
        CONFIG_PLACEHOLDER,
        f'<script type="application/json" id="install-config">{config}</script>',
    )


def download_filename(username: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", username).strip("._") or "staff"
    return f"{stem}-minting-page.html"
