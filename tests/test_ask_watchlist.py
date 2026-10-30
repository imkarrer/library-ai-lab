"""The Watchlist checked in /ask (ADR-0004): every match raises or repeats a Flag, and a
high-severity match gets the Supportive reply with no Catalog search and no model call."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from registration_helpers import batch_cards

from library_assistant.access import (
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
from library_assistant.routers.live import LiveBus, get_live_bus
from library_assistant.routers.session import SUPPORTIVE_REPLY, _in_flight
from library_assistant.staff import create_account
from library_assistant.supportive_replies import get_supportive_reply_text
from library_assistant.watchlist import Entry, Watchlist

ADR_0011 = (
    Path(__file__).parents[1]
    / "docs/adr/0011-supportive-replies-per-rubric-category.md"
)

REGISTRATION_KEY = "s3cret-registration-key"
# Far in the future: the cookie expires with the Card, compared with the real clock.
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
THREAT_ENTRY = Entry(
    id="test-threat-high",
    category="threats-of-violence",
    severity="high",
    phrases=("test threat phrase",),
    must_match=("a test threat phrase here",),
    must_not_match=("nothing",),
)
WATCHLIST = Watchlist(
    version="2026-10-25.1", entries=(HIGH_ENTRY, LOW_ENTRY, THREAT_ENTRY)
)

HIGH_QUESTION = "I keep thinking test high phrase"
LOW_QUESTION = "test low phrase, any book recs?"


class CountingCatalog(Catalog):
    def __init__(self) -> None:
        self.searches: list[str] = []

    def search(self, query: str, k: int) -> list[Record]:
        self.searches.append(query)
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


@pytest.fixture(autouse=True)
def _no_card_left_in_flight():
    _in_flight.clear()
    yield
    _in_flight.clear()


@pytest.fixture
def catalog() -> CountingCatalog:
    return CountingCatalog()


@pytest.fixture
def events(monkeypatch) -> list[tuple[str, dict]]:
    """Every LiveBus event /ask publishes, in order."""
    published: list[tuple[str, dict]] = []
    bus = LiveBus()
    monkeypatch.setattr(
        bus, "publish", lambda kind, data: published.append((kind, data))
    )
    app.dependency_overrides[get_live_bus] = lambda: bus
    return published


@pytest.fixture
def client(catalog, events):
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
    settings = Settings(
        openai_endpoint="http://model.example.com:8080", openai_model="llama3"
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_catalog] = lambda: catalog
    app.dependency_overrides[get_clock] = lambda: NOW
    app.dependency_overrides[get_watchlist] = lambda: WATCHLIST
    try:
        test_client = TestClient(app)
        response = test_client.post(
            "/batches",
            json={
                "registration_key": REGISTRATION_KEY,
                "cards": batch_cards(("token-14", "14")),
                "expires_at": EXPIRES.isoformat(),
                "class_label": "Period 3",
            },
        )
        assert response.status_code == 201
        assert test_client.post("/card", json={"token": "token-14"}).status_code == 200
        yield test_client, db
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def model_calls(monkeypatch) -> list[httpx.URL]:
    """Stands in for the configured OpenAI-compatible endpoint, counting every call."""
    calls: list[httpx.URL] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Try Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    return calls


def test_supportive_reply_is_adr_0011_self_harm_text():
    text = ADR_0011.read_text()
    block = text.split("**Self-harm**", 1)[1].split("**Abuse**", 1)[0]
    lines = [line.removeprefix(">").strip() for line in block.strip().splitlines()]
    paragraphs = [
        " ".join(part.split("\n"))
        for part in re.split(r"\n\n+", "\n".join(lines).strip())
    ]
    expected = (
        "\n\n".join(paragraphs)
        .replace("{counselor}", "a school counselor")
        .replace("**", "")
    )
    assert SUPPORTIVE_REPLY == expected


def test_high_severity_gets_supportive_reply_and_no_model_call(
    client, model_calls, catalog, events
):
    test_client, db = client

    response = test_client.post("/ask", json={"question": HIGH_QUESTION})

    assert response.status_code == 200
    assert response.text == SUPPORTIVE_REPLY
    assert response.headers["cache-control"] == "no-store"
    assert model_calls == []
    assert catalog.searches == []
    assert db.execute("SELECT answer, citations FROM transcripts").fetchone() == (
        SUPPORTIVE_REPLY,
        "",
    )
    # The Flag's Alarm, Open Flags panel row, and count (ADR-0010) come before the
    # Supportive reply's answer.
    assert [kind for kind, _ in events] == [
        "question",
        "alarm",
        "flag",
        "flag_count",
        "answer",
    ]
    assert events[4][1]["answer"] == SUPPORTIVE_REPLY
    assert events[4][1]["citations"] == []
    assert _in_flight == set()


def test_low_severity_flags_and_answers(client, model_calls, catalog):
    test_client, db = client

    response = test_client.post("/ask", json={"question": LOW_QUESTION})

    assert response.status_code == 200
    assert "Try Ferdinand" in response.text
    assert SUPPORTIVE_REPLY not in response.text
    assert len(model_calls) == 1
    assert catalog.searches != []
    assert db.execute("SELECT count(*) FROM flags").fetchone()[0] == 1
    assert _in_flight == set()


def test_flag_names_matching_entry_and_version(client, model_calls):
    test_client, db = client

    test_client.post("/ask", json={"question": f"{HIGH_QUESTION} and {LOW_QUESTION}"})

    rows = db.execute(
        "SELECT category, severity, source, entry_id, watchlist_version, "
        "class_label, card_number, batch_expires_at, raised_at, transcript_id "
        "FROM flags ORDER BY id"
    ).fetchall()
    transcript_id = db.execute("SELECT id FROM transcripts").fetchone()[0]
    rest = (
        WATCHLIST.version,
        "Period 3",
        "14",
        EXPIRES.isoformat(),
        NOW.isoformat(),
        transcript_id,
    )
    assert rows == [
        ("self-harm", "high", "watchlist", HIGH_ENTRY.id, *rest),
        ("bullying", "low", "watchlist", LOW_ENTRY.id, *rest),
    ]


def test_no_match_raises_no_flag(client, model_calls):
    test_client, db = client

    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    assert response.status_code == 200
    assert db.execute("SELECT count(*) FROM flags").fetchone()[0] == 0
    assert len(model_calls) == 1


def test_same_message_again_is_a_repeat_and_still_gets_the_reply(client, model_calls):
    test_client, db = client

    first = test_client.post("/ask", json={"question": HIGH_QUESTION})
    # Normalization makes an evasive spelling the same message.
    second = test_client.post(
        "/ask", json={"question": "I keep thinking TEST HIGH phrase!"}
    )

    assert first.text == SUPPORTIVE_REPLY
    assert second.text == SUPPORTIVE_REPLY
    assert model_calls == []
    assert db.execute("SELECT count(*) FROM flags").fetchone()[0] == 1
    assert db.execute("SELECT repeat_count FROM flags").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM flag_repeats").fetchone()[0] == 1
    assert db.execute("SELECT answer FROM transcripts ORDER BY id").fetchall() == [
        (SUPPORTIVE_REPLY,),
        (SUPPORTIVE_REPLY,),
    ]


def test_threat_gets_the_threats_of_violence_reply(client, model_calls):
    """Watchlist categories are hyphenated; the reply table is not. A threat must get
    its own reply, not the self-harm one (ADR-0011)."""
    test_client, _ = client

    response = test_client.post("/ask", json={"question": "a test threat phrase here"})

    expected = get_supportive_reply_text("threats_of_violence", "a school counselor")
    assert response.text == expected
    assert response.text != SUPPORTIVE_REPLY


def test_several_categories_get_the_first_by_precedence(client, model_calls):
    test_client, _ = client

    response = test_client.post(
        "/ask", json={"question": "a test threat phrase and a test high phrase"}
    )

    assert response.text == SUPPORTIVE_REPLY


def test_reply_uses_the_installs_counselor_line(client, model_calls):
    test_client, db = client
    teacher_id = db.execute("SELECT id FROM staff_accounts").fetchone()[0]
    set_setting(db, "counselor_name", "Ms. Rivera in Room 12", teacher_id, NOW)

    response = test_client.post("/ask", json={"question": HIGH_QUESTION})

    assert "Ms. Rivera in Room 12" in response.text
