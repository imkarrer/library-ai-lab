"""Oversight down does not hold Students (ADR-0004 addendum, lib-f24.55): the class
carries on with the Watchlist alone, the Live view says since when and offers Pause,
and screening catches up oldest first once the probe finds Oversight back, giving way to
any Card awaiting a verdict.

Driven through `httpx.ASGITransport` with fake Answer and Oversight servers, a fake clock,
and a fake probe wait released by the test: nothing sleeps. Every await sits under
`anyio.fail_after`, and the probe task is cancelled after each test.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    connect,
    get_clock,
    get_db,
    issue_registration_key,
)
from library_assistant.app import app
from library_assistant.catalog import Catalog, Record
from library_assistant.config import Settings
from library_assistant.dependencies import get_catalog, get_settings, get_watchlist
from library_assistant.install_settings import OVERSIGHT_DOWN, set_setting
from library_assistant.oversight import PROBE_TEXT, screening_state
from library_assistant.routers import session as session_router
from library_assistant.routers.session import (
    PAUSED_TEXT,
    _in_flight,
    get_now,
    get_probe_wait,
)
from library_assistant.staff import STAFF_SESSION_COOKIE, create_account
from library_assistant.watchlist import Entry, Watchlist

# 09:00 UTC is 03:00 in the school's default timezone (America/Chicago, CST that day).
NOW = datetime(2036, 11, 3, 9, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(hours=6)
WAIT = 5

RECORD = Record(
    id="00057791",
    title="The story of Ferdinand /",
    author="Leaf, Munro,",
    subjects="Bulls -- Fiction",
    summary="A bull who would rather smell flowers than fight.",
    call_number="PZ10.3.L47 St",
)

EMPTY_WATCHLIST = Watchlist(version="2026-10-25.1", entries=())
LOW_ENTRY = Entry(
    id="test-bullying-low",
    category="bullying",
    severity="low",
    phrases=("test low phrase",),
    must_match=("a test low phrase here",),
    must_not_match=("nothing",),
)
LOW_WATCHLIST = Watchlist(version="2026-10-25.1", entries=(LOW_ENTRY,))

SETTINGS = Settings(
    openai_endpoint="http://model.example.com:8080",
    openai_model="llama3",
    oversight_endpoint="http://oversight.example.com",
    oversight_model="guard-model",
)

NO_VERDICT = {"category": None, "severity": None, "reason": "nothing to report"}


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


class FakeLanes:
    """The Answer and Oversight servers. Oversight refuses connections while `down`, and
    can hold its first call for `hold_question` open on an `asyncio.Event`."""

    def __init__(self) -> None:
        self.down = False
        self.verdict: dict = NO_VERDICT
        self.screened: list[str] = []
        self.answer_calls = 0
        self.hold_question: str | None = None
        self.held_entered = asyncio.Event()
        self.held_release = asyncio.Event()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oversight.example.com":
            question = json.loads(request.content)["messages"][1]["content"]
            self.screened.append(question)
            if self.down:
                raise httpx.ConnectError("refused", request=request)
            if question == self.hold_question and not self.held_entered.is_set():
                self.held_entered.set()
                await self.held_release.wait()
            body = json.dumps(
                {"choices": [{"message": {"content": json.dumps(self.verdict)}}]}
            ).encode()
            return httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        self.answer_calls += 1
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )


class FakeWait:
    """The probe's wait: each `release()` lets one wait end. Nothing sleeps."""

    def __init__(self) -> None:
        self._permits = asyncio.Semaphore(0)

    async def __call__(self) -> None:
        await self._permits.acquire()

    def release(self) -> None:
        self._permits.release()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _fresh_screening():
    """Module-level state starts clean, and the probe never outlives its test."""
    screening_state.reset()
    _in_flight.clear()
    yield
    task = session_router._probe_task
    if task is not None:
        task.cancel()
        with anyio.fail_after(WAIT), contextlib.suppress(asyncio.CancelledError):
            await task
    session_router._probe_task = None
    session_router._catch_up_call = None
    screening_state.reset()
    _in_flight.clear()


@pytest.fixture
def lanes(monkeypatch) -> FakeLanes:
    fake = FakeLanes()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await fake.handle(request)

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    return fake


@pytest.fixture
def clock() -> dict:
    return {"now": NOW}


@pytest.fixture
def probe_wait() -> FakeWait:
    return FakeWait()


