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
        close_flag(db, flag_id, "2023-12-01T12:00:00Z")

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
        close_flag(db, flag_id, "2023-12-01T12:00:00Z")

        # Get the flag again - message_hash should be None
        flag = get_flag(db, flag_id)
        assert flag.message_hash is None

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
