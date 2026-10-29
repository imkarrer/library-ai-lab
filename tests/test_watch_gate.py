"""The gate on Card sign-in and asks (lib-793.3, ADR-0010, ADR-0011, decision
lib-f24.77): no Watch in `live` mode closes it, the Watchlist and the Supportive reply
still run, and a status endpoint tells the chat page paused or active."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    PAUSED_TEXT,
    REFUSAL_TEXT,
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    hash_token,
)
from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings, get_watchlist
from library_assistant.flags import get_flag
from library_assistant.install_settings import (
    PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
    REVIEWS_EVERY_MINUTES,
    SUPERVISION_MODE,
    set_setting,
)
from library_assistant.routers.session import SUPPORTIVE_REPLY, _in_flight
from library_assistant.staff import create_account
from library_assistant.watch import gate_is_open, start_watch, watch_is_on
from library_assistant.watchlist import Entry, Watchlist

REGISTRATION_KEY = "s3cret-registration-key"
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

HIGH_ENTRY = Entry(
    id="test-self-harm-high",
    category="self-harm",
    severity="high",
    phrases=("test high phrase",),
    must_match=("a test high phrase here",),
    must_not_match=("nothing",),
)
LOW_ENTRY = Entry(
    id="test-bullying-low",
    category="bullying",
    severity="low",
    phrases=("test low phrase",),
    must_match=("a test low phrase here",),
    must_not_match=("nothing",),
)
WATCHLIST = Watchlist(version="2026-10-25.1", entries=(HIGH_ENTRY, LOW_ENTRY))

HIGH_QUESTION = "I keep thinking test high phrase"
LOW_QUESTION = "test low phrase, any book recs?"


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


@pytest.fixture(autouse=True)
def _no_card_left_in_flight():
    _in_flight.clear()
    yield
    _in_flight.clear()


@pytest.fixture
def settings():
    return Settings(
        openai_endpoint="http://model.example.com:8080", openai_model="llama3"
    )


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def db_and_teacher():
    db = connect(":memory:")
    teacher_id = create_account(db, "registering-teacher", "correct horse", "teacher")
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) "
        "VALUES (?, ?, ?)",
        (teacher_id, hash_token(REGISTRATION_KEY), NOW.isoformat()),
    )
    db.commit()
    return db, teacher_id


@pytest.fixture
def client(db_and_teacher, settings, clock):
    db, _teacher_id = db_and_teacher
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    app.dependency_overrides[get_watchlist] = lambda: WATCHLIST
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


def _make_watcher(db, account_id, now):
    """Starts the Watch for an account with a live staff session (`watch_is_on` drops
    a watcher with no unexpired staff session), without the real `/staff/login` flow."""
    db.execute(
        "INSERT INTO staff_sessions (session_hash, account_id, expires_at) "
        "VALUES (?, ?, ?)",
        (
            f"session-for-{account_id}",
            account_id,
            (now + timedelta(hours=1)).isoformat(),
        ),
    )
    db.commit()
    start_watch(db, account_id, now)


def _register_card(db, teacher_id, token="token-14", card_number="14"):
    """Registers a Batch of one Card directly (ADR-0002): the gate does not guard
    registration, only sign-in and asks."""
    db.execute(
        "INSERT INTO cards (card_number, token_hash, expires_at, class_label) "
        "VALUES (?, ?, ?, ?)",
        (card_number, hash_token(token), EXPIRES.isoformat(), "Period 3"),
    )
    db.commit()


def test_no_watch_valid_card_gets_paused_page_and_no_session_row(client):
    test_client, db = client
    _register_card(db, None)

    response = test_client.post("/card", json={"token": "token-14"})

    assert response.status_code == 503
    assert response.text == PAUSED_TEXT
    assert response.headers["cache-control"] == "no-store"
    assert SESSION_COOKIE not in response.cookies
    assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_no_watch_dead_card_still_refused(client):
    test_client, _db = client

    response = test_client.post("/card", json={"token": "no-such-token"})

    assert response.status_code == 403
    assert response.text == REFUSAL_TEXT


@pytest.fixture
def signed_in_client(db_and_teacher, settings, clock):
    """Signs a Card in while the gate is open, then closes it: for /ask tests, which
    need an existing Session rather than the sign-in gate itself."""
    db, teacher_id = db_and_teacher
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, NOW)
    _register_card(db, teacher_id)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    app.dependency_overrides[get_watchlist] = lambda: WATCHLIST
    try:
        test_client = TestClient(app)
        signed_in = test_client.post("/card", json={"token": "token-14"})
        assert signed_in.status_code == 200
        # Back to the default (live) with no Watch: the gate is now closed.
        set_setting(db, SUPERVISION_MODE, "live", teacher_id, NOW)
        yield test_client, db
    finally:
        app.dependency_overrides.clear()


def test_no_watch_ask_makes_no_model_call_and_gets_paused(
    signed_in_client, monkeypatch
):
    test_client, db = signed_in_client
    calls: list[httpx.URL] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        raise AssertionError("the model must not be called while the gate is closed")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )

    response = test_client.post("/ask", json={"question": "any question"})

    assert response.status_code == 503
    assert response.json() == {"detail": PAUSED_TEXT}
    assert calls == []
    assert db.execute("SELECT answer FROM transcripts").fetchone() == (PAUSED_TEXT,)


def test_no_watch_high_severity_still_gets_supportive_reply_and_raised_unwatched(
    signed_in_client,
):
    test_client, db = signed_in_client

    response = test_client.post("/ask", json={"question": HIGH_QUESTION})

    assert response.status_code == 200
    assert response.text == SUPPORTIVE_REPLY
    flag_id = db.execute("SELECT id FROM flags").fetchone()[0]
    flag = get_flag(db, flag_id)
    assert flag.raised_unwatched == 1


def test_no_watch_low_severity_still_raises_a_flag(signed_in_client):
    test_client, db = signed_in_client

    response = test_client.post("/ask", json={"question": LOW_QUESTION})

    assert response.status_code == 503
    assert response.json() == {"detail": PAUSED_TEXT}
    flag_id = db.execute("SELECT id FROM flags").fetchone()[0]
    flag = get_flag(db, flag_id)
    assert flag.category == "bullying"
    assert flag.raised_unwatched == 1


def test_answer_started_before_the_watch_lapses_completes(
    db_and_teacher, settings, monkeypatch
):
    db, teacher_id = db_and_teacher
    set_setting(db, SUPERVISION_MODE, "live", teacher_id, NOW)
    _make_watcher(db, teacher_id, NOW)
    _register_card(db, teacher_id)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: NOW
    app.dependency_overrides[get_watchlist] = lambda: Watchlist(version="v", entries=())

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # The Watch lapses once the model has already been reached: the gate check at
        # the start of `_answer` must not be re-read mid-stream.
        from library_assistant.watch import end_watch

        end_watch(db, teacher_id)
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Try Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    try:
        test_client = TestClient(app)
        signed_in = test_client.post("/card", json={"token": "token-14"})
        assert signed_in.status_code == 200

        response = test_client.post("/ask", json={"question": "any question"})
    finally:
        app.dependency_overrides.clear()

    assert not watch_is_on(db, NOW)
    assert response.status_code == 200
    assert "Try Ferdinand" in response.text


def test_status_endpoint_reports_paused_or_active(db_and_teacher, settings, clock):
    db, teacher_id = db_and_teacher
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, NOW)
    _register_card(db, teacher_id)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        test_client = TestClient(app)
        signed_in = test_client.post("/card", json={"token": "token-14"})
        assert signed_in.status_code == 200
        set_setting(db, SUPERVISION_MODE, "live", teacher_id, NOW)

        response = test_client.get("/status")
        assert response.status_code == 200
        assert response.json() == {"paused": True}
        assert response.headers["cache-control"] == "no-store"

        _make_watcher(db, teacher_id, NOW)
        response = test_client.get("/status")
        assert response.json() == {"paused": False}
    finally:
        app.dependency_overrides.clear()


# --- `gate_is_open` directly, for `live`/`off`/`periodic` (decision lib-f24.77).


def test_gate_open_live_needs_a_watch():
    db = connect(":memory:")
    account_id = create_account(db, "librarian", "correct horse", "librarian")
    set_setting(db, SUPERVISION_MODE, "live", account_id, NOW)

    assert not gate_is_open(db, NOW)

    _make_watcher(db, account_id, NOW)
    assert gate_is_open(db, NOW)


def test_gate_open_off_is_always_open():
    db = connect(":memory:")
    account_id = create_account(db, "librarian", "correct horse", "librarian")
    set_setting(db, SUPERVISION_MODE, "off", account_id, NOW)

    assert gate_is_open(db, NOW)


def test_gate_open_periodic_pauses_only_past_the_overdue_setting():
    db = connect(":memory:")
    account_id = create_account(db, "librarian", "correct horse", "librarian")
    set_setting(db, SUPERVISION_MODE, "periodic", account_id, NOW)
    set_setting(db, REVIEWS_EVERY_MINUTES, 60, account_id, NOW)
    set_setting(db, PAUSE_WHEN_REVIEW_OVERDUE_MINUTES, 30, account_id, NOW)
    db.execute(
        "INSERT INTO flag_reviews (account_id, reviewed_at) VALUES (?, ?)",
        (account_id, NOW.isoformat()),
    )
    db.commit()

    # due_at = NOW + 60m; overdue past due_at + 30m.
    assert gate_is_open(db, NOW + timedelta(minutes=89))
    assert not gate_is_open(db, NOW + timedelta(minutes=91))


def test_gate_open_periodic_with_no_pause_setting_stays_open():
    db = connect(":memory:")
    account_id = create_account(db, "librarian", "correct horse", "librarian")
    set_setting(db, SUPERVISION_MODE, "periodic", account_id, NOW)
    set_setting(db, REVIEWS_EVERY_MINUTES, 60, account_id, NOW)

    assert gate_is_open(db, NOW + timedelta(days=30))
