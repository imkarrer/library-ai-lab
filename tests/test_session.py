"""Grounded answers in a Session, through the real Card sign-in flow: register a
Batch, sign in with a Card, then ask with the cookie sign-in set."""

import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from page_scripts import assert_scripts_parse
from registration_helpers import batch_cards

from library_assistant.access import (
    REFUSAL_TEXT,
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    hash_token,
)
from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.catalog.marc import parse_marcxml, to_record
from library_assistant.catalog.sqlite_backend import SqliteCatalog
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings
from library_assistant.install_settings import SUPERVISION_MODE, set_setting
from library_assistant.routers.session import BANNER_TEXT, ERROR_TEXT, _in_flight
from library_assistant.staff import create_account

REGISTRATION_KEY = "s3cret-registration-key"
# Far in the future on purpose: sign-in sets the cookie to expire with the Card, an
# absolute time the HTTP client compares with the real clock, so a past NOW drops it.
NOW = datetime(2036, 11, 3, 9, 0, tzinfo=UTC)
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
    teacher_id = create_account(db, "registering-teacher", "correct horse", "teacher")
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) "
        "VALUES (?, ?, ?)",
        (teacher_id, hash_token(REGISTRATION_KEY), NOW.isoformat()),
    )
    db.commit()
    # No Watch is started in this fixture: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, NOW)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        test_client = TestClient(app)
        response = test_client.post(
            "/batches",
            json={
                "registration_key": REGISTRATION_KEY,
                "cards": batch_cards(("token-14", "14"), ("token-15", "15")),
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
    # The old test expected the model to answer directly, but now we're using
    # the research prompt which should return search terms and then the catalog results
    assert "Books in our library:" in response.text
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


def test_two_sign_ins_are_one_session(client):
    """When signing in twice with the same card on the same device,
    the second sign-in replaces the first session."""
    test_client, db = client
    first = _sign_in(test_client)
    second = _sign_in(test_client)
    assert first != second
    # Second sign-in should replace the first session, not create a new one
    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


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


def test_stored_answer_has_no_search_line(client, monkeypatch):
    """The SEARCH line drives the catalog search but the Student never sees it, so it
    must not land in the transcript's answer either."""
    test_client, db = client
    _sign_in(test_client)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"Ferdinand is a gentle bull.\\n"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"SEARCH: bulls\\n"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )

    test_client.post("/ask", json={"question": "a book about bulls?"})

    answer = db.execute("SELECT answer FROM transcripts").fetchone()[0]
    assert "Ferdinand is a gentle bull." in answer
    assert "SEARCH" not in answer


def test_shown_remaining_text_comes_before_books(client, monkeypatch):
    """The overview text released at finish() is shown whole before the citations."""
    test_client, _ = client
    _sign_in(test_client)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"Try Ferdinand.\\n"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"He likes flowers"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )

    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    assert response.text.index("He likes flowers") < response.text.index(
        "Books in our library:"
    )


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
    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    # The stream's 200 was already sent: the Student is told in the answer, not left
    # with a broken stream and nothing on screen.
    assert response.status_code == 200
    assert response.text == ERROR_TEXT
    assert db.execute(
        "SELECT question, answer, citations FROM transcripts"
    ).fetchall() == [("a book about bulls?", "", "")]


def _model_request_body(test_client, monkeypatch) -> dict:
    """The JSON the assistant sent the model for one question."""
    sent: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    _sign_in(test_client)
    assert test_client.post("/ask", json={"question": "bulls?"}).status_code == 200
    [body] = sent
    return body


def test_reasoning_effort_is_sent_when_set(client, settings, monkeypatch):
    test_client, _ = client
    app.dependency_overrides[get_settings] = lambda: dataclasses.replace(
        settings, openai_reasoning_effort="none"
    )
    assert _model_request_body(test_client, monkeypatch)["reasoning_effort"] == "none"


def test_reasoning_effort_is_left_out_by_default(client, monkeypatch):
    test_client, _ = client
    assert "reasoning_effort" not in _model_request_body(test_client, monkeypatch)


def test_answer_cites_books_from_a_real_sqlite_catalog(
    client, settings, monkeypatch, tmp_path
):
    """The streamed answer searches the Catalog on another thread than the one that
    opened it: a real SqliteCatalog, not the fake, must answer there (lib-30v)."""
    catalog_path = tmp_path / "catalog.db"
    loader = SqliteCatalog.open(str(catalog_path))
    loader.load_records(
        to_record(marc_record)
        for marc_record in parse_marcxml(
            str(Path(__file__).parent / "fixtures/catalog/loc-books-2016-sample.xml")
        )
    )
    app.dependency_overrides.pop(get_catalog)
    app.dependency_overrides[get_settings] = lambda: dataclasses.replace(
        settings, catalog_path=str(catalog_path)
    )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Dogs help people."}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"\\nSEARCH: Clifford; dog"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    test_client, _ = client
    _sign_in(test_client)
    response = test_client.post("/ask", json={"question": "books about dogs?"})

    assert response.status_code == 200
    assert "Books in our library:" in response.text
    assert "Clifford the big red dog" in response.text
    assert "SEARCH" not in response.text


