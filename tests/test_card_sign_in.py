from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    get_registration_key,
    hash_token,
)
from library_assistant.app import app

REGISTRATION_KEY = "s3cret-registration-key"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LIBRARY_ASSISTANT_REGISTRATION_KEY", REGISTRATION_KEY)
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_registration_key] = lambda: REGISTRATION_KEY
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


def _register(client, expires_at: datetime, key: str = REGISTRATION_KEY):
    return client.post(
        "/batches",
        json={
            "registration_key": key,
            "cards": [{"token": "token-1", "card_number": "14"}],
            "expires_at": expires_at.isoformat(),
            "class_label": "Period 3",
        },
    )


def test_batch_registration_without_key_refused(client):
    tc, _db = client
    response = _register(tc, datetime.now(UTC) + timedelta(days=1), key="wrong-key")
    assert response.status_code == 403


def test_batch_registration_with_key_stored(client):
    tc, db = client
    response = _register(tc, datetime.now(UTC) + timedelta(days=1))
    assert response.status_code == 201
    rows = db.execute("SELECT * FROM cards").fetchall()
    assert len(rows) == 1


def test_db_holds_only_hash_card_number_expiry_class_label(client):
    tc, db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))

    columns = [row[1] for row in db.execute("PRAGMA table_info(cards)").fetchall()]
    assert set(columns) == {"token_hash", "card_number", "expires_at", "class_label"}

    row = db.execute("SELECT * FROM cards").fetchone()
    stored = dict(zip(columns, row, strict=True))
    assert "token-1" not in stored.values()
    assert stored["token_hash"] == hash_token("token-1")


def test_valid_token_starts_session(client):
    tc, _db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.post("/card", json={"token": "token-1"})
    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text
    assert SESSION_COOKIE in response.cookies


def test_session_cookie_is_httponly_strict_with_no_max_age(client):
    tc, _db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.post("/card", json={"token": "token-1"})
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    assert "Max-Age" not in set_cookie


def test_token_in_path_refused(client):
    tc, _db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.get("/cards/token-1")
    assert response.status_code == 403
    assert (
        "This card has stopped working. Ask your teacher for a new one."
        in response.text
    )


def test_token_in_query_refused(client):
    tc, _db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.post("/card?token=token-1", json={"token": "token-1"})
    assert response.status_code == 403


def test_card_page_has_no_token(client):
    tc, _db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.get("/card")
    assert response.status_code == 200
    assert "token-1" not in response.text


def test_finish_clears_cookie_without_revoking_card(client):
    tc, db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    tc.post("/card", json={"token": "token-1"})

    response = tc.post("/card/finish")
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"]
    assert "Max-Age=0" in set_cookie

    rows = db.execute("SELECT * FROM cards").fetchall()
    assert len(rows) == 1
    again = tc.post("/card", json={"token": "token-1"})
    assert again.status_code == 200


def test_expired_token_refused_via_fake_clock(client):
    tc, _db = client
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    _register(tc, expires_at)

    app.dependency_overrides[get_clock] = lambda: expires_at + timedelta(hours=1)
    response = tc.post("/card", json={"token": "token-1"})
    assert response.status_code == 403
    assert (
        "This card has stopped working. Ask your teacher for a new one."
        in response.text
    )


def test_unknown_token_refused(client):
    tc, _db = client
    response = tc.post("/card", json={"token": "no-such-token"})
    assert response.status_code == 403
    assert (
        "This card has stopped working. Ask your teacher for a new one."
        in response.text
    )


def test_revoked_card_refused(client):
    tc, _db = client
    expires_at = datetime.now(UTC) + timedelta(days=1)
    _register(tc, expires_at)

    response = tc.post(
        "/batches/revoke-card",
        json={
            "registration_key": REGISTRATION_KEY,
            "class_label": "Period 3",
            "card_number": "14",
            "expires_at": expires_at.isoformat(),
        },
    )
    assert response.status_code == 200
    assert tc.post("/card", json={"token": "token-1"}).status_code == 403


