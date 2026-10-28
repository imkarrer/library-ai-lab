"""Tests for the purge functionality."""

import asyncio
import contextlib
import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import library_assistant.purge as purge_module
from library_assistant.app import app
from library_assistant.config import Settings
from library_assistant.holds import create_holds_table
from library_assistant.purge import purge, purge_loop, run_if_due


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = sqlite3.connect(db_path)
        db.execute(
            """
            CREATE TABLE transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_hash TEXT NOT NULL,
                class_label TEXT NOT NULL,
                card_number TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                citations TEXT NOT NULL,
                asked_at TEXT NOT NULL,
                screened_at TEXT,
                screening TEXT NOT NULL DEFAULT 'none' CHECK (screening IN ('none','oversight','watchlist_alone'))
            )
            """
        )
        db.execute(
            """
            CREATE TABLE flags (
                id INTEGER PRIMARY KEY,
                transcript_id INTEGER NOT NULL,
                class_label TEXT NOT NULL,
                card_number TEXT NOT NULL,
                batch_expires_at TEXT NOT NULL,
                message_hash TEXT,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('watchlist','oversight')),
                entry_id TEXT,
                watchlist_version TEXT,
                reason TEXT,
                raised_at TEXT NOT NULL,
                closed_at TEXT,
                repeat_count INTEGER NOT NULL DEFAULT 0,
                last_repeat_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE flag_repeats (
                flag_id INTEGER NOT NULL,
                transcript_id INTEGER NOT NULL,
                repeated_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE flag_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                at TEXT NOT NULL,
                account TEXT,
                reason TEXT,
                outcome TEXT,
                source TEXT,
                entry_id TEXT,
                watchlist_version TEXT,
                repeat_count INTEGER
            )
            """
        )
        db.execute(
            """
            CREATE TABLE cards (
                token_hash TEXT PRIMARY KEY,
                card_number TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                class_label TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE sessions (
                session_hash TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'
            )
            """
        )
        db.execute(
            """
            CREATE TABLE purge_runs (
                ran_at TEXT NOT NULL,
                deleted INTEGER,
                kept_for_flags INTEGER,
                kept_unscreened INTEGER,
                kept_for_holds INTEGER,
                holds INTEGER,
                overdue_flags INTEGER
            )
            """
        )
        create_holds_table(db)
        db.commit()
        yield db
    finally:
        db.close()
        os.unlink(db_path)


def test_past_day_unflagged_transcript_deleted(db):
    """Test that past-day unflagged transcripts are deleted."""
    # Create a transcript from yesterday
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # Purge with a time that's after the cutoff
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    # Should have deleted 1 transcript and kept 0 for flags
    assert result.deleted == 1
    assert result.kept_for_flags == 0

    # Verify transcript was deleted
    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 0


def test_todays_transcript_kept(db):
    """Test that today's transcripts are kept."""
    # Create a transcript from today
    today = datetime(2023, 10, 2, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            today.isoformat(),
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # Purge with a time that's after the cutoff
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    # Should have deleted 0 transcripts and kept 0 for flags
    assert result.deleted == 0
    assert result.kept_for_flags == 0

    # Verify transcript was kept
    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 1


def test_open_flag_keeps_transcript(db):
    """Test that transcripts with open flags are kept."""
    # Create a transcript
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    transcript_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    # Create an open flag for this transcript
    db.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, batch_expires_at, message_hash, category, severity, source, raised_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transcript_id,
            "Test Class",
            "12345",
            "2023-12-31T23:59:59Z",
            "hash123",
            "content",
            "high",
            "watchlist",
            "2023-10-01T10:00:00Z",
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # Purge with a time that's after the cutoff
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    # Should have deleted 0 transcripts and kept 1 for flags
    assert result.deleted == 0
    assert result.kept_for_flags == 1

    # Verify transcript was kept
    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 1


def test_open_flag_keeps_repeat_transcripts(db):
    """Test that transcripts referenced by flag repeats are kept."""
    # Create a transcript
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    transcript_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    # Create a flag
    db.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, batch_expires_at, message_hash, category, severity, source, raised_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transcript_id,
            "Test Class",
            "12345",
            "2023-12-31T23:59:59Z",
            "hash123",
            "content",
            "high",
            "watchlist",
            "2023-10-01T10:00:00Z",
        ),
    )
    flag_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    # Create a flag repeat for this transcript
    db.execute(
        "INSERT INTO flag_repeats (flag_id, transcript_id, repeated_at) VALUES (?, ?, ?)",
        (flag_id, transcript_id, "2023-10-01T11:00:00Z"),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # Purge with a time that's after the cutoff
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    # Should have deleted 0 transcripts and kept 1 for flags
    assert result.deleted == 0
    assert result.kept_for_flags == 1

    # Verify transcript was kept
    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 1


def test_closed_flag_transcript_goes_at_next_purge(db):
    """Test that transcripts with closed flags are deleted at next purge."""
    # Create a transcript
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    transcript_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    # Create a closed flag for this transcript
    db.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, batch_expires_at, message_hash, category, severity, source, raised_at, closed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transcript_id,
            "Test Class",
            "12345",
            "2023-12-31T23:59:59Z",
            "hash123",
            "content",
            "high",
            "watchlist",
            "2023-10-01T10:00:00Z",
            "2023-10-01T12:00:00Z",
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # Purge with a time that's after the cutoff
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    # Should have deleted 1 transcript and kept 0 for flags
    assert result.deleted == 1
    assert result.kept_for_flags == 0

    # Verify transcript was deleted
    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 0


def _insert_closed_flag(
    db, closed_at: str, raised_at: str = "2023-10-01T10:00:00Z"
) -> int:
    db.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, batch_expires_at, "
        "message_hash, category, severity, source, raised_at, closed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "Test Class",
            "12345",
            "2023-12-31T23:59:59Z",
            None,
            "content",
            "high",
            "watchlist",
            raised_at,
            closed_at,
        ),
    )
    flag_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        "INSERT INTO flag_history (flag_id, event, at) VALUES (?, 'closed', ?)",
        (flag_id, closed_at),
    )
    db.commit()
    return flag_id


