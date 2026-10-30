"""The shared palette and stylesheet: one palette for the assistant's pages, the printed
sheets, and the Marp handout, fetched from nowhere but the Install (ADR-0006)."""

import importlib.util
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
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


def test_handout_and_pages_share_one_components_sheet():
    """Headings, tables, callouts, and chips look the same on a staff page and in the
    printed handout: one file, served in /library.css and imported by the Marp theme."""
    components = (STATIC_DIR / "components.css").read_text()
    assert components.startswith("/* @theme library-components */")
    marprc = (REPO / "docs/handout/.marprc.yml").read_text()
    assert "library_assistant/static/components.css" in marprc
    handout = (REPO / "docs/handout/handout.css").read_text()
    assert "@import 'library-components';" in handout
    served = TestClient(app).get("/library.css").text
    assert components in served
    assert served.index(components) < served.index("/* The staff top bar")
    # Colour stays in the palette: the shared sheet names tokens, not hex values, apart
    # from white text on a filled chip.
    assert set(re.findall(r"#[0-9a-fA-F]{3,6}\b", components)) <= {"#fff"}


def test_demo_deck_shares_the_handouts_palette_and_look():
    """The deck that leads into the demo looks like the handout and the app's pages."""
    marprc = (REPO / "docs/handout/.marprc.yml").read_text()
    assert "./deck.css" in marprc
    deck_css = (REPO / "docs/handout/deck.css").read_text()
    assert deck_css.startswith("/* @theme deck */")
    assert "@import 'library-palette';" in deck_css
    assert "@import 'library-components';" in deck_css
    assert "theme: deck" in (REPO / "docs/handout/demo-deck.md").read_text()


def test_demo_deck_introduces_the_cast_the_stack_seeds():
    """`./stack seed` and the deck's "Meet the cast" slide name the same people."""
    spec = importlib.util.spec_from_file_location("stack", REPO / "scripts/stack.py")
    stack = importlib.util.module_from_spec(spec)
    sys.modules["stack"] = stack  # @dataclass looks its module up here
    spec.loader.exec_module(stack)
    deck = (REPO / "docs/handout/demo-deck.md").read_text()
    for persona in stack.DEMO_CAST:
        assert persona.username.startswith(f"{persona.role}.")
        assert persona.name in deck and f"<code>{persona.username}</code>" in deck
    flat = " ".join(deck.split())
    for number, student in enumerate(stack.DEMO_STUDENTS, start=1):
        assert f"<b>{number}</b>{student}" in flat


@pytest.mark.parametrize("doc", ["it-network-request.md", "it-https-rollout.md"])
def test_the_it_sheets_are_built_with_the_handouts_look(doc):
    """The sheets for district IT are part of the Marp build (docs/handout/Makefile)."""
    source = (REPO / "docs/templates" / doc).read_text()
    assert source.startswith("---\nmarp: true\ntheme: handout\n")
    assert f"../templates/{doc}" in (REPO / "docs/handout/Makefile").read_text()


def test_stylesheet_is_revalidated_so_an_update_shows_at_once():
    response = TestClient(app).get("/library.css")
    assert response.headers["cache-control"] == "no-cache"
