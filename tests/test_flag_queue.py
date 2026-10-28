from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db, hash_token
from library_assistant.app import app
from library_assistant.flag_history import get_history
from library_assistant.flags import raise_flag
from library_assistant.staff import STAFF_SESSION_COOKIE, create_account, set_stand_in

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

    response = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "done"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/flags"

    queue = client.get("/staff/flags")
    assert f"/staff/flags/{flag_id}" not in queue.text


def test_teacher_gets_403(client, db):
    _sign_in_as(client, db, "teacher")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    assert client.get("/staff/flags").status_code == 403
    assert client.get(f"/staff/flags/{flag_id}").status_code == 403
    assert (
        client.post(f"/staff/flags/{flag_id}/close", follow_redirects=False).status_code
        == 403
    )


def test_counselor_sees_only_escalated(client, db):
    """A Counselor sees the queue, but only an Escalated Flag in it (ADR-0010)."""
    _sign_in_as(client, db, "counselor")
    transcript_id = _transcript(db)
    open_flag_id = _flag(db, transcript_id)
    escalated_flag_id = _flag(db, transcript_id, category="escalated")

    response = client.get("/staff/flags")
    assert response.status_code == 200
    assert f"/staff/flags/{escalated_flag_id}" in response.text
    assert f"/staff/flags/{open_flag_id}" not in response.text

    assert client.get(f"/staff/flags/{escalated_flag_id}").status_code == 200
    assert client.get(f"/staff/flags/{open_flag_id}").status_code == 403
    assert (
        client.post(
            f"/staff/flags/{escalated_flag_id}/close", follow_redirects=False
        ).status_code
        == 403
    )


def test_stand_in_gets_full_queue_access(client, db):
    """A Stand-in works the queue like a Librarian (ADR-0010)."""
    create_account(db, "teacher-standin", "correct horse", "teacher")
    account_id = db.execute(
        "SELECT id FROM staff_accounts WHERE username = 'teacher-standin'"
    ).fetchone()[0]
    set_stand_in(db, account_id, True)
    response = client.post(
        "/staff/login",
        data={"username": "teacher-standin", "password": "correct horse"},
        follow_redirects=False,
    )
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])

    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    assert client.get("/staff/flags").status_code == 200
    assert client.get(f"/staff/flags/{flag_id}").status_code == 200
    assert (
        client.post(
            f"/staff/flags/{flag_id}/close",
            data={"outcome": "handled", "reason": "done"},
            follow_redirects=False,
        ).status_code
        == 303
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
        client.post(
            "/staff/flags/999/close",
            data={"outcome": "handled", "reason": "done"},
            follow_redirects=False,
        ).status_code
        == 404
    )


def test_raised_records_watchlist_entry_and_version(db):
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, entry_id="entry-1")
    history = get_history(db, flag_id)
    raised = [event for event in history if event.event == "raised"]
    assert len(raised) == 1
    assert raised[0].source == "watchlist"
    assert raised[0].entry_id == "entry-1"


def test_raised_records_oversight_source(db):
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, source="oversight", entry_id=None)
    history = get_history(db, flag_id)
    raised = [event for event in history if event.event == "raised"]
    assert len(raised) == 1
    assert raised[0].source == "oversight"
    assert raised[0].entry_id is None


def test_viewing_flag_records_history(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    response = client.get(f"/staff/flags/{flag_id}")
    assert response.status_code == 200

    history = get_history(db, flag_id)
    viewed = [event for event in history if event.event == "viewed"]
    assert len(viewed) == 1
    assert viewed[0].account == "librarian-account"
    assert viewed[0].at == NOW.isoformat()


def test_close_requires_outcome_and_reason(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    response = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "not-a-real-outcome", "reason": "a reason"},
        follow_redirects=False,
    )
    assert response.status_code == 422

    response = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "  "},
        follow_redirects=False,
    )
    assert response.status_code == 422


def test_close_records_history_with_outcome_and_account(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)

    response = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "not a concern"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    history = get_history(db, flag_id)
    closed = [event for event in history if event.event == "closed"]
    assert len(closed) == 1
    assert closed[0].account == "librarian-account"
    assert closed[0].outcome == "handled"
    assert closed[0].reason == "not a concern"


def test_reopen_requires_reason(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)
    client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "not a concern"},
        follow_redirects=False,
    )

    response = client.post(
        f"/staff/flags/{flag_id}/reopen",
        data={"reason": ""},
        follow_redirects=False,
    )
    assert response.status_code == 422


def test_reopen_reopens_and_records_history(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)
    client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "not a concern"},
        follow_redirects=False,
    )

    response = client.post(
        f"/staff/flags/{flag_id}/reopen",
        data={"reason": "need another look"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    queue = client.get("/staff/flags")
    assert f"/staff/flags/{flag_id}" in queue.text

    history = get_history(db, flag_id)
    reopened = [event for event in history if event.event == "reopened"]
    assert len(reopened) == 1
    assert reopened[0].account == "librarian-account"
    assert reopened[0].reason == "need another look"


def test_reopen_refused_after_exchange_purged(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)
    client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "not a concern"},
        follow_redirects=False,
    )
    db.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
    db.commit()

    response = client.post(
        f"/staff/flags/{flag_id}/reopen",
        data={"reason": "need another look"},
        follow_redirects=False,
    )
    assert response.status_code == 422


