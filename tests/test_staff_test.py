"""The staff test page: the Student's answer with no Card and no Watch, and nothing kept."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db
from library_assistant.app import app
from library_assistant.catalog import Record
from library_assistant.config import Settings
from library_assistant.dependencies import (
    get_catalog,
    get_http_client,
    get_settings,
    get_watchlist,
)
from library_assistant.oversight import (
    OversightUnavailable,
    ScreeningState,
    Verdict,
    get_screening_state,
)
from library_assistant.routers import staff_test
from library_assistant.routers.live import LiveBus, get_live_bus
from library_assistant.routers.session import BANNER_TEXT, _in_flight
from library_assistant.staff import create_account, set_stand_in
from library_assistant.supportive_replies import reply_for
from library_assistant.watch import gate_is_open
from library_assistant.watchlist import Entry, Watchlist

WITH_OVERSIGHT = Settings(
    openai_endpoint="http://model.example.com",
    openai_model="llama3",
    oversight_endpoint="http://oversight.example.com",
    oversight_model="small",
)
NOW = datetime(2036, 11, 3, 9, 0, tzinfo=UTC)
PASSWORD = "correct horse"

RECORD = Record(
    id="1",
    title="The story of Ferdinand /",
    author="Leaf, Munro,",
    subjects="Bulls -- Fiction",
    summary="A bull who would rather smell flowers than fight.",
    call_number="813.52 LEA",
)
WATCHLIST = Watchlist(
    entries=(
        Entry(
            id="test-high",
            category="self-harm",
            severity="high",
            phrases=("test high phrase",),
            must_match=("a test high phrase here",),
            must_not_match=("nothing",),
        ),
        Entry(
            id="test-low",
            category="bullying",
            severity="low",
            phrases=("test low phrase",),
            must_match=("a test low phrase here",),
            must_not_match=("nothing",),
        ),
    ),
    version="test",
)


class OneBookCatalog:
    def search(self, query: str, k: int = 5) -> list[Record]:
        return [RECORD]

    search_strict = search

    def get(self, id: str) -> Record | None:
        return RECORD


def fake_model(request: httpx.Request) -> httpx.Response:
    """The overview as a stream, or the book pick when the request isn't one."""
    if json.loads(request.content)["stream"]:
        chunk = {
            "choices": [{"delta": {"content": "Bulls like flowers.\nSEARCH: bulls\n"}}]
        }
        return httpx.Response(
            200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
        )
    return httpx.Response(
        200, json={"choices": [{"message": {"content": "1 | A gentle bull."}}]}
    )


@pytest.fixture
def harness(monkeypatch):
    db = connect(":memory:")
    create_account(db, "librarian", PASSWORD, "librarian")
    create_account(db, "teacher", PASSWORD, "teacher")
    stand_in_id = create_account(db, "stand-in", PASSWORD, "teacher")
    set_stand_in(db, stand_in_id, True)
    published: list[tuple[str, dict]] = []
    bus = LiveBus()
    monkeypatch.setattr(
        bus, "publish", lambda kind, data: published.append((kind, data))
    )
    model = httpx.AsyncClient(
        transport=httpx.MockTransport(fake_model), base_url="http://model.example.com"
    )

    async def model_client():
        yield model

    app.dependency_overrides.update(
        {
            get_db: lambda: db,
            get_clock: lambda: NOW,
            get_catalog: lambda: OneBookCatalog(),
            get_watchlist: lambda: WATCHLIST,
            get_live_bus: lambda: bus,
            get_http_client: model_client,
            get_settings: lambda: Settings(
                openai_endpoint="http://model.example.com",
                openai_model="llama3",
            ),
        }
    )
    try:
        yield TestClient(app), db, published
    finally:
        app.dependency_overrides.clear()
        _in_flight.clear()


