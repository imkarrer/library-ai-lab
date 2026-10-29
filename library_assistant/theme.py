"""The assistant's one stylesheet, `/library.css`: the shared palette (static/palette.css,
which the Marp handout imports too) followed by the page styles (static/library.css).

Served by the assistant itself, like the chime: a page fetches nothing from past the
Install (ADR-0006). No Session is needed, because the Card and /about pages use it before
a Student signs in.
"""

from __future__ import annotations

import functools
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

STATIC_DIR = Path(__file__).parent / "static"
THEME_PATH = "/library.css"
# Goes in every page's <head>.
THEME_LINK = f'<link rel="stylesheet" href="{THEME_PATH}">'

router = APIRouter()


@functools.cache
def theme_css() -> str:
    return "\n".join(
        (STATIC_DIR / name).read_text(encoding="utf-8")
        for name in ("palette.css", "library.css")
    )


@router.get(THEME_PATH)
def stylesheet() -> Response:
    """The palette and page styles, in one response."""
    return Response(
        theme_css(),
        media_type="text/css",
        headers={"Cache-Control": "max-age=3600"},
    )