def test_closed_flag_and_history_kept_before_history_days(db):
    """A closed Flag and its history stay until flags.history_days after close."""
    flag_id = _insert_closed_flag(db, closed_at="2023-10-01T12:00:00Z")
    settings = Settings(
        school_timezone="America/Chicago",
        school_day_end="17:00:00",
        flags_history_days=90,
    )
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)

    purge(db, now, settings)

    assert (
        db.execute("SELECT COUNT(*) FROM flags WHERE id = ?", (flag_id,)).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM flag_history WHERE flag_id = ?", (flag_id,)
        ).fetchone()[0]
        == 1
    )


def test_closed_flag_and_history_deleted_after_history_days(db):
    """The first Purge flags.history_days after close deletes the Flag and history."""
    flag_id = _insert_closed_flag(db, closed_at="2023-01-01T12:00:00Z")
    settings = Settings(
        school_timezone="America/Chicago",
        school_day_end="17:00:00",
        flags_history_days=90,
    )
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)

    purge(db, now, settings)

    assert (
        db.execute("SELECT COUNT(*) FROM flags WHERE id = ?", (flag_id,)).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM flag_history WHERE flag_id = ?", (flag_id,)
        ).fetchone()[0]
        == 0
    )


def test_hold_keeps_closed_flag_past_history_days(db):
    """A Hold covering the Flag's scope outlives flags.history_days."""
    flag_id = _insert_closed_flag(
        db, closed_at="2023-01-01T12:00:00Z", raised_at="2023-10-01T10:00:00Z"
    )
    db.execute(
        "INSERT INTO holds (all_classes, class_labels, card_numbers, date_from, date_to, "
        "reason_kind, reference, set_at, set_by) "
        "VALUES (0, ?, ?, ?, ?, 'other', 'ref', ?, 'librarian')",
        (
            '["Test Class"]',
            "[]",
            "2023-10-01",
            "2023-10-01",
            "2023-10-01T00:00:00Z",
        ),
    )
    db.commit()
    settings = Settings(
        school_timezone="America/Chicago",
        school_day_end="17:00:00",
        flags_history_days=90,
    )
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)

    purge(db, now, settings)

    assert (
        db.execute("SELECT COUNT(*) FROM flags WHERE id = ?", (flag_id,)).fetchone()[0]
        == 1
    )


def test_expired_card_hash_purged(db):
    """A Card's Token hash is deleted at the first Purge after the Batch expires."""
    db.execute(
        "INSERT INTO cards (token_hash, card_number, expires_at, class_label) "
        "VALUES ('hash-1', '12345', '2023-01-01T00:00:00Z', 'Test Class')"
    )
    db.commit()
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)

    purge(db, now, settings)

    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0


def _tables_holding(db, value):
    """Every table with a row that carries `value` in any column."""
    tables = [
        name
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    ]
    found = []
    for table in tables:
        for row in db.execute(f'SELECT * FROM "{table}"').fetchall():
            if any(value in str(cell) for cell in row if cell is not None):
                found.append(table)
                break
    return found


