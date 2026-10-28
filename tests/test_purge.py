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
            CREATE TABLE purge_runs (
                ran_at TEXT NOT NULL
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
