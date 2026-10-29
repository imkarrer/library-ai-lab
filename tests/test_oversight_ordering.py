"""The Card's in-flight marker, with Oversight enabled (ADR-0004, ADR-0010 rule 3): the
Oversight task starts beside the Answer lane and the marker is held until its verdict is
recorded, not just until the answer ends. Driven through `httpx.ASGITransport` with fake
Answer and Oversight servers held on `asyncio.Event`s, an injected clock, and no sleeps."""

import asyncio
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
from library_assistant.install_settings import SUPERVISION_MODE, set_setting
from library_assistant.routers.session import SUPPORTIVE_REPLY, _in_flight
from library_assistant.staff import create_account
from library_assistant.watchlist import Entry, Watchlist

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
HIGH_ENTRY = Entry(
    id="test-self-harm-high",
    category="self-harm",
    severity="high",
    phrases=("test high phrase",),
    must_match=("a test high phrase here",),
    must_not_match=("nothing",),
)
HIGH_WATCHLIST = Watchlist(version="2026-10-25.1", entries=(HIGH_ENTRY,))

OVERSIGHT_SETTINGS = Settings(
    openai_endpoint="http://model.example.com:8080",
    openai_model="llama3",
    oversight_endpoint="http://oversight.example.com",
    oversight_model="guard-model",
)
OVERSIGHT_OFF_SETTINGS = Settings(
    openai_endpoint="http://model.example.com:8080", openai_model="llama3"
)

NO_VERDICT = {"category": None, "severity": None, "reason": "nothing to report"}


class FakeCatalog(Catalog):
    def search(self, query: str, k: int) -> list[Record]:
        return [RECORD]

    def get(self, id: str) -> Record | None:
        return RECORD if id == RECORD.id else None


