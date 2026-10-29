from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    IDLE_TEXT,
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    hash_token,
    issue_registration_key,
)
from library_assistant.app import app
from library_assistant.config import Settings
from library_assistant.install_settings import (
    SESSION_IDLE_MINUTES,
    SUPERVISION_MODE,
    set_setting,
)
from library_assistant.schoolday import school_day_end_for
from library_assistant.staff import create_account

FIXED_CLOCK = datetime(2027, 1, 15, 14, 0, tzinfo=UTC)
DAY_END = school_day_end_for(FIXED_CLOCK, Settings())

# Set afresh by the `client` fixture each test, to the key it just issued the seeded
# Teacher account: a real, per-account secret rather than a shared constant (lib-90j.1).
REGISTRATION_KEY: str = ""
REGISTRATION_ACCOUNT_ID: int = 0


@pytest.fixture
def client():
    global REGISTRATION_KEY, REGISTRATION_ACCOUNT_ID
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK
    REGISTRATION_ACCOUNT_ID = create_account(db, "teacher", "correct horse", "teacher")
    REGISTRATION_KEY = issue_registration_key(db, REGISTRATION_ACCOUNT_ID, FIXED_CLOCK)
    # No Watch is started in this fixture: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", REGISTRATION_ACCOUNT_ID, FIXED_CLOCK)
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


def _register(client, expires_at: datetime, key: str | None = None):
    return client.post(
        "/batches",
        json={
            "registration_key": key if key is not None else REGISTRATION_KEY,
            "cards": [{"token": "token-1", "card_number": "14"}],
            "expires_at": expires_at.isoformat(),
            "class_label": "Period 3",
        },
    )


def test_batch_registration_without_key_refused(client):
    tc, _db = client
    response = _register(tc, DAY_END, key="wrong-key")
    assert response.status_code == 403


def test_batch_registration_with_key_stored(client):
    tc, db = client
    response = _register(tc, DAY_END)
    assert response.status_code == 201
    rows = db.execute("SELECT * FROM cards").fetchall()
    assert len(rows) == 1


def test_db_holds_only_hash_card_number_expiry_class_label(client):
    """Per-Teacher keys (lib-90j.1) add one staff-account reference, nothing else: the
    Registration payload (token hash, card number, expiry, class label) is unchanged."""
    tc, db = client
    _register(tc, DAY_END)

    columns = [row[1] for row in db.execute("PRAGMA table_info(cards)").fetchall()]
    assert set(columns) == {
        "token_hash",
        "card_number",
        "expires_at",
        "class_label",
        "registered_by_account_id",
    }

    row = db.execute("SELECT * FROM cards").fetchone()
    stored = dict(zip(columns, row, strict=True))
    assert "token-1" not in stored.values()
    assert stored["token_hash"] == hash_token("token-1")
    assert stored["registered_by_account_id"] == REGISTRATION_ACCOUNT_ID


def test_batch_stores_the_registering_teachers_account(client):
    tc, db = client
    _register(tc, DAY_END)
    row = db.execute(
        "SELECT registered_by_account_id FROM cards WHERE card_number = '14'"
    ).fetchone()
    assert row[0] == REGISTRATION_ACCOUNT_ID


def test_rotated_key_refused_at_once(client):
    tc, db = client
    old_key = REGISTRATION_KEY
    new_key = issue_registration_key(db, REGISTRATION_ACCOUNT_ID, FIXED_CLOCK)
    assert new_key != old_key

    refused = _register(tc, DAY_END, key=old_key)
    assert refused.status_code == 403

    accepted = _register(tc, DAY_END, key=new_key)
    assert accepted.status_code == 201


def test_deactivated_accounts_key_refused_at_once(client):
    """ADR-0002 addendum: a deactivated account's still-valid key stops working at once,
    and Batches it already registered keep their reference to it."""
    tc, db = client
    assert _register(tc, DAY_END).status_code == 201

    create_account(db, "librarian", "correct horse", "librarian")
    tc.post("/staff/login", data={"username": "librarian", "password": "correct horse"})
    deactivated = tc.post(
        f"/staff/accounts/{REGISTRATION_ACCOUNT_ID}/deactivate", follow_redirects=False
    )
    assert deactivated.status_code == 303

    assert _register(tc, DAY_END).status_code == 403
    revoke = tc.post(
        "/batches/revoke-batch",
        json={
            "registration_key": REGISTRATION_KEY,
            "class_label": "Period 3",
            "expires_at": DAY_END.isoformat(),
        },
    )
    assert revoke.status_code == 403
    row = db.execute("SELECT registered_by_account_id FROM cards").fetchone()
    assert row == (REGISTRATION_ACCOUNT_ID,)


def test_old_shared_key_setting_not_accepted(client, monkeypatch):
    """The single shared key is gone: setting the old env var opens nothing."""
    tc, _db = client
    monkeypatch.setenv("LIBRARY_ASSISTANT_REGISTRATION_KEY", "old-shared-key")
    assert _register(tc, DAY_END, key="old-shared-key").status_code == 403


