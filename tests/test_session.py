"""Grounded answers in a Session, through the real Card sign-in flow: register a
Batch, sign in with a Card, then ask with the cookie sign-in set."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    REFUSAL_TEXT,
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    get_registration_key,
)
from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings
from library_assistant.routers.session import BANNER_TEXT

REGISTRATION_KEY = "s3cret-registration-key"
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(hours=6)

RECORD = Record(
    id="00057791",
    title="The story of Ferdinand /",
    author="Leaf, Munro,",
    subjects="Bulls -- Fiction",
    summary="A bull who would rather smell flowers than fight.",
    call_number="PZ10.3.L47 St",
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
def clock():
    return {"now": NOW}


@pytest.fixture
def client(settings, clock):
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_registration_key] = lambda: REGISTRATION_KEY
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        test_client = TestClient(app)
        response = test_client.post(
            "/batches",
            json={
                "registration_key": REGISTRATION_KEY,
                "cards": [
                    {"token": "token-14", "card_number": "14"},
                    {"token": "token-15", "card_number": "15"},
                ],
                "expires_at": EXPIRES.isoformat(),
                "class_label": "Period 3",
            },
        )
        assert response.status_code == 201
        yield test_client, db
    finally:
        app.dependency_overrides.clear()


def _sign_in(test_client: TestClient, token: str = "token-14") -> str:
    response = test_client.post("/card", json={"token": token})
    assert response.status_code == 200
    return response.cookies[SESSION_COOKIE]


@pytest.fixture
def model_calls(monkeypatch) -> list[httpx.URL]:
    """Stands in for the configured OpenAI-compatible endpoint at the transport level,
    used by every httpx.AsyncClient in the process, and records every URL asked of it,
    so a test can prove no outbound call reaches anywhere else."""
    calls: list[httpx.URL] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        body = (
            b'data: {"choices":[{"delta":{"content":"Try Ferdinand"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":", a gentle bull."}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    return calls


def test_signed_in_card_gets_a_streamed_grounded_answer(client, model_calls):
    test_client, _ = client
    _sign_in(test_client)

    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    assert response.status_code == 200
    assert "Try Ferdinand, a gentle bull." in response.text
    assert "Citation: The story of Ferdinand / (PZ10.3.L47 St)" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_only_the_configured_endpoint_is_contacted(client, model_calls, settings):
    test_client, _ = client
    _sign_in(test_client)

    test_client.post("/ask", json={"question": "bulls?"})

    configured = httpx.URL(settings.openai_endpoint)
    assert model_calls, "expected at least one outbound call"
    for url in model_calls:
        assert (url.host, url.port) == (configured.host, configured.port)


def test_asking_without_a_session_is_refused(client, model_calls):
    test_client, _ = client
    assert test_client.post("/ask", json={"question": "bulls?"}).status_code == 403
    test_client.cookies.set(SESSION_COOKIE, "made-up")
    assert test_client.post("/ask", json={"question": "bulls?"}).status_code == 403
    assert model_calls == []


def test_the_cookie_is_a_fresh_session_id_never_the_token_or_its_stored_hash(client):
    test_client, db = client
    session_id = _sign_in(test_client)
    stored = [
        value
        for row in db.execute("SELECT * FROM cards").fetchall()
        + db.execute("SELECT * FROM sessions").fetchall()
        for value in row
    ]
    assert session_id != "token-14"
    assert session_id not in stored


def test_two_sign_ins_are_two_sessions(client):
    test_client, db = client
    first = _sign_in(test_client)
    second = _sign_in(test_client)
    assert first != second
    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 2


def test_revoking_the_card_ends_its_session(client, model_calls):
    test_client, _ = client
    _sign_in(test_client)
    response = test_client.post(
        "/batches/revoke-card",
        json={
            "registration_key": REGISTRATION_KEY,
            "class_label": "Period 3",
            "card_number": "14",
            "expires_at": EXPIRES.isoformat(),
        },
    )
    assert response.status_code == 200
    assert test_client.post("/ask", json={"question": "bulls?"}).status_code == 403


def test_the_batch_expiring_ends_its_session(client, clock, model_calls):
    test_client, _ = client
    _sign_in(test_client)
    clock["now"] = EXPIRES + timedelta(seconds=1)
    assert test_client.post("/ask", json={"question": "bulls?"}).status_code == 403


def test_finished_ends_the_session(client, model_calls):
    test_client, db = client
    _sign_in(test_client)
    test_client.post("/card/finish")
    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    test_client.cookies.clear()
    assert test_client.post("/ask", json={"question": "bulls?"}).status_code == 403


def test_the_exchange_is_stored_against_the_session_not_its_cookie(client, model_calls):
    test_client, db = client
    session_id = _sign_in(test_client)

    test_client.post("/ask", json={"question": "a book about bulls?"})

    session_hash, question, answer, citations = db.execute(
        "SELECT session_hash, question, answer, citations FROM transcripts"
    ).fetchone()
    assert session_hash == db.execute("SELECT session_hash FROM sessions").fetchone()[0]
    assert session_hash != session_id
    assert (question, answer, citations) == (
        "a book about bulls?",
        "Try Ferdinand, a gentle bull.",
        RECORD.id,
    )


def test_chat_page_shows_the_banner_and_needs_a_session(client):
    test_client, _ = client
    assert test_client.get("/chat").status_code == 403
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    assert BANNER_TEXT == "This can be wrong, check the source."
    assert BANNER_TEXT in page.text
    assert "Period 3" in page.text and "card 14" in page.text
    assert "End session" in page.text


def test_question_is_recorded_on_arrival(client, monkeypatch):
    """The row exists, with its Class label and Card number, before the model replies."""
    test_client, db = client
    _sign_in(test_client)
    seen_by_model: list[tuple] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        seen_by_model.extend(
            db.execute(
                "SELECT class_label, card_number, question, answer FROM transcripts"
            ).fetchall()
        )
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    test_client.post("/ask", json={"question": "a book about bulls?"})

    assert seen_by_model == [("Period 3", "14", "a book about bulls?", "")]


def test_answer_is_filled_in_after_stream(client, model_calls):
    test_client, db = client
    _sign_in(test_client)
    test_client.post("/ask", json={"question": "a book about bulls?"})

    rows = db.execute(
        "SELECT class_label, card_number, answer, citations FROM transcripts"
    ).fetchall()
    assert rows == [("Period 3", "14", "Try Ferdinand, a gentle bull.", RECORD.id)]


def test_exchange_keeps_its_labels_after_the_card_is_revoked(client, model_calls):
    test_client, db = client
    _sign_in(test_client)
    test_client.post("/ask", json={"question": "a book about bulls?"})
    test_client.post(
        "/batches/revoke-card",
        json={
            "registration_key": REGISTRATION_KEY,
            "class_label": "Period 3",
            "card_number": "14",
            "expires_at": EXPIRES.isoformat(),
        },
    )
    assert (
        db.execute("SELECT count(*) FROM cards WHERE card_number = '14'").fetchone()[0]
        == 0
    )
    assert db.execute(
        "SELECT class_label, card_number FROM transcripts"
    ).fetchall() == [("Period 3", "14")]


def test_model_error_still_finishes_the_exchange_with_what_was_shown(
    client, monkeypatch
):
    test_client, db = client
    _sign_in(test_client)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("model server down")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    with pytest.raises(httpx.ConnectError):
        test_client.post("/ask", json={"question": "a book about bulls?"})

    assert db.execute(
        "SELECT question, answer, citations FROM transcripts"
    ).fetchall() == [("a book about bulls?", "", "")]


def test_chat_page_has_end_session_button(client):
    """Test that the chat page has the new 'End session' button."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    assert "End session" in page.text


def test_refusal_shown_chat_page_script_reads_detail_on_403(client):
    """The /ask submit handler reads `detail` from the 403 JSON body."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    assert "response.status === 403" in page.text
    assert "data.detail" in page.text
    assert '"question").disabled = true' in page.text


def test_refusal_shown_chat_page_has_refusal_text_from_access(client):
    """The refusal wording is the access.py constant, not a duplicated literal."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    assert REFUSAL_TEXT in page.text


def test_refusal_shown_chat_page_never_writes_raw_json(client):
    """Any other non-200 status shows a plain generic message, never the raw response."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    assert "Something went wrong. Ask the librarian." in page.text
    assert "answer.textContent = response" not in page.text
    assert "answer.textContent = JSON.stringify" not in page.text
    assert "answer.textContent = data.detail" in page.text


def test_card_page_has_end_session_button(client):
    """Test that the card page has the new 'End session' button."""
    tc, _db = client
    from tests.test_card_sign_in import _register

    _register(tc, datetime.now(UTC) + timedelta(days=1))
    response = tc.get("/card")
    assert response.status_code == 200
    assert "End session" in response.text
