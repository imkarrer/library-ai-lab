"""The Student's "What happens to what I type" page (lib-bns)."""

import re

from fastapi.testclient import TestClient

from library_assistant.app import app
from library_assistant.routers.about import ABOUT_PATH
from library_assistant.routers.session import CHAT_PAGE_HTML


def test_about_page_needs_no_session_and_is_not_cached():
    response = TestClient(app).get(ABOUT_PATH)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "What happens to what I type" in response.text


def test_about_page_covers_the_card_who_sees_purge_and_help():
    text = TestClient(app).get(ABOUT_PATH).text
    assert "never gets your name" in text
    assert "deleted at the end of the school day" in text
    assert "does not go to a company" in text
    assert "988" in text


def test_about_page_loads_nothing_from_outside_the_install():
    text = TestClient(app).get(ABOUT_PATH).text
    assert not re.search(r"(src|href)=\"(https?:)?//", text)
    assert "<script" not in text


def test_card_and_chat_pages_link_to_it():
    assert f'href="{ABOUT_PATH}"' in TestClient(app).get("/card").text
    assert f'href="{ABOUT_PATH}"' in CHAT_PAGE_HTML