def test_model_error_inside_the_stream_tells_the_student(client, monkeypatch):
    """llama.cpp's own failure report, a 200 stream carrying an error event (lib-30v)."""
    test_client, db = client
    _sign_in(test_client)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"error":{"code":500,"message":"Compute error.",'
            b'"type":"server_error"}}\n\n',
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    assert response.status_code == 200
    assert response.text == ERROR_TEXT
    assert db.execute("SELECT answer FROM transcripts").fetchall() == [("",)]


def test_chat_page_script_parses(client):
    """A syntax error anywhere in the chat script leaves Ask doing nothing (lib-y4j)."""
    test_client, _ = client
    _sign_in(test_client)
    assert_scripts_parse(test_client.get("/chat").text)


def test_chat_page_shows_the_error_text_when_the_stream_breaks(client):
    """A dropped connection mid-answer ends in ERROR_TEXT with Ask enabled again."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat").text
    read_loop = page[page.index("response.body.getReader()") :]
    assert "} catch (error) {" in read_loop
    assert "ERROR_TEXT" in read_loop[: read_loop.index("askButton.disabled = false")]


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


# One message in flight per Card (decision lib-f24.65). These tests drive the app
# concurrently through httpx.ASGITransport, which only returns a response once its body
# has streamed: so request 1 runs as a task, held inside the fake model until released,
# and every wait is bounded so a bug fails fast instead of hanging.

WAIT = 5


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_card_left_in_flight():
    _in_flight.clear()
    yield
    _in_flight.clear()


class HeldModel:
    """The model endpoint: its first call waits for `release`, later calls answer at once."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.fail_first = False
        self.calls = 0


@pytest.fixture
def held_model(monkeypatch) -> HeldModel:
    model = HeldModel()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        model.calls += 1
        if model.calls == 1:
            model.entered.set()
            await model.release.wait()
            if model.fail_first:
                raise httpx.ConnectError("model server down")
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    return model


@asynccontextmanager
async def _signed_in(token: str = "token-14") -> AsyncIterator[httpx.AsyncClient]:
    """A device with its own cookie jar, signed in with the Card `token`."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as device:
        with anyio.fail_after(WAIT):
            response = await device.post("/card", json={"token": token})
        assert response.status_code == 200
        yield device


async def _ask(device: httpx.AsyncClient) -> httpx.Response:
    with anyio.fail_after(WAIT):
        return await device.post("/ask", json={"question": "a book about bulls?"})


@asynccontextmanager
async def _first_message_in_flight(
    device: httpx.AsyncClient, model: HeldModel
) -> AsyncIterator[dict]:
    """Sends a message from `device` and yields once the model holds it; on exit,
    releases the model and waits for that first message to end.

    The yielded dict gets "response" (or "error", on a model error) when it ends."""
    first: dict = {}

    async def ask_first() -> None:
        try:
            first["response"] = await _ask(device)
        except httpx.ConnectError as error:
            first["error"] = error

    with anyio.fail_after(WAIT):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(ask_first)
            await model.entered.wait()
            try:
                yield first
            finally:
                model.release.set()


def _one_moment(response: httpx.Response) -> bool:
    return response.status_code == 409 and response.json() == {"status": "one moment"}


@pytest.mark.anyio
async def test_second_message_while_in_flight_is_409_one_moment(client, held_model):
    _, db = client
    async with _signed_in() as device:
        async with _first_message_in_flight(device, held_model) as first:
            assert _one_moment(await _ask(device))
        assert first["response"].status_code == 200

    # The second message was neither recorded nor sent to the model.
    assert held_model.calls == 1
    assert db.execute("SELECT count(*) FROM transcripts").fetchone()[0] == 1


@pytest.mark.anyio
async def test_other_card_unaffected_while_in_flight(client, held_model):
    async with _signed_in("token-14") as card_14, _signed_in("token-15") as card_15:
        async with _first_message_in_flight(card_14, held_model) as first:
            other = await _ask(card_15)
            assert other.status_code == 200
            assert "Ferdinand" in other.text
            assert first == {}, "card 14's message should still be in flight"
        assert first["response"].status_code == 200


@pytest.mark.anyio
async def test_same_card_second_session_also_409(client, held_model):
    _, db = client
    async with _signed_in() as phone, _signed_in() as laptop:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 2
        async with _first_message_in_flight(phone, held_model) as first:
            assert _one_moment(await _ask(laptop))
        assert first["response"].status_code == 200
    assert held_model.calls == 1


@pytest.mark.anyio
async def test_card_released_after_answer(client, held_model):
    async with _signed_in() as device:
        async with _first_message_in_flight(device, held_model) as first:
            assert _one_moment(await _ask(device))
        assert first["response"].status_code == 200

        again = await _ask(device)
    assert again.status_code == 200
    assert "Ferdinand" in again.text
    assert _in_flight == set()


@pytest.mark.anyio
async def test_card_released_after_model_error(client, held_model):
    held_model.fail_first = True
    async with _signed_in() as device:
        async with _first_message_in_flight(device, held_model) as first:
            assert _one_moment(await _ask(device))
        assert first["response"].status_code == 200
        assert first["response"].text == ERROR_TEXT

        again = await _ask(device)
    assert again.status_code == 200
    assert "Ferdinand" in again.text
    assert _in_flight == set()


def test_chat_page_disables_ask_while_streaming(client):
    """Test that the chat page JavaScript disables the Ask button during streaming."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    # Check that the script disables the question input and ask button
    assert "questionInput.disabled = true" in page.text
    assert "askButton.disabled = true" in page.text


def test_chat_page_handles_one_moment(client):
    """Test that the chat page JavaScript handles 409 'one moment' status."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    # Check that the script handles 409 with status "one moment"
    assert "response.status === 409" in page.text
    assert 'data.status === "one moment"' in page.text
    assert "One moment..." in page.text


def test_chat_page_keeps_question_on_one_moment(client):
    """Test that the chat page JavaScript keeps the question text during 409 'one moment' retries."""
    test_client, _ = client
    _sign_in(test_client)
    page = test_client.get("/chat")
    assert page.status_code == 200
    # Check that the question is preserved during retries
    assert "questionInput.value" in page.text
