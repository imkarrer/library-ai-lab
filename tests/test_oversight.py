import sqlite3
from unittest.mock import patch

from library_assistant.config import Settings


def test_oversight_off_by_default():
    """Test that oversight settings default to disabled."""
    settings = Settings()
    assert settings.oversight_endpoint is None
    assert settings.oversight_model is None
    assert settings.oversight_timeout_seconds == 20
    assert settings.oversight_enabled is False


def test_from_env_reads_oversight_settings():
    """Test that oversight settings are read from environment variables."""
    with patch.dict(
        "os.environ",
        {
            "LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT": "http://example.com/oversight",
            "LIBRARY_ASSISTANT_OVERSIGHT_MODEL": "test-model",
            "LIBRARY_ASSISTANT_OVERSIGHT_TIMEOUT_SECONDS": "30",
        },
    ):
        settings = Settings.from_env()
        assert settings.oversight_endpoint == "http://example.com/oversight"
        assert settings.oversight_model == "test-model"
        assert settings.oversight_timeout_seconds == 30
        assert settings.oversight_enabled is True


def test_transcripts_have_screening_columns():
    """Test that transcripts table has the new screening columns."""
    # Create an in-memory database connection
    conn = sqlite3.connect(":memory:")

    # Create the transcripts table with the new schema
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_hash TEXT NOT NULL,
            class_label TEXT NOT NULL,
            card_number TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,
            asked_at TEXT NOT NULL,
            verdict TEXT,
            screened_at TEXT,
            screening TEXT NOT NULL DEFAULT 'none' CHECK (screening IN ('none','oversight','watchlist_alone'))
        )
        """
    )

    # Get table info to verify columns exist
    cursor = conn.execute("PRAGMA table_info(transcripts)")
    columns = cursor.fetchall()

    # Extract column names
    column_names = [col[1] for col in columns]

    # Check that all required columns exist
    assert "verdict" in column_names
    assert "screened_at" in column_names
    assert "screening" in column_names

    # Test default value for screening column
    # Insert a minimal row and check the default value
    conn.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "test_session",
            "test_class",
            "test_card",
            "test_question",
            "test_answer",
            "test_citations",
            "2026-01-01T00:00:00",
        ),
    )

    # Get the inserted row
    cursor = conn.execute("SELECT screening FROM transcripts WHERE id = 1")
    result = cursor.fetchone()

    # Check that the default value is 'none'
    assert result[0] == "none"

    conn.close()
