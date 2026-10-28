"""Tests for flag management functions."""

import os
import sqlite3
import tempfile

import pytest

from library_assistant.access import connect
from library_assistant.flags import (
    close_flag,
    get_flag,
    open_flags,
    raise_flag,
    raise_or_repeat,
)


def test_raise_and_list_open():
    """Test raising a flag and listing open flags."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag
        flag_id = raise_flag(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
            entry_id="entry123",
            watchlist_version="v1.0",
            reason="Inappropriate content",
        )

        # Verify the flag was raised
        assert flag_id == 1

        # List open flags
        flags = open_flags(db)
        assert len(flags) == 1
        flag = flags[0]
        assert flag.id == 1
        assert flag.transcript_id == 1
        assert flag.class_label == "Test Class"
        assert flag.card_number == "12345"
        assert flag.batch_expires_at == "2023-12-31T23:59:59Z"
        assert flag.message_hash == "abc123"
        assert flag.category == "content"
        assert flag.severity == "high"
        assert flag.source == "watchlist"
        assert flag.entry_id == "entry123"
        assert flag.watchlist_version == "v1.0"
        assert flag.reason == "Inappropriate content"
        assert flag.raised_at == "2023-12-01T10:00:00Z"
        assert flag.closed_at is None

    finally:
        os.unlink(db_path)


def test_open_flags_newest_first():
    """Test that open flags are returned newest first."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise two flags with different timestamps
        raise_flag(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        raise_flag(
            db,
            transcript_id=2,
            class_label="Test Class",
            card_number="67890",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="def456",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T11:00:00Z",
        )

        # List open flags
        flags = open_flags(db)
        assert len(flags) == 2

        # Should be newest first (timestamp 11:00:00 first)
        assert flags[0].raised_at == "2023-12-01T11:00:00Z"
        assert flags[1].raised_at == "2023-12-01T10:00:00Z"

    finally:
        os.unlink(db_path)


def test_close_removes_from_open():
    """Test that closing a flag removes it from open flags list."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag
        flag_id = raise_flag(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        # Verify it's in open flags
        flags = open_flags(db)
        assert len(flags) == 1

        # Close the flag
        close_flag(
            db, flag_id, "2023-12-01T12:00:00Z", "librarian-account", "handled", "done"
        )

        # Verify it's no longer in open flags
        flags = open_flags(db)
        assert len(flags) == 0

    finally:
        os.unlink(db_path)


def test_close_clears_message_hash():
    """Test that closing a flag clears the message_hash."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag with a message hash
        flag_id = raise_flag(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        # Get the flag
        flag = get_flag(db, flag_id)
        assert flag.message_hash == "abc123"

        # Close the flag
        close_flag(
            db, flag_id, "2023-12-01T12:00:00Z", "librarian-account", "handled", "done"
        )

        # Get the flag again - message_hash should be None
        flag = get_flag(db, flag_id)
        assert flag.message_hash is None

    finally:
        os.unlink(db_path)


def test_same_card_and_message_is_repeat():
    """Test that flags with same card and message are treated as repeats."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag
        flag_id_1, _is_repeat_1 = raise_or_repeat(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        # Raise the same flag again
        flag_id_2, _is_repeat_2 = raise_or_repeat(
            db,
            transcript_id=2,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T11:00:00Z",
        )

        # Should return same flag ID and True for is_repeat
        assert flag_id_1 == flag_id_2
        assert _is_repeat_2 is True

        # Check that repeat count was incremented
        flag = get_flag(db, flag_id_1)
        assert flag.repeat_count == 1
        assert flag.last_repeat_at == "2023-12-01T11:00:00Z"

        # Check that a flag_repeats record was created
        rows = db.execute(
            "SELECT * FROM flag_repeats WHERE flag_id = ?",
            (flag_id_1,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == 2  # transcript_id should be 2

    finally:
        os.unlink(db_path)


def test_other_card_or_category_is_new_flag():
    """Test that flags with different card or category create new flags."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag
        flag_id_1, _is_repeat_1 = raise_or_repeat(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        # Raise a flag with different card number
        flag_id_2, is_repeat_2 = raise_or_repeat(
            db,
            transcript_id=2,
            class_label="Test Class",
            card_number="67890",  # Different card
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T11:00:00Z",
        )

        # Should create a new flag
        assert flag_id_1 != flag_id_2
        assert is_repeat_2 is False

        # Raise a flag with different category
        flag_id_3, is_repeat_3 = raise_or_repeat(
            db,
            transcript_id=3,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="behavior",  # Different category
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T12:00:00Z",
        )

        # Should create a new flag
        assert flag_id_1 != flag_id_3
        assert flag_id_2 != flag_id_3
        assert is_repeat_3 is False

    finally:
        os.unlink(db_path)


def test_other_batch_same_card_number_is_new_flag():
    """Test that flags with same card but different batch create new flags."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag
        flag_id_1, _is_repeat_1 = raise_or_repeat(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        # Raise a flag with same card but different batch
        flag_id_2, is_repeat_2 = raise_or_repeat(
            db,
            transcript_id=2,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2024-12-31T23:59:59Z",  # Different batch
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T11:00:00Z",
        )

        # Should create a new flag
        assert flag_id_1 != flag_id_2
        assert is_repeat_2 is False

    finally:
        os.unlink(db_path)


def test_after_close_same_message_is_new_flag():
    """Test that flags created after closing are treated as new flags."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Raise a flag
        flag_id_1, _is_repeat_1 = raise_or_repeat(
            db,
            transcript_id=1,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T10:00:00Z",
        )

        # Close the flag
        close_flag(
            db,
            flag_id_1,
            "2023-12-01T12:00:00Z",
            "librarian-account",
            "handled",
            "done",
        )

        # Raise the same flag again
        flag_id_2, is_repeat_2 = raise_or_repeat(
            db,
            transcript_id=2,
            class_label="Test Class",
            card_number="12345",
            batch_expires_at="2023-12-31T23:59:59Z",
            message_hash="abc123",
            category="content",
            severity="high",
            source="watchlist",
            raised_at="2023-12-01T13:00:00Z",
        )

        # Should create a new flag
        assert flag_id_1 != flag_id_2
        assert is_repeat_2 is False

    finally:
        os.unlink(db_path)


def test_unknown_source_is_refused():
    """Test that raising a flag with an unknown source raises IntegrityError."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = connect(db_path)

        # Try to raise a flag with an invalid source
        with pytest.raises(sqlite3.IntegrityError):
            raise_flag(
                db,
                transcript_id=1,
                class_label="Test Class",
                card_number="12345",
                batch_expires_at="2023-12-31T23:59:59Z",
                message_hash="abc123",
                category="content",
                severity="high",
                source="invalid_source",  # This should fail
                raised_at="2023-12-01T10:00:00Z",
            )

    finally:
        os.unlink(db_path)