def sign_in(client: TestClient, username: str) -> None:
    response = client.post(
        "/staff/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303


def rows(db, table: str) -> int:
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_needs_no_card_and_no_watch(harness) -> None:
    client, db, _ = harness
    assert not gate_is_open(db, NOW)
    sign_in(client, "librarian")

    page = client.get("/staff/test")
    assert page.status_code == 200
    assert BANNER_TEXT in page.text
    assert '"/staff/test/ask"' in page.text

    answer = client.post("/staff/test/ask", json={"question": "bulls?"})
    assert answer.status_code == 200
    assert "Bulls like flowers." in answer.text
    assert "SEARCH" not in answer.text
    assert "Citation: The story of Ferdinand / (813.52 LEA)" in answer.text


def test_a_test_keeps_nothing_and_tells_nobody(harness) -> None:
    client, db, published = harness
    sign_in(client, "librarian")

    client.post("/staff/test/ask", json={"question": "bulls?"})
    client.post("/staff/test/ask", json={"question": "a test high phrase here"})
    client.post("/staff/test/check", json={"question": "a test high phrase here"})

    assert rows(db, "transcripts") == 0
    assert rows(db, "flags") == 0
    assert rows(db, "sessions") == 0
    assert published == []


def test_a_high_severity_match_shows_the_supportive_reply_and_says_what_it_would_do(
    harness,
) -> None:
    client, db, _ = harness
    sign_in(client, "librarian")

    answer = client.post(
        "/staff/test/ask", json={"question": "a test high phrase here"}
    )
    assert answer.text == reply_for(db, ["self-harm"])

    lines = client.post(
        "/staff/test/check", json={"question": "a test high phrase here"}
    ).json()["in_class"]
    assert lines[0] == "A Student would get the Supportive reply, not an answer."
    assert lines[1] == (
        "Watchlist: a high-severity Flag for self harm and the Alarm would sound."
    )


def test_a_low_severity_match_still_gets_the_answer(harness) -> None:
    client, _, _ = harness
    sign_in(client, "librarian")

    answer = client.post("/staff/test/ask", json={"question": "a test low phrase here"})
    assert "Bulls like flowers." in answer.text

    lines = client.post(
        "/staff/test/check", json={"question": "a test low phrase here"}
    ).json()["in_class"]
    assert lines[0] == "Watchlist: a low-severity Flag for bullying, with no Alarm."


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            Verdict(category="threats-of-violence", severity="high", reason="r"),
            (
                "Oversight: a high-severity Flag for threats of violence and the Alarm "
                "would sound."
            ),
        ),
        (Verdict(category=None, severity=None, reason=""), "Oversight found nothing."),
        (
            OversightUnavailable("down"),
            "Oversight did not answer, so it did not check this.",
        ),
    ],
)
def test_the_check_reports_oversight(harness, monkeypatch, outcome, expected) -> None:
    client, _, _ = harness
    sign_in(client, "librarian")
    app.dependency_overrides[get_settings] = lambda: WITH_OVERSIGHT

    async def screen(_client, _settings, _question):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(staff_test, "screen", screen)
    lines = client.post("/staff/test/check", json={"question": "bulls?"}).json()
    assert lines["in_class"] == ["The Watchlist found nothing.", expected]


def test_the_check_says_when_oversight_is_down(harness) -> None:
    client, _, _ = harness
    sign_in(client, "librarian")
    down = ScreeningState()
    down.unavailable_since = NOW
    app.dependency_overrides[get_screening_state] = lambda: down
    app.dependency_overrides[get_settings] = lambda: WITH_OVERSIGHT
    lines = client.post("/staff/test/check", json={"question": "bulls?"}).json()
    assert lines["in_class"] == [
        "The Watchlist found nothing.",
        "Oversight is down, so it did not check this.",
    ]


def test_the_check_says_when_oversight_is_off(harness) -> None:
    client, _, _ = harness
    sign_in(client, "librarian")
    lines = client.post("/staff/test/check", json={"question": "bulls?"}).json()
    assert lines["in_class"] == [
        "The Watchlist found nothing.",
        "Oversight is off on this Install, so it did not check this.",
    ]


def test_one_question_at_a_time_per_account(harness) -> None:
    client, db, _ = harness
    sign_in(client, "librarian")
    account_id = db.execute(
        "SELECT id FROM staff_accounts WHERE username = 'librarian'"
    ).fetchone()[0]
    _in_flight.add(f"staff-test:{account_id}")
    busy = client.post("/staff/test/ask", json={"question": "bulls?"})
    assert busy.status_code == 409
    assert busy.json() == {"status": "one moment"}


def test_the_marker_is_released_after_each_answer(harness) -> None:
    client, _, _ = harness
    sign_in(client, "librarian")
    for _ in range(2):
        response = client.post("/staff/test/ask", json={"question": "bulls?"})
        assert response.status_code == 200
    assert not _in_flight


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/staff/test"),
        ("post", "/staff/test/ask"),
        ("post", "/staff/test/check"),
    ],
)
def test_a_student_or_a_teacher_cannot_reach_it(harness, method, path) -> None:
    client, _, _ = harness
    kwargs = {"json": {"question": "bulls?"}} if method == "post" else {}
    # No staff sign-in at all: this is where a Card holder stands.
    assert getattr(client, method)(path, **kwargs).status_code == 401
    sign_in(client, "teacher")
    assert getattr(client, method)(path, **kwargs).status_code == 403


def test_a_stand_in_can_test_and_finds_the_link(harness) -> None:
    client, _, _ = harness
    sign_in(client, "stand-in")
    assert client.get("/staff/test").status_code == 200
    assert 'href="/staff/test"' in client.get("/staff").text


def test_the_minting_page_links_the_card_on_screen() -> None:
    # One computer has no camera to scan its own screen with.
    page = (Path(__file__).parents[1] / "offline-minting.html").read_text()
    assert 'id="handout-open"' in page
    assert "getElementById('handout-open').href = signInUrl(" in page
