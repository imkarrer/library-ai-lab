"""The assistant's one stylesheet, `/library.css`: the shared palette (static/palette.css)
and shared look (static/components.css), both of which the Marp handout imports too,
followed by the page styles (static/library.css).

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
FAVICON_PATH = "/favicon.svg"
ANSWER_SCRIPT_PATH = "/answer.js"
# Goes in every page's <head>.
THEME_LINK = (
    f'<link rel="stylesheet" href="{THEME_PATH}">\n'
    f'<link rel="icon" href="{FAVICON_PATH}" type="image/svg+xml">'
)

router = APIRouter()


@functools.cache
def theme_css() -> str:
    return "\n".join(
        (STATIC_DIR / name).read_text(encoding="utf-8")
        for name in ("palette.css", "components.css", "library.css")
    )


@router.get(ANSWER_SCRIPT_PATH)
def answer_script() -> Response:
    """Turns a model's Markdown into something a Student can read."""
    return Response(
        (STATIC_DIR / "answer.js").read_text(encoding="utf-8"),
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(FAVICON_PATH)
def favicon() -> Response:
    """The tab icon: a card in a book's pocket."""
    return Response(
        (STATIC_DIR / "favicon.svg").read_text(encoding="utf-8"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(THEME_PATH)
def stylesheet() -> Response:
    """The palette and page styles, in one response."""
    return Response(
        theme_css(),
        media_type="text/css",
        # Revalidated on every page: an updated Install shows its new look at once, not an
        # hour later. The sheet is small and served on the school network.
        headers={"Cache-Control": "no-cache"},
    )
