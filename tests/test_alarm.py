"""The Alarm, Acknowledge, replay, the Counselor's Escalation Alarm, and the chime
(lib-ppv.1, ADR-0010). The clock is injected, nothing sleeps on the wall clock, the model
and Oversight endpoints are faked in process, and every await on a stream is bounded by
STREAM_TIMEOUT so a bug fails the test instead of hanging it."""

import asyncio
import io
import json
import re
import wave
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
from library_assistant.alarms import announce_flag
from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings, get_watchlist
from library_assistant.flags import close_flag, get_flag, raise_flag
from library_assistant.install_settings import (
    ALARM_CHIME,
    ALARM_REPEAT_SECONDS,
    SUPERVISION_MODE,
    set_setting,
)
from library_assistant.oversight import get_screening_state
from library_assistant.routers.alarms import counselor_events
from library_assistant.routers.live import LiveBus, get_live_bus, live_events
from library_assistant.routers.session import _in_flight
from library_assistant.staff import (
    STAFF_SESSION_COOKIE,
    StaffAccount,
    create_account,
    set_stand_in,
)
from library_assistant.watchlist import Entry, Watchlist

NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(hours=6)
STREAM_TIMEOUT = 5
REGISTRATION_KEY = "s3cret-registration-key"

HIGH_QUESTION = "a test high phrase here"
LOW_QUESTION = "a test low phrase here"
PLAIN_QUESTION = "what do snow leopards eat?"
WATCHLIST = Watchlist(
    version="2026-10-25.1",
    entries=(
        Entry(
            id="test-self-harm-high",
            category="self-harm",
            severity="high",
            phrases=("test high phrase",),
            must_match=(HIGH_QUESTION,),
            must_not_match=("nothing",),
        ),
        Entry(
            id="test-bullying-low",
            category="bullying",
            severity="low",
            phrases=("test low phrase",),
            must_match=(LOW_QUESTION,),
            must_not_match=("nothing",),
        ),
    ),
)
RECORD = Record(
    id="00057791",
    title="The story of Ferdinand /",
    author="Leaf, Munro,",
    subjects="Bulls -- Fiction",
    summary="A bull who would rather smell flowers than fight.",
    call_number="PZ10.3.L47 St",
)
ALARM_KEYS = {
    "flag_id",
    "category",
    "severity",
    "source",
    "class_label",
    "card_number",
    "registered_by",
    "raised_at",
    "raised_unwatched",
    "url",
}


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


@pytest.fixture(autouse=True)
def _clean_state():
    _in_flight.clear()
    get_screening_state().reset()
    yield
    _in_flight.clear()
    get_screening_state().reset()
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def bus():
    return LiveBus()


@pytest.fixture
def setup(db, clock, bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    app.dependency_overrides[get_live_bus] = lambda: bus
    app.dependency_overrides[get_watchlist] = lambda: WATCHLIST
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_endpoint="http://model.example.com:8080", openai_model="llama3"
    )
    return db


