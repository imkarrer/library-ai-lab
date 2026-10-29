"""The shared palette and stylesheet: one palette for the assistant's pages, the printed
sheets, and the Marp handout, fetched from nowhere but the Install (ADR-0006)."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from library_assistant.app import app
from library_assistant.mint import mint_cards, qr_sheet_html, roster_sheet_html
from library_assistant.routers.about import ABOUT_PATH
from library_assistant.routers.session import CHAT_PAGE_HTML
from library_assistant.staff import PAGE_HTML
from library_assistant.theme import STATIC_DIR, THEME_PATH, theme_css

REPO = Path(__file__).resolve().parent.parent
LINK = f'<link rel="stylesheet" href="{THEME_PATH}">'


def test_stylesheet_needs_no_session_and_carries_the_palette():
    response = TestClient(app).get(THEME_PATH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--green:" in response.text
    assert ".alarm" in response.text


def test_stylesheet_fetches_nothing():
    """No web font, no remote image, no @import: an Install reaches only the intranet."""
    css = theme_css()
    assert "@import" not in css
    assert "url(" not in css
    assert not re.search(r"https?://", css)


def test_every_page_template_links_the_stylesheet():
    assert LINK in PAGE_HTML
    assert LINK in CHAT_PAGE_HTML
    client = TestClient(app)
    assert LINK in client.get(ABOUT_PATH).text
    assert LINK in client.get("/card").text


def test_page_templates_set_no_colours_of_their_own():
    """Colours live in palette.css; a template that hard-codes one drifts from it."""
    for template in (PAGE_HTML, CHAT_PAGE_HTML, TestClient(app).get(ABOUT_PATH).text):
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", template)


def test_printed_sheets_embed_the_palette_instead_of_linking_it():
    """The sheets are opened from the Teacher's disk, never from the assistant."""
    expires = datetime.now(UTC) + timedelta(hours=8)
    cards = mint_cards(2, "Period 3", expires).cards
    for sheet in (
        qr_sheet_html(cards, "Period 3", base_url="http://intranet"),
        roster_sheet_html(cards, "Period 3", datetime.now(UTC), expires),
    ):
        assert "--green:" in sheet
        assert "<link" not in sheet


def test_handout_uses_the_shared_palette():
    marprc = (REPO / "docs/handout/.marprc.yml").read_text()
    assert "library_assistant/static/palette.css" in marprc
    assert (
        (STATIC_DIR / "palette.css")
        .read_text()
        .startswith("/* @theme library-palette */")
    )
    assert (
        "@import 'library-palette';" in (REPO / "docs/handout/handout.css").read_text()
    )
