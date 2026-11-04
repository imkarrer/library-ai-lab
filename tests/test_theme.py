"""The shared palette and stylesheet: one palette for the assistant's pages, the printed
sheets, and the Marp handout, fetched from nowhere but the Install (ADR-0006)."""

import importlib.util
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from library_assistant.alarm_banner import ALARM_SCRIPT
from library_assistant.app import app
from library_assistant.mint import mint_cards, qr_sheet_html, roster_sheet_html
from library_assistant.routers.about import ABOUT_PATH
from library_assistant.routers.session import BANNER_TEXT, CHAT_PAGE_HTML
from library_assistant.staff import PAGE_HTML
from library_assistant.supportive_replies import DEFAULT_REPLY_TEMPLATES
from library_assistant.theme import FAVICON_PATH, STATIC_DIR, THEME_PATH, theme_css

REPO = Path(__file__).resolve().parent.parent
LINK = f'<link rel="stylesheet" href="{THEME_PATH}">'


def test_the_favicon_needs_no_session_and_fetches_nothing():
    response = TestClient(app).get(FAVICON_PATH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "href" not in response.text


@pytest.mark.parametrize("path", ["/about", "/staff/login", "/staff/setup"])
def test_a_page_shows_the_favicon(path):
    response = TestClient(app, client=("127.0.0.1", 50000)).get(path)
    assert f'<link rel="icon" href="{FAVICON_PATH}"' in response.text


@pytest.mark.parametrize("page", [CHAT_PAGE_HTML, PAGE_HTML])
def test_student_and_staff_pages_link_the_favicon(page):
    assert f'<link rel="icon" href="{FAVICON_PATH}"' in page


def test_the_tab_gets_its_icon_back_after_the_last_alarm():
    assert "open.size ? redDot() : restingIcon" in ALARM_SCRIPT


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


def test_talk_deck_wears_the_flox_theme_and_fetches_nothing():
    """The Planet Nix deck uses the Flox theme, with Geist inlined rather than fetched, so
    a render needs no network and check-overflow.sh always measures the same font."""
    handout = REPO / "docs/handout"
    marprc = (handout / ".marprc.yml").read_text()
    for theme in ("./build/geist.css", "./flox/flox.css", "./flox/planet-nix.css"):
        assert theme in marprc
    flox = (handout / "flox/flox.css").read_text()
    deck_theme = (handout / "flox/planet-nix.css").read_text()
    assert flox.startswith("/* @theme flox */")
    assert deck_theme.startswith("/* @theme planet-nix */")
    assert "@import 'geist';" in flox
    assert "@import 'flox';" in deck_theme
    for css in (flox, deck_theme):
        assert "url(" not in css
        assert not re.search(r"https?://", css)
    deck = (handout / "planet-nix-deck.md").read_text()
    assert "theme: planet-nix" in deck
    assert "I work at Flox" not in deck


def _embed_fonts(tmp_path, fonts):
    env_dir = tmp_path / "env"
    woff2 = env_dir / "share/fonts/woff2"
    woff2.mkdir(parents=True)
    for name in fonts:
        (woff2 / name).write_bytes(b"wOF2" + name.encode())
    out = tmp_path / "build/geist.css"
    result = subprocess.run(
        [str(REPO / "docs/handout/flox/embed-fonts.sh"), str(out)],
        env={**os.environ, "FLOX_ENV": str(env_dir)},
        capture_output=True,
        text=True,
        check=False,
    )
    return result, out


def test_embed_fonts_inlines_both_geist_families(tmp_path):
    result, out = _embed_fonts(tmp_path, ["Geist[wght].woff2", "GeistMono[wght].woff2"])
    assert result.returncode == 0, result.stderr
    css = out.read_text()
    assert css.startswith("/* @theme geist */")
    assert "font-family: 'Geist';" in css
    assert "font-family: 'Geist Mono';" in css
    assert css.count("url(data:font/woff2;base64,") == 2
    assert not re.search(r"https?://", css)


def test_embed_fonts_fails_and_writes_nothing_when_a_font_is_missing(tmp_path):
    result, out = _embed_fonts(tmp_path, ["Geist[wght].woff2"])
    assert result.returncode != 0
    assert "GeistMono[wght].woff2 not found" in result.stderr
    assert not out.exists()


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


@pytest.mark.parametrize("lesson", range(1, 7))
def test_each_lesson_has_a_deck_and_a_handout_in_the_build(lesson):
    """A teacher leads from the deck, and each student keeps the handout."""
    folder = REPO / "docs/curriculum"
    deck = (folder / f"lesson-{lesson}-deck.md").read_text()
    handout = (folder / f"lesson-{lesson}-handout.md").read_text()
    assert deck.startswith("---\nmarp: true\ntheme: deck\n")
    assert handout.startswith("---\nmarp: true\ntheme: handout\n")
    assert f"Lesson {lesson}" in deck and f"Lesson {lesson}" in handout
    assert "../curriculum/lesson-*.md" in (REPO / "docs/handout/Makefile").read_text()


@pytest.mark.parametrize("doc", ["lesson-1-deck.md", "lesson-1-handout.md"])
def test_lesson_one_quotes_the_banner_word_for_word(doc):
    assert BANNER_TEXT in (REPO / "docs/curriculum" / doc).read_text()


@pytest.mark.parametrize("doc", ["lesson-4-deck.md", "lesson-4-handout.md"])
def test_lesson_four_gives_the_numbers_the_supportive_replies_give(doc):
    text = (REPO / "docs/curriculum" / doc).read_text()
    for number in ("988", "1-800-422-4453", "911"):
        assert number in " ".join(DEFAULT_REPLY_TEMPLATES.values())
        assert number in text


def test_the_unit_is_not_written_for_one_age():
    for doc in (REPO / "docs/curriculum").glob("*.md"):
        text = doc.read_text().lower()
        assert "grades 6" not in text and "middle schoolers" not in text


def test_stylesheet_is_revalidated_so_an_update_shows_at_once():
    response = TestClient(app).get("/library.css")
    assert response.headers["cache-control"] == "no-cache"


def test_code_has_a_named_font_on_every_page():
    """Left to the browser, monospace differs by machine and moves printed pages."""
    components = (STATIC_DIR / "components.css").read_text()
    assert "code, pre, kbd, samp {\n  font-family: var(--font-mono);" in components
    assert "--font-mono:" in (STATIC_DIR / "palette.css").read_text()