def _staff(db, username, role, stand_in=False) -> TestClient:
    account_id = create_account(db, username, "correct horse", role)
    if stand_in:
        set_stand_in(db, account_id, True)
    client = TestClient(app)
    response = client.post(
        "/staff/login",
        data={"username": username, "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
    return client


@pytest.fixture
def librarian(setup):
    return _staff(setup, "the-librarian", "librarian")


@pytest.fixture
def student(setup, monkeypatch, librarian):
    """Card 14 of Period 3, registered by Ms Rivera, signed in; the model is faked and
    Oversight answers `verdict["value"]` when it is configured."""
    db = setup
    teacher = create_account(db, "ms-rivera", "correct horse", "teacher")
    db.execute(
        "INSERT INTO registration_keys (account_id, key_hash, rotated_at) "
        "VALUES (?, ?, ?)",
        (teacher, hash_token(REGISTRATION_KEY), NOW.isoformat()),
    )
    db.commit()
    # The gate is open without a Watch, so these tests start one only where they mean to.
    set_setting(db, SUPERVISION_MODE, "off", teacher, NOW)
    client = TestClient(app)
    client.verdict = {"category": None, "severity": None, "reason": "fine"}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oversight.example.com":
            content = json.dumps(client.verdict)
            body = json.dumps({"choices": [{"message": {"content": content}}]})
            return httpx.Response(
                200,
                content=body.encode(),
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Try Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    response = client.post(
        "/batches",
        json={
            "registration_key": REGISTRATION_KEY,
            "cards": batch_cards(("token-14", "14")),
            "expires_at": EXPIRES.isoformat(),
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


def _of(messages, kind) -> list[dict]:
    return [data for k, data in messages if k == kind]


def _high_flag(db, card_number="14", severity="high", question="a private question"):
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s", "Period 3", card_number, question, "a reply", "", NOW.isoformat()),
    )
    transcript_id = db.execute("SELECT max(id) FROM transcripts").fetchone()[0]
    return raise_flag(
        db,
        transcript_id,
        "Period 3",
        card_number,
        EXPIRES.isoformat(),
        f"h-{transcript_id}",
        "self-harm",
        severity,
        "watchlist",
        NOW.isoformat(),
    )


def _config(page_text: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="alarm-config">(.*?)</script>',
        page_text,
        re.DOTALL,
    )
    assert match, "no Alarm on this page"
    return json.loads(match.group(1))


# --- Raising: a high-severity Flag sounds the Alarm on every stream; low only counts.


def test_high_watchlist_flag_alarms_every_open_stream(student, bus, db):
    first, second = bus.subscribe(), bus.subscribe()

    student.post("/ask", json={"question": HIGH_QUESTION})

    for queue in (first, second):
        messages = _drain(queue)
        (alarm,) = _of(messages, "alarm")
        assert set(alarm) == ALARM_KEYS
        flag = get_flag(db, alarm["flag_id"])
        assert alarm == {
            "flag_id": flag.id,
            "category": "self-harm",
            "severity": "high",
            "source": "watchlist",
            "class_label": "Period 3",
            "card_number": "14",
            "registered_by": "ms-rivera",
            "raised_at": NOW.isoformat(),
            "raised_unwatched": False,
            "url": f"/staff/flags/{flag.id}",
        }
        assert _of(messages, "flag_count") == [{"open": 1}]


def test_alarm_carries_no_exchange_text(student, bus):
    queue = bus.subscribe()

    student.post("/ask", json={"question": HIGH_QUESTION})

    (alarm,) = _of(_drain(queue), "alarm")
    text = json.dumps(alarm)
    assert "phrase" not in text
    assert "Supportive" not in text
    assert "988" not in text


def test_low_flag_sounds_no_alarm_but_reaches_the_panel(student, bus):
    """ADR-0010 amendment: a low-severity Flag is silent, but whoever is on Watch sees it
    at once as an Open Flags row, never with its category or words."""
    queue = bus.subscribe()

    student.post("/ask", json={"question": LOW_QUESTION})

    messages = _drain(queue)
    assert _of(messages, "alarm") == []
    assert _of(messages, "flag_count") == [{"open": 1}]
    [row] = _of(messages, "flag")
    assert row["severity"] == "low"
    assert "category" not in row and "reason" not in row
    assert LOW_QUESTION not in json.dumps(row)
    assert {kind for kind, _ in messages} == {
        "question",
        "delta",
        "answer",
        "flag",
        "flag_count",
    }


def test_repeat_sounds_no_second_alarm(student, bus):
    student.post("/ask", json={"question": HIGH_QUESTION})
    queue = bus.subscribe()

    student.post("/ask", json={"question": HIGH_QUESTION})

    messages = _drain(queue)
    assert _of(messages, "alarm") == []
    assert _of(messages, "flag_count") == []


def test_raised_unwatched_rides_the_alarm(student, bus, db):
    set_setting(db, SUPERVISION_MODE, "live", 1, NOW)
    queue = bus.subscribe()

    student.post("/ask", json={"question": HIGH_QUESTION})

    (alarm,) = _of(_drain(queue), "alarm")
    assert alarm["raised_unwatched"] is True


@pytest.mark.parametrize("severity,alarms", [("high", 1), ("low", 0)])
def test_oversight_verdict_sounds_the_alarm(student, bus, db, severity, alarms):
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_endpoint="http://model.example.com:8080",
        openai_model="llama3",
        oversight_endpoint="http://oversight.example.com",
        oversight_model="guard-model",
    )
    student.verdict = {"category": "abuse", "severity": severity, "reason": "r"}
    queue = bus.subscribe()

    response = student.post("/ask", json={"question": PLAIN_QUESTION})

    assert response.status_code == 200
    messages = _drain(queue)
    found = _of(messages, "alarm")
    assert len(found) == alarms
    if found:
        assert found[0]["source"] == "oversight"
        assert found[0]["category"] == "abuse"
        assert "snow" not in json.dumps(found[0])
    assert _of(messages, "flag_count") == [{"open": 1}]


def test_alarm_reaches_the_live_view_stream():
    """Through the real SSE route: the `alarm` event arrives on an open stream."""
    db = connect(":memory:")
    flag_id = _high_flag(db)
    bus = LiveBus()
    librarian = StaffAccount(id=1, username="the-librarian", role="librarian")

    async def never() -> None:
        await asyncio.Event().wait()

    async def scenario():
        response = await live_events(librarian, bus, never)
        stream = response.body_iterator
        announce_flag(db, bus.publish, flag_id, is_repeat=False)
        events = [
            await asyncio.wait_for(anext(stream), STREAM_TIMEOUT) for _ in range(3)
        ]
        await stream.aclose()
        return events

    first, row, count = asyncio.run(scenario())

    assert first.startswith("event: alarm\ndata: ")
    assert json.loads(first.split("data: ", 1)[1])["flag_id"] == flag_id
    assert row.startswith("event: flag\ndata: ")
    assert json.loads(row.split("data: ", 1)[1])["flag_id"] == flag_id
    assert count == 'event: flag_count\ndata: {"open": 1}\n\n'


# --- Acknowledge


def test_acknowledge_records_account_and_time_and_silences_all(
    librarian, setup, bus, clock
):
    db = setup
    flag_id = _high_flag(db)
    first, second = bus.subscribe(), bus.subscribe()
    clock["now"] = NOW + timedelta(minutes=3)

    response = librarian.post(f"/staff/alarms/{flag_id}/acknowledge")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    silenced = {
        "flag_id": flag_id,
        "escalation": False,
        "acknowledged_by": "the-librarian",
        "acknowledged_at": clock["now"].isoformat(),
    }
    assert response.json() == silenced
    for queue in (first, second):
        assert _drain(queue) == [("silenced", silenced)]
    row = db.execute(
        "SELECT acknowledged_at, acknowledged_by, closed_at FROM flags WHERE id = ?",
        (flag_id,),
    ).fetchone()
    assert row[0] == clock["now"].isoformat()
    assert row[1] is not None
    # Acknowledging is not closing.
    assert row[2] is None
    # The Flag page shows who and when.
    page = librarian.get(f"/staff/flags/{flag_id}").text
    assert f"the-librarian at {clock['now'].isoformat()}" in page


def test_a_later_acknowledge_keeps_the_first(librarian, setup, clock):
    db = setup
    flag_id = _high_flag(db)
    librarian.post(f"/staff/alarms/{flag_id}/acknowledge")
    stand_in = _staff(db, "aide", "teacher", stand_in=True)
    clock["now"] = NOW + timedelta(minutes=5)

    response = stand_in.post(f"/staff/alarms/{flag_id}/acknowledge")

    assert response.status_code == 200
    assert response.json()["acknowledged_by"] == "the-librarian"
    assert response.json()["acknowledged_at"] == NOW.isoformat()


def test_stand_in_may_acknowledge(setup):
    db = setup
    flag_id = _high_flag(db)
    stand_in = _staff(db, "aide", "teacher", stand_in=True)

    response = stand_in.post(f"/staff/alarms/{flag_id}/acknowledge")

    assert response.status_code == 200
    assert response.json()["acknowledged_by"] == "aide"


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_others_may_not_acknowledge(setup, role):
    db = setup
    flag_id = _high_flag(db)

    response = _staff(db, f"{role}-account", role).post(
        f"/staff/alarms/{flag_id}/acknowledge"
    )

    assert response.status_code == 403
    assert get_flag(db, flag_id) is not None
    assert (
        db.execute(
            "SELECT acknowledged_at FROM flags WHERE id = ?", (flag_id,)
        ).fetchone()[0]
        is None
    )


def test_low_flag_has_no_alarm_to_acknowledge(librarian, setup):
    flag_id = _high_flag(setup, severity="low")

    assert librarian.post(f"/staff/alarms/{flag_id}/acknowledge").status_code == 404
    assert librarian.post("/staff/alarms/999/acknowledge").status_code == 404


# --- Replay: at Start watch, and on the next staff page in periodic or off mode.


def test_start_watch_replays_unacknowledged_alarms(librarian, setup):
    db = setup
    waiting = _high_flag(db, card_number="3")
    acknowledged = _high_flag(db, card_number="4")
    _high_flag(db, card_number="5", severity="low")
    closed = _high_flag(db, card_number="6")
    librarian.post(f"/staff/alarms/{acknowledged}/acknowledge")
    close_flag(db, closed, NOW.isoformat(), "the-librarian", "handled", "done")

    response = librarian.post("/staff/watch/start")

    assert response.json()["watching"] is True
    assert [alarm["flag_id"] for alarm in response.json()["alarms"]] == [waiting]
    assert set(response.json()["alarms"][0]) == ALARM_KEYS


def test_live_mode_page_open_waits_for_start_watch(librarian, setup):
    _high_flag(setup)

    assert _config(librarian.get("/staff/live").text)["pending"] == []

    librarian.post("/staff/watch/start")
    # A watching page that reloads replays too.
    assert len(_config(librarian.get("/staff/live").text)["pending"]) == 1


@pytest.mark.parametrize("mode", ["periodic", "off"])
@pytest.mark.parametrize("url", ["/staff/live", "/staff/flags"])
def test_periodic_or_off_page_open_replays(librarian, setup, mode, url):
    db = setup
    flag_id = _high_flag(db)
    set_setting(db, SUPERVISION_MODE, mode, 1, NOW)

    pending = _config(librarian.get(url).text)["pending"]

    assert [alarm["flag_id"] for alarm in pending] == [flag_id]
    assert "a private question" not in json.dumps(pending)


@pytest.mark.parametrize("url", ["/staff", "/staff/accounts", "/staff/settings"])
def test_unacknowledged_alarm_shows_on_every_staff_page(librarian, setup, url):
    """Every staff page carries the Alarm (lib-f24.77, ADR-0010's supervision-mode
    amendment), not just the Live view, Session detail, Flag queue and Flag pages."""
    db = setup
    flag_id = _high_flag(db)
    set_setting(db, SUPERVISION_MODE, "periodic", 1, NOW)

    pending = _config(librarian.get(url).text)["pending"]

    assert [alarm["flag_id"] for alarm in pending] == [flag_id]


def test_chime_settings_reach_the_page(librarian, setup):
    db = setup
    config = _config(librarian.get("/staff/live").text)
    assert config["chime_on"] is True
    assert config["repeat_seconds"] == 30
    assert config["chime"] == "/staff/alarm/chime.wav"

    set_setting(db, ALARM_CHIME, "off", 1, NOW)
    set_setting(db, ALARM_REPEAT_SECONDS, 45, 1, NOW)
    config = _config(librarian.get("/staff/live").text)

    assert config["chime_on"] is False
    assert config["repeat_seconds"] == 45


def test_page_alarm_listens_and_plays(librarian, setup):
    text = librarian.get("/staff/live").text
    script = text[text.index('id="alarm-config"') :]
    assert "addEventListener(config.alarm_event" in script
    assert 'addEventListener("silenced"' in script
    assert "chime.play()" in script
    assert "setInterval(play, config.repeat_seconds * 1000)" in script
    assert _config(text)["alarm_event"] == "alarm"
    # Start watch plays the chime once as the sound check, and replays what it is handed.
    assert "window.alarmChime()" in text
    assert '"alarm-replay"' in text


# --- Escalation: reaches an open Counselor page live.


def test_escalation_reaches_the_counselor_stream(librarian, setup, bus):
    db = setup
    counselor = _staff(db, "the-counselor", "counselor")
    flag_id = _high_flag(db)
    queue = bus.subscribe()

    response = librarian.post(
        f"/staff/flags/{flag_id}/escalate",
        data={"reason": "needs the counselor"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    (escalated,) = _of(_drain(queue), "escalated")
    assert escalated["flag_id"] == flag_id
    assert escalated["url"] == f"/staff/counselor/flags/{flag_id}"
    assert escalated["escalated_at"] == NOW.isoformat()
    assert "a private question" not in json.dumps(escalated)
    assert "needs the counselor" not in json.dumps(escalated)

    # Opened later, the Counselor page shows it until the Counselor Acknowledges.
    config = _config(counselor.get("/staff/counselor").text)
    assert config["events"] == "/staff/counselor/events"
    assert [alarm["flag_id"] for alarm in config["pending"]] == [flag_id]
    assert (
        counselor.post(f"/staff/counselor/alarms/{flag_id}/acknowledge").status_code
        == 200
    )
    assert _config(counselor.get("/staff/counselor").text)["pending"] == []
    # The Librarian's Alarm is separate: still unacknowledged.
    assert len(librarian.post("/staff/watch/start").json()["alarms"]) == 1


def test_counselor_stream_carries_only_escalations():
    bus = LiveBus()
    counselor = StaffAccount(id=2, username="the-counselor", role="counselor")

    async def never() -> None:
        await asyncio.Event().wait()

    async def scenario():
        response = await counselor_events(counselor, bus, never)
        stream = response.body_iterator
        bus.publish("question", {"question": "words"})
        bus.publish("alarm", {"flag_id": 1})
        bus.publish("flag_count", {"open": 1})
        bus.publish("silenced", {"flag_id": 1, "escalation": False})
        bus.publish("escalated", {"flag_id": 1})
        bus.publish("silenced", {"flag_id": 1, "escalation": True})
        first = await asyncio.wait_for(anext(stream), STREAM_TIMEOUT)
        second = await asyncio.wait_for(anext(stream), STREAM_TIMEOUT)
        await stream.aclose()
        return first, second

    first, second = asyncio.run(scenario())

    assert first == 'event: escalated\ndata: {"flag_id": 1}\n\n'
    assert second == ('event: silenced\ndata: {"flag_id": 1, "escalation": true}\n\n')


@pytest.mark.parametrize("role", ["librarian", "teacher"])
def test_counselor_stream_is_the_counselors(setup, role):
    client = _staff(setup, f"{role}-account", role)

    assert client.get("/staff/counselor/events").status_code == 403


# --- The chime, and nothing external.


def test_chime_is_a_small_local_wav(librarian):
    response = librarian.get("/staff/alarm/chime.wav")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) < 32_000
    with wave.open(io.BytesIO(response.content)) as wav:
        assert wav.getnframes() > 0


def test_chime_needs_a_staff_session(setup):
    assert TestClient(app).get("/staff/alarm/chime.wav").status_code == 401


URL = re.compile(r"(?:https?:)?//[^\s\"'<>)\\]+", re.IGNORECASE)


def _external_urls(text: str) -> list[str]:
    """Every absolute URL in the page that is not the Install itself."""
    found = []
    for match in URL.findall(text):
        if match.startswith("//") and not match.startswith("///"):
            host = match[2:].split("/")[0]
        elif match.lower().startswith("http"):
            host = match.split("//", 1)[1].split("/")[0]
        else:
            continue
        if host and host.split(":")[0] != "testserver":
            found.append(match)
    return found


def test_url_scan_catches_an_external_url():
    assert _external_urls('<audio src="https://cdn.example.com/c.mp3">') == [
        "https://cdn.example.com/c.mp3"
    ]
    assert _external_urls("<script src='//cdn.example.com/x.js'>") == [
        "//cdn.example.com/x.js"
    ]
    assert _external_urls('<a href="/staff/flags/1">') == []


def test_staff_pages_load_nothing_external(librarian, setup):
    db = setup
    counselor = _staff(db, "the-counselor", "counselor")
    set_setting(db, SUPERVISION_MODE, "off", 1, NOW)
    db.execute(
        "INSERT INTO cards (token_hash, card_number, expires_at, class_label) "
        "VALUES (?, ?, ?, ?)",
        (hash_token("token-14"), "14", EXPIRES.isoformat(), "Period 3"),
    )
    db.execute(
        "INSERT INTO sessions (session_hash, token_hash, started_at) VALUES (?, ?, ?)",
        ("s", hash_token("token-14"), NOW.isoformat()),
    )
    db.commit()
    flag_id = _high_flag(db)
    librarian.post(
        f"/staff/flags/{flag_id}/escalate", data={"reason": "counselor please"}
    )
    session_no = db.execute("SELECT rowid FROM sessions").fetchone()[0]

    pages = [
        (librarian, "/staff/live"),
        (librarian, f"/staff/live/sessions/{session_no}"),
        (librarian, "/staff/flags"),
        (librarian, f"/staff/flags/{flag_id}"),
        (counselor, "/staff/counselor"),
        (counselor, f"/staff/counselor/flags/{flag_id}"),
        (counselor, "/staff/flags"),
        (librarian, "/staff"),
        (librarian, "/staff/accounts"),
        (librarian, "/staff/settings"),
        (librarian, "/staff/keys"),
        (librarian, "/staff/holds"),
        (librarian, "/staff/supportive-replies-preview"),
    ]
    for client, url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
        # The page carries the Alarm, with its chime from the Install itself.
        assert '"/staff/alarm/chime.wav"' in response.text, url
        assert _external_urls(response.text) == [], url
        assert re.search(r"<script[^>]*\ssrc\s*=", response.text) is None, url
