from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
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
    response = tc.get("/cards/token-1")
    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text


def test_expired_token_refused_via_fake_clock(client):
    tc, _db = client
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    _register(tc, expires_at)

    app.dependency_overrides[get_clock] = lambda: expires_at + timedelta(hours=1)
    response = tc.get("/cards/token-1")
    assert response.status_code == 403
    assert "ask your teacher" in response.text


def test_unknown_token_refused(client):
    tc, _db = client
    response = tc.get("/cards/no-such-token")
    assert response.status_code == 403
    assert "ask your teacher" in response.text


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
    assert tc.get("/cards/token-1").status_code == 403


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
    assert tc.get("/cards/token-1").status_code == 403
    assert tc.get("/cards/token-2").status_code == 403
    assert db.execute("SELECT * FROM cards").fetchall() == []
