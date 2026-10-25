from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_clock, get_db, get_settings

RECORD = Record(
    id="loc0001",
    title="Where the wild things are",
    author="Sendak, Maurice.",
    subjects="Monsters",
    summary="A boy sails to an island of monsters.",
    call_number="PZ7.S47 Wh",
)


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


@pytest.fixture
def settings():
    return Settings(
        openai_endpoint="http://model.example.com:8080", openai_model="llama3"
    )


@pytest.fixture
def client(settings):
    import sqlite3

    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            card_number TEXT NOT NULL,
            class_label TEXT NOT NULL,
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,
            asked_at TEXT NOT NULL
        )
        """
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    db.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
        (
            "session-1",
            "14",
            "Period 3",
            now.isoformat(),
            (now + timedelta(hours=1)).isoformat(),
        ),
    )
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: now
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


def _fake_openai_server(host_calls: list[httpx.URL]):
    """Stands in for the configured OpenAI-compatible endpoint at the transport
    level, used by every httpx.AsyncClient in the process. Records every URL
    asked of it, so a test can prove no outbound call ever reaches anywhere else.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host_calls.append(request.url)
        body = (
            b'data: {"choices":[{"delta":{"content":"Cats"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":" are great."}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    return handle_async_request


def test_ask_streams_answer_and_renders_citations(client, monkeypatch):
    test_client, _db = client
    host_calls: list[httpx.URL] = []
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        _fake_openai_server(host_calls),
    )

    response = test_client.post("/session/session-1/ask", json={"question": "cats?"})

    assert response.status_code == 200
    assert "Cats are great." in response.text
    assert "Citation: PZ7.S47 Wh" in response.text


def test_only_the_configured_endpoint_is_contacted(client, monkeypatch, settings):
    test_client, _db = client
    host_calls: list[httpx.URL] = []
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        _fake_openai_server(host_calls),
    )

    test_client.post("/session/session-1/ask", json={"question": "cats?"})

    configured = httpx.URL(settings.openai_endpoint)
    assert host_calls, "expected at least one outbound call"
    for url in host_calls:
        assert url.host == configured.host
        assert url.port == configured.port


def test_ask_without_a_valid_session_is_refused(client):
    test_client, _db = client
    response = test_client.post(
        "/session/no-such-session/ask", json={"question": "cats?"}
    )
    assert response.status_code == 400


def test_ask_stores_the_exchange_in_the_transcript(client, monkeypatch):
    test_client, db = client
    host_calls: list[httpx.URL] = []
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        _fake_openai_server(host_calls),
    )

    test_client.post("/session/session-1/ask", json={"question": "cats?"})

    row = db.execute(
        "SELECT session_id, question, answer, citations FROM transcripts"
    ).fetchone()
    assert row == ("session-1", "cats?", "Cats are great.", "PZ7.S47 Wh")