class FakeLanes:
    """The Answer and Oversight servers: each one's first call can be held open on an
    `asyncio.Event`, later calls answer at once (same convention as `HeldModel`)."""

    def __init__(self) -> None:
        self.answer_entered = asyncio.Event()
        self.answer_release = asyncio.Event()
        self.oversight_entered = asyncio.Event()
        self.oversight_release = asyncio.Event()
        self.hold_first_answer = False
        self.hold_first_oversight = False
        self.answer_calls = 0
        self.oversight_calls = 0
        self.verdict: dict = NO_VERDICT

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oversight.example.com":
            self.oversight_calls += 1
            if self.hold_first_oversight and self.oversight_calls == 1:
                self.oversight_entered.set()
                await self.oversight_release.wait()
            body = json.dumps(
                {"choices": [{"message": {"content": json.dumps(self.verdict)}}]}
            ).encode()
            return httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        self.answer_calls += 1
        if self.hold_first_answer and self.answer_calls == 1:
            self.answer_entered.set()
            await self.answer_release.wait()
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Ferdinand"}}]}\n\n'
            b"data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_card_left_in_flight():
    _in_flight.clear()
    yield
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
def client(lanes):
    db = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: db
    teacher_id = create_account(db, "registering-teacher", "correct horse", "teacher")
    registration_key = issue_registration_key(db, teacher_id, NOW)
    # No Watch is started in this fixture: open the gate directly (lib-793.3).
    set_setting(db, SUPERVISION_MODE, "off", teacher_id, NOW)
    app.dependency_overrides[get_settings] = lambda: OVERSIGHT_SETTINGS
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog()
    app.dependency_overrides[get_clock] = lambda: NOW
    app.dependency_overrides[get_watchlist] = lambda: EMPTY_WATCHLIST
    try:
        test_client = TestClient(app)
        response = test_client.post(
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
        yield test_client, db
    finally:
        app.dependency_overrides.clear()


def _sign_in(test_client: TestClient, token: str) -> None:
    assert test_client.post("/card", json={"token": token}).status_code == 200


@asynccontextmanager
async def _signed_in(token: str = "token-14") -> AsyncIterator[httpx.AsyncClient]:
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


def _one_moment(response: httpx.Response) -> bool:
    return response.status_code == 409 and response.json() == {"status": "one moment"}


@pytest.mark.anyio
async def test_both_lanes_start_same_instant(client, lanes):
    lanes.hold_first_answer = True
    lanes.hold_first_oversight = True
    async with _signed_in() as device:
        result: dict = {}

        async def run() -> None:
            result["response"] = await _ask(device)

        with anyio.fail_after(WAIT):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(run)
                # Neither lane is released yet: both must have already started their
                # own request before either can finish, proving they began together.
                await lanes.answer_entered.wait()
                await lanes.oversight_entered.wait()
                lanes.answer_release.set()
                lanes.oversight_release.set()

        assert result["response"].status_code == 200
    assert lanes.answer_calls == 1
    assert lanes.oversight_calls == 1


@pytest.mark.anyio
async def test_second_message_waits_for_verdict(client, lanes):
    lanes.hold_first_oversight = True
    async with _signed_in() as device:
        first: dict = {}

        async def run() -> None:
            first["response"] = await _ask(device)

        async with anyio.create_task_group() as tasks:
            with anyio.fail_after(WAIT):
                tasks.start_soon(run)
                await lanes.oversight_entered.wait()

            # The Answer lane has already finished (it was never held); the verdict
            # has not. The Card must still be in flight.
            with anyio.fail_after(WAIT):
                second = await _ask(device)
            assert _one_moment(second)
            assert "response" not in first

            lanes.oversight_release.set()

        assert first["response"].status_code == 200

        third = await _ask(device)
    assert third.status_code == 200
    assert lanes.oversight_calls == 2


@pytest.mark.anyio
async def test_other_card_unaffected(client, lanes):
    lanes.hold_first_oversight = True
    async with _signed_in("token-14") as card_14, _signed_in("token-15") as card_15:
        first: dict = {}

        async def run() -> None:
            first["response"] = await _ask(card_14)

        async with anyio.create_task_group() as tasks:
            with anyio.fail_after(WAIT):
                tasks.start_soon(run)
                await lanes.oversight_entered.wait()

            other = await _ask(card_15)
            assert other.status_code == 200
            assert "Ferdinand" in other.text
            assert "response" not in first, (
                "card 14's message should still be in flight"
            )

            lanes.oversight_release.set()

        assert first["response"].status_code == 200


@pytest.mark.anyio
async def test_no_cancel_when_another_student_asks(client, lanes):
    lanes.hold_first_oversight = True
    lanes.verdict = {"category": "bullying", "severity": "low", "reason": "flagged"}
    _, db = client
    async with _signed_in("token-14") as card_14, _signed_in("token-15") as card_15:
        first: dict = {}

        async def run() -> None:
            first["response"] = await _ask(card_14)

        async with anyio.create_task_group() as tasks:
            with anyio.fail_after(WAIT):
                tasks.start_soon(run)
                await lanes.oversight_entered.wait()

            # A second student's whole exchange runs to completion while card 14's
            # Oversight task is still suspended, open on the event loop.
            other = await _ask(card_15)
            assert other.status_code == 200

            lanes.oversight_release.set()

        assert first["response"].status_code == 200

    # The held task was never cancelled: it still recorded its verdict.
    row = db.execute(
        "SELECT screening, verdict FROM transcripts WHERE card_number = '14'"
    ).fetchone()
    assert row[0] == "oversight"
    assert json.loads(row[1])["category"] == "bullying"


def test_oversight_flag_on_right_message(client, lanes):
    test_client, db = client
    lanes.verdict = {"category": "bullying", "severity": "low", "reason": "flagged"}
    _sign_in(test_client, "token-14")

    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    assert response.status_code == 200
    transcript_id = db.execute("SELECT id FROM transcripts").fetchone()[0]
    flag = db.execute(
        "SELECT category, severity, source, transcript_id FROM flags"
    ).fetchone()
    assert flag == ("bullying", "low", "oversight", transcript_id)
    assert _in_flight == set()


def test_oversight_same_category_on_watchlist_flag_is_repeat(client, lanes):
    test_client, db = client
    app.dependency_overrides[get_watchlist] = lambda: LOW_WATCHLIST
    lanes.verdict = {"category": "bullying", "severity": "low", "reason": "agrees"}
    _sign_in(test_client, "token-14")

    response = test_client.post(
        "/ask", json={"question": "a test low phrase here, any book recs?"}
    )

    assert response.status_code == 200
    assert db.execute("SELECT count(*) FROM flags").fetchone()[0] == 1
    assert db.execute("SELECT repeat_count FROM flags").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM flag_repeats").fetchone()[0] == 1


def test_supportive_reply_message_still_screened(client, lanes):
    test_client, db = client
    app.dependency_overrides[get_watchlist] = lambda: HIGH_WATCHLIST
    lanes.verdict = {"category": None, "severity": None, "reason": "fine"}
    _sign_in(test_client, "token-14")

    response = test_client.post(
        "/ask", json={"question": "I keep thinking test high phrase"}
    )

    assert response.status_code == 200
    assert response.text == SUPPORTIVE_REPLY
    assert lanes.answer_calls == 0
    assert lanes.oversight_calls == 1
    row = db.execute("SELECT screening FROM transcripts").fetchone()
    assert row[0] == "oversight"
    assert _in_flight == set()


def test_oversight_off_sends_only_answer_lane(client, lanes):
    test_client, _db = client
    app.dependency_overrides[get_settings] = lambda: OVERSIGHT_OFF_SETTINGS
    _sign_in(test_client, "token-14")

    response = test_client.post("/ask", json={"question": "a book about bulls?"})

    assert response.status_code == 200
    assert lanes.answer_calls == 1
    assert lanes.oversight_calls == 0
    assert _in_flight == set()