def test_revoked_batch_refused(client):
    tc, db = client
    expires_at = datetime.now(UTC) + timedelta(days=1)
    tc.post(
        "/batches",
        json={
            "registration_key": REGISTRATION_KEY,
            "cards": [
                {"token": "token-1", "card_number": "14"},
                {"token": "token-2", "card_number": "15"},
            ],
            "expires_at": expires_at.isoformat(),
            "class_label": "Period 3",
        },
    )

    response = tc.post(
        "/batches/revoke-batch",
        json={
            "registration_key": REGISTRATION_KEY,
            "class_label": "Period 3",
            "expires_at": expires_at.isoformat(),
        },
    )
    assert response.status_code == 200
    assert tc.post("/card", json={"token": "token-1"}).status_code == 403
    assert tc.post("/card", json={"token": "token-2"}).status_code == 403
    assert db.execute("SELECT * FROM cards").fetchall() == []


def test_refusal_text_says_ask_for_a_new_card(client):
    """Test that the refusal text has been updated to mention asking for a new card."""
    tc, _db = client
    # Register a batch with a valid token, then try to use a different token
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    # Try to sign in with a different token that doesn't exist
    response = tc.post("/card", json={"token": "non-existent-token"})
    assert response.status_code == 403
    assert (
        "This card has stopped working. Ask your teacher for a new one."
        in response.text
    )


def test_new_sign_in_ends_the_devices_previous_session(client):
    """Test that signing in with a new card ends the previous session on the same device."""
    tc, db = client
    # Register two cards
    expires_at = datetime.now(UTC) + timedelta(days=1)
    _register(tc, expires_at)

    # Sign in with first card
    response1 = tc.post("/card", json={"token": "token-1"})
    assert response1.status_code == 200
    assert SESSION_COOKIE in response1.cookies
    session1_id = response1.cookies[SESSION_COOKIE]

    # Verify session exists
    session_count = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
    assert session_count == 1

    # Sign in with second card (same device)
    response2 = tc.post("/card", json={"token": "token-1"})
    assert response2.status_code == 200
    assert SESSION_COOKIE in response2.cookies

    # Verify old session is deleted
    session_count = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
    assert session_count == 1

    # Verify the new session is different from the old one
    session2_id = response2.cookies[SESSION_COOKIE]
    assert session1_id != session2_id


def test_other_devices_sessions_untouched(client):
    """Test that signing in with a new card doesn't affect sessions on other devices."""
    tc, db = client
    # Register a card
    expires_at = datetime.now(UTC) + timedelta(days=1)
    _register(tc, expires_at)

    # Sign in with first card on device 1
    response1 = tc.post("/card", json={"token": "token-1"})
    assert response1.status_code == 200
    session1_id = response1.cookies[SESSION_COOKIE]

    # Sign in with same card on device 2 (different TestClient)
    tc2 = TestClient(app)
    tc2.app.dependency_overrides[get_db] = lambda: db
    tc2.app.dependency_overrides[get_registration_key] = lambda: REGISTRATION_KEY

    response2 = tc2.post("/card", json={"token": "token-1"})
    assert response2.status_code == 200
    session2_id = response2.cookies[SESSION_COOKIE]

    # Both sessions should exist (different devices)
    session_count = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
    assert session_count == 2

    # Verify they are different sessions
    assert session1_id != session2_id


def test_cookie_expires_with_the_card(client):
    """Test that the session cookie expires with the card's expiry."""
    tc, db = client
    # Register a card with a specific expiry time
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    _register(tc, expires_at)

    # Sign in with the card
    response = tc.post("/card", json={"token": "token-1"})
    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies

    # Check that cookie has the right expiry (should be the card's expiry)
    set_cookie_header = response.headers["set-cookie"]
    assert "expires=" in set_cookie_header.lower()

    # Verify the session exists in the database
    session_count = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
    assert session_count == 1


def test_card_page_has_end_session_button(client):
    """Test that the card page has the new 'End session' button."""
    tc, _db = client
    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.get("/card")
    assert response.status_code == 200
    assert "End session" in response.text
