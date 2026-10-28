from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db, hash_token
from library_assistant.app import app
from library_assistant.flags import raise_flag
from library_assistant.staff import STAFF_SESSION_COOKIE, create_account

# Far in the future on purpose, matching tests/test_staff.py's convention: a past NOW
# would make every Card and staff session in this file look already expired.
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def client(db, clock):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sign_in_as(client, db, role) -> TestClient:
    create_account(db, f"{role}-account", "correct horse", role)
    response = client.post(
        "/staff/login",
        data={"username": f"{role}-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
    return client


def _transcript(db, question="what do snow leopards eat?", answer="a good answer"):
    cursor = db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            hash_token("session-1"),
            "Period 3",
            "14",
            question,
            answer,
            "[]",
            NOW.isoformat(),
        ),
    )
    db.commit()
    return cursor.lastrowid


def _flag(
    db,
    transcript_id,
    class_label="Period 3",
    card_number="14",
    category="content",
    severity="high",
    source="watchlist",
    entry_id="entry-1",
):
    return raise_flag(
        db,
        transcript_id=transcript_id,
        class_label=class_label,
        card_number=card_number,
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash="abc123",
        category=category,
        severity=severity,
        source=source,
        raised_at=NOW.isoformat(),
        entry_id=entry_id,
    )


def test_queue_lists_flag_without_exchange_text(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(
        db, question="is this ok?", answer="an answer that must not leak"
    )
    flag_id = _flag(db, transcript_id)

    response = client.get("/staff/flags")

    assert response.status_code == 200
    assert "content" in response.text
    assert "high" in response.text
    assert "watchlist" in response.text
    assert "entry-1" in response.text
    assert "Period 3" in response.text
    assert "14" in response.text
    assert f"/staff/flags/{flag_id}" in response.text
    assert "is this ok?" not in response.text
    assert "an answer that must not leak" not in response.text


def test_flag_page_shows_exchange_no_store(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(
        db, question="is this ok?", answer="the full answer text"
    )
    flag_id = _flag(db, transcript_id)

    response = client.get(f"/staff/flags/{flag_id}")

    assert response.status_code == 200
    assert "is this ok?" in response.text
    assert "the full answer text" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_close_removes_from_queue(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    response = client.post(f"/staff/flags/{flag_id}/close", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/flags"

    queue = client.get("/staff/flags")
    assert f"/staff/flags/{flag_id}" not in queue.text


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_teacher_and_counselor_get_403(client, db, role):
    _sign_in_as(client, db, role)
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    assert client.get("/staff/flags").status_code == 403
    assert client.get(f"/staff/flags/{flag_id}").status_code == 403
    assert (
        client.post(f"/staff/flags/{flag_id}/close", follow_redirects=False).status_code
        == 403
    )


def test_anonymous_gets_401(client, db):
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    assert client.get("/staff/flags").status_code == 401
    assert client.get(f"/staff/flags/{flag_id}").status_code == 401
    assert (
        client.post(f"/staff/flags/{flag_id}/close", follow_redirects=False).status_code
        == 401
    )


def test_unknown_flag_404(client, db):
    _sign_in_as(client, db, "librarian")

    assert client.get("/staff/flags/999").status_code == 404
    assert (
        client.post("/staff/flags/999/close", follow_redirects=False).status_code == 404
    )