def test_overdue_flag_marked_in_queue(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash="abc123",
        category="content",
        severity="high",
        source="watchlist",
        raised_at=(NOW - timedelta(days=8)).isoformat(),
        entry_id="entry-1",
    )

    response = client.get("/staff/flags")
    assert response.status_code == 200
    assert "Overdue" in response.text
    assert f"/staff/flags/{flag_id}" in response.text
    response = client.get("/staff/flags")
    assert response.status_code == 200
    assert "Overdue" in response.text
    assert f"/staff/flags/{flag_id}" in response.text


def test_mark_reviewed_records_account_and_time(client, db):
    """Test that marking a review records the account and time."""
    # Create a librarian account
    create_account(db, "librarian-account", "correct horse", "librarian")
    response = client.post(
        "/staff/login",
        data={"username": "librarian-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])

    # Create a transcript and flag
    transcript_id = _transcript(db)
    _flag(db, transcript_id)

    # Mark review
    response = client.post("/staff/flags/reviewed", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/staff/flags"

    # Check that a review was recorded
    rows = db.execute("SELECT account_id, reviewed_at FROM flag_reviews").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1  # librarian account ID
    # The timestamp should be NOW (as set in the fixture)


def test_header_shows_last_and_next_due_in_periodic(client, db):
    """Test that the header shows last reviewed and next due times in periodic mode."""
    # Set up periodic mode
    db.execute(
        "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
        ("supervision_mode", "periodic"),
    )
    db.execute(
        "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
        ("reviews_every_minutes", "120"),
    )
    db.commit()

    # Create a librarian account
    create_account(db, "librarian-account", "correct horse", "librarian")
    response = client.post(
        "/staff/login",
        data={"username": "librarian-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])

    # Create a transcript and flag
    transcript_id = _transcript(db)
    _flag(db, transcript_id)

    # Mark a review (this sets the last review time)
    response = client.post("/staff/flags/reviewed", follow_redirects=False)
    assert response.status_code == 303

    # Check that the queue shows the review header
    response = client.get("/staff/flags")
    assert response.status_code == 200
    # Should contain last reviewed text and next due text
    assert "Last reviewed" in response.text
    assert "next due" in response.text


def test_overdue_shown_after_due(client, db):
    """Test that 'overdue' is shown when the review time has passed."""
    # Set up periodic mode
    db.execute(
        "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
        ("supervision_mode", "periodic"),
    )
    db.execute(
        "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
        ("reviews_every_minutes", "120"),
    )
    db.commit()

    # Create a librarian account
    create_account(db, "librarian-account", "correct horse", "librarian")
    response = client.post(
        "/staff/login",
        data={"username": "librarian-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])

    # Create a transcript and flag
    transcript_id = _transcript(db)
    _flag(db, transcript_id)

    # Mark review with a past time (using the NOW from fixture but moving it back)
    # Since we're using the test fixture with NOW = 2036-10-27 14:00 UTC, we'll make the
    # last review time 3 hours ago (so that 2 hour due period makes it overdue)
    past_review_time = NOW - timedelta(hours=3)
    db.execute(
        "INSERT INTO flag_reviews (account_id, reviewed_at) VALUES (?, ?)",
        (1, past_review_time.isoformat()),
    )
    db.commit()

    # Check that the queue shows overdue in the header
    response = client.get("/staff/flags")
    assert response.status_code == 200
    # Should contain overdue in the header info
    assert "(overdue)" in response.text


def test_no_review_header_in_live_mode(client, db):
    """Test that no review header is shown in live mode."""
    # Set up live mode
    db.execute(
        "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
        ("supervision_mode", "live"),
    )
    db.commit()

    # Create a librarian account
    create_account(db, "librarian-account", "correct horse", "librarian")
    response = client.post(
        "/staff/login",
        data={"username": "librarian-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])

    # Create a transcript and flag
    transcript_id = _transcript(db)
    _flag(db, transcript_id)

    # Mark a review
    response = client.post("/staff/flags/reviewed", follow_redirects=False)
    assert response.status_code == 303

    # Check that the queue does NOT show review header in live mode
    response = client.get("/staff/flags")
    assert response.status_code == 200
    # Should not crash and work normally


def test_mark_reviewed_teacher_403(client, db):
    """Test that teachers cannot mark reviews."""
    # Create a teacher account
    create_account(db, "teacher-account", "correct horse", "teacher")
    response = client.post(
        "/staff/login",
        data={"username": "teacher-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])

    # Try to mark a review - should fail with 403
    response = client.post("/staff/flags/reviewed", follow_redirects=False)
    assert response.status_code == 403