@pytest.fixture
def db(lanes, clock, probe_wait):
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    app.dependency_overrides[get_now] = lambda: lambda: clock["now"]
    app.dependency_overrides[get_probe_wait] = lambda: probe_wait
    app.dependency_overrides[get_watchlist] = lambda: EMPTY_WATCHLIST
    registration_key = issue_registration_key(
        db, create_account(db, "registering-teacher", "correct horse", "teacher"), NOW
    )
    try:
        response = TestClient(app).post(
            "/batches",
            json={
                "registration_key": registration_key,
                "cards": [
                    {"token": "token-14", "card_number": "14"},
                    {"token": "token-15", "card_number": "15"},
                ],
                "expires_at": EXPIRES.isoformat(),
                "class_label": "Period 3",
            },
        )
        assert response.status_code == 201
        yield db
    finally:
        app.dependency_overrides.clear()


def _device() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


@asynccontextmanager
async def _signed_in(token: str = "token-14") -> AsyncIterator[httpx.AsyncClient]:
    async with _device() as device:
        with anyio.fail_after(WAIT):
            response = await device.post("/card", json={"token": token})
        assert response.status_code == 200
        yield device


@asynccontextmanager
async def _librarian(db) -> AsyncIterator[httpx.AsyncClient]:
    create_account(db, "librarian-account", "correct horse", "librarian")
    async with _device() as staff:
        with anyio.fail_after(WAIT):
            response = await staff.post(
                "/staff/login",
                data={"username": "librarian-account", "password": "correct horse"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        staff.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
        yield staff


async def _ask(device: httpx.AsyncClient, question: str) -> httpx.Response:
    with anyio.fail_after(WAIT):
        return await device.post("/ask", json={"question": question})


async def _caught_up() -> None:
    """Wait for the probe-and-catch-up task to finish: it ends once nothing is left."""
    task = session_router._probe_task
    assert task is not None
    with anyio.fail_after(WAIT):
        await task


def _row(db, question: str) -> tuple:
    return db.execute(
        "SELECT id, screening, screened_at, verdict, asked_at FROM transcripts "
        "WHERE question = ?",
        (question,),
    ).fetchone()


@pytest.mark.anyio
async def test_down_marks_watchlist_alone_and_releases_card(db, lanes):
    lanes.down = True
    async with _signed_in() as device:
        response = await _ask(device, "a book about bulls?")

    assert response.status_code == 200
    assert "Ferdinand" in response.text
    _id, screening, screened_at, verdict, _asked_at = _row(db, "a book about bulls?")
    assert screening == "watchlist_alone"
    assert screened_at is None
    assert verdict is None
    assert _in_flight == set()
    assert screening_state.unavailable_since == NOW


@pytest.mark.anyio
async def test_next_message_admitted_while_down(db, lanes):
    lanes.down = True
    async with _signed_in() as device:
        first = await _ask(device, "a book about bulls?")
        second = await _ask(device, "a book about flowers?")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Ferdinand" in second.text
    # Only the first message tried Oversight; the second skipped it.
    assert lanes.screened == ["a book about bulls?"]
    assert _row(db, "a book about flowers?")[1:3] == ("watchlist_alone", None)
    assert _in_flight == set()


@pytest.mark.anyio
async def test_live_view_says_unavailable_since(db, lanes):
    async with _librarian(db) as staff:
        with anyio.fail_after(WAIT):
            before = await staff.get("/staff/live")
        assert "Screening is unavailable" not in before.text

        lanes.down = True
        async with _signed_in() as device:
            await _ask(device, "a book about bulls?")

        with anyio.fail_after(WAIT):
            during = await staff.get("/staff/live")

    assert during.status_code == 200
    assert "Screening is unavailable since 03:00" in during.text
    assert 'action="/staff/live/screening-mode"' in during.text
    assert 'value="pause"' in during.text


@pytest.mark.anyio
async def test_pause_and_resume(db, lanes):
    app.dependency_overrides[get_watchlist] = lambda: LOW_WATCHLIST
    lanes.down = True
    async with _signed_in() as device, _librarian(db) as staff:
        await _ask(device, "a book about bulls?")
        answers_before = lanes.answer_calls

        with anyio.fail_after(WAIT):
            paused = await staff.post(
                "/staff/live/screening-mode",
                data={"mode": "pause"},
                follow_redirects=False,
            )
        assert paused.status_code == 303
        assert screening_state.paused

        refused = await _ask(device, "a test low phrase here, any book recs?")
        assert refused.status_code == 503
        assert refused.json() == {"detail": PAUSED_TEXT}
        assert lanes.answer_calls == answers_before
        # The Watchlist ran before the pause answered.
        flag = db.execute("SELECT category, source FROM flags").fetchone()
        assert flag == ("bullying", "watchlist")
        assert _in_flight == set()

        with anyio.fail_after(WAIT):
            page = await staff.get("/staff/live")
        assert 'value="resume"' in page.text

        with anyio.fail_after(WAIT):
            resumed = await staff.post(
                "/staff/live/screening-mode",
                data={"mode": "resume"},
                follow_redirects=False,
            )
        assert resumed.status_code == 303
        assert not screening_state.paused

        answered = await _ask(device, "a book about flowers?")
        assert answered.status_code == 200
        assert "Ferdinand" in answered.text


@pytest.mark.anyio
async def test_catch_up_screens_oldest_first_after_recovery(
    db, lanes, clock, probe_wait
):
    lanes.down = True
    async with _signed_in() as device:
        await _ask(device, "first question")
        clock["now"] = NOW + timedelta(minutes=1)
        await _ask(device, "second question")

    lanes.down = False
    clock["now"] = NOW + timedelta(minutes=5)
    probe_wait.release()
    await _caught_up()

    assert screening_state.unavailable_since is None
    # The failed live call, the probe, then the catch-up, oldest first.
    assert lanes.screened == [
        "first question",
        PROBE_TEXT,
        "first question",
        "second question",
    ]
    for question in ("first question", "second question"):
        _id, screening, screened_at, verdict, _asked_at = _row(db, question)
        assert screening == "watchlist_alone"
        assert screened_at == clock["now"].isoformat()
        assert json.loads(verdict)["category"] is None
    assert db.execute("SELECT count(*) FROM flags").fetchone()[0] == 0


@pytest.mark.anyio
async def test_catch_up_flag_raised(db, lanes, clock, probe_wait):
    lanes.down = True
    async with _signed_in() as device:
        await _ask(device, "a book about bulls?")

    lanes.down = False
    lanes.verdict = {"category": "bullying", "severity": "low", "reason": "late"}
    clock["now"] = NOW + timedelta(minutes=10)
    probe_wait.release()
    await _caught_up()

    transcript_id, *_rest, asked_at = _row(db, "a book about bulls?")
    flag = db.execute(
        "SELECT transcript_id, category, severity, source, reason, raised_at FROM flags"
    ).fetchone()
    # The raised time shows how late the Flag came against the exchange's time.
    assert flag == (
        transcript_id,
        "bullying",
        "low",
        "oversight",
        "late",
        (NOW + timedelta(minutes=10)).isoformat(),
    )
    assert asked_at == NOW.isoformat()


@pytest.mark.anyio
async def test_catch_up_gives_way_to_card_awaiting_verdict(db, lanes, probe_wait):
    lanes.down = True
    async with _signed_in("token-14") as card_14:
        await _ask(card_14, "caught up later")

    lanes.down = False
    lanes.hold_question = "caught up later"
    probe_wait.release()
    with anyio.fail_after(WAIT):
        await lanes.held_entered.wait()

    # A live Student's message starts awaiting its verdict: the held catch-up call is
    # cancelled, and the live message is screened and answered.
    async with _signed_in("token-15") as card_15:
        live = await _ask(card_15, "a live question")
    assert live.status_code == 200
    assert _row(db, "a live question")[1] == "oversight"
    assert _row(db, "a live question")[2] is not None
    assert _row(db, "caught up later")[2] is None

    probe_wait.release()
    await _caught_up()

    assert _row(db, "caught up later")[2] is not None
    assert lanes.screened.count("caught up later") == 3  # failed, cancelled, screened


@pytest.mark.anyio
async def test_oversight_down_setting_pauses_until_back(db, lanes, probe_wait):
    """oversight_down = pause (decision lib-f24.77): the Install pauses Sessions itself
    when Oversight goes down, and lifts that pause when it answers again."""
    set_setting(db, OVERSIGHT_DOWN, "pause", 1, NOW)
    lanes.down = True
    async with _signed_in() as device:
        first = await _ask(device, "a book about bulls?")
        assert first.status_code == 200
        assert screening_state.paused

        refused = await _ask(device, "a book about flowers?")
        assert refused.status_code == 503

        lanes.down = False
        probe_wait.release()
        await _caught_up()
        assert not screening_state.paused

        answered = await _ask(device, "a book about clouds?")
    assert answered.status_code == 200
