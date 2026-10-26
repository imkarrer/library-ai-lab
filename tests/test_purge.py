"""Tests for the purge functionality."""

import os
import sqlite3
import tempfile
from datetime import UTC, datetime

import pytest

from library_assistant.config import Settings
from library_assistant.purge import purge


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
                asked_at TEXT NOT NULL
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
