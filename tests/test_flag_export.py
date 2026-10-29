"""Tests for the Flag Export (ADR-0003 addendum)."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db, hash_token
from library_assistant.app import app
from library_assistant.flags import get_flag, raise_flag
from library_assistant.staff import STAFF_SESSION_COOKIE, create_account

NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: NOW
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


def _transcript(db, question="is this ok?", answer="an answer, timed"):
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


def _flag(db, transcript_id, category="content", severity="high", escalated=False):
    flag_id = raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash="abc123hash",
        category=category,
        severity=severity,
        source="watchlist",
        raised_at=NOW.isoformat(),
        entry_id="entry-1",
    )
    if escalated:
        db.execute(
            "UPDATE flags SET escalated_at = ? WHERE id = ?", (NOW.isoformat(), flag_id)
        )
        db.commit()
    return flag_id


def test_export_has_required_fields_no_hash_no_token(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db, question="is this ok?", answer="an answer, timed")
    flag_id = _flag(db, transcript_id)

    response = client.get(f"/staff/flags/{flag_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    body = response.text
    assert "Period 3" in body
    assert "14" in body
    assert NOW.isoformat() in body
    assert "content" in body
    assert "high" in body
    assert "watchlist" in body
    assert "entry-1" in body
    assert "is this ok?" in body
    assert "an answer, timed" in body
    assert "raised" in body
    assert "abc123hash" not in body
    assert "hash" not in body.lower()
    assert "token" not in body.lower()
    assert "session-1" not in body


def test_export_does_not_leak_other_sessions_text(client, db):
    _sign_in_as(client, db, "librarian")
    other_transcript_id = _transcript(
        db, question="unrelated question", answer="an unrelated answer"
    )
    _flag(db, other_transcript_id)
    transcript_id = _transcript(db, question="is this ok?", answer="an answer, timed")
    flag_id = _flag(db, transcript_id)

    response = client.get(f"/staff/flags/{flag_id}/export")

    assert response.status_code == 200
    assert "unrelated question" not in response.text
    assert "unrelated answer" not in response.text


def test_export_records_exported_and_leaves_no_file(tmp_path, monkeypatch, client, db):
    # The app's data folder is its working directory (the database path is relative).
    monkeypatch.chdir(tmp_path)
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id)
    assert not get_flag(db, flag_id).exported

    before = sorted(tmp_path.rglob("*"))
    response = client.get(f"/staff/flags/{flag_id}/export")
    after = sorted(tmp_path.rglob("*"))

    assert response.status_code == 200
    assert after == before
    assert get_flag(db, flag_id).exported == 1


def test_closing_does_not_count_as_an_export(client, db):
    """A confirmed close is not an Export: after a reopen, closing again still needs
    the confirmation."""
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, severity="high")

    closed = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "done", "confirm": "true"},
        follow_redirects=False,
    )
    assert closed.status_code == 303
    assert not get_flag(db, flag_id).exported

    reopened = client.post(
        f"/staff/flags/{flag_id}/reopen",
        data={"reason": "more to do"},
        follow_redirects=False,
    )
    assert reopened.status_code == 303

    again = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "done"},
        follow_redirects=False,
    )
    assert again.status_code == 400
    assert "Purge" in again.text
    assert get_flag(db, flag_id).closed_at is None


def test_close_page_shows_next_purge_and_confirmation(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, severity="high")

    body = client.get(f"/staff/flags/{flag_id}").text
    assert "Next Purge" in body
    assert 'name="confirm"' in body

    client.get(f"/staff/flags/{flag_id}/export")
    body = client.get(f"/staff/flags/{flag_id}").text
    assert 'name="confirm"' not in body


def test_older_flags_table_gains_the_exported_column(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE flags (id INTEGER PRIMARY KEY, transcript_id INTEGER NOT NULL, "
        "class_label TEXT NOT NULL, card_number TEXT NOT NULL, "
        "batch_expires_at TEXT NOT NULL, message_hash TEXT, category TEXT NOT NULL, "
        "severity TEXT NOT NULL, source TEXT NOT NULL, entry_id TEXT, "
        "watchlist_version TEXT, reason TEXT, raised_at TEXT NOT NULL, "
        "closed_at TEXT, repeat_count INTEGER NOT NULL DEFAULT 0, "
        "last_repeat_at TEXT, raised_by INTEGER)"
    )
    old.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, "
        "batch_expires_at, category, severity, source, raised_at) "
        "VALUES (1, 'Period 3', '14', ?, 'content', 'high', 'watchlist', ?)",
        (NOW.isoformat(), NOW.isoformat()),
    )
    old.commit()
    old.close()

    db = connect(str(path))

    assert not get_flag(db, 1).exported


def test_high_severity_close_needs_confirmation_shows_next_purge(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, severity="high")

    response = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "done"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Purge" in response.text

    confirmed = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "done", "confirm": "true"},
        follow_redirects=False,
    )
    assert confirmed.status_code == 303


def test_high_severity_close_after_export_needs_no_confirmation(client, db):
    _sign_in_as(client, db, "librarian")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, severity="high")

    client.get(f"/staff/flags/{flag_id}/export")

    response = client.post(
        f"/staff/flags/{flag_id}/close",
        data={"outcome": "handled", "reason": "done"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_teacher_cannot_export(client, db):
    _sign_in_as(client, db, "teacher")
    transcript_id = _transcript(db)
    flag_id = _flag(db, transcript_id, escalated=True)

    response = client.get(f"/staff/flags/{flag_id}/export")
    assert response.status_code == 403


def test_counselor_can_export_only_escalated(client, db):
    _sign_in_as(client, db, "counselor")
    transcript_id = _transcript(db)
    open_flag_id = _flag(db, transcript_id, category="content")
    escalated_flag_id = _flag(db, transcript_id, escalated=True)

    assert client.get(f"/staff/flags/{open_flag_id}/export").status_code == 403
    assert client.get(f"/staff/flags/{escalated_flag_id}/export").status_code == 200
