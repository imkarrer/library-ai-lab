import asyncio
import json
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from registration_helpers import batch_cards

from library_assistant.access import (
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
from library_assistant.install_settings import SUPERVISION_MODE, set_setting
from library_assistant.routers.live import LiveBus, get_live_bus, live_events
from library_assistant.staff import (
    STAFF_SESSION_COOKIE,
    StaffAccount,
    create_account,
    deactivate_account,
)
from library_assistant.watchlist import Entry, Watchlist

# Far in the future on purpose, matching tests/test_staff.py's convention: a past NOW
# would make every Card and staff session in this file look already expired.
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def client(db, clock):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _card(
    db,
    token,
    card_number,
    class_label="Period 3",
    expires_at=NOW + timedelta(hours=6),
    registered_by_account_id=None,
):
    db.execute(
        "INSERT INTO cards (token_hash, card_number, expires_at, class_label, "
        "registered_by_account_id) VALUES (?, ?, ?, ?, ?)",
        (
            hash_token(token),
            card_number,
            expires_at.isoformat(),
            class_label,
            registered_by_account_id,
        ),
    )
    db.commit()


def _session(db, token, started_at=NOW) -> str:
    session_hash = hash_token(f"session-for-{token}")
    db.execute(
        "INSERT INTO sessions (session_hash, token_hash, started_at) VALUES (?, ?, ?)",
        (session_hash, hash_token(token), started_at.isoformat()),
    )
    db.commit()
    return session_hash


def _ask(db, session_hash, class_label, card_number, question, asked_at=NOW):
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            session_hash,
            class_label,
            card_number,
            question,
            "an answer",
            "[]",
            asked_at.isoformat(),
        ),
    )
    db.commit()


