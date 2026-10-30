"""The Minting page a Librarian or Teacher downloads, with the address and a new key filled
in (ADR-0002 addendum, lib-ers): the Teacher never types either."""

import json
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from page_scripts import assert_scripts_parse

from library_assistant.access import (
    account_for_registration_key,
    connect,
    get_clock,
    get_db,
    issue_registration_key,
)
from library_assistant.app import app
from library_assistant.minting_page import (
    CONFIG_PLACEHOLDER,
    PAGE_PATH,
    download_filename,
    filled_minting_page,
)
from library_assistant.staff import create_account

# Far in the future on purpose: the staff session cookie's expiry is compared with the
# real clock by the HTTP client.
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)
CONFIG_RE = re.compile(
    r'<script type="application/json" id="install-config">(.*?)</script>', re.DOTALL
)


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def accounts(db):
    return {
        role: create_account(db, f"demo-{role}", "correct horse", role)
        for role in ("librarian", "teacher", "counselor")
    }


@pytest.fixture
def client(db, accounts):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: NOW
    try:
        yield TestClient(app, base_url="http://192.0.2.10:8000")
    finally:
        app.dependency_overrides.clear()


def _sign_in(client: TestClient, role: str) -> None:
    response = client.post(
        "/staff/login",
        data={"username": f"demo-{role}", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _config(page: str) -> dict:
    return json.loads(CONFIG_RE.search(page).group(1))


def test_librarian_downloads_a_teachers_page_with_address_and_new_key(
    client, db, accounts
):
    old_key = issue_registration_key(db, accounts["teacher"], NOW)
    _sign_in(client, "librarian")

    response = client.post(f"/staff/accounts/{accounts['teacher']}/minting-page")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="demo-teacher-minting-page.html"'
    )
    assert response.headers["cache-control"] == "no-store"
    config = _config(response.text)
    assert config["assistant_url"] == "http://192.0.2.10:8000"
    assert config["username"] == "demo-teacher"
    # The built-in key registers as the Teacher; the one it replaced no longer does.
    assert (
        account_for_registration_key(db, config["registration_key"])
        == (accounts["teacher"])
    )
    assert account_for_registration_key(db, old_key) is None


def test_teacher_downloads_their_own_page(client, db, accounts):
    _sign_in(client, "teacher")
    response = client.post("/staff/minting-page")
    assert response.status_code == 200
    key = _config(response.text)["registration_key"]
    assert account_for_registration_key(db, key) == accounts["teacher"]


def test_counselor_gets_no_minting_page(client, accounts):
    _sign_in(client, "counselor")
    assert client.post("/staff/minting-page").status_code == 403
    assert "Download my Minting page" not in client.get("/staff").text


def test_librarian_cannot_download_a_page_for_a_counselor(client, accounts):
    _sign_in(client, "librarian")
    response = client.post(f"/staff/accounts/{accounts['counselor']}/minting-page")
    assert response.status_code == 400


def test_teacher_cannot_download_another_accounts_page(client, accounts):
    _sign_in(client, "teacher")
    response = client.post(
        f"/staff/accounts/{accounts['librarian']}/minting-page", follow_redirects=False
    )
    assert response.status_code == 403


def test_minting_buttons_appear_where_staff_look(client, accounts):
    _sign_in(client, "teacher")
    assert "Download my Minting page" in client.get("/staff").text
    _sign_in(client, "librarian")
    keys = client.get("/staff/keys").text
    assert f"/staff/accounts/{accounts['teacher']}/minting-page" in keys
    assert f"/staff/accounts/{accounts['counselor']}/minting-page" not in keys


def test_downloaded_page_is_the_shipped_page_but_for_its_config():
    """Only the install-config block differs, so the page can be checked against the repo."""
    shipped = PAGE_PATH.read_text(encoding="utf-8")
    filled = filled_minting_page("http://192.0.2.10:8000/", "demo-teacher", "k")
    assert CONFIG_PLACEHOLDER in shipped
    assert CONFIG_RE.sub("", filled) == CONFIG_RE.sub("", shipped)
    assert _config(filled)["assistant_url"] == "http://192.0.2.10:8000"


def test_config_cannot_break_out_of_its_script_element():
    filled = filled_minting_page("http://x", "</script><b>&", "k")
    block = CONFIG_RE.search(filled).group(1)
    assert "<" not in block and ">" not in block and "&" not in block
    assert json.loads(block)["username"] == "</script><b>&"


def test_download_filename_keeps_to_safe_characters():
    assert download_filename("demo-teacher") == "demo-teacher-minting-page.html"
    assert download_filename('a "b"/c') == "a_b_c-minting-page.html"


@pytest.mark.parametrize(
    "path", ["/staff", "/staff/live", "/staff/flags", "/staff/keys", "/staff/settings"]
)
def test_staff_page_scripts_parse(client, accounts, path):
    _sign_in(client, "librarian")
    response = client.get(path)
    assert response.status_code == 200
    assert_scripts_parse(response.text)


def test_downloaded_minting_page_scripts_parse():
    assert_scripts_parse(filled_minting_page("http://192.0.2.10:8000", "t", "k"))


def test_downloaded_page_defaults_the_stop_time_to_the_school_day_end():
    filled = filled_minting_page("http://192.0.2.10:8000", "t", "k", "15:15")
    assert _config(filled)["school_day_end"] == "15:15"
    assert "school_day_end" not in _config(filled_minting_page("http://x", "t", "k"))