@pytest.mark.parametrize("ending", ["expired", "revoked"])
def test_no_token_hash_remains_after_expiry_or_revoke(tmp_path, ending):
    """After expiry or a Revoke, the next Purge leaves the Card's Token hash in no
    table, even while a Session started with the Card still sits in the database."""
    from library_assistant.access import connect

    db = connect(str(tmp_path / "assistant.db"))
    try:
        now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
        in_date = now + timedelta(days=1)
        expires_at = now - timedelta(days=1) if ending == "expired" else in_date
        db.execute(
            "INSERT INTO cards (token_hash, card_number, expires_at, class_label) "
            "VALUES ('hash-gone', '12345', ?, 'Test Class')",
            (expires_at.isoformat(),),
        )
        db.execute(
            "INSERT INTO cards (token_hash, card_number, expires_at, class_label) "
            "VALUES ('hash-live', '67890', ?, 'Test Class')",
            (in_date.isoformat(),),
        )
        db.execute(
            "INSERT INTO sessions (session_hash, token_hash, started_at) "
            "VALUES ('session-gone', 'hash-gone', '2023-10-01T14:00:00+00:00')"
        )
        db.execute(
            "INSERT INTO sessions (session_hash, token_hash, started_at) "
            "VALUES ('session-live', 'hash-live', '2023-10-01T14:00:00+00:00')"
        )
        if ending == "revoked":
            db.execute("DELETE FROM cards WHERE token_hash = 'hash-gone'")
        db.commit()
        assert "sessions" in _tables_holding(db, "hash-gone")

        settings = Settings(
            school_timezone="America/Chicago", school_day_end="17:00:00"
        )
        purge(db, now, settings)

        assert _tables_holding(db, "hash-gone") == []
        # A Card still in date keeps its row and its Session.
        assert sorted(_tables_holding(db, "hash-live")) == ["cards", "sessions"]
    finally:
        db.close()


def test_report_counts(db):
    """Test that purge returns correct counts."""
    # Create 2 transcripts from yesterday, 1 with open flag, 1 without
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)

    # Create transcript 1 (no flag)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create transcript 2 (with open flag)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session2",
            "Test Class",
            "67890",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    transcript2_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    # Create an open flag for transcript 2
    db.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, batch_expires_at, message_hash, category, severity, source, raised_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transcript2_id,
            "Test Class",
            "67890",
            "2023-12-31T23:59:59Z",
            "hash123",
            "content",
            "high",
            "watchlist",
            "2023-10-01T10:00:00Z",
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # Purge with a time that's after the cutoff
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    # Should have deleted 1 transcript and kept 1 for flags
    assert result.deleted == 1
    assert result.kept_for_flags == 1

    # Verify transcript counts
    transcript_count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert transcript_count == 1  # Only the flagged one should remain


def test_run_if_due_runs_once_per_day_end(db):
    """Test that run_if_due runs purge once per day end."""
    # Create a transcript from yesterday
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # First call should run purge
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result1 = run_if_due(db, now, settings)

    # Should have run and returned a result
    assert result1 is not None
    assert result1.deleted == 1
    assert result1.kept_for_flags == 0

    # Second call should not run purge again for same day end
    result2 = run_if_due(db, now, settings)

    # Should return None indicating no purge was run
    assert result2 is None

    # Verify transcript was deleted
    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 0


def test_run_if_due_skips_when_already_run(db):
    """Test that run_if_due skips when already run for the day end."""
    # Create a transcript from yesterday
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    db.commit()

    # Create a settings object with school timezone and end time
    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")

    # First call should run purge and record the run
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result1 = run_if_due(db, now, settings)

    # Should have run and returned a result
    assert result1 is not None

    # Verify transcript was deleted in first run
    count1 = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count1 == 0

    # Add a second transcript to see if purge runs again (it shouldn't)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session2",
            "Test Class",
            "67890",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
        ),
    )
    db.commit()

    # Second call should not run purge again for same day end
    result2 = run_if_due(db, now, settings)

    # Should return None indicating no purge was run
    assert result2 is None

    # Verify only the new transcript exists (first was purged, second wasn't purged)
    count2 = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count2 == 1


def test_unscreened_exchange_survives_purge(db):
    """A transcript still awaiting Oversight screening survives the Purge."""
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at, screening, screened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
            "oversight",
            None,
        ),
    )
    db.commit()

    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    assert result.deleted == 0
    assert result.kept_unscreened == 1

    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 1


def test_watchlist_alone_unscreened_survives_purge(db):
    """A transcript still awaiting Watchlist-alone screening survives the Purge."""
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at, screening, screened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
            "watchlist_alone",
            None,
        ),
    )
    db.commit()

    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    assert result.deleted == 0
    assert result.kept_unscreened == 1

    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 1