def _sign_in_as(client, db, role) -> TestClient:
    create_account(db, f"{role}-account", "correct horse", role)
    response = client.post(
        "/staff/login",
        data={"username": f"{role}-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
    return client


def test_tile_per_active_session_with_label_and_card(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "what do snow leopards eat?")

    response = client.get("/staff/live")

    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text
    assert "what do snow leopards eat?" in response.text


def test_tile_shows_registering_teacher_even_once_deactivated(client, db):
    _sign_in_as(client, db, "librarian")
    teacher_id = create_account(db, "ms-alvarez", "correct horse", "teacher")
    _card(
        db,
        "token-14",
        "14",
        class_label="Period 3",
        registered_by_account_id=teacher_id,
    )
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "what do snow leopards eat?")
    deactivate_account(db, teacher_id)

    response = client.get("/staff/live")

    assert "Registered by ms-alvarez" in response.text


def test_expired_or_revoked_session_has_no_tile(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-expired", "15", expires_at=NOW - timedelta(hours=1))
    _session(db, "token-expired")
    # Revoked: no Card row at all for this Session's token.
    _session(db, "token-revoked")

    response = client.get("/staff/live")

    assert "15" not in response.text
    assert "No active Sessions." in response.text


def test_tiles_most_recent_activity_first(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-older", "1")
    older_hash = _session(db, "token-older", started_at=NOW - timedelta(minutes=10))
    _ask(
        db,
        older_hash,
        "Period 3",
        "1",
        "older question",
        asked_at=NOW - timedelta(minutes=10),
    )

    _card(db, "token-newer", "2")
    newer_hash = _session(db, "token-newer", started_at=NOW - timedelta(minutes=5))
    _ask(
        db,
        newer_hash,
        "Period 3",
        "2",
        "newer question",
        asked_at=NOW - timedelta(minutes=1),
    )

    response = client.get("/staff/live")

    assert response.text.index("newer question") < response.text.index("older question")


def test_latest_question_truncated(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    long_question = "why " * 30
    _ask(db, session_hash, "Period 3", "14", long_question)

    response = client.get("/staff/live")

    assert long_question not in response.text
    assert long_question[:80] + "..." in response.text


def test_overview_has_no_forms(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    response = client.get("/staff/live")

    # The one control is Start watch (ADR-0010); nothing that changes a Session.
    assert "<form" not in response.text
    assert response.text.count("<button") == 1
    assert '<button id="watch-toggle"' in response.text
    assert "Revoke" not in response.text


def test_page_has_no_token_or_hash(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    response = client.get("/staff/live")

    lowered = response.text.lower()
    assert "token" not in lowered
    assert "hash" not in lowered
    assert session_hash not in response.text
    assert hash_token("token-14") not in response.text


def test_tile_shows_high_when_any_open_high_flag(client, db):
    """Test that a tile shows 'flag-high' when there's an open high-severity flag."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    # Add a high severity flag
    from library_assistant.flags import raise_flag

    transcript_id = db.execute(
        "SELECT id FROM transcripts WHERE session_hash = ?", (session_hash,)
    ).fetchone()[0]
    raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash=None,
        category="test-category",
        severity="high",
        source="watchlist",
        raised_at=NOW.isoformat(),
    )

    response = client.get("/staff/live")

    assert response.status_code == 200
    assert "flag-high" in response.text
    assert "Flag: high" in response.text


def test_tile_shows_low_when_only_low(client, db):
    """Test that a tile shows 'flag-low' when there's an open low-severity flag."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    # Add a low severity flag
    from library_assistant.flags import raise_flag

    transcript_id = db.execute(
        "SELECT id FROM transcripts WHERE session_hash = ?", (session_hash,)
    ).fetchone()[0]
    raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash=None,
        category="test-category",
        severity="low",
        source="watchlist",
        raised_at=NOW.isoformat(),
    )

    response = client.get("/staff/live")

    assert response.status_code == 200
    assert "flag-low" in response.text
    assert "Flag: low" in response.text


def _tiles_html(page: str) -> str:
    """The Session tiles alone: the Open Flags panel's markup and script also say "flag-"."""
    start = page.index('<div id="tiles">')
    return page[start : page.index("<script>", start)]


def test_closed_flags_do_not_mark(client, db):
    """Test that closed flags do not affect the tile marker."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    # Add a closed high severity flag
    from library_assistant.flags import close_flag, raise_flag

    transcript_id = db.execute(
        "SELECT id FROM transcripts WHERE session_hash = ?", (session_hash,)
    ).fetchone()[0]
    flag_id = raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash=None,
        category="test-category",
        severity="high",
        source="watchlist",
        raised_at=NOW.isoformat(),
    )
    close_flag(
        db,
        flag_id,
        (NOW + timedelta(minutes=1)).isoformat(),
        "librarian-account",
        "handled",
        "done",
    )

    response = client.get("/staff/live")

    assert response.status_code == 200
    tiles = _tiles_html(response.text)
    assert "flag-high" not in tiles
    assert "Flag: high" not in tiles


def test_no_flag_no_marker(client, db):
    """Test that a tile has no flag marker when no open flags exist."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    response = client.get("/staff/live")

    assert response.status_code == 200
    tiles = _tiles_html(response.text)
    assert "flag-" not in tiles
    assert "Flag:" not in tiles


def test_tile_shows_high_when_high_and_low_flags_exist(client, db):
    """Test that a tile shows 'flag-high' when both high and low severity flags exist."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    # Add both high and low severity flags (should show high)
    from library_assistant.flags import raise_flag

    transcript_id = db.execute(
        "SELECT id FROM transcripts WHERE session_hash = ?", (session_hash,)
    ).fetchone()[0]

    # First, add a low severity flag
    raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash=None,
        category="test-category",
        severity="low",
        source="watchlist",
        raised_at=NOW.isoformat(),
    )

    # Then add a high severity flag on the same transcript
    raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash=None,
        category="test-category",
        severity="high",
        source="watchlist",
        raised_at=NOW.isoformat(),
    )

    response = client.get("/staff/live")

    assert response.status_code == 200
    assert "flag-high" in response.text
    assert "Flag: high" in response.text


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_teacher_and_counselor_403(client, db, role):
    _sign_in_as(client, db, role)

    response = client.get("/staff/live")

    assert response.status_code == 403


def test_anonymous_401(client):
    response = client.get("/staff/live")

    assert response.status_code == 401


def test_detail_shows_questions_answers_citations_oldest_first(client, db):
    """Test that session detail shows exchanges ordered oldest first."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")

    # Add multiple exchanges
    _ask(
        db,
        session_hash,
        "Period 3",
        "14",
        "First question",
        asked_at=NOW - timedelta(minutes=10),
    )
    _ask(
        db,
        session_hash,
        "Period 3",
        "14",
        "Second question",
        asked_at=NOW - timedelta(minutes=5),
    )

    # Get the session_no from the session_hash (it's the rowid)
    session_row = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()
    session_no = session_row[0]

    response = client.get(f"/staff/live/sessions/{session_no}")

    assert response.status_code == 200
    assert "Period 3" in response.text
    assert "14" in response.text
    assert "First question" in response.text
    assert "Second question" in response.text
    # Check ordering - first question should come before second question
    first_pos = response.text.index("First question")
    second_pos = response.text.index("Second question")
    assert first_pos < second_pos


def test_detail_unknown_session_404(client, db):
    """Test that accessing a non-existent session returns 404."""
    _sign_in_as(client, db, "librarian")

    response = client.get("/staff/live/sessions/999999")

    assert response.status_code == 404


def test_detail_has_no_token_or_hash(client, db):
    """Test that session detail page does not contain token or hash."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")

    # Get the session_no from the session_hash (it's the rowid)
    session_row = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()
    session_no = session_row[0]

    response = client.get(f"/staff/live/sessions/{session_no}")

    assert response.status_code == 200
    lowered = response.text.lower()
    assert "token" not in lowered
    assert "hash" not in lowered
    assert session_hash not in response.text


def test_detail_teacher_403(client, db):
    """Test that teacher role gets 403 for session detail."""
    _sign_in_as(client, db, "teacher")

    response = client.get("/staff/live/sessions/1")

    assert response.status_code == 403


def test_tile_links_to_detail(client, db):
    """Test that tile links properly to session detail."""
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "what do snow leopards eat?")

    # First get the live view to get session_no
    response = client.get("/staff/live")
    assert response.status_code == 200

    # Check that there's a link to the detail view
    assert "/staff/live/sessions/" in response.text


def test_catalog_record_page_shows_the_record(client, db):
    """Test that the Catalog record page renders the Record's details."""
    _sign_in_as(client, db, "librarian")
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()

    response = client.get(f"/staff/catalog/record/{RECORD.id}")

    assert response.status_code == 200
    assert "PZ10.3.L47 St" in response.text
    assert "The story of Ferdinand /" in response.text


def test_catalog_record_unknown_is_404(client, db):
    """Test that an unknown Record id 404s."""
    _sign_in_as(client, db, "librarian")
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()

    response = client.get("/staff/catalog/record/no-such-id")

    assert response.status_code == 404


def test_catalog_record_teacher_403(client, db):
    """Test that teacher role gets 403 for the Catalog record page."""
    _sign_in_as(client, db, "teacher")
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()

    response = client.get(f"/staff/catalog/record/{RECORD.id}")

    assert response.status_code == 403


def _session_no_for_card(db, card_number, class_label) -> int:
    row = db.execute(
        "SELECT sessions.rowid FROM sessions "
        "JOIN cards ON cards.token_hash = sessions.token_hash "
        "WHERE cards.card_number = ? AND cards.class_label = ?",
        (card_number, class_label),
    ).fetchone()
    return row[0]


def test_revoke_card_refuses_next_ask_other_cards_continue(client, db):
    _sign_in_as(client, db, "librarian")
    # No Watch is started in this test: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", account_id=1, now=NOW)
    expires_at = NOW + timedelta(hours=6)
    _card(db, "token-14", "14", class_label="Period 3", expires_at=expires_at)
    _card(db, "token-15", "15", class_label="Period 3", expires_at=expires_at)
    # Separate clients: posting /card with an existing session cookie would
    # delete the first Card's Session (a new sign-in on the same device).
    sess14 = (
        TestClient(app)
        .post("/card", json={"token": "token-14"})
        .cookies[SESSION_COOKIE]
    )
    sess15 = (
        TestClient(app)
        .post("/card", json={"token": "token-15"})
        .cookies[SESSION_COOKIE]
    )
    session_no = _session_no_for_card(db, "14", "Period 3")

    response = client.post(
        f"/staff/live/sessions/{session_no}/revoke-card",
        data={"confirm": "yes"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/live"
    checker14 = TestClient(app)
    checker14.cookies.set(SESSION_COOKIE, sess14)
    checker15 = TestClient(app)
    checker15.cookies.set(SESSION_COOKIE, sess15)
    assert checker14.get("/chat").status_code == 403
    assert checker15.get("/chat").status_code == 200


def test_revoke_batch_refuses_every_card(client, db):
    _sign_in_as(client, db, "librarian")
    # No Watch is started in this test: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", account_id=1, now=NOW)
    expires_at = NOW + timedelta(hours=6)
    _card(db, "token-14", "14", class_label="Period 3", expires_at=expires_at)
    _card(db, "token-15", "15", class_label="Period 3", expires_at=expires_at)
    sess14 = (
        TestClient(app)
        .post("/card", json={"token": "token-14"})
        .cookies[SESSION_COOKIE]
    )
    sess15 = (
        TestClient(app)
        .post("/card", json={"token": "token-15"})
        .cookies[SESSION_COOKIE]
    )
    session_no = _session_no_for_card(db, "14", "Period 3")

    response = client.post(
        f"/staff/live/sessions/{session_no}/revoke-batch",
        data={"confirm": "yes"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/staff/live"
    checker14 = TestClient(app)
    checker14.cookies.set(SESSION_COOKIE, sess14)
    checker15 = TestClient(app)
    checker15.cookies.set(SESSION_COOKIE, sess15)
    assert checker14.get("/chat").status_code == 403
    assert checker15.get("/chat").status_code == 403


def test_revoke_requires_confirm(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    session_row = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()
    session_no = session_row[0]

    response = client.post(f"/staff/live/sessions/{session_no}/revoke-card", data={})

    assert response.status_code == 400
    assert db.execute("SELECT 1 FROM cards").fetchone() is not None


def test_revoke_teacher_403(client, db):
    _sign_in_as(client, db, "teacher")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    session_row = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()
    session_no = session_row[0]

    response = client.post(
        f"/staff/live/sessions/{session_no}/revoke-card", data={"confirm": "yes"}
    )

    assert response.status_code == 403
    assert db.execute("SELECT 1 FROM cards").fetchone() is not None


def test_overview_still_has_no_forms(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14", class_label="Period 3")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "what do snow leopards eat?")

    response = client.get("/staff/live")

    assert response.status_code == 200
    assert "<form" not in response.text


# --- Live updates over SSE (lib-f24.48). No test sleeps on the wall clock: the ping wait
# is injected, and every await on the stream is bounded by STREAM_TIMEOUT so a bug fails
# the test instead of hanging it.

STREAM_TIMEOUT = 5
REGISTRATION_KEY = "s3cret-registration-key"
RECORD = Record(
    id="00057791",
    title="The story of Ferdinand /",
    author="Leaf, Munro,",
    subjects="Bulls -- Fiction",
    summary="A bull who would rather smell flowers than fight.",
    call_number="PZ10.3.L47 St",
)
LIBRARIAN = StaffAccount(id=1, username="librarian-account", role="librarian")


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


@pytest.fixture
def bus():
    bus = LiveBus()
    app.dependency_overrides[get_live_bus] = lambda: bus
    return bus


@pytest.fixture
def asking_client(client, db, bus, monkeypatch):
    """A Card signed in through the real flow, with the model endpoint faked."""
    teacher_id = create_account(db, "registering-teacher", "correct horse", "teacher")
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) "
        "VALUES (?, ?, ?)",
        (teacher_id, hash_token(REGISTRATION_KEY), NOW.isoformat()),
    )
    db.commit()
    # No Watch is started in this fixture: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, NOW)
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_endpoint="http://model.example.com:8080", openai_model="llama3"
    )
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"Try Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    response = client.post(
        "/batches",
        json={
            "registration_key": REGISTRATION_KEY,
            "cards": batch_cards(("token-14", "14")),
            "expires_at": (NOW + timedelta(hours=6)).isoformat(),
            "class_label": "Period 3",
        },
    )
    assert response.status_code == 201
    response = client.post("/card", json={"token": "token-14"})
    assert response.status_code == 200
    client.cookies.set(SESSION_COOKIE, response.cookies[SESSION_COOKIE])
    return client


def _drain(queue) -> list[tuple[str, dict]]:
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    return messages


def test_question_event_published_on_ask(asking_client, db, bus):
    queue = bus.subscribe()

    asking_client.post("/ask", json={"question": "a book about bulls?"})

    kind, data = _drain(queue)[0]
    session_no, session_hash = db.execute(
        "SELECT rowid, session_hash FROM sessions"
    ).fetchone()
    transcript_id = db.execute("SELECT id FROM transcripts").fetchone()[0]
    assert kind == "question"
    assert data == {
        "session_no": session_no,
        "transcript_id": transcript_id,
        "class_label": "Period 3",
        "card_number": "14",
        "question": "a book about bulls?",
        "asked_at": NOW.isoformat(),
    }
    assert session_hash not in json.dumps(data)


def test_answer_event_published_after_finish(asking_client, db, bus):
    queue = bus.subscribe()

    asking_client.post("/ask", json={"question": "a book about bulls?"})

    messages = _drain(queue)
    assert [kind for kind, _ in messages] == ["question", "delta", "answer"]
    _, data = messages[-1]
    session_no = db.execute("SELECT rowid FROM sessions").fetchone()[0]
    transcript_id, stored_answer = db.execute(
        "SELECT id, answer FROM transcripts"
    ).fetchone()
    assert data == {
        "session_no": session_no,
        "transcript_id": transcript_id,
        "answer": "Try Ferdinand",
        "citations": [
            {
                "record_id": RECORD.id,
                "title": RECORD.title,
                "call_number": RECORD.call_number,
            }
        ],
    }
    # Published after finish_exchange: the transcript already holds the answer.
    assert stored_answer == "Try Ferdinand"


def _fake_model(monkeypatch, deltas: list[str]) -> None:
    """The model endpoint streams `deltas`, one SSE chunk each."""
    body = b"".join(
        b"data: "
        + json.dumps({"choices": [{"delta": {"content": delta}}]}).encode()
        + b"\n\n"
        for delta in deltas
    )
    body += b"data: [DONE]\n\n"

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )


SHOWN_DELTAS = ["Try Ferdinand.\n", "It is about a bull.\n", "He likes flowers.\n"]


def test_delta_events_in_order_for_each_delta(asking_client, bus, monkeypatch):
    _fake_model(monkeypatch, [*SHOWN_DELTAS, "SEARCH: bulls; flowers\n"])
    queue = bus.subscribe()

    response = asking_client.post("/ask", json={"question": "a book about bulls?"})

    messages = _drain(queue)
    assert [kind for kind, _ in messages] == [
        "question",
        "delta",
        "delta",
        "delta",
        "answer",
    ]
    texts = [data["text"] for kind, data in messages if kind == "delta"]
    # Only what the Student is shown: the SEARCH line never goes out.
    assert texts == SHOWN_DELTAS
    assert response.text.startswith("".join(SHOWN_DELTAS))
    assert "SEARCH" not in response.text


def test_delta_events_carry_session_no_and_transcript_id(
    asking_client, db, bus, monkeypatch
):
    _fake_model(monkeypatch, SHOWN_DELTAS)
    queue = bus.subscribe()

    asking_client.post("/ask", json={"question": "a book about bulls?"})

    session_no, session_hash = db.execute(
        "SELECT rowid, session_hash FROM sessions"
    ).fetchone()
    transcript_id = db.execute("SELECT id FROM transcripts").fetchone()[0]
    deltas = [data for kind, data in _drain(queue) if kind == "delta"]
    assert deltas == [
        {"session_no": session_no, "transcript_id": transcript_id, "text": text}
        for text in SHOWN_DELTAS
    ]
    assert session_hash not in json.dumps(deltas)


def test_answer_event_matches_shown_deltas(asking_client, bus, monkeypatch):
    _fake_model(monkeypatch, [*SHOWN_DELTAS, "SEARCH: bulls; flowers\n"])
    queue = bus.subscribe()

    asking_client.post("/ask", json={"question": "a book about bulls?"})

    messages = _drain(queue)
    deltas = [data["text"] for kind, data in messages if kind == "delta"]
    answer = next(data for kind, data in messages if kind == "answer")["answer"]
    assert answer == "".join(deltas)


def test_supportive_reply_sends_no_delta_events(asking_client, bus):
    entry = Entry(
        id="test-self-harm-high",
        category="self-harm",
        severity="high",
        phrases=("test high phrase",),
        must_match=("a test high phrase here",),
        must_not_match=("nothing",),
    )
    app.dependency_overrides[get_watchlist] = lambda: Watchlist(
        version="2026-10-25.1", entries=(entry,)
    )
    queue = bus.subscribe()

    response = asking_client.post("/ask", json={"question": "a test high phrase here"})

    messages = _drain(queue)
    # No model call, so nothing streams: the answer event carries the reply whole. The
    # Flag's Alarm, its Open Flags panel row, and the count (ADR-0010) come first.
    assert [kind for kind, _ in messages] == [
        "question",
        "alarm",
        "flag",
        "flag_count",
        "answer",
    ]
    assert messages[-1][1]["answer"] == response.text


def test_detail_page_script_handles_delta_events(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")
    session_no = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()[0]

    response = client.get(f"/staff/live/sessions/{session_no}")

    script = response.text[response.text.index("<script>") :]
    assert 'addEventListener("delta"' in script
    assert ".textContent += data.text" in script
    # The delta listener comes before the answer listener that replaces its text.
    assert script.index('addEventListener("delta"') < script.index(
        'addEventListener("answer"'
    )


async def _never_returns() -> None:
    await asyncio.Event().wait()


def test_events_stream_delivers_published_messages():
    bus = LiveBus()

    async def scenario():
        response = await live_events(LIBRARIAN, bus, _never_returns)
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-store"
        stream = response.body_iterator
        bus.publish("question", {"session_no": 3, "question": "snow leopards?"})
        bus.publish("answer", {"session_no": 3, "answer": "they eat ibex"})
        first = await asyncio.wait_for(anext(stream), STREAM_TIMEOUT)
        second = await asyncio.wait_for(anext(stream), STREAM_TIMEOUT)
        await stream.aclose()
        return first, second

    first, second = asyncio.run(scenario())

    assert first == (
        'event: question\ndata: {"session_no": 3, "question": "snow leopards?"}\n\n'
    )
    assert second == (
        'event: answer\ndata: {"session_no": 3, "answer": "they eat ibex"}\n\n'
    )
    # Closing the stream unsubscribed it: a later publish reaches no queue.
    assert not bus._subscribers


def test_events_ping_each_time_the_wait_returns():
    bus = LiveBus()
    waits = []

    async def wait() -> None:
        waits.append(1)
        if len(waits) > 1:
            await asyncio.Event().wait()

    async def scenario():
        response = await live_events(LIBRARIAN, bus, wait)
        stream = response.body_iterator
        ping = await asyncio.wait_for(anext(stream), STREAM_TIMEOUT)
        bus.publish("question", {"session_no": 3})
        message = await asyncio.wait_for(anext(stream), STREAM_TIMEOUT)
        await stream.aclose()
        return ping, message

    ping, message = asyncio.run(scenario())

    assert ping == "event: ping\ndata: {}\n\n"
    assert message == 'event: question\ndata: {"session_no": 3}\n\n'


def test_events_teacher_403(client, db):
    _sign_in_as(client, db, "teacher")

    response = client.get("/staff/live/events")

    assert response.status_code == 403


def test_live_pages_load_no_external_script(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")
    session_no = db.execute(
        "SELECT rowid FROM sessions WHERE session_hash = ?", (session_hash,)
    ).fetchone()[0]

    for url in ("/staff/live", f"/staff/live/sessions/{session_no}"):
        response = client.get(url)

        assert response.status_code == 200
        assert "<script>" in response.text
        assert "/staff/live/events" in response.text
        assert re.search(r"<script[^>]*\ssrc\s*=", response.text) is None
        # The one stylesheet is the assistant's own (/library.css), never fetched.
        assert re.findall(r"<link[^>]*>", response.text) == [
            '<link rel="stylesheet" href="/library.css">'
        ]


# The Open Flags panel (ADR-0010 amendment, lib-4m7): whoever is on Watch sees every open
# Flag on the page they watch, low-severity too, without its category or words.


def _flag(db, session_hash, severity, source="watchlist", minutes=0) -> int:
    from library_assistant.flags import raise_flag

    transcript_id = db.execute(
        "SELECT id FROM transcripts WHERE session_hash = ? ORDER BY id DESC",
        (session_hash,),
    ).fetchone()[0]
    return raise_flag(
        db,
        transcript_id=transcript_id,
        class_label="Period 3",
        card_number="14",
        batch_expires_at=(NOW + timedelta(hours=6)).isoformat(),
        message_hash=None,
        category="bullying",
        severity=severity,
        source=source,
        raised_at=(NOW + timedelta(minutes=minutes)).isoformat(),
        reason="names a classmate",
    )


def _panel_html(page: str) -> str:
    start = page.index('<section id="open-flags-panel"')
    return page[start : page.index("</section>", start)]


def test_live_view_panel_lists_every_open_flag_high_first(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "Billy says I stink and makes me cry")
    low = _flag(db, session_hash, "low", source="oversight", minutes=5)
    high = _flag(db, session_hash, "high", minutes=1)

    panel = _panel_html(client.get("/staff/live").text)

    assert panel.index(f'data-flag-id="{high}"') < panel.index(f'data-flag-id="{low}"')
    assert f'href="/staff/flags/{low}"' in panel
    assert "Oversight" in panel and "Watchlist" in panel
    assert "Period 3 &middot; card 14" in panel
    # Safe on a shared screen: no category, no reason, no words.
    for withheld in ("bullying", "names a classmate", "Billy", "stink"):
        assert withheld not in panel


def test_panel_omits_closed_flags_and_says_when_none_are_open(client, db):
    from library_assistant.flags import close_flag

    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")
    flag_id = _flag(db, session_hash, "low")
    close_flag(db, flag_id, NOW.isoformat(), "librarian-account", "handled", "done")

    panel = _panel_html(client.get("/staff/live").text)

    assert "data-flag-id" not in panel
    assert "No open Flags." in panel


def test_session_detail_carries_the_panel_too(client, db):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")
    flag_id = _flag(db, session_hash, "low")
    session_no = _session_no_for_card(db, "14", "Period 3")

    page = client.get(f"/staff/live/sessions/{session_no}").text

    assert f'data-flag-id="{flag_id}"' in _panel_html(page)


def test_closing_a_flag_takes_it_off_the_panel_and_lowers_the_tile(client, db, bus):
    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")
    _flag(db, session_hash, "low")
    high = _flag(db, session_hash, "high")
    db.execute("UPDATE flags SET exported = 1 WHERE id = ?", (high,))
    db.commit()
    queue = bus.subscribe()

    response = client.post(
        f"/staff/flags/{high}/close",
        data={"outcome": "handled", "reason": "spoke with the student"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    closed = [data for kind, data in messages if kind == "flag_closed"]
    assert closed == [
        {
            "flag_id": high,
            "session_no": _session_no_for_card(db, "14", "Period 3"),
            "session_severity": "low",
        }
    ]
    assert ("flag_count", {"open": 1}) in messages


def test_reopening_a_flag_puts_it_back_on_the_panel(client, db, bus):
    from library_assistant.flags import close_flag

    _sign_in_as(client, db, "librarian")
    _card(db, "token-14", "14")
    session_hash = _session(db, "token-14")
    _ask(db, session_hash, "Period 3", "14", "a question")
    flag_id = _flag(db, session_hash, "low")
    close_flag(db, flag_id, NOW.isoformat(), "librarian-account", "handled", "done")
    queue = bus.subscribe()

    client.post(
        f"/staff/flags/{flag_id}/reopen",
        data={"reason": "came back"},
        follow_redirects=False,
    )

    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    [row] = [data for kind, data in messages if kind == "flag"]
    assert row["flag_id"] == flag_id
    assert row["session_severity"] == "low"
    assert not [kind for kind, _ in messages if kind == "alarm"]
