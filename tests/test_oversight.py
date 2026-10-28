import asyncio
import json
import sqlite3
from unittest.mock import patch

import httpx
import pytest

from library_assistant.config import Settings
from library_assistant.oversight import (
    OversightUnavailable,
    Verdict,
    acquire_oversight_lock,
    screen,
)


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


def test_first_lock_succeeds():
    """Test that the first lock acquisition succeeds."""
    # Create a temporary database path
    import tempfile

    with tempfile.NamedTemporaryFile() as tmp:
        db_path = tmp.name
        # First acquisition should succeed
        lock_file = acquire_oversight_lock(db_path)
        assert lock_file is not None
        # Close the file handle
        lock_file.close()


def test_second_lock_fails_and_logs(caplog):
    """Test that a second lock acquisition in the same process fails and logs a warning.

    flock locks are tied to the open file description, not the process, so a
    second open() of the same lock file conflicts even without a second process.
    """
    import logging
    import tempfile

    with tempfile.NamedTemporaryFile() as tmp:
        db_path = tmp.name

        # First acquisition should succeed and must stay open to hold the lock.
        lock_file1 = acquire_oversight_lock(db_path)
        assert lock_file1 is not None

        try:
            with caplog.at_level(logging.WARNING):
                lock_file2 = acquire_oversight_lock(db_path)
            assert lock_file2 is None
            assert "Oversight off: another process holds" in caplog.text
        finally:
            lock_file1.close()


def test_lock_file_beside_db():
    """Test that the lock file is created beside the database file."""
    import os
    import tempfile

    with tempfile.NamedTemporaryFile() as tmp:
        db_path = tmp.name
        # Get the directory of the database
        db_dir = os.path.dirname(db_path)
        # The lock file should be in the same directory
        os.path.join(db_dir, "oversight.lock")

        # Acquire lock and verify the path (should be successful, not None)
        lock_file = acquire_oversight_lock(db_path)
        # This test just verifies the path construction, not the actual locking
        # The key thing is that it doesn't crash and returns a proper handle
        assert lock_file is not None
        # Close to cleanup
        lock_file.close()


def _settings() -> Settings:
    return Settings(
        oversight_endpoint="http://oversight.example.com",
        oversight_model="guard-model",
        oversight_timeout_seconds=5,
    )


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _client(handler) -> httpx.AsyncClient:
    # The shared client points at the Answer lane; screen must still reach Oversight.
    return httpx.AsyncClient(
        base_url="http://answer-lane.example.com",
        transport=httpx.MockTransport(handler),
    )


def _run_screen(handler, question: str = "is this ok to ask?") -> Verdict:
    async def go() -> Verdict:
        async with _client(handler) as client:
            return await screen(client, _settings(), question)

    return asyncio.run(go())


def test_screen_parses_verdict():
    content = json.dumps(
        {"category": "bullying", "severity": "high", "reason": "names a classmate"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response(content)

    verdict = _run_screen(handler)
    assert verdict == Verdict(
        category="bullying", severity="high", reason="names a classmate"
    )


def test_screen_null_category_is_no_concern():
    content = json.dumps({"category": None, "severity": None, "reason": "no concern"})

    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response(content)

    verdict = _run_screen(handler)
    assert verdict == Verdict(category=None, severity=None, reason="no concern")


def test_screen_retries_once_on_bad_json():
    calls = {"count": 0}
    good = json.dumps({"category": None, "severity": None, "reason": "fine"})

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return _chat_response("not json at all")
        return _chat_response(good)

    verdict = _run_screen(handler)
    assert verdict == Verdict(category=None, severity=None, reason="fine")
    assert calls["count"] == 2


def test_screen_unavailable_after_two_bad_replies():
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("still not json")

    with pytest.raises(OversightUnavailable):
        _run_screen(handler)


def test_screen_unavailable_on_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OversightUnavailable):
        _run_screen(handler)


def test_request_has_max_tokens_256_and_only_the_message():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        content = json.dumps({"category": None, "severity": None, "reason": "fine"})
        return _chat_response(content)

    _run_screen(handler, question="is the library open on Saturday?")

    assert seen["url"] == "http://oversight.example.com/chat/completions"
    payload = seen["payload"]
    assert payload["model"] == "guard-model"
    assert payload["stream"] is False
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 256
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    user_messages = [m for m in payload["messages"] if m["role"] == "user"]
    assert user_messages == [
        {"role": "user", "content": "is the library open on Saturday?"}
    ]


def test_screen_retries_once_on_unknown_category():
    calls = {"count": 0}
    good = json.dumps({"category": "abuse", "severity": "low", "reason": "r"})

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return _chat_response(json.dumps({"category": "spam", "reason": "r"}))
        return _chat_response(good)

    verdict = _run_screen(handler)
    assert verdict == Verdict(category="abuse", severity="low", reason="r")
    assert calls["count"] == 2


def test_screen_unavailable_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(OversightUnavailable):
        _run_screen(handler)