def test_other_accounts_key_registers_under_that_account(client):
    """Each account's key is its own: a Batch is stored under the key's account."""
    tc, db = client
    other_account_id = create_account(db, "other-teacher", "correct horse", "teacher")
    other_key = issue_registration_key(db, other_account_id, FIXED_CLOCK)

    response = _register(tc, DAY_END, key=other_key)
    assert response.status_code == 201
    row = db.execute(
        "SELECT registered_by_account_id FROM cards WHERE card_number = '14'"
    ).fetchone()
    assert row[0] == other_account_id


def test_valid_token_starts_session(client):
    tc, _db = client
    _register(tc, DAY_END)
    response = tc.post("/card", json={"token": "token-1"})
    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text
    assert SESSION_COOKIE in response.cookies


def test_session_cookie_is_httponly_strict_with_no_max_age(client):
    tc, _db = client
    _register(tc, DAY_END)
    response = tc.post("/card", json={"token": "token-1"})
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    assert "Max-Age" not in set_cookie


def test_token_in_path_refused(client):
    tc, _db = client
    _register(tc, DAY_END)
    response = tc.get("/cards/token-1")
    assert response.status_code == 403
    assert (
        "This card has stopped working. Ask your teacher for a new one."
        in response.text
    )


def test_token_in_query_refused(client):
    tc, _db = client
    _register(tc, DAY_END)
    response = tc.post("/card?token=token-1", json={"token": "token-1"})
    assert response.status_code == 403


def test_card_page_has_no_token(client):
    tc, _db = client
    _register(tc, DAY_END)
    response = tc.get("/card")
    assert response.status_code == 200
    assert "token-1" not in response.text


def test_finish_clears_cookie_without_revoking_card(client):
    tc, db = client
    _register(tc, DAY_END)
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
    expires_at = FIXED_CLOCK + timedelta(hours=1)
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
    expires_at = DAY_END
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
    expires_at = DAY_END
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
    _register(tc, DAY_END)
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
    expires_at = DAY_END
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
    expires_at = DAY_END
    _register(tc, expires_at)

    # Sign in with first card on device 1
    response1 = tc.post("/card", json={"token": "token-1"})
    assert response1.status_code == 200
    session1_id = response1.cookies[SESSION_COOKIE]

    # Sign in with same card on device 2 (different TestClient)
    tc2 = TestClient(app)
    tc2.app.dependency_overrides[get_db] = lambda: db

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
    expires_at = FIXED_CLOCK + timedelta(hours=1)
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
    _register(tc, DAY_END)
    response = tc.get("/card")
    assert response.status_code == 200
    assert "End session" in response.text


def test_expiry_past_day_end_refused(client):
    tc, _db = client
    response = _register(tc, DAY_END + timedelta(minutes=1))
    assert response.status_code == 422
    assert "A Batch must expire by the end of today's school day." in response.text


def test_expiry_at_day_end_accepted(client):
    tc, _db = client
    response = _register(tc, DAY_END)
    assert response.status_code == 201


def test_registration_after_day_end_refused(client):
    tc, _db = client
    tc.app.dependency_overrides[get_clock] = lambda: DAY_END
    response = _register(tc, DAY_END)
    assert response.status_code == 422
    assert "Registration is closed: today's school day has ended." in response.text


def _set_idle_minutes(db, minutes: int) -> None:
    db.execute(
        "INSERT INTO install_settings (key, value) VALUES (?, ?)",
        (SESSION_IDLE_MINUTES, str(minutes)),
    )
    db.commit()


def test_session_ends_after_idle_minutes(client):
    tc, db = client
    _register(tc, DAY_END)
    _set_idle_minutes(db, 5)
    tc.post("/card", json={"token": "token-1"})

    tc.app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK + timedelta(minutes=6)
    response = tc.get("/chat")
    assert response.status_code == 403
    assert response.json()["detail"] == IDLE_TEXT
    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_activity_keeps_session_alive(client):
    tc, db = client
    _register(tc, DAY_END)
    _set_idle_minutes(db, 5)
    tc.post("/card", json={"token": "token-1"})

    tc.app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK + timedelta(minutes=4)
    assert tc.get("/chat").status_code == 200

    tc.app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK + timedelta(minutes=8)
    assert tc.get("/chat").status_code == 200


def test_zero_means_no_limit(client):
    tc, _db = client
    _register(tc, DAY_END)
    tc.post("/card", json={"token": "token-1"})

    tc.app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK + timedelta(hours=6)
    assert tc.get("/chat").status_code == 200


def test_card_signs_in_again_after_idle(client):
    tc, db = client
    _register(tc, DAY_END)
    _set_idle_minutes(db, 5)
    tc.post("/card", json={"token": "token-1"})

    tc.app.dependency_overrides[get_clock] = lambda: FIXED_CLOCK + timedelta(minutes=6)
    assert tc.get("/chat").status_code == 403

    response = tc.post("/card", json={"token": "token-1"})
    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies
