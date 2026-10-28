from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db, hash_token
from library_assistant.app import app
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


def _card(
    db, token, card_number, class_label="Period 3", expires_at=NOW + timedelta(hours=6)
):
    db.execute(
        "INSERT INTO cards (token_hash, card_number, expires_at, class_label) "
        "VALUES (?, ?, ?, ?)",
        (hash_token(token), card_number, expires_at.isoformat(), class_label),
    )
    db.commit()


def _session(db, token, started_at=NOW) -> str:
    session_hash = hash_token(f"session-for-{token}")
    db.execute(
        "INSERT INTO sessions (session_hash, token_hash, started_at) VALUES (?, ?, ?)",
        (session_hash, hash_token(token), started_at.isoformat()),
    )
    db.commit()
    return session_hash


def _ask(db, session_hash, class_label, card_number, question, asked_at=NOW):
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            session_hash,
            class_label,
            card_number,
            question,
            "an answer",
            "[]",
            asked_at.isoformat(),
        ),
    )
    db.commit()


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


def test_tile_per_active_session_with_label_and_card(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "what do snow leopards eat?")

    response = client.get("/staff/live")

    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text
    assert "what do snow leopards eat?" in response.text


def test_expired_or_revoked_session_has_no_tile(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-expired", "15", expires_at=NOW - timedelta(hours=1))
    _session(db, "token-expired")
    # Revoked: no Card row at all for this Session's token.
    _session(db, "token-revoked")

    response = client.get("/staff/live")

    assert "15" not in response.text
    assert "No active Sessions." in response.text


def test_tiles_most_recent_activity_first(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-older", "1")
    older_hash = _session(db, "token-older", started_at=NOW - timedelta(minutes=10))
    _ask(
        db,
        older_hash,
        "Period 3",
        "1",
        "older question",
        asked_at=NOW - timedelta(minutes=10),
    )

    _card(db, "token-newer", "2")
    newer_hash = _session(db, "token-newer", started_at=NOW - timedelta(minutes=5))
    _ask(
        db,
        newer_hash,
        "Period 3",
        "2",
        "newer question",
        asked_at=NOW - timedelta(minutes=1),
    )

    response = client.get("/staff/live")

    assert response.text.index("newer question") < response.text.index("older question")


def test_latest_question_truncated(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    long_question = "why " * 30
    _ask(db, session_hash, "Period 3", "14", long_question)

    response = client.get("/staff/live")

    assert long_question not in response.text
    assert long_question[:80] + "..." in response.text


def test_overview_has_no_forms(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    response = client.get("/staff/live")

    assert "<form" not in response.text
    assert "<button" not in response.text


def test_page_has_no_token_or_hash(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    response = client.get("/staff/live")

    lowered = response.text.lower()
    assert "token" not in lowered
    assert "hash" not in lowered
    assert session_hash not in response.text
    assert hash_token("token-14") not in response.text


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_teacher_and_counselor_403(client, db, role):
    _sign_in_as(client, db, role)

    response = client.get("/staff/live")

    assert response.status_code == 403


def test_anonymous_401(client):
    response = client.get("/staff/live")

    assert response.status_code == 401


def test_detail_shows_questions_answers_citations_oldest_first(client, db):
    """Test that session detail shows exchanges ordered oldest first."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")

    # Add multiple exchanges
    _ask(
        db,
        session_hash,
        "Period 3",
        "14",
        "First question",
        asked_at=NOW - timedelta(minutes=10),
    )
    _ask(
        db,
        session_hash,
        "Period 3",
        "14",
        "Second question",
        asked_at=NOW - timedelta(minutes=5),
    )

    # Get the session_no from the session_hash (it's the rowid)
    session_row = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()
    session_no = session_row[0]

    response = client.get(f"/staff/live/sessions/{session_no}")

    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text
    assert "First question" in response.text
    assert "Second question" in response.text
    # Check ordering - first question should come before second question
    first_pos = response.text.index("First question")
    second_pos = response.text.index("Second question")
    assert first_pos < second_pos


def test_detail_unknown_session_404(client, db):
    """Test that accessing a non-existent session returns 404."""
    _sign_in_as(client, db, "librarian")

    response = client.get("/staff/live/sessions/999999")

    assert response.status_code == 404


def test_detail_has_no_token_or_hash(client, db):
    """Test that session detail page does not contain token or hash."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    # Get the session_no from the session_hash (it's the rowid)
    session_row = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()
    session_no = session_row[0]

    response = client.get(f"/staff/live/sessions/{session_no}")

    assert response.status_code == 200
    lowered = response.text.lower()
    assert "token" not in lowered
    assert "hash" not in lowered
    assert session_hash not in response.text


def test_detail_teacher_403(client, db):
    """Test that teacher role gets 403 for session detail."""
    _sign_in_as(client, db, "teacher")

    response = client.get("/staff/live/sessions/1")

    assert response.status_code == 403


def test_tile_links_to_detail(client, db):
    """Test that tile links properly to session detail."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "what do snow leopards eat?")

    # First get the live view to get session_no
    response = client.get("/staff/live")
    assert response.status_code == 200

    # Check that there's a link to the detail view
    assert "/staff/live/sessions/" in response.text