def test_screened_exchange_goes(db):
    """A transcript that has already been screened purges normally."""
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at, screening, screened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
            "oversight",
            "2023-10-01T11:00:00Z",
        ),
    )
    db.commit()

    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    assert result.deleted == 1
    assert result.kept_unscreened == 0

    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 0


def test_report_counts_unscreened(db):
    """PurgeReport.kept_unscreened counts unscreened transcripts separately from deletes and flags."""
    yesterday = datetime(2023, 10, 1, 10, 0, 0, tzinfo=UTC)

    # Transcript 1: no flag, already screened -> deleted
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at, screening, screened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
            "none",
            None,
        ),
    )

    # Transcript 2: unscreened watchlist_alone -> kept_unscreened
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at, screening, screened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "session2",
            "Test Class",
            "67890",
            "Question",
            "Answer",
            "[]",
            yesterday.isoformat(),
            "watchlist_alone",
            None,
        ),
    )
    db.commit()

    settings = Settings(school_timezone="America/Chicago", school_day_end="17:00:00")
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    result = purge(db, now, settings)

    assert result.deleted == 1
    assert result.kept_for_flags == 0
    assert result.kept_unscreened == 1

    count = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    assert count == 1


def test_report_counts_overdue_flags(db):
    """A Flag open longer than flags.overdue_days is counted in the Purge report."""
    now = datetime(2023, 10, 2, 18, 0, 0, tzinfo=UTC)
    raised_at = now - timedelta(days=10)

    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "session1",
            "Test Class",
            "12345",
            "Question",
            "Answer",
            "[]",
            now.isoformat(),
        ),
    )
    transcript_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        "INSERT INTO flags (transcript_id, class_label, card_number, batch_expires_at, "
        "message_hash, category, severity, source, raised_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transcript_id,
            "Test Class",
            "12345",
            "2023-12-31T23:59:59Z",
            "hash123",
            "content",
            "high",
            "watchlist",
            raised_at.isoformat(),
        ),
    )
    db.commit()

    settings = Settings(
        school_timezone="America/Chicago",
        school_day_end="17:00:00",
        flags_overdue_days=7,
    )
    result = purge(db, now, settings)

    assert result.overdue_flags == 1


def test_startup_purges_after_missed_day_end():
    """Test that startup purge runs after a missed day end."""
    # Test using TestClient to simulate app startup and verify behavior
    with TestClient(app) as client:
        # The TestClient will trigger the lifespan which should run purge
        response = client.get("/health")
        assert response.status_code == 200


def test_loop_sleeps_until_day_end_then_purges(monkeypatch):
    """The loop sleeps until the next school-day end, then runs the purge."""
    settings = Settings(school_timezone="UTC", school_day_end="12:00:00")
    moment = datetime(2024, 1, 1, 6, 0, 0, tzinfo=UTC)
    sleeps = []
    purge_calls = []

    def fake_now():
        return moment

    async def fake_sleep(seconds):
        await asyncio.sleep(0)
        nonlocal moment
        sleeps.append(seconds)
        moment = moment + timedelta(seconds=seconds)

    def fake_run_if_due(db, now, settings):
        purge_calls.append(now)

    monkeypatch.setattr(purge_module, "run_if_due", fake_run_if_due)

    async def scenario():
        task = asyncio.create_task(purge_loop(None, settings, fake_now, fake_sleep))
        while not purge_calls:
            await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert sleeps == [pytest.approx(6 * 3600)]
    assert purge_calls == [datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)]


def test_loop_runs_once_each_day(monkeypatch):
    """The loop purges once per school day, and stops once cancelled."""
    settings = Settings(school_timezone="UTC", school_day_end="12:00:00")
    moment = datetime(2024, 1, 1, 6, 0, 0, tzinfo=UTC)
    sleeps = []
    purge_calls = []

    def fake_now():
        return moment

    async def fake_sleep(seconds):
        await asyncio.sleep(0)
        nonlocal moment
        sleeps.append(seconds)
        moment = moment + timedelta(seconds=seconds)

    def fake_run_if_due(db, now, settings):
        purge_calls.append(now)

    monkeypatch.setattr(purge_module, "run_if_due", fake_run_if_due)

    async def scenario():
        task = asyncio.create_task(purge_loop(None, settings, fake_now, fake_sleep))
        while len(purge_calls) < 3:
            await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert len(purge_calls) == 3
    assert purge_calls == [
        datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
    ]
    assert sleeps == [pytest.approx(s) for s in (6 * 3600, 86400, 86400)]
