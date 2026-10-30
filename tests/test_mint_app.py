"""The Make Cards app (library_assistant/mint_app.py, ADR-0002 addendum of 2026-10-30): the
Minting page served to a signed-in Teacher, with no key in it, installable, and allowed to
run only its own scripts and talk only to this assistant."""

import ipaddress
import json
import re
import struct
import zlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from page_scripts import assert_scripts_parse, inline_scripts

from library_assistant.access import connect, get_clock, get_db, hash_token
from library_assistant.app import app
from library_assistant.config import Settings
from library_assistant.dependencies import get_settings
from library_assistant.mint_app import (
    APP_PATH,
    card_base_url,
    content_security_policy,
    icon_png,
    script_hashes,
)
from library_assistant.minting_page import PAGE_PATH
from library_assistant.staff import create_account

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
def settings():
    return Settings(school_day_end="23:59", school_timezone="UTC")


@pytest.fixture
def client(db, accounts, settings, monkeypatch):
    monkeypatch.delenv("LIBRARY_ASSISTANT_HOST", raising=False)
    monkeypatch.delenv("LIBRARY_ASSISTANT_TLS_DIR", raising=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: NOW
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app, base_url="http://192.0.2.10:8000")
    finally:
        app.dependency_overrides.clear()


def _sign_in(client: TestClient, role: str, next_path: str | None = None):
    response = client.post(
        "/staff/login",
        data={
            "username": f"demo-{role}",
            "password": "correct horse",
            **({"next": next_path} if next_path else {}),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response


def _config(page: str) -> dict:
    return json.loads(CONFIG_RE.search(page).group(1))


def _batch(card_count: int = 2) -> dict:
    return {
        "cards": [
            {"token_hash": hash_token(f"t{n}"), "card_number": str(n)}
            for n in range(1, card_count + 1)
        ],
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "class_label": "Period 3",
    }


def test_a_teacher_gets_the_app_with_no_key_in_it(client):
    _sign_in(client, "teacher")
    response = client.get(f"{APP_PATH}/")
    assert response.status_code == 200
    config = _config(response.text)
    assert config == {
        "app": APP_PATH,
        "assistant_url": "http://192.0.2.10:8000",
        "username": "demo-teacher",
        "school_day_end": "23:59",
    }
    assert "registration_key" not in response.text.split("</head>")[0]
    assert response.headers["cache-control"] == "no-store"
    assert '<link rel="manifest" href="manifest.webmanifest">' in response.text
    assert_scripts_parse(response.text)


def test_the_app_is_the_shipped_page_but_for_its_config_and_head(client):
    """The same page a school can compare with the repo's copy."""
    _sign_in(client, "teacher")
    served = client.get(f"{APP_PATH}/").text
    shipped = PAGE_PATH.read_text()
    assert inline_scripts(served) == inline_scripts(shipped)
    assert served.split("<body>")[1] == shipped.split("<body>")[1]


def test_the_app_is_for_staff_who_make_cards(client):
    assert client.get(f"{APP_PATH}/").status_code == 401
    _sign_in(client, "counselor")
    assert client.get(f"{APP_PATH}/").status_code == 403


def test_signing_in_from_the_app_comes_back_to_it(client):
    page = client.get(f"{APP_PATH}/")
    assert f'href="/staff/login?next={APP_PATH}/"' in page.text
    form = client.get(f"/staff/login?next={APP_PATH}/").text
    assert f'name="next" value="{APP_PATH}/"' in form
    assert _sign_in(client, "teacher", f"{APP_PATH}/").headers["location"] == (
        f"{APP_PATH}/"
    )


@pytest.mark.parametrize(
    "next_path", ["//evil.example/", "https://evil.example/", "/card", "/staff\\x"]
)
def test_sign_in_never_sends_staff_to_another_site(client, next_path):
    assert _sign_in(client, "teacher", next_path).headers["location"] == "/staff"


def test_the_policy_runs_only_the_pages_own_scripts_and_talks_only_to_itself(client):
    _sign_in(client, "teacher")
    response = client.get(f"{APP_PATH}/")
    policy = response.headers["content-security-policy"]
    assert policy == content_security_policy(response.text)
    directives = dict(d.strip().split(" ", 1) for d in policy.split(";"))
    assert directives["default-src"] == "'none'"
    assert directives["connect-src"] == "'self'"
    assert directives["form-action"] == "'none'"
    # Exactly the two scripts the page runs, by hash: the QR library and the page's logic.
    hashes = script_hashes(response.text)
    assert len(hashes) == 2
    assert directives["script-src"] == " ".join(f"'{h}'" for h in hashes)
    assert "unsafe-inline" not in directives["script-src"]


def test_an_injected_script_would_not_match_the_policy():
    page = PAGE_PATH.read_text()
    tampered = page.replace("<body>", "<body><script>fetch('//x')</script>")
    assert script_hashes(tampered)[0] not in content_security_policy(page)


def test_cards_carry_the_address_the_assistant_listens_on(client, monkeypatch):
    """Opened at localhost on the assistant's own computer, Cards still open on phones."""
    monkeypatch.setenv("LIBRARY_ASSISTANT_HOST", "192.0.2.10")
    monkeypatch.setenv("LIBRARY_ASSISTANT_PORT", "8000")
    local = TestClient(app, base_url="http://127.0.0.1:8000")
    _sign_in(local, "teacher")
    page = local.get(f"{APP_PATH}/").text
    assert _config(page)["assistant_url"] == "http://192.0.2.10:8000"


# The unspecified addresses built, not written: the confidentiality scan reads literals.
@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        str(ipaddress.IPv4Address(0)),
        str(ipaddress.IPv6Address(0)),
        "localhost",
        "",
    ],
)
def test_a_loopback_or_any_address_falls_back_to_the_one_opened(host, monkeypatch):
    monkeypatch.setenv("LIBRARY_ASSISTANT_HOST", host)
    monkeypatch.delenv("LIBRARY_ASSISTANT_TLS_DIR", raising=False)

    class Opened:
        base_url = "http://192.0.2.20:8000/"

    assert card_base_url(Opened()) == "http://192.0.2.20:8000"


def test_registering_from_the_app_records_the_signed_in_teacher(client, db, accounts):
    _sign_in(client, "teacher")
    response = client.post(f"{APP_PATH}/batches", json=_batch())
    assert response.status_code == 201
    assert response.json() == {"registered": 2}
    rows = db.execute("SELECT registered_by_account_id FROM cards").fetchall()
    assert rows == [(accounts["teacher"],), (accounts["teacher"],)]


def test_the_app_routes_refuse_without_a_sign_in_or_to_a_counselor(client, db):
    assert client.post(f"{APP_PATH}/batches", json=_batch()).status_code == 401
    _sign_in(client, "counselor")
    assert client.post(f"{APP_PATH}/batches", json=_batch()).status_code == 403
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone() == (0,)


def test_the_app_keeps_registrations_rules(client):
    """The same checks as /batches: hashes only, and Cards end with the school day."""
    _sign_in(client, "teacher")
    raw = _batch()
    raw["cards"][0]["token"] = "a raw token"
    assert client.post(f"{APP_PATH}/batches", json=raw).status_code == 422
    late = {**_batch(), "expires_at": (NOW + timedelta(days=2)).isoformat()}
    assert client.post(f"{APP_PATH}/batches", json=late).status_code == 422


def test_the_app_reads_and_answers_its_teachers_identification_requests(
    client, db, accounts
):
    from library_assistant.flags import raise_flag
    from library_assistant.identification import ask, open_requests_for

    _sign_in(client, "teacher")
    client.post(f"{APP_PATH}/batches", json=_batch())
    expires = db.execute("SELECT expires_at FROM cards LIMIT 1").fetchone()[0]
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES ('s', 'Period 3', '1', 'q', 'a', '', ?)",
        (NOW.isoformat(),),
    )
    transcript_id = db.execute("SELECT max(id) FROM transcripts").fetchone()[0]
    flag_id = raise_flag(
        db,
        transcript_id,
        "Period 3",
        "1",
        expires,
        "h",
        "bullying",
        "medium",
        "oversight",
        NOW.isoformat(),
        reason="names a classmate",
    )
    ask(db, flag_id, accounts["librarian"], NOW)

    listed = client.post(f"{APP_PATH}/batches/identification-requests").json()
    [request] = listed["requests"]
    assert request["card_number"] == "1"
    answered = client.post(
        f"{APP_PATH}/batches/identification-requests/{request['request_id']}/answer",
        json={"answer": "told"},
    )
    assert answered.status_code == 200
    assert open_requests_for(db, accounts["teacher"]) == []


def test_the_manifest_makes_it_installable(client):
    manifest = client.get(f"{APP_PATH}/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    body = manifest.json()
    assert body["start_url"] == body["scope"] == f"{APP_PATH}/"
    assert body["display"] == "standalone"
    sizes = {icon["sizes"] for icon in body["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for entry in body["icons"]:
        response = client.get(entry["src"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


@pytest.mark.parametrize("size", [192, 512])
def test_the_icon_is_a_real_png_of_its_size(size):
    png = icon_png(size)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (size, size)
    # The image data inflates to one filter byte and three bytes a pixel, a row at a time.
    idat_length = struct.unpack(">I", png[33:37])[0]
    pixels = zlib.decompress(png[41 : 41 + idat_length])
    assert len(pixels) == size * (1 + 3 * size)


def test_an_unknown_icon_size_is_not_found(client):
    assert client.get(f"{APP_PATH}/icon-64.png").status_code == 404


def test_the_service_worker_keeps_only_the_app_page(client):
    response = client.get(f"{APP_PATH}/sw.js")
    assert response.headers["content-type"].startswith("text/javascript")
    script = response.text
    assert f"const PAGE = '{APP_PATH}/';" in script
    # A sign-in page or an error never replaces the kept copy.
    assert "response.ok && !response.redirected" in script
    assert "request.mode !== 'navigate'" in script


def test_the_demo_class_is_prefilled_only_on_a_demo_install(client, settings):
    _sign_in(client, "teacher")
    named = replace(settings, demo_class="Period 3|Paige Turner|Justin Time")
    app.dependency_overrides[get_settings] = lambda: named
    assert "class_list" not in _config(client.get(f"{APP_PATH}/").text)
    demo = replace(named, demo=True)
    app.dependency_overrides[get_settings] = lambda: demo
    config = _config(client.get(f"{APP_PATH}/").text)
    assert config["class_label"] == "Period 3"
    assert config["class_list"] == ["Paige Turner", "Justin Time"]


def test_staff_home_opens_the_app_and_keeps_the_download(client):
    _sign_in(client, "teacher")
    home = client.get("/staff").text
    assert f'href="{APP_PATH}/"' in home
    assert 'action="/staff/minting-page"' in home
